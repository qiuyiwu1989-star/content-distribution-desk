import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from werkzeug.exceptions import BadRequest, NotFound, Conflict
from server import create_app
from channel_observations import install


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(self.root)
        self.app.testing = True
        def fail(message, code=400):
            raise {400: BadRequest, 404: NotFound, 409: Conflict}.get(code, BadRequest)(message)
        def get(c, table, rid):
            row = c.execute('SELECT * FROM ' + table + ' WHERE id=?', (rid,)).fetchone()
            if not row:
                fail('不存在', 404)
            return dict(row)
        def text(value, maxlen=50000, required=False):
            if not isinstance(value, str) or len(value) > maxlen:
                fail('文字格式错误')
            value = value.strip()
            if required and not value:
                fail('必填')
            return value
        install(self.app, self.root, self.db, get, fail, text, lambda: datetime.now(timezone.utc).isoformat())
        self.client = self.app.test_client()
        token = re.search('name="desk-token" content="([^"]+)"', self.client.get('/').text).group(1)
        self.headers = {'X-Desk-Token': token}
        self.aid = self.client.post('/api/accounts', json={'platform': 'channels', 'name': '目标账号'}, headers=self.headers).json['id']
        self.pid = self.client.post('/api/packages', json={'title': '内容一', 'body': '原文'}, headers=self.headers).json['id']
        self.tid = self.client.post('/api/tasks', json={'package_id': self.pid, 'account_id': self.aid, 'format': 'video'}, headers=self.headers).json['id']

    def test_extension_origin_only_allowed_on_observation_route(self):
        headers={**self.headers,'Origin':'chrome-extension://'+'a'*32}
        payload={'task_id':self.tid,'revision':1,'event_id':'origin-test','event_kind':'submit_clicked','page_url':'https://channels.weixin.qq.com/platform/post/create','source':'session_observer'}
        self.assertEqual(self.client.post('/api/channel-observations',json=payload,headers=headers).status_code,201)
        self.assertEqual(self.client.post('/api/accounts',json={'platform':'channels','name':'blocked'},headers=headers).status_code,403)
        self.assertEqual(self.client.post('/api/channel-observations',json=payload,headers={'Origin':headers['Origin']}).status_code,403)
        self.assertEqual(self.client.post('/api/channel-observations',json=payload,headers={**self.headers,'Origin':'https://example.com'}).status_code,403)

    def tearDown(self):
        self.tmp.cleanup()

    def db(self):
        c = sqlite3.connect(self.root / 'desk.sqlite3')
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        return c

    def post(self, **extra):
        data = {'task_id': self.tid, 'revision': 1, 'event_id': 'unique-event', 'event_kind': 'submit_clicked', 'page_url': 'https://channels.weixin.qq.com/platform/post/create', 'source': 'session_observer', **extra}
        return self.client.post('/api/channel-observations', json=data, headers=self.headers)

    def test_click_is_observation_only_and_bound_to_original_task_snapshot(self):
        response = self.post(scheduled_text='2026年10月9日 10:30')
        self.assertEqual(response.status_code, 201)
        row = response.json['observation']
        self.assertEqual(row['identity_match'], 'unverified')
        self.assertEqual(row['target_account_name'], '目标账号')
        self.assertEqual(row['task_snapshot']['title'], '内容一')
        with self.db() as c:
            task = dict(c.execute('SELECT * FROM tasks WHERE id=?', (self.tid,)).fetchone())
            self.assertEqual(task['status'], 'draft')
            self.assertIsNone(task['scheduled'])
            self.assertEqual(task['revision'], 1)
            self.assertEqual(c.execute('SELECT count(*) FROM runs').fetchone()[0], 0)
            c.execute('UPDATE tasks SET title=? WHERE id=?', ('后来改名', self.tid))
        persisted = self.client.get('/api/channel-observations?task_id=' + self.tid).json['observations'][0]
        self.assertEqual(persisted['task_snapshot']['title'], '内容一')

    def test_identity_uses_server_binding_and_missing_account_never_assumed(self):
        with self.db() as c:
            c.execute("INSERT INTO connections(account_id,identity,display_name) VALUES(?,?,?)", (self.aid, 'id-123', '页面作者'))
        self.assertEqual(self.post(observed_account='页面作者').json['observation']['identity_match'], 'matched')
        self.assertEqual(self.post(event_id='different', observed_account='别的作者').json['observation']['identity_match'], 'mismatch')
        self.assertEqual(self.post(event_id='blank').json['observation']['identity_match'], 'unverified')

    def test_idempotency_conflict_and_stale_revision(self):
        self.assertEqual(self.post().status_code, 201)
        self.assertTrue(self.post().json['duplicate'])
        self.assertEqual(self.post(result_text='different payload').status_code, 409)
        with self.db() as c:
            c.execute('UPDATE tasks SET revision=2 WHERE id=?', (self.tid,))
        self.assertEqual(self.post(event_id='stale').status_code, 409)
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.post(event_id='fresh', revision=2).status_code, 201)

    def test_url_validation_payload_limits_and_no_query_session_storage(self):
        for url in ['https://evil.test/platform/post/create', 'https://channels.weixin.qq.com.evil.test/platform/post/create', 'http://channels.weixin.qq.com/platform/post/create', 'https://channels.weixin.qq.com/not-approved', 'https://user:secret@channels.weixin.qq.com/platform/post/create']:
            self.assertEqual(self.post(page_url=url).status_code, 400)
        response = self.post(page_url='https://channels.weixin.qq.com/platform/post/create?token=secret#fragment')
        self.assertEqual(response.status_code, 201)
        self.assertNotIn('secret', str(response.json))
        self.assertEqual(self.post(event_id='big', result_text='x' * 4001).status_code, 400)
        self.assertEqual(self.post(event_id='unknown', password='secret').status_code, 400)
        self.assertEqual(self.post(event_kind='published').status_code, 400)
        self.assertEqual(self.post(event_kind='manual_confirmation', result_text='confirmed').status_code, 400)
        self.assertEqual(self.post(event_id='manual', event_kind='manual_confirmation', source='manual', result_text='人工查看作品列表').status_code, 201)

    def test_manual_publication_progress_is_shared_reversible_and_revision_scoped(self):
        endpoint = '/api/publication-progress'
        payload = {'task_id': self.tid, 'revision': 1, 'status': 'published'}
        self.assertEqual(self.client.post(endpoint, json=payload).status_code, 403)
        self.assertEqual(self.client.post(endpoint, json=payload, headers={**self.headers, 'Origin': 'chrome-extension://'+'a'*32}).status_code, 403)
        self.assertEqual(self.client.post(endpoint, json=payload, headers=self.headers).status_code, 201)
        task = next(t for t in self.client.get('/api/state').json['tasks'] if t['id'] == self.tid)
        self.assertEqual(task['status'], 'draft')
        self.assertEqual(task['publication_progress']['status'], 'published')
        snapshot_task=next(t for t in self.client.get('/api/library').json['snapshot']['tasks'] if t['id']==self.tid)
        self.assertEqual(snapshot_task['publication_progress']['status'], 'published')
        self.assertEqual(task['publication_progress']['account_id'], self.aid)
        # Neither a success toast nor arbitrary manual prose overrides explicit confirmation.
        self.post(event_id='toast', event_kind='result_observed', result_text='发表成功')
        self.post(event_id='prose', event_kind='manual_confirmation', source='manual', result_text='可能已发布')
        self.assertEqual(self.client.get(endpoint).json['progress'][self.tid]['status'], 'published')
        self.assertEqual(self.client.post(endpoint, json={**payload, 'status': 'unconfirmed'}, headers=self.headers).status_code, 201)
        result = self.client.get(endpoint).json
        self.assertEqual(result['progress'][self.tid]['status'], 'unconfirmed')
        self.assertEqual(len(result['history'][self.tid]), 2)
        with self.db() as c:
            c.execute('UPDATE tasks SET revision=2 WHERE id=?', (self.tid,))
        self.assertEqual(self.client.get(endpoint).json['progress'][self.tid]['revision'], 1)
        self.assertEqual(len(self.client.get(endpoint).json['history'][self.tid]), 2)
        self.assertEqual(self.client.post(endpoint, json=payload, headers=self.headers).status_code, 409)
        self.assertEqual(self.client.post(endpoint, json={**payload, 'revision': 2}, headers=self.headers).status_code, 201)
        self.assertEqual(self.client.get(endpoint).json['progress'][self.tid]['revision'], 2)

    def test_non_channels_task_rejected_and_existing_guard_applies(self):
        with self.db() as c:
            c.execute("UPDATE accounts SET platform='rednote' WHERE id=?", (self.aid,))
        self.assertEqual(self.post().status_code, 400)
        self.assertEqual(self.client.post('/api/channel-observations', json={}).status_code, 403)


if __name__ == '__main__':
    unittest.main()
