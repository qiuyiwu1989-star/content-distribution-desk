import tempfile,re,unittest
from server import create_app
class AssignmentTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.c=create_app(self.tmp.name).test_client();self.h={'X-Desk-Token':re.search('name="desk-token" content="([^"]+)"',self.c.get('/').text).group(1)}
 def tearDown(self):self.tmp.cleanup()
 def post(self,p,d):return self.c.post('/api'+p,json=d,headers=self.h)
 def test_neutral_then_explicit_assignment_and_manual_record(self):
  pid=self.post('/packages',{'title':'内容','body':'正文'}).json['id'];self.assertEqual(len(self.c.get('/api/state').json['tasks']),0)
  self.assertEqual(self.c.put('/api/packages/'+pid+'/defaults',json={'tags':'#主题'},headers=self.h).status_code,200)
  aid=self.post('/accounts',{'name':'指定账号','platform':'channels'}).json['id']
  r=self.post('/packages/'+pid+'/distribute',{'targets':[{'account_id':aid,'format':'video'}]});self.assertEqual(r.status_code,201)
  t=self.c.get('/api/state').json['tasks'][0];self.assertEqual(t['tags'],'#主题')
  self.post('/tasks/'+t['id']+'/transition',{'revision':t['revision'],'status':'canceled'})
  r=self.post('/packages/'+pid+'/distribute',{'targets':[{'account_id':aid,'format':'video'}]});self.assertEqual(r.status_code,201,r.json)
  data={'account_id':aid,'format':'video','published_at':'2026-01-01T00:00:00+08:00','request_id':'74ccf337-51ed-44cb-87da-0e7c1c7a9392'}
  self.assertEqual(self.post('/packages/'+pid+'/publication-record',data).status_code,201);self.assertEqual(self.post('/packages/'+pid+'/publication-record',data).status_code,200)
  ts=self.c.get('/api/state').json['tasks'];self.assertEqual(sum(x['status']=='published' for x in ts),1)
 def test_requires_account_and_time(self):
  pid=self.post('/packages',{'title':'内容'}).json['id'];self.assertEqual(self.post('/packages/'+pid+'/publication-record',{}).status_code,400)
 def test_copy_updates_pending_and_new_tasks_without_touching_custom_copy(self):
  pid=self.post('/packages',{'title':'内容','body':'原正文'}).json['id']
  aid=self.post('/accounts',{'name':'甲','platform':'channels'}).json['id']
  tid=self.post('/packages/'+pid+'/distribute',{'targets':[{'account_id':aid,'format':'video'}]}).json['created'][0]
  r=self.c.patch('/api/packages/'+pid+'/copy',json={'revision':0,'short_title':'新短标题','body':'新正文','tags':'#造物云 #FDE'},headers=self.h)
  self.assertEqual(r.status_code,200,r.json);t=next(t for t in self.c.get('/api/state').json['tasks'] if t['id']==tid)
  self.assertEqual((t['title'],t['body'],t['tags']),('新短标题','新正文','#造物云 #FDE'))
  self.assertEqual(self.c.patch('/api/packages/'+pid+'/copy',json={'revision':0,'body':'过期正文'},headers=self.h).status_code,409)
  self.c.patch('/api/tasks/'+tid,json={'revision':t['revision'],'body':'此渠道单独文案'},headers=self.h)
  self.c.patch('/api/packages/'+pid+'/copy',json={'revision':1,'body':'第三版正文'},headers=self.h)
  t=next(t for t in self.c.get('/api/state').json['tasks'] if t['id']==tid);self.assertEqual(t['body'],'此渠道单独文案')
  bid=self.post('/accounts',{'name':'乙','platform':'channels'}).json['id'];tid2=self.post('/packages/'+pid+'/distribute',{'targets':[{'account_id':bid,'format':'video'}]}).json['created'][0]
  t2=next(t for t in self.c.get('/api/state').json['tasks'] if t['id']==tid2);self.assertEqual((t2['title'],t2['body']),('新短标题','第三版正文'))
 def test_copy_preserves_published_history_and_rejects_long_title(self):
  pid=self.post('/packages',{'title':'原标题','body':'原正文'}).json['id'];aid=self.post('/accounts',{'name':'甲','platform':'channels'}).json['id']
  data={'account_id':aid,'format':'video','published_at':'2026-01-01T00:00:00+08:00','request_id':'8a777592-cf98-4b2f-a44a-c772a220cb90'};tid=self.post('/packages/'+pid+'/publication-record',data).json['id']
  self.assertEqual(self.c.patch('/api/packages/'+pid+'/copy',json={'revision':0,'short_title':'长'*17},headers=self.h).status_code,400)
  r=self.c.patch('/api/packages/'+pid+'/copy',json={'revision':0,'short_title':'新标题','body':'新正文'},headers=self.h);self.assertEqual(r.status_code,200,r.json)
  t=next(t for t in self.c.get('/api/state').json['tasks'] if t['id']==tid);self.assertEqual((t['title'],t['body'],t['status']),('原标题','原正文','published'))
 def test_legacy_fields_backfilled_and_account_neutral_export(self):
  import io,json,zipfile,sqlite3,hashlib
  from pathlib import Path
  pid=self.post('/packages',{'title':'内部内容名称','body':'原正文'}).json['id'];aid=self.post('/accounts',{'name':'旧账号','platform':'channels'}).json['id'];tid=self.post('/tasks',{'package_id':pid,'account_id':aid,'format':'video'}).json['id']
  vid=self.c.post('/api/packages/'+pid+'/assets',data={'file':(io.BytesIO(b'video-bytes'),'video.mp4')},headers=self.h).json['id']
  cid=self.c.post('/api/packages/'+pid+'/assets',data={'file':(io.BytesIO(b'image-bytes'),'cover.png')},headers=self.h).json['id']
  with sqlite3.connect(Path(self.tmp.name)/'desk.sqlite3') as c:c.execute('UPDATE tasks SET title=?,tags=?,asset_ids=?,cover_id=? WHERE id=?',('短标题','#业务 #FDE',json.dumps([vid]),cid,tid))
  self.app=create_app(self.tmp.name);self.c=self.app.test_client();self.h={'X-Desk-Token':re.search('name="desk-token" content="([^"]+)"',self.c.get('/').text).group(1)}
  copy=self.c.get('/api/packages/'+pid+'/copy').json;self.assertEqual(copy['short_title'],'短标题');self.assertIn('#业务',copy['tags']);self.assertIn('#造物云',copy['tags']);self.assertEqual(copy['cover_id'],cid)
  response=self.c.get('/api/packages/'+pid+'/content-bundle');self.assertEqual(response.status_code,200)
  with zipfile.ZipFile(io.BytesIO(response.data)) as z:
   m=json.loads(z.read('batch.json'));item=m['items'][0];self.assertEqual(item['body'],'原正文');self.assertEqual(item['short_title'],'短标题');self.assertNotIn('account_id',item);self.assertEqual(item['assets']['video']['sha256'],hashlib.sha256(b'video-bytes').hexdigest());self.assertEqual(z.read(item['assets']['video']['path']),b'video-bytes')
  response.close()
