"""Read canonical skills live; freeze the skill and content context per Agent request."""
import hashlib
import json
import threading
import uuid
from pathlib import Path
from flask import jsonify, request
from werkzeug.exceptions import ServiceUnavailable


def frontmatter(raw, key):
    if not raw.startswith('---'):
        return ''
    for line in raw.split('---', 2)[1].splitlines():
        if key == 'version':
            line = line.strip()
        if line.startswith(key + ':'):
            return line.split(':', 1)[1].strip().strip('"\'')
    return ''


class SkillCatalog:
    def __init__(self, registry):
        self.registry = Path(registry)
        self.cache = {}
        self.lock = threading.RLock()

    def rows(self):
        return json.loads(self.registry.read_text())['skills']

    def read(self, sid):
        row = next((x for x in self.rows() if x['id'] == sid), None)
        if row is None:
            raise KeyError(sid)
        root = Path(row['path']).expanduser().resolve()
        if not (root / 'SKILL.md').is_file():
            return dict(row, available=False, revision=None, error='技能原始文件不可用')
        # The signature includes support files; text is re-read only when one changes.
        files = sorted(p for p in root.rglob('*') if p.is_file() and not any(x.startswith('.') or x == '__pycache__' for x in p.relative_to(root).parts) and p.resolve().is_relative_to(root))
        signature = (str(root), tuple((str(p.relative_to(root)), p.stat().st_mtime_ns, p.stat().st_ctime_ns, p.stat().st_size) for p in files))
        with self.lock:
            cached = self.cache.get(sid)
            if cached and cached[0] == signature:
                return dict(cached[1], **row)
            dig = hashlib.sha256()
            resources, texts = [], {}
            for p in files:
                rel = str(p.relative_to(root))
                content = p.read_bytes()
                sha = hashlib.sha256(content).hexdigest()
                dig.update((rel + '\0' + sha).encode())
                resources.append(dict(path=rel, sha256=sha, size=len(content)))
                if p.suffix in {'.md', '.txt', '.json', '.py', '.js', '.yaml', '.yml'} and len(content) <= 512000:
                    try:
                        texts[rel] = content.decode('utf-8')
                    except UnicodeDecodeError:
                        pass
            raw = texts['SKILL.md']
            result = dict(row, available=True, revision=dig.hexdigest(), version=frontmatter(raw, 'version') or None,
                          description=frontmatter(raw, 'description'), updated_ns=max(p.stat().st_mtime_ns for p in files),
                          source_path=str(root / 'SKILL.md'), content=raw, resources=resources, supporting_texts=texts)
            self.cache[sid] = (signature, result)
            return result

    def bundle(self, skill):
        return dict(skill)


