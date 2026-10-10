"""Edit the canonical ASR dictionary with locking and recoverable snapshots."""
import json, os, uuid, fcntl
from pathlib import Path
from flask import request, jsonify
PATH=Path('/Users/Apple/Documents/邱懿武03/协作资料/技能/asr-text-correction/references/hotwords.json')
def install(app,data,fail,text,now):
 history=Path(data)/'hotword-history';history.mkdir(exist_ok=True)
 @app.get('/api/hotwords')
 def hotword_list():
  return jsonify(json.loads(PATH.read_text()))
 @app.post('/api/hotwords')
 @app.patch('/api/hotwords/<tid>')
 def hotword_save(tid=None):
  d=request.get_json() or {}
  with open(str(PATH)+'.lock','a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   raw=PATH.read_text();v=json.loads(raw)
   if d.get('version')!=v['version']:fail('热词库已更新，请重新打开后修改',409)
   old=next((x for x in v['terms'] if x['id']==tid),None)
   if tid and not old:fail('找不到热词',404)
   x=dict(old or {});x['id']=tid or 'HW-'+uuid.uuid4().hex[:12]
   for k,n in [('canonical',200),('category',100),('scope',2000),('evidence',2000)]:x[k]=text(d.get(k,x.get(k,'')),n,k=='canonical')
   variants=d.get('variants',x.get('variants',[]))
   if not isinstance(variants,list) or any(not isinstance(a,str) for a in variants):fail('误识别词格式不正确')
   x['variants']=list(dict.fromkeys(a.strip() for a in variants if a.strip() and a.strip()!=x['canonical']))
   if len(x['variants'])>50 or any(len(a)>200 for a in x['variants']):fail('误识别词过多或过长')
   if any(a['id']!=x['id'] and a['canonical'].casefold()==x['canonical'].casefold() for a in v['terms']):fail('这个正确词已经存在，请修改已有条目')
   x.update(auto_replace=False,heard_verified=False,status='candidate-needs-context' if x['variants'] else 'reference-term')
   x['recognition_hint']=True
   if old:v['terms'][v['terms'].index(old)]=x
   else:v['terms'].append(x)
   (history/(uuid.uuid4().hex+'.json')).write_text(raw)
   parts=v['version'].split('.');parts[-1]=str(int(parts[-1])+1);v['version']='.'.join(parts);v['updated']=now()[:10]
   tmp=PATH.with_name('.hotwords-'+uuid.uuid4().hex+'.tmp');tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');os.replace(tmp,PATH)
  return jsonify(ok=True,version=v['version'])
