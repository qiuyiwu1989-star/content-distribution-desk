"""Versioned personal oral-edit examples. Approval is recorded feedback, not inferred."""
import json,uuid
from pathlib import Path
from urllib.parse import urlparse
from flask import request,jsonify,send_file

def install(app,data,db,get,fail,text,now):
 folder=Path(data)/'oral-cases';folder.mkdir(exist_ok=True)
 with db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS oral_cases(id TEXT PRIMARY KEY,value TEXT NOT NULL,revision INTEGER NOT NULL,archived INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL)')
  c.execute('CREATE TABLE IF NOT EXISTS oral_case_history(id INTEGER PRIMARY KEY,case_id TEXT,value TEXT,revision INTEGER,created TEXT)')
 def obj(r):
  d=json.loads(r['value']);d.update(id=r['id'],revision=r['revision'],archived=bool(r['archived']),created=r['created']);return d
 def fields(d,old=None):
  old=old or {};v={}
  for k,n in [('title',200),('source',2000),('source_version',200),('location',500),('original',6000),('context',6000),('decision',4000),('reason',4000),('protected',3000),('feedback',5000),('confirmed_by',200),('confirmed_at',200),('scope_note',3000),('before_url',2000),('after_url',2000)]:v[k]=text(d.get(k,old.get(k,'')),n,k=='title')
  for k in ['before_url','after_url']:
   if v[k] and (urlparse(v[k]).scheme not in {'http','https'} or not urlparse(v[k]).netloc):fail('请输入有效的音视频链接')
  for k,allowed,default in [('category',{'repetition','restart','filler','detour','keep'},'repetition'),('status',{'candidate','applied','approved','rejected'},'candidate'),('scope',{'this-case','similar-context','personal-default'},'this-case')]:
   v[k]=d.get(k,old.get(k,default))
   if v[k] not in allowed:fail('案例分类、状态或适用范围不正确')
  if v['status']=='approved' and not all(v[k].strip() for k in ['feedback','confirmed_by','confirmed_at','scope_note']):fail('认可案例需填写反馈、确认人、日期和适用说明')
  if v['scope']=='personal-default' and v['status']!='approved':fail('只有明确认可的案例可以设为长期参考')
  v['media']=old.get('media',{}).copy();return v
 def uploads(v):
  for key in ['before','after']:
   f=request.files.get(key)
   if not f or not f.filename:continue
   if Path(f.filename).suffix.lower() not in {'.mp4','.mov','.webm','.m4v','.mp3','.wav','.m4a','.ogg'}:fail('支持常见音频和视频文件')
   fid=uuid.uuid4().hex;f.save(folder/fid);v['media'][key]={'id':fid,'name':text(Path(f.filename).name,200,True)}
 @app.get('/api/oral-cases')
 def oral_case_list():
  q=request.args.get('q','').casefold();status=request.args.get('status','')
  with db() as c:items=[obj(r) for r in c.execute('SELECT * FROM oral_cases WHERE archived=? ORDER BY created DESC',(int(request.args.get('archived')=='1'),))]
  return jsonify(items=[x for x in items if q in json.dumps(x,ensure_ascii=False).casefold() and (not status or x['status']==status)])
 @app.get('/api/oral-cases/<cid>')
 def oral_case_detail(cid):
  with db() as c:
   d=obj(get(c,'oral_cases',cid));d['history']=[dict(r) for r in c.execute('SELECT revision,value,created FROM oral_case_history WHERE case_id=? ORDER BY revision DESC',(cid,))]
  return jsonify(d)
 @app.post('/api/oral-cases')
 def oral_case_add():
  d=request.form if request.mimetype=='multipart/form-data' else request.get_json() or {};v=fields(d);uploads(v);cid=uuid.uuid4().hex
  with db() as c:c.execute('INSERT INTO oral_cases VALUES(?,?,1,0,?)',(cid,json.dumps(v,ensure_ascii=False),now()))
  return jsonify(id=cid,revision=1),201
 @app.patch('/api/oral-cases/<cid>')
 def oral_case_edit(cid):
  d=request.form if request.mimetype=='multipart/form-data' else request.get_json() or {}
  with db() as c:
   c.execute('BEGIN IMMEDIATE');r=get(c,'oral_cases',cid)
   if str(d.get('revision'))!=str(r['revision']):fail('案例已更新，请重新打开后编辑',409)
   archived=d.get('archived',bool(r['archived']))
   if type(archived) is not bool:fail('归档标记格式不正确')
   v=fields(d,json.loads(r['value']));uploads(v)
   c.execute('INSERT INTO oral_case_history(case_id,value,revision,created) VALUES(?,?,?,?)',(cid,r['value'],r['revision'],now()));c.execute('UPDATE oral_cases SET value=?,revision=revision+1,archived=? WHERE id=?',(json.dumps(v,ensure_ascii=False),int(archived),cid))
  return jsonify(ok=True,revision=r['revision']+1)
 @app.get('/api/oral-cases/<cid>/media/<fid>')
 def oral_case_media(cid,fid):
  with db() as c:
   r=get(c,'oral_cases',cid);values=[json.loads(r['value'])]+[json.loads(x['value']) for x in c.execute('SELECT value FROM oral_case_history WHERE case_id=?',(cid,))]
  m=next((m for v in values for m in v.get('media',{}).values() if m['id']==fid),None)
  if not m:fail('找不到案例音视频',404)
  return send_file(folder/fid,download_name=m['name'],conditional=True)
