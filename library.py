"""Content organization and human review; independent of dispatch authorization."""
import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

from flask import jsonify, request


def migrate_v1(db, data, seed_path, now):
    with db() as c:
        exists = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='library_migrations'").fetchone()
        if exists and c.execute('SELECT 1 FROM library_migrations WHERE version=1').fetchone():
            return
    # Fail closed if the consistent, WAL-aware snapshot cannot be written.
    backup_dir = Path(data) / 'migration-backups'
    backup_dir.mkdir(exist_ok=True)
    target = backup_dir / ('before-library-v1-' + uuid.uuid4().hex + '.sqlite3')
    with db() as source, sqlite3.connect(target) as dest:
        source.backup(dest)
    seed = json.loads(Path(seed_path).read_text()) if Path(seed_path).exists() else {}
    with db() as c:
        c.executescript('''
        BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS library_migrations(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS library_batches(id TEXT PRIMARY KEY,name TEXT NOT NULL,created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS library_packages(package_id TEXT PRIMARY KEY REFERENCES packages(id),batch_id TEXT NOT NULL REFERENCES library_batches(id),sequence INTEGER,archived INTEGER NOT NULL DEFAULT 0,supersedes_id TEXT UNIQUE REFERENCES packages(id));
        CREATE TABLE IF NOT EXISTS library_reviews(id INTEGER PRIMARY KEY AUTOINCREMENT,package_id TEXT NOT NULL REFERENCES packages(id),status TEXT NOT NULL,note TEXT NOT NULL,fingerprint TEXT NOT NULL,reviewed_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS library_reviews_package ON library_reviews(package_id,id);
        ''')
        c.execute('INSERT OR IGNORE INTO library_batches VALUES(?,?,?)', ('unassigned', '尚未归入批次', now()))
        for batch in seed.get('batches', []):
            if isinstance(batch, dict) and isinstance(batch.get('id'), str) and isinstance(batch.get('name'), str):
                c.execute('INSERT OR IGNORE INTO library_batches VALUES(?,?,?)', (batch['id'], batch['name'], now()))
        for pid, meta in seed.get('packages', {}).items():
            if not isinstance(meta, dict):
                continue
            if not c.execute('SELECT 1 FROM packages WHERE id=?', (pid,)).fetchone():
                continue
            bid = meta.get('batch_id', 'unassigned')
            if not c.execute('SELECT 1 FROM library_batches WHERE id=?', (bid,)).fetchone():
                bid = 'unassigned'
            seq = meta.get('sequence')
            if type(seq) is not int or seq < 1:
                seq = None
            c.execute('INSERT OR IGNORE INTO library_packages VALUES(?,?,?,0,NULL)', (pid, bid, seq))
        c.execute('INSERT OR IGNORE INTO library_migrations VALUES(1,?)', (now(),))


def migrate(db, data, seed_path, now):
    migrate_v1(db, data, seed_path, now)
    with db() as c:
        if c.execute('SELECT 1 FROM library_migrations WHERE version=2').fetchone():
            return
    target = Path(data) / 'migration-backups' / ('before-library-v2-' + uuid.uuid4().hex + '.sqlite3')
    with db() as source, sqlite3.connect(target) as dest:
        source.backup(dest)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('CREATE TABLE IF NOT EXISTS library_review_snapshots(review_id INTEGER PRIMARY KEY REFERENCES library_reviews(id),value TEXT NOT NULL)')
        c.execute('INSERT OR IGNORE INTO library_migrations VALUES(2,?)', (now(),))


