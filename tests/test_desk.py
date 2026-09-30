import io
import json
import re
import sqlite3
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from server import create_app
from PIL import Image


class DeskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(self.tmp.name)
        self.app.testing = True
        self.client = self.app.test_client()
        page = self.client.get('/').get_data(as_text=True)
        self.headers = {'X-Desk-Token': re.search('name="desk-token" content="([^"]+)"', page).group(1)}

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, path, data):
        return self.client.post('/api' + path, json=data, headers=self.headers)

    def state(self):
        return self.client.get('/api/state').json

    def task(self, platform='wechat', format='article', body='这是一份测试成品，不发布到外部平台。'):
        a = self.post('/accounts', {'platform': platform, 'name': '验收账号'}).json['id']
        p = self.post('/packages', {'title': '验收内容', 'body': body}).json['id']
        t = self.post('/tasks', {'package_id': p, 'account_id': a, 'format': format})
        self.assertEqual(t.status_code, 201)
        return t.json['id'], p

    def row(self, id):
        return next(x for x in self.state()['tasks'] if x['id'] == id)

    def move(self, id, status, **extra):
        return self.post('/tasks/' + id + '/transition', {'status': status, 'revision': self.row(id)['revision'], **extra})

    def test_local_security(self):
        self.assertEqual(self.client.post('/api/accounts', json={}).status_code, 403)
        self.assertEqual(self.client.get('/api/state', headers={'Host': 'attacker.test'}).status_code, 403)
        self.assertEqual(self.client.post('/api/accounts', json={}, headers={**self.headers, 'Origin': 'https://evil.test'}).status_code, 403)

    def test_task_unique_and_publication_evidence(self):
        t, p = self.task()
        row = self.row(t)
        duplicate = self.post('/tasks', {'package_id': p, 'account_id': row['account_id'], 'format': 'article'})
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(self.move(t, 'published', url='https://mp.weixin.qq.com/s/example', note='test').status_code, 400)
        self.assertEqual(self.move(t, 'ready').status_code, 200)
        self.assertEqual(self.move(t, 'published', url='https://mp.weixin.qq.com.evil.test/s/a', note='test').status_code, 400)
        self.assertEqual(self.move(t, 'published', url='https://mp.weixin.qq.com/s/example').status_code, 400)
        self.assertEqual(self.move(t, 'published', url='https://mp.weixin.qq.com/s/example', note='测试用人工记录').status_code, 200)
        self.assertEqual(self.move(t, 'ready').status_code, 400)
        self.assertEqual(self.client.patch('/api/tasks/' + t, json={'revision': self.row(t)['revision'], 'title': '修改'}, headers=self.headers).status_code, 400)

    def test_revision_conflict_and_reschedule_after_edit(self):
        t, _ = self.task()
        future = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        self.assertEqual(self.move(t, 'scheduled', scheduled=future).status_code, 200)
        old = self.row(t)['revision']
        r = self.client.patch('/api/tasks/'+t, json={'revision': old, 'title': '已修改标题'}, headers=self.headers)
        self.assertEqual(r.status_code, 200)
        row = self.row(t)
        self.assertEqual(row['status'], 'draft')
        self.assertIsNone(row['scheduled'])
        self.assertEqual(self.post('/tasks/'+t+'/transition', {'revision':old,'status':'ready'}).status_code,409)

    def test_due_schedule_becomes_ready_never_published(self):
        t, _ = self.task()
        future = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        self.assertEqual(self.move(t,'scheduled',scheduled='2000-01-01T00:00:00Z').status_code,400)
        self.move(t, 'scheduled', scheduled=future)
        with sqlite3.connect(Path(self.tmp.name)/'desk.sqlite3') as c:
            c.execute("UPDATE tasks SET scheduled='2000-01-01T00:00:00+00:00' WHERE id=?", (t,))
        self.app.desk_tick()
        self.assertEqual(self.row(t)['status'], 'ready')
        self.assertEqual(self.row(t)['url'], '')

    def test_failure_retry_requires_duplicate_check(self):
        t, _ = self.task()
        self.move(t,'ready')
        self.assertEqual(self.move(t,'failed').status_code,400)
        self.move(t,'failed',note='上传超时，结果未知')
        self.assertEqual(self.move(t,'ready').status_code,400)
        self.assertEqual(self.move(t,'ready',checked=True).status_code,200)

    def test_media_validation_export_and_backup(self):
        t,p = self.task('rednote','gallery')
        self.assertEqual(self.move(t,'ready').status_code,400)
        image=io.BytesIO();Image.new('RGB',(20,20),'green').save(image,format='PNG');image_bytes=image.getvalue()
        r=self.client.post('/api/packages/'+p+'/assets',data={'file':(io.BytesIO(image_bytes),'01.png')},headers=self.headers)
        self.assertEqual(r.status_code,201)
        asset=r.json['id']
        r=self.client.patch('/api/tasks/'+t,json={'revision':self.row(t)['revision'],'asset_ids':[asset],'cover_id':asset},headers=self.headers)
        self.assertEqual(r.status_code,200)
        self.assertEqual(self.move(t,'ready').status_code,200)
        r=self.client.get('/api/tasks/'+t+'/bundle')
        self.assertEqual(r.status_code,200)
        with zipfile.ZipFile(io.BytesIO(r.data)) as z:
            self.assertEqual(z.read('素材/01-01.png'), image_bytes)
            self.assertEqual(json.loads(z.read('manifest.json'))['cover_id'],asset)
        backup=self.client.get('/api/backup')
        with zipfile.ZipFile(io.BytesIO(backup.data)) as z:
            self.assertIn('desk.sqlite3',z.namelist())
            self.assertIn('files/'+asset,z.namelist())
        self.assertEqual(self.row(t)['status'],'ready')

    def test_cross_package_asset_and_persistence(self):
        t,p=self.task()
        other=self.post('/packages',{'title':'其他成品'}).json['id']
        r=self.client.post('/api/packages/'+other+'/assets',data={'file':(io.BytesIO(b'png'),'x.png')},headers=self.headers)
        self.assertEqual(self.client.patch('/api/tasks/'+t,json={'revision':1,'asset_ids':[r.json['id']]},headers=self.headers).status_code,400)
        fresh=create_app(self.tmp.name).test_client()
        self.assertEqual(len(fresh.get('/api/state').json['tasks']),1)

if __name__ == '__main__':
    unittest.main()
