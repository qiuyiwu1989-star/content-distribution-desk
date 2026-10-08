"""Atomic channel edits and reconciliation, isolated from platform adapters."""
import json
import sqlite3
from pathlib import Path
from test_desk import DeskTests


class UXIntegrationTests(DeskTests):
    def test_editor_saves_options_and_content_in_one_revision(self):
        tid, _ = self.task()
        r = self.client.patch('/api/tasks/'+tid, json={'revision':1,'title':'新渠道标题','options':{'mode':'manual','collection':'一个合集'}},headers=self.headers)
        self.assertEqual(r.status_code,200)
        row=self.row(tid)
        self.assertEqual((row['title'],row['options']['collection'],row['revision']),('新渠道标题','一个合集',2))
        r = self.client.patch('/api/tasks/'+tid,json={'revision':2,'title':'不能保存','options':{'mode':'unsupported'}},headers=self.headers)
        self.assertEqual(r.status_code,400)
        self.assertEqual(self.row(tid)['title'],'新渠道标题')
        r = self.client.patch('/api/tasks/'+tid,json={'revision':2,'title':'','options':{'mode':'manual','collection':'不能提交'}},headers=self.headers)
        self.assertEqual(r.status_code,400)
        self.assertEqual(self.row(tid)['options']['collection'],'一个合集')

    def test_historical_unknown_can_be_reconciled_without_rewriting_current_task(self):
        tid,_=self.task()
        db=Path(self.tmp.name)/'desk.sqlite3'
        with sqlite3.connect(db) as c:
            c.execute("INSERT INTO runs(id,task_id,fingerprint,snapshot,status,not_before,created,updated) VALUES(?,?,?,?,?,?,?,?)",('old',tid,'old-fp','{}','unknown','2026','2026','2026'))
        r=self.post('/runs/old/reconcile',{'outcome':'not_found','note':'测试：已检查平台'})
        self.assertEqual(r.status_code,400)
        r=self.post('/runs/old/reconcile',{'outcome':'not_found','note':'测试：已检查平台','checked':True})
        self.assertEqual(r.status_code,200)
        self.assertEqual(self.row(tid)['status'],'draft')
        self.assertEqual(self.state()['runs'][0]['status'],'resolved')
        self.assertEqual(self.post('/runs/old/reconcile',{'outcome':'not_found','note':'重复','checked':True}).status_code,409)