def editorial_snapshot(c, pid, data):
    p = dict(c.execute('SELECT id,title,body,notes FROM packages WHERE id=?', (pid,)).fetchone())
    assets = []
    for row in c.execute('SELECT id,name,mime,size,kind FROM assets WHERE package_id=? ORDER BY id', (pid,)):
        a = dict(row)
        path = Path(data) / 'files' / a['id']
        try:
            stat = path.stat()
            a['file'] = {'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns, 'ctime_ns': stat.st_ctime_ns}
        except FileNotFoundError:
            a['file'] = {'missing': True}
        # Stat information catches same-size replacements without reading entire videos.
        # Populating the separate media analysis cache does not invalidate review.
        assets.append(a)
    tasks = []
    for row in c.execute('SELECT id,format,title,body,tags,asset_ids,cover_id FROM tasks WHERE package_id=? ORDER BY id', (pid,)):
        t = dict(row)
        t['asset_ids'] = json.loads(t['asset_ids'])
        option = c.execute('SELECT value FROM task_options WHERE task_id=?', (t['id'],)).fetchone()
        o = json.loads(option['value']) if option else {}
        t['options'] = {k: o.get(k, default) for k, default in [('category', None), ('collection', ''), ('landscape_cover_id', None)]}
        tasks.append(t)
    return {'package': p, 'assets': assets, 'channels': tasks}


def content_fingerprint(content):
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def fingerprint(c, pid, data):
    return content_fingerprint(editorial_snapshot(c, pid, data))


def install(app, data, db, get, fail, text, now, seed_path):
    migrate(db, data, seed_path, now)

    def metadata(c, pid):
        row = c.execute('SELECT * FROM library_packages WHERE package_id=?', (pid,)).fetchone()
        meta = dict(row) if row else dict(batch_id='unassigned', sequence=None, archived=0, supersedes_id=None)
        meta.pop('package_id', None)
        meta['archived'] = bool(meta['archived'])
        replacement = c.execute('SELECT package_id FROM library_packages WHERE supersedes_id=?', (pid,)).fetchone()
        meta['superseded_by'] = replacement['package_id'] if replacement else None
        fp = fingerprint(c, pid, data)
        last = c.execute('SELECT status,note,fingerprint,reviewed_at FROM library_reviews WHERE package_id=? ORDER BY id DESC LIMIT 1', (pid,)).fetchone()
        review = dict(last) if last else dict(status='pending', note='', fingerprint=None, reviewed_at=None)
        review['stale'] = bool(last and review['fingerprint'] != fp)
        review['previous_status'] = review['status']
        if review['stale']:
            review['status'] = 'pending'
        return dict(meta, fingerprint=fp, review=review)

    @app.get('/api/library')
    def library():
        with db() as c:
            # A deferred read transaction pins every editorial row and fingerprint
            # to one SQLite snapshot, even when another client edits concurrently.
            c.execute('BEGIN')
            snapshot = {table: [dict(r) for r in c.execute(f'SELECT * FROM {table} ORDER BY created DESC')] for table in ['packages', 'assets', 'tasks']}
            for t in snapshot['tasks']:
                t['asset_ids'] = json.loads(t['asset_ids'])
                row = c.execute('SELECT value FROM task_options WHERE task_id=?', (t['id'],)).fetchone()
                t['options'] = {'mode': 'manual', 'category': None, 'collection': '', 'landscape_cover_id': None, **(json.loads(row['value']) if row else {})}
            for a in snapshot['assets']:
                row = c.execute('SELECT value FROM asset_meta WHERE asset_id=?', (a['id'],)).fetchone()
                a['metadata'] = json.loads(row['value']) if row else {}
                if not (Path(data) / 'files' / a['id']).exists():
                    a['metadata']['error'] = '原始文件不存在'
            return jsonify(batches=[dict(r) for r in c.execute('SELECT id,name FROM library_batches ORDER BY created,id')],
                           packages={p['id']: metadata(c, p['id']) for p in snapshot['packages']}, snapshot=snapshot)

    @app.post('/api/library/batches')
    def new_batch():
        name = text(request.get_json().get('name'), 200, True)
        bid = uuid.uuid4().hex
        with db() as c:
            c.execute('INSERT INTO library_batches VALUES(?,?,?)', (bid, name, now()))
        return jsonify(id=bid, name=name), 201

    @app.put('/api/packages/<pid>/review')
    def review(pid):
        d = request.get_json()
        status = d.get('status')
        if status not in {'approved', 'changes_requested', 'pending'}:
            fail('请选择有效的人工审核结果')
        note = text(d.get('note', ''), 5000)
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            get(c, 'packages', pid)
            reviewed_content = editorial_snapshot(c, pid, data)
            fp = content_fingerprint(reviewed_content)
            if d.get('fingerprint') != fp:
                fail('内容已变化，请重新检查当前版本后确认', 409)
            inserted = c.execute('INSERT INTO library_reviews(package_id,status,note,fingerprint,reviewed_at) VALUES(?,?,?,?,?)', (pid, status, note, fp, now()))
            c.execute('INSERT INTO library_review_snapshots VALUES(?,?)', (inserted.lastrowid, json.dumps(reviewed_content, ensure_ascii=False)))
            result = metadata(c, pid)
        return jsonify(result)

    @app.get('/api/packages/<pid>/reviews')
    def reviews(pid):
        with db() as c:
            get(c, 'packages', pid)
            rows = [dict(r) for r in c.execute('SELECT id,status,note,fingerprint,reviewed_at FROM library_reviews WHERE package_id=? ORDER BY id DESC', (pid,))]
            if request.args.get('include_snapshot') == '1':
                for r in rows:
                    saved = c.execute('SELECT value FROM library_review_snapshots WHERE review_id=?', (r['id'],)).fetchone()
                    r['snapshot'] = json.loads(saved['value']) if saved else None
            return jsonify(reviews=rows)

    @app.patch('/api/packages/<pid>/library')
    def update_library(pid):
        d = request.get_json()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            get(c, 'packages', pid)
            old = metadata(c, pid)
            bid = d.get('batch_id', old['batch_id'])
            if not isinstance(bid, str) or not c.execute('SELECT 1 FROM library_batches WHERE id=?', (bid,)).fetchone():
                fail('请选择已有批次')
            seq = d.get('sequence', old['sequence'])
            if seq is not None and (type(seq) is not int or not 1 <= seq <= 999999):
                fail('顺序需要是正整数或空值')
            archived = d.get('archived', old['archived'])
            if type(archived) is not bool:
                fail('归档标记需要是布尔值')
            previous = d.get('supersedes_id', old['supersedes_id'])
            if previous is not None:
                if not isinstance(previous, str):
                    fail('请选择被替代的内容')
                get(c, 'packages', previous)
                if previous == pid:
                    fail('版本关系不能引用自身或形成循环')
                other = c.execute('SELECT package_id FROM library_packages WHERE supersedes_id=? AND package_id<>?', (previous, pid)).fetchone()
                if other:
                    fail('该内容已有替代版本，请先解除已有关系', 409)
                cursor, visited = previous, {pid}
                while cursor:
                    if cursor in visited:
                        fail('版本关系不能引用自身或形成循环')
                    visited.add(cursor)
                    row = c.execute('SELECT supersedes_id FROM library_packages WHERE package_id=?', (cursor,)).fetchone()
                    cursor = row['supersedes_id'] if row else None
            c.execute('INSERT INTO library_packages VALUES(?,?,?,?,?) ON CONFLICT(package_id) DO UPDATE SET batch_id=excluded.batch_id,sequence=excluded.sequence,archived=excluded.archived,supersedes_id=excluded.supersedes_id', (pid, bid, seq, int(archived), previous))
            result = metadata(c, pid)
        return jsonify(result)
