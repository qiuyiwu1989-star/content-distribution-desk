import io,re,tempfile,unittest
from PIL import Image
from server import create_app
class BrandTests(unittest.TestCase):
 def test_upload_filter_archive_restore(self):
  with tempfile.TemporaryDirectory() as d:
   app=create_app(d);c=app.test_client();token=re.search('name="desk-token" content="([^"]+)"',c.get('/').text)[1];h={'X-Desk-Token':token};image=io.BytesIO();Image.new('RGBA',(12,16),(0,0,0,0)).save(image,'PNG');image.seek(0)
   r=c.post('/api/brand-assets',headers=h,data={'file':(image,'logo.png'),'name':'示例标志','category':'logo','brand':'测试品牌','tags':'蓝色,品牌'});self.assertEqual(r.status_code,201);aid=r.json['id']
   self.assertEqual(len(c.get('/api/brand-assets?q=蓝色').json['items']),1);self.assertEqual(c.get('/api/brand-assets/'+aid+'/file').mimetype,'image/png')
   self.assertEqual(c.patch('/api/brand-assets/'+aid,headers=h,json={'archived':True}).status_code,200);self.assertEqual(c.get('/api/brand-assets').json['items'],[]);self.assertEqual(len(c.get('/api/brand-assets?archived=1').json['items']),1)
   c.patch('/api/brand-assets/'+aid,headers=h,json={'archived':False});self.assertEqual(len(c.get('/api/brand-assets').json['items']),1)
   r=c.post('/api/brand-assets',headers=h,data={'file':(io.BytesIO(b'not image'),'bad.png'),'name':'坏文件'});self.assertEqual(r.status_code,400)
