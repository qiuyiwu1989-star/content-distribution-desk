"""Reusable design/editor catalog and persisted production choices, without rendering."""
import json
from pathlib import Path
from flask import jsonify, request


def install(app, db, get, fail, now):
    from template_editor import install as install_layouts
    install_layouts(app, db, fail, now)
    catalog_path = Path(__file__).parent / 'static/creative/catalog.json'
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS creative_choices(
            package_id TEXT PRIMARY KEY REFERENCES packages(id),
            value TEXT NOT NULL, revision INTEGER NOT NULL, updated TEXT NOT NULL)''')

    def catalog():
        value = json.loads(catalog_path.read_text())
        with db() as c:
            hidden = {r["id"] for r in c.execute("SELECT id FROM removed_cover_templates")}
        value["covers"] = [x for x in value["covers"] if x["id"] not in hidden]
        return value

    def read(c, pid):
        row = c.execute('SELECT value,revision,updated FROM creative_choices WHERE package_id=?', (pid,)).fetchone()
        return dict(json.loads(row['value']), revision=row['revision'], updated=row['updated']) if row else dict(template_id=None,editor_id=None,cover_id=None,versions={},revision=0,updated=None)

    @app.get('/api/creative/catalog')
    def creative_catalog():
        return jsonify(catalog())

    @app.get('/api/packages/<pid>/creative')
    def creative_choice(pid):
        with db() as c:
            get(c, 'packages', pid)
            return jsonify(read(c, pid))

    @app.put('/api/packages/<pid>/creative')
    def save_choice(pid):
        d = request.get_json()
        if not isinstance(d, dict):
            fail('请选择制作方案')
        lib = catalog()
        value, versions = {}, {}
        for field, collection in [('template_id', 'templates'), ('editor_id', 'editors'), ('cover_id', 'covers')]:
            selected = d.get(field)
            if selected is not None and not isinstance(selected, str):
                fail('选择编号无效')
            item = next((x for x in lib[collection] if x['id'] == selected), None)
            if selected is not None and item is None:
                fail('该模板或剪辑师已不可用，请重新选择')
            value[field] = selected
            if item:
                versions[field] = item.get('version', 'concept-01')
        value['versions'] = versions
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            get(c, 'packages', pid)
            old = read(c, pid)
            if type(d.get('revision')) is not int or d['revision'] != old['revision']:
                fail('制作方案已变化，请重新打开后再保存', 409)
            c.execute('INSERT INTO creative_choices VALUES(?,?,?,?) ON CONFLICT(package_id) DO UPDATE SET value=excluded.value,revision=excluded.revision,updated=excluded.updated',
                      (pid, json.dumps(value, ensure_ascii=False), old['revision'] + 1, now()))
            return jsonify(read(c, pid))
