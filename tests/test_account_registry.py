import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from werkzeug.exceptions import BadRequest, NotFound, Conflict
from server import create_app
from account_registry import install, migrate


class RegistryTests(unittest.TestCase):
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
        install(self.app, self.root, self.db, get, fail, text, self.now)
        self.client = self.app.test_client()
        token = re.search('name="desk-token" content="([^"]+)"', self.client.get('/').text).group(1)
        self.headers = {'X-Desk-Token': token}

    def tearDown(self):
        self.tmp.cleanup()

    def now(self):
        return datetime.now(timezone.utc).isoformat()

    def db(self):
        c = sqlite3.connect(self.root / 'desk.sqlite3')
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        return c

    def post(self, path, values):
        return self.client.post('/api/account-registry/' + path, json=values, headers=self.headers)

    def patch(self, path, values):
        return self.client.patch('/api/account-registry/' + path, json=values, headers=self.headers)

    def account(self, **extra):
        return self.post('accounts', {'platform': '任意工具平台', 'name': '测试工具', 'kind': 'tool', **extra})

    def test_phones_normalized_unique_editable_and_persisted(self):
        created = self.post('phones', {'number': '+86 138-0000-0000', 'entity': '主体甲'})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json['number'], '+8613800000000')
        self.assertEqual(self.post('phones', {'number': '+8613800000000'}).status_code, 409)
        edited = self.patch('phones/' + created.json['id'], {'holder': '管理员', 'status': 'pending_verification'})
        self.assertEqual(edited.json['entity'], '主体甲')
        self.assertEqual(edited.json['holder'], '管理员')
        self.assertEqual(self.post('phones', {'number': 'not-a-phone'}).status_code, 400)

    def test_registry_arbitrary_platform_does_not_create_execution_account(self):
        created = self.account(source_id='22', login_identifier='editor@example.test')
        self.assertEqual(created.status_code, 201)
        self.assertIsNone(created.json['linked_account_id'])
        self.assertEqual(self.account(source_id='22').status_code, 409)
        self.assertEqual(self.account(source_id='').status_code, 201)
        self.assertEqual(self.account(source_id=None).status_code, 201)
        with self.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM accounts').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT count(*) FROM tasks').fetchone()[0], 0)
        self.assertEqual(self.account(phone_id='missing').status_code, 404)
        self.assertEqual(self.account(linked_account_id='missing').status_code, 404)
        self.assertEqual(self.account(kind='unknown').status_code, 400)

    def test_sensitive_unknown_fields_rejected_and_guard_reused(self):
        self.assertEqual(self.account(password='do-not-store').status_code, 400)
        self.assertEqual(self.post('phones', {'number': '13800000000', 'token': 'do-not-store'}).status_code, 400)
        self.assertEqual(self.client.post('/api/account-registry/accounts', json={'name': 'x'}).status_code, 403)
        with self.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM registry_accounts').fetchone()[0], 0)

    def test_historical_notes_are_manual_and_do_not_mutate_dispatch(self):
        aid = self.account().json['id']
        created = self.post('accounts/' + aid + '/records', {'title': '以前的一篇文章', 'note': '日期待核实'})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json['source'], 'manual')
        self.assertIsNone(created.json['occurred_on'])
        self.assertEqual(self.patch('records/' + created.json['id'], {'occurred_on': '2026-02-30'}).status_code, 400)
        self.assertEqual(self.patch('records/' + created.json['id'], {'url': 'javascript:alert(1)'}).status_code, 400)
        self.assertEqual(self.patch('records/' + created.json['id'], {'url': 'https://user:secret@example.test'}).status_code, 400)
        self.assertEqual(self.patch('records/' + created.json['id'], {'source': 'verified'}).status_code, 400)
        edited = self.patch('records/' + created.json['id'], {'occurred_on': '2026-10-08', 'content_type': '视频', 'url': 'https://example.test/work'})
        self.assertEqual(edited.status_code, 200)
        listing = self.client.get('/api/account-registry').json
        self.assertEqual(listing['records'][0]['note'], '日期待核实')
        with self.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM tasks').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT count(*) FROM runs').fetchone()[0], 0)

    def test_link_requires_unique_matching_distribution_platform(self):
        with self.db() as c:
            c.execute("INSERT INTO accounts VALUES('execution','channels','已有视频号','old')")
        self.assertEqual(self.account(platform='rednote', kind='distribution', linked_account_id='execution').status_code, 400)
        self.assertEqual(self.account(platform='channels', kind='tool', linked_account_id='execution').status_code, 400)
        created = self.account(platform='channels', kind='distribution', linked_account_id='execution')
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.account(platform='channels', kind='distribution', linked_account_id='execution').status_code, 409)
        rid = created.json['id']
        self.assertEqual(self.patch('accounts/' + rid, {'platform': 'rednote'}).status_code, 400)
        self.assertEqual(self.patch('accounts/' + rid, {'kind': 'mail'}).status_code, 400)
        changed = self.patch('accounts/' + rid, {'platform': 'rednote', 'linked_account_id': None})
        self.assertEqual(changed.status_code, 200)
        self.assertIsNone(changed.json['linked_account_id'])

    def test_migration_seeds_existing_accounts_once_without_copying_secrets(self):
        with self.db() as c:
            c.execute("INSERT INTO accounts VALUES('old','wechat','已有账号','old')")
            c.execute('DELETE FROM account_registry_migrations')
        migrate(self.db, self.root, self.now)
        before = self.client.get('/api/account-registry').json
        self.assertEqual(len(before['accounts']), 1)
        seeded = before['accounts'][0]
        self.assertEqual(seeded['linked_account_id'], 'old')
        self.assertIsNone(seeded['source_id'])
        self.assertEqual(seeded['login_identifier'], '')
        self.assertEqual(seeded['status'], 'pending_verification')
        backups = list((self.root / 'migration-backups').glob('before-account-registry-*'))
        migrate(self.db, self.root, self.now)
        self.assertEqual(len(backups), len(list((self.root / 'migration-backups').glob('before-account-registry-*'))))
        self.assertEqual(self.client.get('/api/account-registry').json, before)
        edited = self.patch('accounts/' + seeded['id'], {'source_id': '1', 'owner': '主体甲'})
        self.assertEqual(edited.json['linked_account_id'], 'old')
        with self.db() as c:
            self.assertEqual(c.execute("SELECT name FROM accounts WHERE id='old'").fetchone()[0], '已有账号')


if __name__ == '__main__':
    unittest.main()
