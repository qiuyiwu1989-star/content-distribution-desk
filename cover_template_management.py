"""Persistent user removal of selectable covers, with recovery."""
import json
from pathlib import Path
from flask import jsonify, request


def install(app, db, fail, now):
    root = Path(__file__).parent
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS removed_cover_templates(id TEXT PRIMARY KEY,removed TEXT NOT NULL)')

    def removed():
        with db() as c:
            return {r['id'] for r in c.execute('SELECT id FROM removed_cover_templates')}

    def filtered_catalog():
        value = json.loads((root / 'static/creative/catalog.json').read_text())
        hidden = removed()
        value['covers'] = [x for x in value['covers'] if x['id'] not in hidden]
        return jsonify(value)

    # Existing production choices keep their historical IDs; new choices exclude removed covers.
    app.view_functions['creative_catalog'] = filtered_catalog

    @app.get('/api/cover-design/catalog')
    def cover_catalog():
        value = json.loads((root / 'static/cover-design/catalog.json').read_text())
        hidden = removed()
        archived = request.args.get('removed') == '1'
        value['templates'] = [x for x in value['templates'] if (x['id'] in hidden) == archived]
        value['removed_count'] = len(hidden)
        return jsonify(value)

    def valid_id(tid):
        value = json.loads((root / 'static/cover-design/catalog.json').read_text())
        if not any(x['id'] == tid for x in value['templates']):
            fail('模板不存在', 404)

    @app.delete('/api/cover-design/templates/<tid>')
    def remove_cover_template(tid):
        valid_id(tid)
        with db() as c:
            c.execute('INSERT OR IGNORE INTO removed_cover_templates VALUES(?,?)', (tid, now()))
        return jsonify(ok=True)

    @app.post('/api/cover-design/templates/<tid>/restore')
    def restore_cover_template(tid):
        valid_id(tid)
        with db() as c:
            c.execute('DELETE FROM removed_cover_templates WHERE id=?', (tid,))
        return jsonify(ok=True)
