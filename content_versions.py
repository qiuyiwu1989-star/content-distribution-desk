"""Immutable, lazily captured editorial versions; no approval/publication inference.
Install after library/distribution: install(app, data, db, get, fail, text, now).
app.desk_content_version(c, pid) captures the current version in the caller transaction.
"""
import hashlib
import json
import uuid
from pathlib import Path
from flask import jsonify, request


def snapshot(connection, pid, data):
    package = connection.execute('SELECT id,title,body,notes FROM packages WHERE id=?', (pid,)).fetchone()
    if package is None:
        return None
    assets = []
    for row in connection.execute('SELECT id,name,mime,size,kind FROM assets WHERE package_id=? ORDER BY id', (pid,)):
        asset = dict(row)
        try:
            stat = (Path(data) / 'files' / asset['id']).stat()
            asset['file'] = {'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns, 'ctime_ns': stat.st_ctime_ns}
        except FileNotFoundError:
            asset['file'] = {'missing': True}
        assets.append(asset)
    meta = connection.execute('SELECT value FROM package_meta WHERE package_id=?', (pid,)).fetchone()
    defaults = json.loads(meta['value']).get('content_defaults', {}) if meta else {}
    return {'package': dict(package), 'assets': assets, 'content_defaults': defaults}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def install(app, data, db, get, fail, text, now):
    if getattr(app, "desk_content_version", None) is not None:
        return
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS content_versions(
          id TEXT PRIMARY KEY,package_id TEXT NOT NULL REFERENCES packages(id),
          number INTEGER NOT NULL,fingerprint TEXT NOT NULL,snapshot TEXT NOT NULL,created TEXT NOT NULL,
          UNIQUE(package_id,number));
        CREATE INDEX IF NOT EXISTS content_versions_package ON content_versions(package_id,number);
        CREATE TABLE IF NOT EXISTS content_version_links(
          id TEXT PRIMARY KEY,version_id TEXT NOT NULL REFERENCES content_versions(id),
          kind TEXT NOT NULL,reference_id TEXT NOT NULL,reference_revision INTEGER,
          snapshot TEXT NOT NULL,created TEXT NOT NULL);
        ''')

    def current(c, pid):
        get(c, 'packages', pid)
        value = snapshot(c, pid, data)
        fp = digest(value)
        last = c.execute('SELECT * FROM content_versions WHERE package_id=? ORDER BY number DESC LIMIT 1', (pid,)).fetchone()
        if last and last['fingerprint'] == fp:
            result = dict(last)
            result['snapshot'] = json.loads(result['snapshot'])
            return result
        # Keep a new version on revert as well: chronology is not deduplicated by hash.
        result = dict(id=uuid.uuid4().hex, package_id=pid, number=last['number'] + 1 if last else 1,
                      fingerprint=fp, snapshot=value, created=now())
        c.execute('INSERT INTO content_versions VALUES(?,?,?,?,?,?)',
                  (result['id'], pid, result['number'], fp, json.dumps(value, ensure_ascii=False), result['created']))
        return result

    app.desk_content_version = current

    @app.get('/api/packages/<pid>/versions')
    def versions(pid):
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            latest = current(c, pid)
            rows = [dict(r) for r in c.execute('SELECT id,number,fingerprint,created FROM content_versions WHERE package_id=? ORDER BY number DESC', (pid,))]
            for row in rows:
                row['links'] = [dict(r) for r in c.execute('SELECT id,kind,reference_id,reference_revision,created FROM content_version_links WHERE version_id=? ORDER BY created', (row['id'],))]
        return jsonify(current={k: latest[k] for k in ('id','number','fingerprint','created')}, versions=rows,
                       history_boundary='首次读取或制作任务创建时开始记录版本；未捕获的旧版本不会补造。')

    @app.get('/api/packages/<pid>/versions/<vid>')
    def version_detail(pid, vid):
        with db() as c:
            get(c, 'packages', pid)
            row = c.execute('SELECT * FROM content_versions WHERE id=? AND package_id=?', (vid,pid)).fetchone()
            if not row:
                fail('内容版本不存在',404)
            result = dict(row)
            result['snapshot'] = json.loads(result['snapshot'])
            result['links'] = [dict(r) for r in c.execute('SELECT * FROM content_version_links WHERE version_id=?', (vid,))]
            for link in result['links']:
                link['snapshot'] = json.loads(link['snapshot'])
        return jsonify(result)

    @app.post('/api/packages/<pid>/versions/channel-link')
    def channel_link(pid):
        body = request.get_json(silent=True) or {}
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            version = current(c, pid)
            if body.get('fingerprint') != version['fingerprint']:
                fail('内容已更新，请重新读取版本',409)
            task = get(c,'tasks',body.get('task_id'))
            if task['package_id'] != pid:
                fail('发布任务不属于此内容')
            if type(body.get('revision')) is not int or body['revision'] != task['revision']:
                fail('发布任务已更新，请刷新',409)
            existing = c.execute('SELECT id FROM content_version_links WHERE version_id=? AND kind=? AND reference_id=? AND reference_revision=?',
                                 (version['id'],'channel',task['id'],task['revision'])).fetchone()
            if existing:
                return jsonify(id=existing['id'],version_id=version['id'])
            link_id = uuid.uuid4().hex
            c.execute('INSERT INTO content_version_links VALUES(?,?,?,?,?,?,?)',
                      (link_id,version['id'],'channel',task['id'],task['revision'],json.dumps(task,ensure_ascii=False),now()))
        return jsonify(id=link_id,version_id=version['id']),201
