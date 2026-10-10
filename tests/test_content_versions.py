import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from werkzeug.exceptions import BadRequest, Conflict, NotFound
from server import create_app, now
from content_versions import install


class ContentVersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.app = create_app(self.data)
        def db():
            c = sqlite3.connect(self.data/'desk.sqlite3')
            c.row_factory = sqlite3.Row
            c.execute('PRAGMA foreign_keys=ON')
            return c
        self.db = db
        def fail(message, code=400):
            raise {400:BadRequest,409:Conflict,404:NotFound}[code](message)
        def get(c, table, key):
            row = c.execute('SELECT * FROM '+table+' WHERE id=?',(key,)).fetchone()
            if not row: fail('missing',404)
            return dict(row)
        if not hasattr(self.app,'desk_content_version'):
            install(self.app,self.data,db,get,fail,lambda x,*args:x,now)
        self.client = self.app.test_client()
        self.headers = {'X-Desk-Token':re.search('name="desk-token" content="([^"]+)"',self.client.get('/').text).group(1)}
        self.pid = self.client.post('/api/packages',json={'title':'标题','body':'原文'},headers=self.headers).json['id']
    def tearDown(self):
        self.tmp.cleanup()
    def versions(self):
        r=self.client.get('/api/packages/'+self.pid+'/versions')
        self.assertEqual(r.status_code,200)
        return r.json
    def test_capture_change_and_revert_are_immutable(self):
        first=self.versions()['current']
        self.assertEqual(self.versions()['current']['id'],first['id'])
        with self.db() as c:c.execute('UPDATE packages SET body=? WHERE id=?',('新版',self.pid))
        second=self.versions()['current']
        self.assertEqual(second['number'],2)
        old=self.client.get('/api/packages/'+self.pid+'/versions/'+first['id']).json
        self.assertEqual(old['snapshot']['package']['body'],'原文')
        with self.db() as c:c.execute('UPDATE packages SET body=? WHERE id=?',('原文',self.pid))
        third=self.versions()['current']
        self.assertEqual(third['number'],3)
        self.assertEqual(third['fingerprint'],first['fingerprint'])
        self.assertNotEqual(third['id'],first['id'])
    def test_publication_note_does_not_create_content_version(self):
        first=self.versions()['current']
        aid=self.client.post('/api/accounts',json={'name':'账号','platform':'channels'},headers=self.headers).json['id']
        tid=self.client.post('/api/tasks',json={'package_id':self.pid,'account_id':aid,'format':'video'},headers=self.headers).json['id']
        self.assertEqual(self.versions()['current']['id'],first['id'])
        with self.db() as c:c.execute('UPDATE tasks SET note=?,status=? WHERE id=?',('已登记','draft',tid))
        self.assertEqual(self.versions()['current']['id'],first['id'])
    def test_channel_binding_checks_revision_and_retains_snapshot(self):
        aid=self.client.post('/api/accounts',json={'name':'账号','platform':'channels'},headers=self.headers).json['id']
        tid=self.client.post('/api/tasks',json={'package_id':self.pid,'account_id':aid,'format':'video'},headers=self.headers).json['id']
        v=self.versions()['current']
        with self.db() as c:t=dict(c.execute('SELECT * FROM tasks WHERE id=?',(tid,)).fetchone())
        route='/api/packages/'+self.pid+'/versions/channel-link'
        self.assertEqual(self.client.post(route,json={'task_id':tid,'revision':t['revision'],'fingerprint':'stale'},headers=self.headers).status_code,409)
        result=self.client.post(route,json={'task_id':tid,'revision':t['revision'],'fingerprint':v['fingerprint']},headers=self.headers)
        self.assertEqual(result.status_code,201)
        again=self.client.post(route,json={'task_id':tid,'revision':t['revision'],'fingerprint':v['fingerprint']},headers=self.headers)
        self.assertEqual(again.json['id'],result.json['id'])
        with self.db() as c:c.execute('UPDATE tasks SET title=? WHERE id=?',('后来的渠道标题',tid))
        detail=self.client.get('/api/packages/'+self.pid+'/versions/'+v['id']).json
        self.assertEqual(detail['links'][0]['snapshot']['title'],t['title'])
    def test_missing_package(self):
        self.assertEqual(self.client.get('/api/packages/missing/versions').status_code,404)
