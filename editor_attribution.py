"""Version-bound editorial credits, distinct from recommendations and choices."""
import json
from pathlib import Path
from flask import jsonify, request


def install(app, db, get, fail, now):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS editor_credits(
            id INTEGER PRIMARY KEY AUTOINCREMENT, package_id TEXT NOT NULL REFERENCES packages(id),
            video_id TEXT NOT NULL, value TEXT NOT NULL, revision INTEGER NOT NULL,
            created TEXT NOT NULL)''')

    def read(c, pid):
        get(c, 'packages', pid)
        choice = c.execute('SELECT value FROM creative_choices WHERE package_id=?', (pid,)).fetchone()
        selected = json.loads(choice['value']).get('editor_id') if choice else None
        meta = c.execute('SELECT value FROM package_meta WHERE package_id=?', (pid,)).fetchone()
        video_id = json.loads(meta['value']).get('content_defaults', {}).get('video_id') if meta else None
        rows = c.execute('SELECT * FROM editor_credits WHERE package_id=? ORDER BY id DESC', (pid,)).fetchall()
        return {'selected_editor_id': selected, 'selected_video_id': video_id, 'revision': rows[0]['revision'] if rows else 0,
                'history': [dict(json.loads(r['value']), id=r['id'], created=r['created']) for r in rows]}

    @app.get('/api/creative/attributions')
    def all_credits():
        with db() as c:
            return jsonify(contents={r['id']: read(c, r['id']) for r in c.execute('SELECT id FROM packages')})

    @app.route('/api/packages/<pid>/editor-credit', methods=['GET', 'POST'])
    def credits(pid):
        if request.method == 'GET':
            with db() as c:
                return jsonify(read(c, pid))
        d = request.get_json()
        if not isinstance(d, dict): fail('请提供剪辑归属记录')
        video_id = d.get('video_id')
        contributors = d.get('contributors')
        if not isinstance(contributors, list) or not 1 <= len(contributors) <= 5:
            fail('请记录 1 至 5 位剪辑师')
        catalog = json.loads((Path(__file__).parent / 'static/creative/catalog.json').read_text())
        editors = {e['id']: e for e in catalog['editors']}
        values = []
        for entry in contributors:
            if not isinstance(entry, dict) or not isinstance(entry.get('editor_id'), str) or entry['editor_id'] not in editors:
                fail('剪辑师编号无效')
            if entry.get('role') not in {'主剪', '精修', '复核'}:
                fail('职责应为主剪、精修或复核')
            e = editors[entry['editor_id']]
            values.append({'editor_id': e['id'], 'editor_version': e['version'],
                           'name': e['persona']['name'], 'role': entry['role']})
        if len({(x['editor_id'], x['role']) for x in values}) != len(values):fail('职责记录重复')
        if sum(x['role'] == '主剪' for x in values) > 1:fail('同一版本只记录一位主剪')
        for field, limit in [('output_revision', 120), ('evidence', 3000), ('recorded_by', 120)]:
            if not isinstance(d.get(field), str) or not d[field].strip() or len(d[field]) > limit:
                fail('请填写成片版本、制作依据和记录者')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            current = read(c, pid)
            if type(d.get('revision')) is not int or d['revision'] != current['revision']:
                fail('归属记录已变化，请重新读取', 409)
            asset = c.execute('SELECT * FROM assets WHERE id=? AND package_id=? AND kind=?', (video_id, pid, 'video')).fetchone()
            if asset is None:fail('请绑定本条内容的实际视频')
            value = {'video_id': video_id, 'video_name': asset['name'], 'output_revision': d['output_revision'].strip(),
                     'contributors': values, 'evidence': d['evidence'].strip(), 'recorded_by': d['recorded_by'].strip(),
                     'basis': 'recorded-production-credit', 'review_approval': False}
            c.execute('INSERT INTO editor_credits(package_id,video_id,value,revision,created) VALUES(?,?,?,?,?)',
                      (pid, video_id, json.dumps(value, ensure_ascii=False), current['revision'] + 1, now()))
            return jsonify(read(c, pid)), 201
