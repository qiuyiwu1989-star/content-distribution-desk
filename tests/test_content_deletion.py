import tempfile,re,sqlite3,unittest
from pathlib import Path
from server import create_app
class DeletionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.app=create_app(self.tmp.name);self.c=self.app.test_client();self.h={'X-Desk-Token':re.search('name="desk-token" content="([^"]+)"',self.c.get('/').text).group(1)}
 def tearDown(self):self.tmp.cleanup()
 def post(self,path,d):return self.c.post('/api'+path,json=d,headers=self.h)
 def package(self):return self.post('/packages',{'title':'可删除内容','body':'正文'}).json['id']
 def test_delete_restore_preserves_media_and_history(self):
  pid=self.package();aid=self.post('/accounts',{'platform':'channels','name':'甲'}).json['id'];tid=self.post('/packages/'+pid+'/distribute',{'targets':[{'account_id':aid,'format':'video'}]}).json['created'][0]
  r=self.c.delete('/api/packages/'+pid,headers=self.h);self.assertEqual(r.status_code,200,r.json)
  meta=self.c.get('/api/library').json['packages'][pid];self.assertTrue(meta['deleted']);self.assertEqual(len(self.c.get('/api/library/trash').json['items']),1)
  self.assertEqual(self.post('/packages/'+pid+'/distribute',{'targets':[{'account_id':aid,'format':'video'}]}).status_code,409)
  t=next(t for t in self.c.get('/api/state').json['tasks'] if t['id']==tid);self.assertEqual(t['status'],'canceled')
  self.assertEqual(self.post('/packages/'+pid+'/restore',{}).status_code,200);self.assertFalse(self.c.get('/api/library').json['packages'][pid]['deleted']);self.assertEqual(self.c.get('/api/library/trash').json['items'],[])
 def test_batch_atomic_if_one_running_and_published_preserved(self):
  one=self.package();two=self.package();aid=self.post('/accounts',{'platform':'channels','name':'甲'}).json['id'];tid=self.post('/packages/'+two+'/distribute',{'targets':[{'account_id':aid,'format':'video'}]}).json['created'][0]
  with sqlite3.connect(Path(self.tmp.name)/'desk.sqlite3') as c:c.execute("UPDATE tasks SET status='running' WHERE id=?",(tid,))
  self.assertEqual(self.post('/library/trash',{'package_ids':[one,two]}).status_code,409);self.assertEqual(self.c.get('/api/library/trash').json['items'],[])
  with sqlite3.connect(Path(self.tmp.name)/'desk.sqlite3') as c:c.execute("UPDATE tasks SET status='published' WHERE id=?",(tid,))
  self.assertEqual(self.post('/library/trash',{'package_ids':[one,two]}).status_code,200)
  t=next(t for t in self.c.get('/api/state').json['tasks'] if t['id']==tid);self.assertEqual(t['status'],'published')