def install(app, db, get, fail, text, now, registry=None):
    catalog = SkillCatalog(registry or Path(__file__).parent / 'skill_sources.json')
    from skill_audit import SkillAudit
    audit = SkillAudit(catalog, db, now)
    audit.install(app)
    from agent_onboarding import install as install_onboarding
    install_onboarding(app, catalog, fail)
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS skill_requests(
            id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL, skill_id TEXT NOT NULL,
            skill_revision TEXT NOT NULL, value TEXT NOT NULL, status TEXT NOT NULL,
            worker TEXT, result TEXT, created TEXT NOT NULL, updated TEXT NOT NULL)''')

    def skill(sid):
        try:
            value = catalog.read(sid)
        except KeyError:
            fail('技能不存在', 404)
        if not value['available']:
            raise ServiceUnavailable('技能原始文件不可用，请检查本机技能路径')
        return value

    def record(row, detail=False):
        d = dict(row)
        value = json.loads(d.pop('value'))
        d.pop('idempotency_key', None)
        d['result'] = json.loads(d['result']) if d['result'] else None
        d.update(instruction=value['instruction'], contents=[{'id': p['id'], 'title': p['title']} for p in value['contents']])
        if detail:
            d['context'] = value
        return d

    @app.get('/api/skills')
    def skills():
        rows = [audit.observe(catalog.read(x['id'])) for x in catalog.rows()]
        return jsonify(skills=[{k: v for k, v in x.items() if k not in {'content', 'resources', 'supporting_texts'}} for x in rows], synchronization='live-canonical-files', execution='agent-queue')

    @app.get('/api/skills/<sid>')
    def read_skill(sid):
        return jsonify(catalog.bundle(audit.observe(skill(sid))))

    @app.get('/api/skill-requests')
    def requests_list():
        with db() as c:
            return jsonify(requests=[record(row) for row in c.execute('SELECT * FROM skill_requests ORDER BY created DESC LIMIT 100')])

    @app.get('/api/skill-requests/<rid>')
    def request_detail(rid):
        with db() as c:
            row = c.execute('SELECT * FROM skill_requests WHERE id=?', (rid,)).fetchone()
            if row is None:
                fail('任务不存在', 404)
            return jsonify(record(row, True))

    @app.post('/api/skill-requests')
    def new_request():
        d = request.get_json()
        sid = text(d.get('skill_id'), 100, True)
        instruction = text(d.get('instruction'), 5000, True)
        key = text(d.get('idempotency_key'), 100, True)
        ids = d.get('package_ids')
        if not isinstance(ids, list) or not 1 <= len(ids) <= 200 or any(not isinstance(x, str) for x in ids) or len(set(ids)) != len(ids):
            fail('请选择 1 至 200 条不同内容')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            old = c.execute('SELECT * FROM skill_requests WHERE idempotency_key=?', (key,)).fetchone()
            if old:
                previous = json.loads(old['value'])
                if old['skill_id'] != sid or previous['instruction'] != instruction or [p['id'] for p in previous['contents']] != ids:
                    fail('重试编号与原任务不一致', 409)
                return jsonify(record(old, True))
            current = skill(sid)
            if d.get('skill_revision') != current['revision']:
                fail('技能已更新，请重新查看后调用', 409)
            value = dict(instruction=instruction, skill=catalog.bundle(current), contents=[])
            for pid in ids:
                p = dict(get(c, 'packages', pid))
                p['assets'] = [dict(x) for x in c.execute('SELECT id,name,kind,mime,size FROM assets WHERE package_id=?', (pid,))]
                for a in p['assets']:
                    a['url'] = 'http://127.0.0.1:4318/api/assets/' + a['id']
                m = c.execute('SELECT * FROM library_packages WHERE package_id=?', (pid,)).fetchone()
                p['library'] = dict(m) if m else {}
                b = c.execute('SELECT name FROM library_batches WHERE id=?', (p['library'].get('batch_id'),)).fetchone()
                p['batch_name'] = b['name'] if b else None
                creative = c.execute('SELECT value FROM creative_choices WHERE package_id=?', (pid,)).fetchone()
                p['creative'] = json.loads(creative['value']) if creative else {}
                review = c.execute('SELECT status,note,fingerprint FROM library_reviews WHERE package_id=? ORDER BY id DESC LIMIT 1', (pid,)).fetchone()
                p['review'] = dict(review) if review else {'status': 'pending'}
                value['contents'].append(p)
            rid = uuid.uuid4().hex
            stamp = now()
            c.execute('INSERT INTO skill_requests VALUES(?,?,?,?,?,?,?,?,?,?)', (rid, key, sid, current['revision'], json.dumps(value, ensure_ascii=False), 'pending', None, None, stamp, stamp))
            row = c.execute('SELECT * FROM skill_requests WHERE id=?', (rid,)).fetchone()
            return jsonify(record(row, True)), 201

    @app.post('/api/skill-requests/<rid>/transition')
    def update_request(rid):
        d = request.get_json()
        status = d.get('status')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM skill_requests WHERE id=?', (rid,)).fetchone()
            if row is None:
                fail('任务不存在', 404)
            worker = row['worker']
            result = row['result']
            if status == 'canceled' and row['status'] == 'pending':
                pass
            elif status == 'running' and row['status'] == 'pending':
                worker = text(d.get('worker'), 100, True)
            elif status in {'completed', 'failed'} and row['status'] == 'running':
                if d.get('worker') != worker:
                    fail('仅接单 Agent 可以更新执行结果', 409)
                summary = text(d.get('summary'), 5000, True)
                result = json.dumps({'summary': summary, 'reported_by': worker}, ensure_ascii=False)
            else:
                fail('任务状态已变化，请刷新后重试', 409)
            c.execute('UPDATE skill_requests SET status=?,worker=?,result=?,updated=? WHERE id=?', (status, worker, result, now(), rid))
            return jsonify(record(c.execute('SELECT * FROM skill_requests WHERE id=?', (rid,)).fetchone(), True))
