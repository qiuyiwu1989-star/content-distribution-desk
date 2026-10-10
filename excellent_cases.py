"""Local reference videos and learning notes; no scraping or automatic analysis."""
import json,uuid
from pathlib import Path
from urllib.parse import urlparse
from flask import request,jsonify,send_file

def install(app,data,db,get,fail,text,now):
 folder=Path(data)/'excellent-cases';folder.mkdir(exist_ok=True)
 with db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS excellent_cases(id TEXT PRIMARY KEY,value TEXT NOT NULL,revision INTEGER NOT NULL,archived INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL)')
  c.execute('CREATE TABLE IF NOT EXISTS excellent_case_history(id INTEGER PRIMARY KEY,case_id TEXT,value TEXT,revision INTEGER,created TEXT)')
 def obj(r):
  d=json.loads(r['value']);d.update(id=r['id'],revision=r['revision'],archived=bool(r['archived']),created=r['created']);return d
 def fields(d,old=None):
  old=old or {};v={}
  for k,n in [('title',200),('url',2000),('creator',200),('why',4000),('segments',5000),('analysis',6000),('applicability',3000)]:v[k]=text(d.get(k,old.get(k,'')),n,k=='title')
  if v['url'] and (urlparse(v['url']).scheme not in {'https','http'} or not urlparse(v['url']).netloc):fail('请输入有效的 http 或 https 链接')
  tags=d.get('tags',old.get('tags',[]));tags=tags.replace('，',',').split(',') if isinstance(tags,str) else tags
  if not isinstance(tags,list) or len(tags)>30 or not all(isinstance(x,str) and len(x)<=80 for x in tags):fail('标签格式不正确')
  v['tags']=list(dict.fromkeys(x.strip() for x in tags if x.strip()));v['file_name']=old.get('file_name','');return v
 @app.get('/api/excellent-cases')
 def excellent_case_listing():
  q=request.args.get('q','').casefold();archived=int(request.args.get('archived')=='1')
  with db() as c:items=[obj(r) for r in c.execute('SELECT * FROM excellent_cases WHERE archived=? ORDER BY created DESC',(archived,))]
  return jsonify(items=[x for x in items if q in json.dumps(x,ensure_ascii=False).casefold()])
 @app.get('/api/excellent-cases/<cid>')
 def excellent_case_detail(cid):
  with db() as c:
   d=obj(get(c,'excellent_cases',cid));d['history']=[dict(r) for r in c.execute('SELECT revision,value,created FROM excellent_case_history WHERE case_id=? ORDER BY revision DESC',(cid,))]
  return jsonify(d)
 @app.post('/api/excellent-cases')
 def excellent_case_add():
  d=request.form if request.mimetype=='multipart/form-data' else (request.get_json() or {});v=fields(d);f=request.files.get('file');f=f if f and f.filename else None;cid=uuid.uuid4().hex
  if not f and not v['url']:fail('请选择视频或填写链接')
  if f:
   if Path(f.filename).suffix.lower() not in {'.mp4','.mov','.webm','.m4v'}:fail('支持 MP4、MOV、WebM、M4V')
   v['file_name']=text(Path(f.filename).name,200,True);f.save(folder/cid)
  with db() as c:c.execute('INSERT INTO excellent_cases VALUES(?,?,1,0,?)',(cid,json.dumps(v,ensure_ascii=False),now()))
  return jsonify(id=cid,revision=1),201
 @app.patch('/api/excellent-cases/<cid>')
 def excellent_case_edit(cid):
  d=request.get_json() or {}
  with db() as c:
   c.execute('BEGIN IMMEDIATE');r=get(c,'excellent_cases',cid)
   if d.get('revision')!=r['revision']:fail('案例已更新，请重新打开后编辑',409)
   archived=d.get('archived',bool(r['archived']))
   if type(archived) is not bool:fail('归档格式不正确')
   v=fields(d,json.loads(r['value']));c.execute('INSERT INTO excellent_case_history(case_id,value,revision,created) VALUES(?,?,?,?)',(cid,r['value'],r['revision'],now()));c.execute('UPDATE excellent_cases SET value=?,revision=revision+1,archived=? WHERE id=?',(json.dumps(v,ensure_ascii=False),int(archived),cid))
  return jsonify(ok=True,revision=r['revision']+1)
 @app.get('/api/excellent-cases/<cid>/file')
 def excellent_case_media(cid):
  with db() as c:d=obj(get(c,'excellent_cases',cid))
  if not d['file_name']:fail('此案例没有本地视频',404)
  return send_file(folder/cid,download_name=d['file_name'],conditional=True)
