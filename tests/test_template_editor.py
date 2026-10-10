import unittest,tempfile,re
from server import create_app
class LayoutTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.app=create_app(self.tmp.name);self.c=self.app.test_client();self.h={'X-Desk-Token':re.search('name="desk-token" content="([^"]+)',self.c.get('/').text).group(1)}
  self.d={'schema':'desk-layout.v1','name':'编辑测试','base':'T02','layers':[{'id':'title','kind':'text','text':'测试','x':12,'y':34,'font':'harmonyos-sans','fill':'#ffffff'}]}
 def test_save_reload_conflict_and_auth(self):
  self.assertEqual(self.c.post('/api/layouts',json={'document':self.d}).status_code,403)
  r=self.c.post('/api/layouts',json={'document':self.d},headers=self.h);self.assertEqual(r.status_code,200);path='/api/layouts/'+r.json['id'];self.assertEqual(self.c.get(path).json['document'],self.d)
  self.d['layers'][0]['x']=99
  self.assertEqual(self.c.put(path,json={'document':self.d,'revision':1},headers=self.h).json['revision'],2)
  self.assertEqual(self.c.put(path,json={'document':self.d,'revision':1},headers=self.h).status_code,409)
  self.assertEqual(self.c.get(path).json['document']['layers'][0]['x'],99)
 def test_reject_unsafe_and_invalid(self):
  for key,value in [('x',float('inf')),('font','unknown'),('fill','url(javascript:x)'),('src','https://external.example/file')]:
   d=__import__('copy').deepcopy(self.d);d['layers'][0][key]=value
   self.assertEqual(self.c.post('/api/layouts',json={'document':d},headers=self.h).status_code,400)
