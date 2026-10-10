import importlib.util,io,json,tempfile,unittest,zipfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('publisher',Path(__file__).resolve().parents[1]/'scripts/publish_browser_plugin.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
def blob(version,script=b'one'):
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w') as z:
  z.writestr('plugin/manifest.json',json.dumps({'name':'Plugin','version':version,'manifest_version':3,'background':{'service_worker':'background.js'}}));z.writestr('plugin/background.js',script)
 return out.getvalue()
class Releases(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.public=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def test_immutable_versions_and_recommendation(self):
  a=blob('1.0.0');p.publish('test-plugin',a,'first',recommend=True,public=self.public)
  before=(self.public/'catalog.json').read_bytes()
  with self.assertRaises(ValueError):p.publish('test-plugin',blob('1.0.0',b'changed'),'first',public=self.public)
  self.assertEqual((self.public/'catalog.json').read_bytes(),before)
  p.publish('test-plugin',blob('1.0.1'),'second',recommend=True,public=self.public)
  p.publish('test-plugin',a,'first',recommend=True,public=self.public)
  catalog=json.loads((self.public/'catalog.json').read_text());self.assertEqual(catalog['plugins'][0]['current_version'],'1.0.0');self.assertEqual(len(catalog['plugins'][0]['releases']),2)
 def test_invalid_archive_reference_rejected(self):
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z:z.writestr('manifest.json',json.dumps({'name':'Plugin','version':'1.0.0','background':{'service_worker':'missing.js'}}))
  with self.assertRaises(ValueError):p.publish('test-plugin',out.getvalue(),'invalid',public=self.public)
  self.assertFalse((self.public/'catalog.json').exists())
