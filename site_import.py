"""Import reviewed site snapshots without changing existing channel drafts."""
import hashlib
import json
import re
import uuid

from flask import jsonify, request

SCHEMA = 'qiuyiwu.site-draft.v1'
OUTLETS = {'essay', 'social_signed', 'social_geo'}


def install(app, db, fail, text, now):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS site_imports(
            source_id TEXT NOT NULL, text_sha256 TEXT NOT NULL,
            package_id TEXT NOT NULL UNIQUE REFERENCES packages(id),
            source_file TEXT NOT NULL, approved_at TEXT NOT NULL, imported_at TEXT NOT NULL,
            PRIMARY KEY(source_id,text_sha256))''')

    @app.post('/api/site-import')
    def site_import():
        d = request.get_json()
        if d.get('schema') != SCHEMA or not isinstance(d.get('source'), dict):
            fail('请选择网站导出的内容快照 JSON')
        source = d['source']
        slug = source.get('slug')
        outlet = source.get('outlet')
        if source.get('site') != 'qiuyiwu.com' or not isinstance(slug, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}-[\w一-龥][\w一-龥-]{0,39}', slug) or outlet not in OUTLETS:
            fail('来源信息不正确')
        body = d.get('body')
        if not isinstance(body, str) or not body.strip() or len(body) > 50000:
            fail('网站正文为空或超过 50000 字')
        title = text(d.get('title'), 200, True)
        digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
        if digest != source.get('text_sha256'):
            fail('正文与网站批准版本的哈希不一致')
        if source.get('source_file') not in {'01-草稿.md', '02-初稿.md', '定稿.md'} or not isinstance(source.get('approved_at'), str) or not source['approved_at']:
            fail('缺少网站版本信息')
        signoff = source.get('signoff')
        if not isinstance(signoff, dict) or signoff.get('决定') not in {'signed', 'unsigned'}:
            fail('缺少网站发布签字记录')
        source_id = f'qiuyiwu.com/{slug}/{outlet}'
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            prior = c.execute('SELECT package_id FROM site_imports WHERE source_id=? AND text_sha256=?', (source_id, digest)).fetchone()
            if prior:
                return jsonify(package_id=prior['package_id'], created=False, source_id=source_id)
            older = c.execute('SELECT package_id FROM site_imports WHERE source_id=? ORDER BY imported_at DESC LIMIT 1', (source_id,)).fetchone()
            pid = uuid.uuid4().hex
            c.execute('INSERT INTO packages VALUES(?,?,?,?,?)', (pid, title, body, f'网站来源：{slug} · {outlet} · 版本 {digest[:10]}', now()))
            c.execute('INSERT INTO site_imports VALUES(?,?,?,?,?,?)', (source_id, digest, pid, source['source_file'], source['approved_at'], now()))
        return jsonify(package_id=pid, created=True, previous_package_id=older['package_id'] if older else None, source_id=source_id), 201

    @app.get('/api/site-imports')
    def site_imports():
        with db() as c:
            rows = c.execute('SELECT * FROM site_imports ORDER BY imported_at DESC').fetchall()
        return jsonify(items=[dict(r) for r in rows])
