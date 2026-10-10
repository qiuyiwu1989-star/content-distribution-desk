import re
import tempfile
import unittest
from server import create_app


class CoverTemplateManagementTests(unittest.TestCase):
    def test_remove_persist_restore_and_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(folder)
            c = app.test_client()
            token = re.search(r'name="desk-token" content="([^"]+)"', c.get('/').text).group(1)
            h = {'X-Desk-Token': token}
            tid = c.get('/api/cover-design/catalog').json['templates'][0]['id']
            path = '/api/cover-design/templates/' + tid
            self.assertEqual(c.delete(path).status_code, 403)
            self.assertEqual(c.delete(path, headers=h).status_code, 200)
            self.assertNotIn(tid, [a['id'] for a in c.get('/api/cover-design/catalog').json['templates']])
            self.assertNotIn(tid, [a['id'] for a in c.get('/api/creative/catalog').json['covers']])
            fresh = create_app(folder).test_client()
            self.assertIn(tid, [a['id'] for a in fresh.get('/api/cover-design/catalog?removed=1').json['templates']])
            self.assertEqual(c.post(path+'/restore', json={}, headers=h).status_code, 200)
            self.assertIn(tid, [a['id'] for a in c.get('/api/cover-design/catalog').json['templates']])
            self.assertEqual(c.delete('/api/cover-design/templates/missing', headers=h).status_code, 404)
