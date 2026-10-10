import unittest,tempfile,re
from pathlib import Path
from server import create_app
class LifecycleTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.client=create_app(Path(self.tmp.name)).test_client()
  self.headers={'X-Desk-Token':re.search('name="desk-token" content="([^"]+)"',self.client.get('/').text).group(1)}
  self.pid=self.client.post('/api/packages',json={'title':'<script>alert(1)</script>','body':'原文'},headers=self.headers).json['id']
 def tearDown(self):self.tmp.cleanup()
 def test_records_independent_of_review(self):
  before=self.client.get('/api/library').json['packages'][self.pid]
  r=self.client.post('/api/packages/'+self.pid+'/feedback',json={'kind':'metrics','author':'本人','note':'10月9日播放量100，人工核对'},headers=self.headers)
  self.assertEqual(r.status_code,201)
  d=self.client.get('/api/packages/'+self.pid+'/lifecycle').json
  self.assertEqual(d['feedback'][0]['kind'],'metrics');self.assertEqual(d['tasks'],[])
  self.assertEqual(before,self.client.get('/api/library').json['packages'][self.pid])
 def test_preview_escapes_content(self):
  r=self.client.get('/preview/'+self.pid);self.assertEqual(r.status_code,200)
  self.assertNotIn('<script>alert',r.text);self.assertIn('&lt;script&gt;',r.text)
 def test_invalid_reference(self):
  r=self.client.post('/api/packages/'+self.pid+'/feedback',json={'note':'备注','url':'javascript:alert(1)'},headers=self.headers)
  self.assertEqual(r.status_code,400)

 def test_publication_record_is_separate(self):
  aid=self.client.post('/api/accounts',json={'name':'示例','platform':'channels'},headers=self.headers).json['id']
  t=self.client.post('/api/tasks',json={'package_id':self.pid,'account_id':aid,'format':'video'},headers=self.headers).json
  t=next(x for x in self.client.get('/api/state').json['tasks'] if x['id']==t['id'])
  r=self.client.put('/api/tasks/'+t['id']+'/publication-record',json={'revision':t['revision'],'url':'https://example.com/clip','note':'人工记录'},headers=self.headers)
  self.assertEqual(r.status_code,200)
  saved=self.client.get('/api/packages/'+self.pid+'/lifecycle').json['tasks'][0]
  self.assertEqual(saved['status'],t['status']);self.assertEqual(saved['url'],'https://example.com/clip')
