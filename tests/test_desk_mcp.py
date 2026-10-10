import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'mcp'))
from library_import import prepare,run
class MCPManifestTests(unittest.TestCase):
 def test_preview_and_missing_assets(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'v.mp4').write_bytes(b'fixture');m={'batch_name':'测试','items':[{'id':'c1','version':'v1','title':'测试','sequence':2,'video':'v.mp4'}]};(p/'batch.json').write_text(json.dumps(m))
   self.assertEqual(run(p/'batch.json')['missing_covers'],['c1'])
   self.assertFalse((p/'batch.json.desk-receipt.json').exists())
   m['items'].append(m['items'][0]);(p/'batch.json').write_text(json.dumps(m))
   with self.assertRaises(ValueError):prepare(p/'batch.json')
 def test_sync_requires_account(self):
  from desk_mcp import call
  with self.assertRaises(ValueError):call('sync_production_batch',{'batch':'test'})
