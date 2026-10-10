"""Content-level history and a standalone local finished-content preview."""
import json
from html import escape
from pathlib import Path
from flask import jsonify, request, Response

def install(app, db, get, fail, text, now):
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS content_feedback(id INTEGER PRIMARY KEY AUTOINCREMENT,package_id TEXT NOT NULL REFERENCES packages(id),kind TEXT NOT NULL,author TEXT NOT NULL,note TEXT NOT NULL,url TEXT NOT NULL,created TEXT NOT NULL)')
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS content_provenance(id INTEGER PRIMARY KEY AUTOINCREMENT,package_id TEXT NOT NULL REFERENCES packages(id),video_id TEXT NOT NULL REFERENCES assets(id),value TEXT NOT NULL,created TEXT NOT NULL)')
    @app.get('/api/packages/<pid>/provenance')
    def provenance(pid):
        with db() as c:
            get(c,'packages',pid)
            row=c.execute('SELECT value,created FROM content_provenance WHERE package_id=? AND video_id=? ORDER BY id DESC LIMIT 1',(pid,request.args.get('video_id',''))).fetchone()
        return jsonify(record=json.loads(row['value']) if row else None,created=row['created'] if row else None)
    @app.post('/api/packages/<pid>/provenance')
    def save_provenance(pid):
        d=request.get_json();sources=d.get('sources',[]);segments=d.get('segments',[])
        if not isinstance(sources,list) or not isinstance(segments,list) or len(segments)>2000:fail('来源清单格式不正确')
        ids={s.get('id') for s in sources if isinstance(s,dict)}
        if len(ids)!=len(sources) or not all(isinstance(i,str) and i for i in ids):fail('原片 ID 缺失或重复')
        for seg in segments:
            if seg.get('source_id') not in ids:fail('片段原片不存在')
            for key in ['source_start_ms','source_end_ms','output_start_ms','output_end_ms']:
                if type(seg.get(key)) is not int or seg[key]<0:fail('时间码需要非负毫秒整数')
            if seg['source_end_ms']<=seg['source_start_ms'] or seg['output_end_ms']<=seg['output_start_ms']:fail('片段结束需晚于开始')
        with db() as c:
            get(c,'packages',pid);asset=get(c,'assets',d.get('video_id'))
            if asset['package_id']!=pid or asset['kind']!='video':fail('来源必须绑定本条视频')
            c.execute('INSERT INTO content_provenance(package_id,video_id,value,created) VALUES(?,?,?,?)',(pid,asset['id'],json.dumps(d,ensure_ascii=False),now()))
        return jsonify(ok=True),201

    @app.get('/api/agent-import-info')
    def agent_import_info():
        return jsonify(protocol='stdio',local_only=True,config={'mcpServers':{'content-desk':{'command':'python3','args':[str(Path(__file__).resolve().parent/'mcp'/'desk_mcp.py')]}}},guide='/static/agent-import.md',tools=['desk_status','preview_library_batch','import_library_batch','desk_content_history'])

    @app.get('/api/packages/<pid>/lifecycle')
    def lifecycle(pid):
        with db() as c:
            p = dict(get(c, 'packages', pid))
            tasks = [dict(r) for r in c.execute('SELECT t.*,a.name AS account_name,a.platform FROM tasks t JOIN accounts a ON a.id=t.account_id WHERE package_id=? ORDER BY t.created', (pid,))]
            events = [dict(r) for r in c.execute('SELECT e.* FROM events e JOIN tasks t ON t.id=e.task_id WHERE t.package_id=? ORDER BY e.created DESC', (pid,))]
            feedback = [dict(r) for r in c.execute('SELECT * FROM content_feedback WHERE package_id=? ORDER BY id DESC', (pid,))]
            annotations = [dict(r) for r in c.execute('SELECT id,note,fingerprint,created FROM library_annotations WHERE package_id=? ORDER BY id DESC', (pid,))]
        return jsonify(package=p,tasks=tasks,events=events,feedback=feedback,annotations=annotations)
    @app.post('/api/packages/<pid>/feedback')
    def feedback(pid):
        d=request.get_json();kind=d.get('kind','evaluation')
        if kind not in {'planning','evaluation','metrics'}:fail('请选择策划、评价或数据记录')
        note=text(d.get('note'),5000,True);author=text(d.get('author','本人'),120);url=text(d.get('url',''),2000)
        if url and not url.startswith(('https://','http://')):fail('链接需以 http 或 https 开头')
        with db() as c:
            get(c,'packages',pid)
            r=c.execute('INSERT INTO content_feedback(package_id,kind,author,note,url,created) VALUES(?,?,?,?,?,?)',(pid,kind,author,note,url,now()))
        return jsonify(id=r.lastrowid),201
    @app.put('/api/tasks/<tid>/publication-record')
    def publication_record(tid):
        d=request.get_json();url=text(d.get('url',''),2000);note=text(d.get('note',''),5000)
        if url and not url.startswith(('https://','http://')):fail('作品链接需以 http 或 https 开头')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');t=get(c,'tasks',tid)
            if d.get('revision')!=t['revision']:fail('任务已更新，请刷新后重试',409)
            c.execute('UPDATE tasks SET url=?,note=?,updated=? WHERE id=?',(url,note,now(),tid))
        return jsonify(ok=True)

    @app.get('/preview/<pid>')
    def preview(pid):
        with db() as c:
            p=dict(get(c,'packages',pid));assets=[dict(r) for r in c.execute('SELECT * FROM assets WHERE package_id=?',(pid,))]
            row=c.execute('SELECT value FROM package_meta WHERE package_id=?',(pid,)).fetchone()
            defaults=json.loads(row['value']).get('content_defaults',{}) if row else {}
        video=next((a for a in assets if a['id']==defaults.get('video_id')),None) or next((a for a in assets if a['kind']=='video'),None)
        cover=next((a for a in assets if a['id']==defaults.get('cover_id')),None) or next((a for a in assets if a['kind']=='image'),None)
        title=escape(defaults.get('short_title') or p['title'])
        media=(f'<video controls preload="metadata" src="/api/assets/{video["id"]}"'+(f' poster="/api/assets/{cover["id"]}"' if cover else '')+'></video>') if video else ''
        art=f'<img src="/api/assets/{cover["id"]}" alt="发布封面">' if cover else ''
        html=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · 成品预览</title><style>body{{margin:0;background:#f4f6f5;color:#243b33;font:16px/1.8 system-ui}}main{{max-width:1060px;margin:40px auto;padding:24px}}.media{{display:grid;grid-template-columns:minmax(0,2fr) minmax(160px,1fr);gap:24px}}video{{width:100%;max-height:70vh;background:#111;border-radius:12px}}img{{width:100%;max-height:60vh;object-fit:contain}}article{{background:white;padding:24px;border-radius:12px;margin-top:24px;white-space:pre-wrap}}@media(max-width:640px){{main{{margin:0;padding:18px}}.media{{grid-template-columns:1fr}}img{{max-height:220px}}}}a{{color:#285447}}</style><main><small>成品预览 · 本机链接</small><h1>{title}</h1><div class="media">{media}{art}</div><article>{escape(p['body'])}</article><p>{escape(defaults.get('tags',''))}</p><a href="/">返回内容工作台</a></main></html>'''
        return Response(html,mimetype='text/html')
