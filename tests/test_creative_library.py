import re
import tempfile
import unittest
from server import create_app


class CreativeLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client = create_app(self.tmp.name).test_client()
        html = self.client.get('/').get_data(as_text=True)
        token = re.search(r'name="desk-token" content="([^"]+)"', html).group(1)
        self.headers = {'X-Desk-Token': token}
        self.pid = self.client.post('/api/packages', json={'title': '独立观点', 'body': '原始内容'}, headers=self.headers).json['id']

    def test_catalog_uses_existing_assets_and_roles(self):
        catalog = self.client.get('/api/creative/catalog').json
        self.assertEqual(len(catalog['templates']), 18)
        self.assertEqual(sum(x.get('collection') == 'initial-12' for x in catalog['templates']), 12)
        self.assertGreaterEqual(len(catalog['editors']), 5)
        self.assertEqual(catalog['coordinator']['name'], '阿剪')
        for item in catalog['templates'] + catalog['covers']:
            response = self.client.get(item['preview'])
            self.assertEqual(response.status_code, 200)
            response.close()

    def test_choice_persists_without_changing_content_or_dispatch(self):
        path = f'/api/packages/{self.pid}/creative'
        before = self.client.get('/api/state').json
        saved = self.client.put(path, json={'revision': 0, 'template_id': 'T07', 'editor_id': 'E02', 'cover_id': 'COVER-A'}, headers=self.headers)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(self.client.get(path).json['editor_id'], 'E02')
        self.assertIn('editor_id', saved.json['versions'])
        after = self.client.get('/api/state').json
        for field in ['packages', 'assets', 'tasks']:
            self.assertEqual(before[field], after[field])
        stale = self.client.put(path, json={'revision': 0}, headers=self.headers)
        self.assertEqual(stale.status_code, 409)
        undone = self.client.put(path, json={'revision': 1}, headers=self.headers)
        self.assertIsNone(undone.json['template_id'])
        self.assertEqual(undone.json['revision'], 2)

    def test_invalid_choice_and_unauthorized_write_are_rejected(self):
        path = f'/api/packages/{self.pid}/creative'
        self.assertEqual(self.client.put(path, json={'revision': 0}).status_code, 403)
        for value in ['not-an-editor', ['E02']]:
            self.assertEqual(self.client.put(path, json={'revision': 0, 'editor_id': value}, headers=self.headers).status_code, 400)
        self.assertEqual(self.client.get(path).json['revision'], 0)


if __name__ == '__main__':
    unittest.main()
