"""Append-only skill history with complete content-addressed snapshots."""
import difflib
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import tempfile
import threading
import uuid
import zipfile
from flask import jsonify, request, send_file
from werkzeug.exceptions import BadRequest, Conflict, NotFound


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class SkillAudit:
    def __init__(self, catalog, db, now):
        self.catalog, self.db, self.now = catalog, db, now
        self.lock = threading.RLock()
        with db() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS skill_audit_blobs(sha TEXT PRIMARY KEY, content BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS skill_audit_versions(
                    id TEXT PRIMARY KEY, skill_id TEXT NOT NULL, sequence INTEGER NOT NULL,
                    revision TEXT NOT NULL, event TEXT NOT NULL, event_hash TEXT NOT NULL,
                    UNIQUE(skill_id, sequence));
                CREATE TABLE IF NOT EXISTS skill_audit_evidence(id TEXT PRIMARY KEY, skill_id TEXT NOT NULL, evidence_key TEXT NOT NULL, event TEXT NOT NULL, event_hash TEXT NOT NULL, UNIQUE(skill_id,evidence_key));
            """)
            for table in ('skill_audit_blobs', 'skill_audit_versions', 'skill_audit_evidence'):
                for op in ('UPDATE', 'DELETE'):
                    c.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()} BEFORE {op} ON {table} "
                              "BEGIN SELECT RAISE(ABORT, 'skill audit records are append-only'); END")

    def head(self, c, sid):
        return c.execute('SELECT * FROM skill_audit_versions WHERE skill_id=? ORDER BY sequence DESC LIMIT 1', (sid,)).fetchone()

    def value(self, row):
        return dict(json.loads(row['event']), event_hash=row['event_hash']) if row else None

    def capture(self, skill):
        root = Path(skill['source_path']).parent.resolve()
        blobs = {}
        for item in skill['resources']:
            path = (root / item['path']).resolve()
            if not path.is_relative_to(root):
                raise Conflict('技能路径已变化，请重新读取')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != item['sha256']:
                raise Conflict('技能正在被外部修改，请重新读取')
            blobs[item['sha256']] = data
        if self.catalog.read(skill['id'])['revision'] != skill['revision']:
            raise Conflict('技能目录正在变化，请重新读取')
        return blobs

    def append(self, c, skill, blobs, kind, actor, reason, source_ref='', head=None):
        previous = self.value(head)
        event = dict(id=uuid.uuid4().hex, skill_id=skill['id'], sequence=previous['sequence']+1 if previous else 1,
                     parent_id=previous['id'] if previous else None,
                     parent_hash=previous['event_hash'] if previous else None,
                     revision=skill['revision'], version=skill.get('version'), source_path=skill['source_path'],
                     recorded_at=self.now(), kind=kind, actor=actor, reason=reason,
                     source_ref=source_ref, resources=skill['resources'])
        raw = encoded(event)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        for sha, data in blobs.items():
            c.execute('INSERT OR IGNORE INTO skill_audit_blobs VALUES(?,?)', (sha, sqlite3.Binary(data)))
        c.execute('INSERT INTO skill_audit_versions VALUES(?,?,?,?,?,?)',
                  (event['id'], skill['id'], event['sequence'], skill['revision'], raw, digest))
        return dict(event, event_hash=digest)

    def observe(self, skill):
        if not skill.get('available'):
            return skill
        with self.lock:
            with self.db() as c:
                head = self.head(c, skill['id'])
                if head and head['revision'] == skill['revision']:
                    return dict(skill, audit_head=self.value(head))
            blobs = self.capture(skill)
            with self.db() as c:
                c.execute('BEGIN IMMEDIATE')
                head = self.head(c, skill['id'])
                if head and head['revision'] == skill['revision']:
                    event = self.value(head)
                else:
                    event = self.append(c, skill, blobs, 'external' if head else 'baseline',
                                        dict(type='unknown', name='未知', assurance='unknown'),
                                        '检测到外部修改，作者未登记' if head else '接入版本管理时的完整基线，不推断此前作者', head=head)
            return dict(skill, audit_head=event)

    def get(self, c, sid, vid):
        row = c.execute('SELECT * FROM skill_audit_versions WHERE skill_id=? AND id=?', (sid, vid)).fetchone()
        if row is None:
            raise NotFound('版本不存在')
        return self.value(row)

    def content(self, c, item):
        row = c.execute('SELECT content FROM skill_audit_blobs WHERE sha=?', (item['sha256'],)).fetchone()
        if row is None or hashlib.sha256(row['content']).hexdigest() != item['sha256']:
            raise Conflict('历史快照完整性检查失败')
        return bytes(row['content'])

    def difference(self, c, before, after):
        left = {x['path']: x for x in before['resources']} if before else {}
        right = {x['path']: x for x in after['resources']}
        changes = []
        for path in sorted(set(left) | set(right)):
            a, b = left.get(path), right.get(path)
            if a and b and a['sha256'] == b['sha256']:
                continue
            item = dict(path=path, status='added' if not a else 'deleted' if not b else 'modified',
                        before_sha=a['sha256'] if a else None, after_sha=b['sha256'] if b else None,
                        before_size=a['size'] if a else 0, after_size=b['size'] if b else 0)
            try:
                if max(item['before_size'], item['after_size']) > 512000:
                    raise ValueError()
                old = self.content(c, a).decode('utf-8') if a else ''
                new = self.content(c, b).decode('utf-8') if b else ''
                if '\0' in old or '\0' in new:
                    raise ValueError()
                diff = ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile='before/'+path, tofile='after/'+path))
                item.update(diff=diff[:200000], truncated=len(diff)>200000, binary=False)
            except (UnicodeDecodeError, ValueError):
                item.update(diff=None, binary=True, truncated=False)
            changes.append(item)
        return changes

    def identity(self, data):
        name, kind, reason, ref = data.get('actor_name'), data.get('actor_type'), data.get('reason'), data.get('source_ref', '')
        if not isinstance(kind, str) or kind not in {'human', 'agent'}:
            raise BadRequest('请选择修改者类型')
        for value, length in ((name, 120), (reason, 5000), (ref, 2000)):
            if not isinstance(value, str) or len(value)>length:
                raise BadRequest('修改者、原因或来源格式不正确')
        if not name.strip() or not reason.strip():
            raise BadRequest('修改者和修改原因必填')
        return dict(type=kind, name=name.strip(), assurance='self-declared'), reason.strip(), ref.strip()

    def edit(self, sid, data):
        actor, reason, ref = self.identity(data)
        rel, content = data.get('path'), data.get('content')
        if not isinstance(rel, str) or not isinstance(content, str) or len(content.encode())>512000:
            raise BadRequest('文本格式不正确或超过512KB')
        path = PurePosixPath(rel)
        if path.is_absolute() or any(x in {'.', '..'} or x.startswith('.') for x in path.parts):
            raise BadRequest('不允许的文件路径')
        with self.lock:
            current = self.observe(self.catalog.read(sid))
            if not current.get('available'):
                raise Conflict('技能正本不可用')
            if data.get('expected_revision') != current['revision'] or data.get('expected_version_id') != current['audit_head']['id']:
                raise Conflict('技能版本已变化，请重新读取并合并，草稿未保存')
            if rel not in current['supporting_texts']:
                raise BadRequest('只能修改现有可编辑文本资源')
            if rel == 'SKILL.md' and not content.strip():
                raise BadRequest('技能正文不能为空')
            if content == current['supporting_texts'][rel]:
                raise BadRequest('内容没有变化')
            root = Path(current['source_path']).parent.resolve()
            dest = root/rel
            if dest.is_symlink() or not dest.resolve().is_relative_to(root):
                raise BadRequest('不能修改符号链接或目录外文件')
            original = dest.read_bytes()
            item = next(x for x in current['resources'] if x['path']==rel)
            if hashlib.sha256(original).hexdigest()!=item['sha256']:
                raise Conflict('文件已被外部修改')
            with self.db() as c:
                c.execute('BEGIN IMMEDIATE')
                head = self.head(c, sid)
                if head['id'] != data['expected_version_id']:
                    raise Conflict('版本历史已更新，请重新读取')
                tmp = None
                wrote = False
                try:
                    with tempfile.NamedTemporaryFile(dir=dest.parent, prefix='.skill-edit-', delete=False) as f:
                        tmp = Path(f.name); f.write(content.encode()); f.flush(); os.fsync(f.fileno())
                    os.chmod(tmp, dest.stat().st_mode & 0o777)
                    if dest.read_bytes()!=original:
                        raise Conflict('文件已被外部修改')
                    os.replace(tmp, dest); tmp = None; wrote = True
                    updated = self.catalog.read(sid)
                    expected = {x['path']: x['sha256'] for x in current['resources']}
                    expected[rel] = hashlib.sha256(content.encode()).hexdigest()
                    if expected != {x['path']: x['sha256'] for x in updated['resources']}:
                        raise Conflict('同时检测到外部资源变化，停止提交，请重新核对')
                    event = self.append(c, updated, self.capture(updated), 'edit', actor, reason, ref, head)
                    c.commit()
                except Exception:
                    c.rollback()
                    if wrote and dest.exists() and dest.read_bytes()==content.encode():
                        dest.write_bytes(original)
                    raise
                finally:
                    if tmp is not None and tmp.exists():
                        tmp.unlink()
            return event


    def historical_evidence(self, sid, data):
        actor, reason, ref = self.identity(data)
        if not ref:
            raise BadRequest('补录历史证据必须注明来源')
        files = data.get('files')
        if not isinstance(files, list) or not 1 <= len(files) <= 50:
            raise BadRequest('历史证据须包含1至50个文本文件')
        current = self.observe(self.catalog.read(sid))
        if data.get('expected_revision') != current.get('revision'):
            raise Conflict('技能当前版本已变化，停止补录')
        seen = set()
        for item in files:
            if not isinstance(item, dict) or set(item) != {'path', 'before', 'after'}:
                raise BadRequest('历史文件字段不正确')
            path, before, after = item['path'], item['before'], item['after']
            if not isinstance(path, str) or path in seen or path not in current['supporting_texts']:
                raise BadRequest('历史证据须对应当前文本文件且不能重复')
            if before is not None and (not isinstance(before, str) or len(before.encode())>512000):
                raise BadRequest('历史正文不正确')
            if after != current['supporting_texts'][path]:
                raise Conflict('补录的修改后内容与当前版本不符')
            if before == after:
                raise BadRequest('历史证据没有内容差异')
            seen.add(path)
        body = dict(skill_id=sid, anchor_version=current['audit_head']['id'], actor=actor,
                    reason=reason, source_ref=ref, files=files,
                    scope='retrospective-text-evidence-not-complete-version')
        key = hashlib.sha256(encoded(body).encode()).hexdigest()
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            old = c.execute('SELECT event,event_hash FROM skill_audit_evidence WHERE skill_id=? AND evidence_key=?', (sid,key)).fetchone()
            if old:
                return dict(json.loads(old['event']), event_hash=old['event_hash'])
            event = dict(body, id=uuid.uuid4().hex, recorded_at=self.now())
            raw = encoded(event); digest = hashlib.sha256(raw.encode()).hexdigest()
            c.execute('INSERT INTO skill_audit_evidence VALUES(?,?,?,?,?)', (event['id'],sid,key,raw,digest))
        return dict(event,event_hash=digest)

    def install(self, app):
        @app.get('/api/skills/<sid>/history')
        def skill_audit_history(sid):
            try:
                self.observe(self.catalog.read(sid))
            except KeyError:
                pass
            with self.db() as c:
                rows = c.execute('SELECT * FROM skill_audit_versions WHERE skill_id=? ORDER BY sequence DESC', (sid,)).fetchall()
                if not rows:
                    raise NotFound('尚无版本记录')
                evidence = [dict(json.loads(x['event']),event_hash=x['event_hash']) for x in c.execute('SELECT event,event_hash FROM skill_audit_evidence WHERE skill_id=? ORDER BY rowid DESC',(sid,))]
                return jsonify(evidence=evidence, versions=[{k:v for k,v in self.value(row).items() if k!='resources'} for row in rows],
                               actor_assurance='self-declared', external_capture='on-read')

        @app.get('/api/skills/<sid>/history/<vid>')
        def skill_audit_version(sid, vid):
            with self.db() as c:
                value = self.get(c, sid, vid)
                base = request.args.get('base', value['parent_id'])
                previous = self.get(c, sid, base) if base and base != 'empty' else None
                return jsonify(version=value, base_id=base, changes=self.difference(c, previous, value))

        @app.get('/api/skills/<sid>/history/<vid>/download')
        def skill_audit_download(sid, vid):
            output = io.BytesIO()
            with self.db() as c:
                value = self.get(c, sid, vid)
                with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr('audit.json', encoded(value))
                    evidence = [dict(json.loads(x['event']),event_hash=x['event_hash']) for x in c.execute('SELECT event,event_hash FROM skill_audit_evidence WHERE skill_id=?',(sid,)) if json.loads(x['event'])['anchor_version']==vid]
                    archive.writestr('historical-evidence.json',encoded(evidence))
                    for item in value['resources']:
                        archive.writestr('files/'+item['path'], self.content(c, item))
            output.seek(0)
            return send_file(output, mimetype='application/zip', as_attachment=True, download_name=f'{sid}-v{value["sequence"]}.zip')

        @app.post('/api/skills/<sid>/edit')
        def edit_skill(sid):
            data = request.get_json()
            if not isinstance(data, dict):
                raise BadRequest('请求须为JSON对象')
            try:
                event = self.edit(sid, data)
            except KeyError:
                raise NotFound('技能不存在')
            return jsonify(version=event), 201


        @app.post('/api/skills/<sid>/history-evidence')
        def skill_audit_import_evidence(sid):
            data = request.get_json()
            if not isinstance(data, dict):
                raise BadRequest('请求须为JSON对象')
            try:
                event = self.historical_evidence(sid, data)
            except KeyError:
                raise NotFound('技能不存在')
            return jsonify(evidence=event), 201

        @app.get('/api/skills/<sid>/history-integrity')
        def skill_audit_integrity(sid):
            with self.db() as c:
                rows = c.execute('SELECT * FROM skill_audit_versions WHERE skill_id=? ORDER BY sequence', (sid,)).fetchall()
                if not rows:
                    raise NotFound('尚无版本记录')
                previous = None; previous_id = None; checked = set()
                for i, row in enumerate(rows, 1):
                    value = self.value(row)
                    if hashlib.sha256(row['event'].encode()).hexdigest()!=row['event_hash'] or value['sequence']!=i or value['parent_hash']!=previous or value['parent_id']!=previous_id:
                        raise Conflict('版本链完整性检查失败')
                    for item in value['resources']:
                        if item['sha256'] not in checked:
                            self.content(c, item); checked.add(item['sha256'])
                    digest = hashlib.sha256()
                    for item in value['resources']:
                        digest.update((item['path']+'\0'+item['sha256']).encode())
                    if digest.hexdigest()!=value['revision']:
                        raise Conflict('版本清单与内容指纹不一致')
                    previous = row['event_hash']; previous_id = row['id']
                for evidence in c.execute('SELECT event,event_hash FROM skill_audit_evidence WHERE skill_id=?',(sid,)):
                    if hashlib.sha256(evidence['event'].encode()).hexdigest()!=evidence['event_hash']:
                        raise Conflict('历史证据校验失败')
                return jsonify(valid=True, versions=len(rows), resources=len(checked), head_hash=previous)
