import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from server import create_app
from skill_center import SkillCatalog


class SkillAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        (self.source / 'references').mkdir(parents=True)
        (self.source / 'SKILL.md').write_text('---\nname: sample\nmetadata:\n  version: "1.0.0"\n---\n# Original\n')
        (self.source / 'references/rules.md').write_text('Keep original audio.\n')
        (self.source / 'reference.bin').write_bytes(b'\0\xffbinary')
        reg = self.root/'registry.json'
        reg.write_text(json.dumps({'skills':[dict(id='sample', label='Sample', path=str(self.source))]}))
        with patch('skill_center.SkillCatalog', return_value=SkillCatalog(reg)):
            self.app = create_app(self.root/'data')
        self.app.testing = True
        self.client = self.app.test_client()
        token = re.search(r'name="desk-token" content="([^"]+)"', self.client.get('/').text).group(1)
        self.headers = {'X-Desk-Token':token}
        self.base = self.client.get('/api/skills/sample').json

    def history(self):
        return self.client.get('/api/skills/sample/history').json['versions']

    def payload(self):
        return dict(expected_revision=self.base['revision'], expected_version_id=self.base['audit_head']['id'],
                    actor_type='agent', actor_name='Test Agent', reason='Protect an important condition',
                    source_ref='test-session', path='references/rules.md', content='Keep original audio and conditions.\n')

    def edit(self, body=None):
        return self.client.post('/api/skills/sample/edit', json=body or self.payload(), headers=self.headers)

    def test_baseline_idempotent_and_metadata_version(self):
        self.client.get('/api/skills')
        self.client.get('/api/skills/sample')
        self.assertEqual(len(self.history()),1)
        self.assertEqual(self.history()[0]['kind'],'baseline')
        self.assertEqual(self.base['version'],'1.0.0')
        self.assertEqual(self.history()[0]['actor']['assurance'],'unknown')

    def test_edit_diff_author_and_frozen_archive(self):
        result=self.edit(); self.assertEqual(result.status_code,201,result.json)
        h=self.history(); self.assertEqual(len(h),2)
        self.assertEqual(h[0]['actor']['name'],'Test Agent')
        self.assertEqual(h[0]['actor']['assurance'],'self-declared')
        d=self.client.get('/api/skills/sample/history/'+h[0]['id']).json
        self.assertEqual(len(d['changes']),1)
        self.assertIn('+Keep original audio and conditions.',d['changes'][0]['diff'])
        old=self.client.get('/api/skills/sample/history/'+h[1]['id']+'/download')
        with zipfile.ZipFile(io.BytesIO(old.data)) as z:
            self.assertEqual(z.read('files/references/rules.md'),b'Keep original audio.\n')
            self.assertEqual(z.read('files/reference.bin'),b'\0\xffbinary')
        self.assertTrue(self.client.get('/api/skills/sample/history-integrity').json['valid'])

    def test_stale_edits_and_auth_are_rejected(self):
        self.assertEqual(self.client.post('/api/skills/sample/edit',json=self.payload()).status_code,403)
        self.assertEqual(self.edit().status_code,201)
        self.assertEqual(self.edit().status_code,409)
        self.assertEqual(len(self.history()),2)

    def test_identity_reason_and_paths_are_required(self):
        for key,value in [('actor_name',''),('reason',''),('actor_type','admin'),('path','../escape.md')]:
            body=self.payload(); body[key]=value
            self.assertEqual(self.edit(body).status_code,400,(key,value))
        self.assertEqual(len(self.history()),1)

    def test_external_changes_and_return_to_old_content_are_distinct_events(self):
        p=self.source/'references/rules.md'; original=p.read_text(); p.write_text('External change')
        h=self.history(); self.assertEqual(h[0]['kind'],'external')
        self.assertEqual(h[0]['actor']['type'],'unknown')
        p.write_text(original); h=self.history()
        self.assertEqual(len(h),3)
        self.assertEqual(h[0]['revision'],h[2]['revision'])
        self.assertNotEqual(h[0]['id'],h[2]['id'])

    def test_external_added_deleted_and_binary_files_preserved(self):
        (self.source/'references/new.md').write_text('New')
        # These are disposable test fixtures, not user materials.
        (self.source/'references/rules.md').unlink()
        (self.source/'reference.bin').write_bytes(b'\0\xfechanged')
        h=self.history(); d=self.client.get('/api/skills/sample/history/'+h[0]['id']).json
        self.assertEqual({x['status'] for x in d['changes']},{'added','deleted','modified'})
        self.assertTrue(next(x for x in d['changes'] if x['path']=='reference.bin')['binary'])

    def test_history_survives_missing_source(self):
        (self.source/'SKILL.md').unlink()
        self.assertEqual(len(self.history()),1)
        self.assertEqual(self.client.get('/api/skills/sample').status_code,503)
        vid=self.history()[0]['id']
        self.assertEqual(self.client.get('/api/skills/sample/history/'+vid+'/download').status_code,200)

    def test_no_publication_or_content_mutations(self):
        before=self.client.get('/api/state').json
        self.edit()
        after=self.client.get('/api/state').json
        for key in ['packages','assets','tasks']:
            self.assertEqual(before[key],after[key])

    def test_database_failure_restores_file_without_false_version(self):
        with patch('skill_audit.SkillAudit.append',side_effect=RuntimeError('database fault')):
            with self.assertRaises(RuntimeError): self.edit()
        self.assertEqual((self.source/'references/rules.md').read_text(),'Keep original audio.\n')
        self.assertEqual(len(self.history()),1)

    def test_history_tables_reject_update_and_delete(self):
        with sqlite3.connect(self.root/'data/desk.sqlite3') as c:
            for sql in ['DELETE FROM skill_audit_versions','UPDATE skill_audit_versions SET revision="bad"',
                        'DELETE FROM skill_audit_blobs','UPDATE skill_audit_blobs SET content="bad"']:
                with self.assertRaises(sqlite3.IntegrityError): c.execute(sql)

    def test_cross_skill_version_access_rejected(self):
        vid=self.history()[0]['id']
        self.assertEqual(self.client.get('/api/skills/other/history/'+vid).status_code,404)


    def test_historical_evidence_is_separate_idempotent_and_anchored(self):
        body=dict(actor_type='agent',actor_name='Earlier Agent',reason='Historical review',source_ref='backup/manifest.json',expected_revision=self.base['revision'],files=[dict(path='references/rules.md',before='Old rules',after='Keep original audio.\n')])
        route='/api/skills/sample/history-evidence'
        a=self.client.post(route,json=body,headers=self.headers)
        self.assertEqual(a.status_code,201,a.json)
        b=self.client.post(route,json=body,headers=self.headers)
        self.assertEqual(a.json['evidence']['id'],b.json['evidence']['id'])
        self.assertEqual(len(self.history()),1)
        self.assertEqual(len(self.client.get('/api/skills/sample/history').json['evidence']),1)
        body['files'][0]['after']='Unverified after'
        self.assertEqual(self.client.post(route,json=body,headers=self.headers).status_code,409)
        self.assertTrue(self.client.get('/api/skills/sample/history-integrity').json['valid'])

    def test_simultaneous_edits_have_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        def submit(suffix):
            client=self.app.test_client()
            client.get('/')
            body=self.payload();body['content']+=suffix
            return client.post('/api/skills/sample/edit',json=body,headers=self.headers).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(submit,['one','two']))
        self.assertEqual(sorted(statuses),[201,409])
        self.assertEqual(len(self.history()),2)

    def test_compare_nonadjacent_and_empty_versions(self):
        self.edit();vid=self.history()[0]['id']
        result=self.client.get('/api/skills/sample/history/'+vid+'?base=empty')
        self.assertEqual(result.status_code,200)
        self.assertEqual(len(result.json['changes']),3)

    def test_large_reference_preserved_in_download(self):
        payload=b'long-text'*70000
        (self.source/'references/large.txt').write_bytes(payload)
        vid=self.history()[0]['id']
        result=self.client.get('/api/skills/sample/history/'+vid+'/download')
        with zipfile.ZipFile(io.BytesIO(result.data)) as archive:
            self.assertEqual(archive.read('files/references/large.txt'),payload)


if __name__ == '__main__':
    unittest.main()
