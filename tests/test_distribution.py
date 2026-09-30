"""Local workflow acceptance. Adapter mocks never contact publishing platforms."""
import io
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
import test_desk
import unittest
from server import create_app
import adapters

class DistributionTests(unittest.TestCase):
    setUp=test_desk.DeskTests.setUp
    tearDown=test_desk.DeskTests.tearDown
    post=test_desk.DeskTests.post
    state=test_desk.DeskTests.state
    task=test_desk.DeskTests.task
    row=test_desk.DeskTests.row
    move=test_desk.DeskTests.move
    def options(self,t,mode='draft',**kw):
        return self.client.put('/api/tasks/'+t+'/options',json={'revision':self.row(t)['revision'],'mode':mode,**kw},headers=self.headers)
    def bind_fake(self,t):
        aid=self.row(t)['account_id']
        self.client.patch('/api/accounts/'+aid+'/connection',json={'adapter':'wechatsync'},headers=self.headers)
        with patch('adapters.check_account',return_value={'identity':'qa-identity','display_name':'测试身份','cookie_digest':''}):
            check=self.post('/accounts/'+aid+'/check',{}).json
        self.assertEqual(self.post('/accounts/'+aid+'/bind',{'check_id':check['check_id'],'confirmed':True}).status_code,200)
        self.app.desk_bridge.status=lambda:{'connected':True,'started':True,'error':None}
        self.assertEqual(self.options(t).status_code,200)
        return aid
    def dispatch(self,t,**kw):
        r=self.client.get('/api/tasks/'+t+'/preflight').json
        return self.post('/tasks/'+t+'/dispatch',{'fingerprint':r['fingerprint'],'revision':r['revision'],'confirmed':True,**kw})
    def test_batch_atomic_and_duplicate(self):
        t,p=self.task();a=self.row(t)['account_id']
        r=self.post('/packages/'+p+'/distribute',{'targets':[{'account_id':a,'format':'gallery'},{'account_id':a,'format':'video'}]})
        self.assertEqual(r.status_code,400);self.assertEqual(len(self.state()['tasks']),1)
        r=self.post('/packages/'+p+'/distribute',{'targets':[{'account_id':a,'format':'article'},{'account_id':a,'format':'gallery'}]})
        self.assertEqual(len(r.json['created']),1);self.assertEqual(r.json['skipped'],[t])
    def test_import_preserves_channel_version(self):
        t,p=self.task();old=self.row(t)['body']
        r=self.client.post('/api/packages/'+p+'/assets',data={'file':(io.BytesIO('# 导入成品'.encode()),'成品.md')},headers=self.headers)
        self.assertEqual(self.post('/packages/'+p+'/import-text',{'asset_id':r.json['id']}).status_code,400)
        self.assertEqual(self.post('/packages/'+p+'/import-text',{'asset_id':r.json['id'],'replace':True}).status_code,200)
        self.assertEqual(self.state()['packages'][0]['body'],'# 导入成品');self.assertEqual(self.row(t)['body'],old)
    def test_binding_invalidated_by_config_change(self):
        t,_=self.task();aid=self.row(t)['account_id']
        self.client.patch('/api/accounts/'+aid+'/connection',json={'adapter':'wechatsync'},headers=self.headers)
        with patch('adapters.check_account',return_value={'identity':'old','display_name':'old','cookie_digest':''}):check=self.post('/accounts/'+aid+'/check',{}).json
        self.client.patch('/api/accounts/'+aid+'/connection',json={'adapter':'manual'},headers=self.headers)
        self.assertEqual(self.post('/accounts/'+aid+'/bind',{'check_id':check['check_id'],'confirmed':True}).status_code,400)
    def test_unbound_and_stale_approval_blocked(self):
        t,_=self.task();self.options(t)
        self.assertEqual(self.dispatch(t).status_code,400)
        self.bind_fake(t);r=self.client.get('/api/tasks/'+t+'/preflight').json
        self.client.patch('/api/tasks/'+t,json={'revision':self.row(t)['revision'],'title':'新标题'},headers=self.headers)
        self.assertEqual(self.post('/tasks/'+t+'/dispatch',{'revision':r['revision'],'fingerprint':r['fingerprint'],'confirmed':True}).status_code,409)
    def test_queue_execute_and_never_auto_publish(self):
        t,_=self.task();aid=self.bind_fake(t)
        self.assertEqual(self.dispatch(t).status_code,202)
        self.assertEqual(self.dispatch(t).status_code,409)
        self.assertEqual(self.client.patch('/api/accounts/'+aid+'/connection',json={'adapter':'manual'},headers=self.headers).status_code,409)
        with patch('adapters.execute',return_value={'status':'delivered','message':'模拟草稿回执'}) as execute:
            self.app.desk_process_one();self.app.desk_process_one();self.assertEqual(execute.call_count,1)
            self.assertEqual(execute.call_args.args[0]['task']['body'],self.row(t)['body'])
        self.assertEqual(self.row(t)['status'],'delivered');self.assertEqual(self.row(t)['url'],'')
    def test_cancel_reapprove_and_edit_invalidate(self):
        t,_=self.task();self.bind_fake(t);self.dispatch(t)
        self.assertEqual(self.move(t,'draft').status_code,200)
        self.assertEqual(self.dispatch(t).status_code,202)
        self.client.patch('/api/tasks/'+t,json={'revision':self.row(t)['revision'],'body':'修改后的渠道版本'},headers=self.headers)
        with patch('adapters.execute') as execute:self.app.desk_process_one();execute.assert_not_called()
        self.assertEqual(self.row(t)['status'],'draft')
    def test_unknown_requires_checked_retry(self):
        t,_=self.task();self.bind_fake(t);r=self.dispatch(t);rid=r.json['run_id']
        with patch('adapters.execute',side_effect=TimeoutError()):self.app.desk_process_one()
        self.assertEqual(self.row(t)['status'],'unknown')
        self.assertEqual(self.post('/runs/'+rid+'/retry',{'note':'未核对'}).status_code,400)
        self.assertEqual(self.post('/runs/'+rid+'/retry',{'note':'测试：核对无重复','checked':True}).status_code,200)
        self.assertEqual(self.state()['runs'][0]['attempt'],2)
    def test_restart_marks_interrupted_unknown(self):
        t,_=self.task();self.bind_fake(t);r=self.dispatch(t)
        with sqlite3.connect(Path(self.tmp.name)/'desk.sqlite3') as c:c.execute("UPDATE runs SET status='running' WHERE id=?",(r.json['run_id'],))
        fresh=create_app(self.tmp.name).test_client().get('/api/state').json
        self.assertEqual(fresh['tasks'][0]['status'],'unknown');self.assertEqual(fresh['runs'][0]['status'],'unknown')
    def test_missing_category_and_corrupt_image_rejected(self):
        t,p=self.task('bilibili','video')
        r=self.client.get('/api/tasks/'+t+'/preflight').json
        self.assertTrue(any('分区' in x for x in r['errors']))
        t,p=self.task('rednote','gallery');r=self.client.post('/api/packages/'+p+'/assets',data={'file':(io.BytesIO(b'bad'),'bad.png')},headers=self.headers)
        self.client.patch('/api/tasks/'+t,json={'revision':1,'asset_ids':[r.json['id']]},headers=self.headers)
        r=self.client.get('/api/tasks/'+t+'/preflight').json
        self.assertTrue(any('无法解析' in x for x in r['errors']))
    def test_publish_mode_requires_explicit_confirmation(self):
        # Real image input, mock only login and runtime; no external upload.
        from PIL import Image
        t,p=self.task('rednote','gallery');b=io.BytesIO();Image.new('RGB',(30,40)).save(b,format='PNG')
        asset=self.client.post('/api/packages/'+p+'/assets',data={'file':(io.BytesIO(b.getvalue()),'image.png')},headers=self.headers).json['id']
        self.client.patch('/api/tasks/'+t,json={'revision':1,'asset_ids':[asset]},headers=self.headers)
        aid=self.row(t)['account_id'];self.client.patch('/api/accounts/'+aid+'/connection',json={'adapter':'sau','reference':'qa'},headers=self.headers)
        with patch('adapters.check_account',return_value={'identity':'qa','display_name':'测试','cookie_digest':'fake'}):check=self.post('/accounts/'+aid+'/check',{}).json
        self.post('/accounts/'+aid+'/bind',{'confirmed':True,'check_id':check['check_id']});self.options(t,'publish')
        with patch('adapters.runtime_status',return_value={'sau_installed':True}):
            self.assertEqual(self.dispatch(t).status_code,400)
            self.assertEqual(self.dispatch(t,publish_confirmed=True).status_code,202)
    def test_due_automatic_task_not_converted_to_manual(self):
        t,_=self.task();self.bind_fake(t)
        self.dispatch(t,scheduled=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
        with sqlite3.connect(Path(self.tmp.name)/'desk.sqlite3') as c:c.execute("UPDATE tasks SET scheduled='2000-01-01T00:00:00+00:00'")
        self.app.desk_tick();self.assertEqual(self.row(t)['status'],'scheduled')
        with patch('adapters.execute') as execute:self.app.desk_process_one();execute.assert_not_called()

    def test_reapprove_blocked_retains_run_and_drops_foreign_receipt(self):
        t,_=self.task();self.bind_fake(t);rid=self.dispatch(t).json['run_id']
        with patch('adapters.execute',return_value={'status':'blocked','message':'测试：未提交'}):self.app.desk_process_one()
        self.assertEqual(self.dispatch(t).json['run_id'],rid)
        self.assertEqual(self.state()['runs'][0]['attempt'],2)
        with patch('adapters.execute',return_value={'status':'delivered','message':'模拟草稿','receipt_url':'https://evil.test/draft'}):self.app.desk_process_one()
        self.assertEqual(self.state()['runs'][0]['receipt_url'],'')
