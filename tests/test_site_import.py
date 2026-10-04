import hashlib
import json
import re
import tempfile
import unittest

from server import create_app


def snapshot(body='网站已批准的正文'):
    return {'schema': 'qiuyiwu.site-draft.v1',
            'source': {'site': 'qiuyiwu.com', 'slug': '2026-10-04-test', 'outlet': 'essay',
                       'source_file': '定稿.md', 'approved_at': '2026-10-04T10:00:00Z',
                       'text_sha256': hashlib.sha256(body.encode()).hexdigest(),
                       'signoff': {'决定': 'signed', '签字人': '测试'}},
            'title': '网站内容', 'body': body}


class SiteImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(self.tmp.name)
        self.app.testing = True
        self.client = self.app.test_client()
        page = self.client.get('/').get_data(as_text=True)
        self.headers = {'X-Desk-Token': re.search('name="desk-token" content="([^"]+)"', page).group(1)}

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, path, payload):
        return self.client.post(path, json=payload, headers=self.headers)

    def test_idempotence_and_new_version_preserves_channel_draft(self):
        original = self.post('/api/site-import', snapshot())
        self.assertEqual(original.status_code, 201)
        pid = original.json['package_id']
        again = self.post('/api/site-import', snapshot())
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json['package_id'], pid)
        account = self.post('/api/accounts', {'platform': 'zhihu', 'name': '测试账号'}).json['id']
        task = self.post('/api/tasks', {'package_id': pid, 'account_id': account, 'format': 'article'}).json['id']
        changed = self.post('/api/site-import', snapshot('网站已批准的新版正文'))
        self.assertEqual(changed.status_code, 201)
        self.assertEqual(changed.json['previous_package_id'], pid)
        state = self.client.get('/api/state').json
        self.assertEqual(len(state['packages']), 2)
        self.assertEqual(next(x for x in state['tasks'] if x['id'] == task)['body'], '网站已批准的正文')

    def test_modified_body_and_unapproved_snapshot_rejected(self):
        forged = snapshot()
        forged['body'] = '内容被改过'
        self.assertEqual(self.post('/api/site-import', forged).status_code, 400)
        hold = snapshot()
        hold['source']['signoff']['决定'] = 'hold'
        self.assertEqual(self.post('/api/site-import', hold).status_code, 400)
        self.assertEqual(len(self.client.get('/api/state').json['packages']), 0)


if __name__ == '__main__':
    unittest.main()
