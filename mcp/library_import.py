"""Portable library-only manifest importer, resumable through local receipts."""
import json, hashlib, mimetypes, urllib.request, uuid
from pathlib import Path
from desk_cli import DeskClient

def digest(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def prepare(path):
 p=Path(path).resolve();j=json.loads(p.read_text());items=j['items'];seen=set();sequences=set()
 if not isinstance(j.get('batch_name'),str) or not j['batch_name'].strip():raise ValueError('batch_name必填')
 if not items:raise ValueError('批次为空')
 for x in items:
  if not isinstance(x.get('id'),str) or not x['id'] or not x.get('version') or not x.get('title'):raise ValueError('每条需要id、version和title')
  key=(x['id'],str(x['version']))
  if key in seen:raise ValueError('重复内容ID和版本')
  seen.add(key)
  if type(x.get('sequence')) is not int or x['sequence']<1:raise ValueError('sequence必须为正整数')
  if x['sequence'] in sequences:raise ValueError('批次顺序重复')
  sequences.add(x['sequence'])
  for k in ['video','cover']:
   if x.get(k):
    f=(p.parent/x[k]).resolve()
    if not f.is_file() or not f.stat().st_size:raise ValueError('素材不可读：'+str(f))
    x[k]=str(f)
  if not x.get('video'):raise ValueError('视频缺失：'+x['id'])
 return p,j

def run(path,apply=False):
 p,j=prepare(path)
 if not apply:return {'count':len(j['items']),'batch':j['batch_name'],'missing_covers':[x['id'] for x in j['items'] if not x.get('cover')],'written':False}
 c=DeskClient();s=c.request('/api/library');batch=next((b for b in s['batches'] if b['name']==j['batch_name']),None) or c.request('/api/library/batches','POST',{'name':j['batch_name']})
 receipt=p.with_suffix(p.suffix+'.desk-receipt.json');ledger=json.loads(receipt.read_text()) if receipt.exists() else {};out=[]
 def persist():
  tmp=receipt.with_suffix(receipt.suffix+'.tmp');tmp.write_text(json.dumps(ledger,ensure_ascii=False,indent=2));tmp.replace(receipt)
 for x in j['items']:
  hashes={k:digest(x[k]) for k in ['video','cover'] if x.get(k)}
  key=hashlib.sha256(json.dumps({'batch':j['batch_name'],'item':x,'hashes':hashes},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
  mark='agent-import:'+key;record=ledger.get(key,{})
  if not record:
   candidates=[v for v in s['snapshot']['packages'] if mark in v.get('notes','')]
   if len(candidates)>1:raise ValueError('发现重复入库记录，请核对')
   pid=candidates[0]['id'] if candidates else c.request('/api/packages','POST',{'title':x['title'],'body':x.get('body',''),'notes':mark+'\n'+json.dumps({'content_id':x['id'],'version':x['version'],'tags':x.get('tags',[]),'source':x.get('source',{}),'review':x.get('review',{}),'intent':x.get('intent','publish')},ensure_ascii=False)})['id']
   record={'package_id':pid,'uploaded':{}};ledger[key]=record;persist()
  pid=record['package_id']
  c.request('/api/packages/'+pid+'/library','PATCH',{'batch_id':batch['id'],'sequence':x['sequence']})
  for kind in ['video','cover']:
   if not x.get(kind) or kind in record['uploaded']:continue
   f=Path(x[kind]);boundary=uuid.uuid4().hex
   data=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{f.name.replace(chr(34),"")}"\r\nContent-Type: {mimetypes.guess_type(f.name)[0] or "application/octet-stream"}\r\n\r\n').encode()+f.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
   req=urllib.request.Request(c.base+'/api/packages/'+pid+'/assets',data=data,headers={'X-Desk-Token':c.token,'Content-Type':'multipart/form-data; boundary='+boundary},method='POST')
   with urllib.request.urlopen(req,timeout=180) as r:record['uploaded'][kind]=json.load(r)
   persist()
  out.append({'content_id':x['id'],'package_id':pid})
 return {'imported':out,'receipt':str(receipt),'tasks_created':0,'published':False,'note':'intent与review作为交付元数据保留，尚未转换为界面不发标签；同一MCP串行导入，勿多客户端并发同一清单'}
