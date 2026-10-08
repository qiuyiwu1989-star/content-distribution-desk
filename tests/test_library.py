import io
import json
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import library
from pathlib import Path

from server import create_app
from library import migrate


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(self.root)
        self.app.testing = True
        self.client = self.app.test_client()
        token = re.search('name="desk-token" content="([^"]+)"', self.client.get('/').text).group(1)
        self.headers = {'X-Desk-Token': token}
        self.pid = self.post('/api/packages', {'title': '同名内容', 'body': '原文'}).json['id']

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, path, payload):
        return self.client.post(path, json=payload, headers=self.headers)

    def meta(self, pid=None):
        return self.client.get('/api/library').json['packages'][pid or self.pid]

    def review(self, status='approved', fingerprint=None):
        return self.client.put('/api/packages/' + self.pid + '/review', json={'status': status, 'note': '人工看过', 'fingerprint': fingerprint or self.meta()['fingerprint']}, headers=self.headers)

    def patch(self, pid=None, **values):
        return self.client.patch('/api/packages/' + (pid or self.pid) + '/library', json=values, headers=self.headers)

    def db(self):
        c = sqlite3.connect(self.root / 'desk.sqlite3')
        c.row_factory = sqlite3.Row
        return c

    def test_review_stales_after_content_change_and_retains_history(self):
        fp = self.meta()['fingerprint']
        self.assertEqual(self.review().status_code, 200)
        with self.db() as c:
            c.execute('UPDATE packages SET body=? WHERE id=?', ('修改后的原文', self.pid))
        meta = self.meta()
        self.assertEqual(meta['review']['status'], 'pending')
        self.assertTrue(meta['review']['stale'])
        self.assertEqual(self.review(fingerprint=fp).status_code, 409)
        self.assertEqual(self.review('changes_requested').status_code, 200)
        history = self.client.get('/api/packages/' + self.pid + '/reviews').json['reviews']
        self.assertEqual([r['status'] for r in history], ['changes_requested', 'approved'])

    def test_editorial_options_change_but_execution_state_does_not(self):
        aid = self.post('/api/accounts', {'platform': 'wechat', 'name': '测试'}).json['id']
        tid = self.post('/api/tasks', {'package_id': self.pid, 'account_id': aid, 'format': 'article'}).json['id']
        fp = self.meta()['fingerprint']
        self.review()
        with self.db() as c:
            c.execute("UPDATE tasks SET status='published',updated='later',revision=revision+1,url='https://mp.weixin.qq.com/a' WHERE id=?", (tid,))
            c.execute('INSERT OR REPLACE INTO task_options VALUES(?,?)', (tid, json.dumps({'mode': 'publish'})))
            c.execute('UPDATE accounts SET name=? WHERE id=?', ('重命名账号', aid))
        self.assertEqual(self.meta()['fingerprint'], fp)
        with self.db() as c:
            c.execute('UPDATE task_options SET value=? WHERE task_id=?', (json.dumps({'collection': '新合集'}), tid))
        self.assertTrue(self.meta()['review']['stale'])
        with self.db() as c:
            self.assertEqual(c.execute('SELECT status FROM tasks WHERE id=?', (tid,)).fetchone()[0], 'published')

    def test_file_replacement_and_selection_invalidate_review(self):
        upload = self.client.post('/api/packages/' + self.pid + '/assets', data={'file': (io.BytesIO(b'one'), 'a.mp4')}, headers=self.headers)
        asset = upload.json['id']
        self.review()
        (self.root / 'files' / asset).write_bytes(b'two')
        self.assertTrue(self.meta()['review']['stale'])
        self.review()
        (self.root / 'files' / asset).unlink()
        self.assertTrue(self.meta()['review']['stale'])

    def test_explicit_version_relation_archive_restore_and_validation(self):
        second = self.post('/api/packages', {'title': '同名内容', 'body': '第二条'}).json['id']
        self.assertIsNone(self.meta(second)['supersedes_id'])
        self.assertEqual(self.patch(second, supersedes_id=self.pid).status_code, 200)
        self.assertEqual(self.meta()['superseded_by'], second)
        self.assertEqual(self.patch(supersedes_id=second).status_code, 400)
        self.assertEqual(self.patch(supersedes_id=self.pid).status_code, 400)
        self.assertEqual(self.patch(archived='false').status_code, 400)
        self.assertEqual(self.patch(sequence=True).status_code, 400)
        self.assertEqual(self.patch(batch_id='missing').status_code, 400)
        self.assertTrue(self.patch(archived=True).json['archived'])
        self.assertFalse(self.patch(archived=False).json['archived'])
        self.assertEqual(self.patch(second, supersedes_id=None).status_code, 200)
        self.assertIsNone(self.meta()['superseded_by'])

    def test_migration_id_only_import_backup_and_idempotency(self):
        # Recreate only the new schema in an isolated test database.
        with self.db() as c:
            for table in ['library_review_snapshots', 'library_reviews', 'library_packages', 'library_batches', 'library_migrations']:
                c.execute('DROP TABLE ' + table)
        seed = self.root / 'seed.json'
        seed.write_text(json.dumps({'batches': [{'id': 'b', 'name': '批次'}], 'packages': {self.pid: {'batch_id': 'b', 'sequence': 2}, 'absent': {'batch_id': 'b', 'sequence': 2}}}))
        migrate(self.db, self.root, seed, lambda: 'now')
        self.assertEqual(self.meta()['sequence'], 2)
        self.assertEqual(self.patch(sequence=8).status_code, 200)
        backups = list((self.root / 'migration-backups').glob('*.sqlite3'))
        migrate(self.db, self.root, seed, lambda: 'later')
        self.assertEqual(self.meta()['sequence'], 8)
        self.assertEqual(len(backups), len(list((self.root / 'migration-backups').glob('*.sqlite3'))))
        with self.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM library_packages').fetchone()[0], 1)
        latest = max((p for p in backups if 'v1-' in p.name), key=lambda p: p.stat().st_mtime_ns)
        with sqlite3.connect(latest) as c:
            self.assertEqual(c.execute('SELECT title FROM packages WHERE id=?', (self.pid,)).fetchone()[0], '同名内容')
            self.assertIsNone(c.execute("SELECT 1 FROM sqlite_master WHERE name='library_reviews'").fetchone())

    def test_snapshot_content_and_fingerprint_remain_atomic_during_concurrent_edit(self):
        original = library.editorial_snapshot
        before = self.client.get('/api/library').json
        edited = False
        def concurrent_edit(c, pid, data):
            nonlocal edited
            if not edited:
                edited = True
                with self.db() as other:
                    other.execute('UPDATE packages SET body=? WHERE id=?', ('concurrent new body', self.pid))
            return original(c, pid, data)
        with patch('library.editorial_snapshot', side_effect=concurrent_edit):
            raced = self.client.get('/api/library').json
        self.assertEqual(raced['snapshot']['packages'][0]['body'], '原文')
        self.assertEqual(raced['packages'][self.pid]['fingerprint'], before['packages'][self.pid]['fingerprint'])
        self.assertEqual(self.review(fingerprint=raced['packages'][self.pid]['fingerprint']).status_code, 409)
        after = self.client.get('/api/library').json
        self.assertEqual(after['snapshot']['packages'][0]['body'], 'concurrent new body')
        self.assertNotEqual(after['packages'][self.pid]['fingerprint'], raced['packages'][self.pid]['fingerprint'])
        self.assertEqual(self.review(fingerprint=after['packages'][self.pid]['fingerprint']).status_code, 200)

    def test_review_snapshot_preserves_original_editorial_evidence(self):
        self.review()
        with self.db() as c:
            c.execute('UPDATE packages SET body=? WHERE id=?', ('updated body', self.pid))
        plain = self.client.get('/api/packages/' + self.pid + '/reviews').json['reviews'][0]
        self.assertNotIn('snapshot', plain)
        saved = self.client.get('/api/packages/' + self.pid + '/reviews?include_snapshot=1').json['reviews'][0]
        self.assertEqual(saved['snapshot']['package']['body'], '原文')
        self.assertEqual(library.content_fingerprint(saved['snapshot']), saved['fingerprint'])

    def test_snapshot_keeps_decoded_options_and_cached_asset_metadata(self):
        aid = self.post('/api/accounts', {'platform': 'wechat', 'name': '测试'}).json['id']
        self.post('/api/tasks', {'package_id': self.pid, 'account_id': aid, 'format': 'article'})
        upload = self.client.post('/api/packages/' + self.pid + '/assets', data={'file': (io.BytesIO(b'video'), 'a.mp4')}, headers=self.headers)
        with self.db() as c:
            c.execute('INSERT INTO asset_meta VALUES(?,?)', (upload.json['id'], json.dumps({'bytes': 5, 'width': 1920})))
        snapshot = self.client.get('/api/library').json['snapshot']
        self.assertIsInstance(snapshot['tasks'][0]['asset_ids'], list)
        self.assertEqual(snapshot['tasks'][0]['options']['mode'], 'manual')
        self.assertEqual(snapshot['assets'][0]['metadata']['width'], 1920)

    def test_batch_creation_and_review_do_not_change_dispatch(self):
        batch = self.post('/api/library/batches', {'name': '新批次'})
        self.assertEqual(batch.status_code, 201)
        self.assertEqual(self.patch(batch_id=batch.json['id'], sequence=1).status_code, 200)
        self.assertEqual(self.review().status_code, 200)
        with self.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM runs').fetchone()[0], 0)
        self.assertEqual(self.client.put('/api/packages/' + self.pid + '/review', json={'status': 'approved'}).status_code, 403)


if __name__ == '__main__':
    unittest.main()
