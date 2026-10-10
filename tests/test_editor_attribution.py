import io,re,tempfile,unittest
from server import create_app
class EditorAttributionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.client=create_app(self.tmp.name).test_client()
  token=re.search(r'name="desk-token" content="([^"]+)"',self.client.get('/').get_data(as_text=True)).group(1);self.headers={'X-Desk-Token':token}
  self.pid=self.client.post('/api/packages',json={'title':'测试片','body':'测试'},headers=self.headers).json['id']
  self.video=self.client.post(f'/api/packages/{self.pid}/assets',data={'file':(io.BytesIO(b'fixture-only'),'v001.mp4')},headers=self.headers).json['id']
 def test_selected_editor_is_not_credit(self):
  self.client.put(f'/api/packages/{self.pid}/creative',json={'revision':0,'editor_id':'E02'},headers=self.headers)
  d=self.client.get(f'/api/packages/{self.pid}/editor-credit').json;self.assertEqual(d['selected_editor_id'],'E02');self.assertEqual(d['history'],[])
 def test_credit_history_binding_and_conflict(self):
  url=f'/api/packages/{self.pid}/editor-credit';p={'revision':0,'video_id':self.video,'contributors':[{'editor_id':'E02','role':'主剪'}],'output_revision':'v001','evidence':'测试制作记录','recorded_by':'unit-test'}
  self.assertEqual(self.client.post(url,json=p).status_code,403)
  self.assertEqual(self.client.post(url,json={**p,'video_id':'unrelated'},headers=self.headers).status_code,400)
  saved=self.client.post(url,json=p,headers=self.headers);self.assertEqual(saved.status_code,201);self.assertEqual(saved.json['history'][0]['video_id'],self.video);self.assertFalse(saved.json['history'][0]['review_approval'])
  self.assertEqual(self.client.post(url,json=p,headers=self.headers).status_code,409)
  p['revision']=1;p['contributors'].append({'editor_id':'E05','role':'精修'});newer=self.client.post(url,json=p,headers=self.headers)
  self.assertEqual(len(newer.json['history']),2);self.assertEqual(len(newer.json['history'][0]['contributors']),2);self.assertEqual(len(newer.json['history'][1]['contributors']),1)
  self.assertEqual(self.client.get('/api/creative/attributions').json['contents'][self.pid]['revision'],2)
