import contextlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException
import content_versions
import production_tasks

class ProductionTaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        app = Flask(__name__)
        @contextlib.contextmanager
        def db():
            c = sqlite3.connect(str(data/'test.sqlite'))
            c.row_factory = sqlite3.Row
            try:
                yield c
                c.commit()
            finally:
                c.close()
        def fail(message, code=400):
            error = HTTPException(message);error.code=code;raise error
        @app.errorhandler(HTTPException)
        def error(e):return jsonify(error=e.description),e.code
        def get(c, table, rid):
            r=c.execute('SELECT * FROM '+table+' WHERE id=?',(rid,)).fetchone()
            if not r:fail('missing',404)
            return r
        def text(v, limit=5000, required=False):
            if not isinstance(v,str) or len(v)>limit or (required and not v.strip()):fail('bad text')
            return v.strip()
        with db() as c:
            c.executescript('CREATE TABLE packages(id TEXT PRIMARY KEY,title TEXT,body TEXT,notes TEXT); CREATE TABLE assets(id TEXT PRIMARY KEY,package_id TEXT,name TEXT,mime TEXT,size INTEGER,kind TEXT); CREATE TABLE package_meta(package_id TEXT,value TEXT);')
            c.execute('INSERT INTO packages VALUES(?,?,?,?)',('p','内容','正文',''))
        content_versions.install(app,data,db,get,fail,text,lambda:'2026-10-10T12:00:00Z')
        production_tasks.install(app,db,get,fail,text,lambda:'2026-10-10T12:00:00Z')
        self.client=app.test_client();self.db=db
    def tearDown(self):self.tmp.cleanup()
    def create(self, **extra):
        v=self.client.get('/api/packages/p/production-tasks').json['input_version']
        d=dict(idempotency_key='one',input_version_id=v['id'],input_fingerprint=v['fingerprint'],capability_kind='tool',capability_id='check-plan',capability_version='1',instruction='检查来源')
        d.update(extra)
        return self.client.post('/api/packages/p/production-tasks',json=d)
    def test_idempotent_and_conflicting_retry(self):
        a=self.create();self.assertEqual(a.status_code,201)
        b=self.create();self.assertEqual(b.status_code,200);self.assertEqual(a.json['id'],b.json['id'])
        self.assertEqual(self.create(instruction='其他指令').status_code,409)
        self.assertEqual(self.create(idempotency_key='two',input_version_id='fake').status_code,409)
    def test_worker_revision_and_terminal_protection(self):
        tid=self.create().json['id'];url='/api/production-tasks/'+tid+'/transition'
        r=self.client.post(url,json={'revision':1,'status':'running','worker':'codex'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(self.client.post(url,json={'revision':1,'status':'completed','worker':'codex','summary':'完成'}).status_code,409)
        self.assertEqual(self.client.post(url,json={'revision':2,'status':'completed','worker':'other','summary':'完成'}).status_code,409)
        r=self.client.post(url,json={'revision':2,'status':'completed','worker':'codex','summary':'完成','artifacts':[{'name':'结果','reference':'/local/result.json'}]})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json['revision'],3)
        self.assertEqual(self.client.post(url,json={'revision':3,'status':'running','worker':'codex'}).status_code,409)
        self.assertEqual(self.client.get('/api/production-tasks/'+tid).json['events'][-1]['status'],'completed')
    def test_stale_start_blocked_historical_result_retained(self):
        tid=self.create().json['id'];url='/api/production-tasks/'+tid+'/transition'
        with self.db() as c:c.execute("UPDATE packages SET body='新正文' WHERE id='p'")
        self.assertEqual(self.client.post(url,json={'revision':1,'status':'running','worker':'codex'}).status_code,409)
        self.assertTrue(self.client.get('/api/production-tasks/'+tid).json['input_stale'])
        self.assertEqual(self.client.post(url,json={'revision':1,'status':'canceled'}).status_code,200)
        tid=self.create(idempotency_key='two').json['id'];url='/api/production-tasks/'+tid+'/transition'
        self.client.post(url,json={'revision':1,'status':'running','worker':'codex'})
        with self.db() as c:c.execute("UPDATE packages SET body='第三版' WHERE id='p'")
        r=self.client.post(url,json={'revision':2,'status':'completed','worker':'codex','summary':'历史版本结果'})
        self.assertEqual(r.status_code,200);self.assertTrue(r.json['input_stale'])
        with self.db() as c:self.assertEqual(c.execute("SELECT body FROM packages WHERE id='p'").fetchone()[0],'第三版')
