"""Editable account inventory, independent of platform credentials and execution."""
import re
import sqlite3
import uuid
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from flask import jsonify, request

KINDS = {'distribution', 'tool', 'store', 'mail', 'miniapp'}
PHONE_FIELDS = {'number', 'entity', 'carrier', 'holder', 'status', 'notes'}
ACCOUNT_FIELDS = {'source_id', 'platform', 'name', 'phone_id', 'login_identifier', 'login_method', 'owner', 'operator', 'content_direction', 'kind', 'notes', 'status', 'linked_account_id'}
RECORD_FIELDS = {'package_id', 'title', 'content_type', 'occurred_on', 'url', 'note', 'source'}


def migrate(db, data, now):
    with db() as c:
        exists = c.execute("SELECT 1 FROM sqlite_master WHERE name='account_registry_migrations' AND type='table'").fetchone()
        if exists and c.execute('SELECT 1 FROM account_registry_migrations WHERE version=1').fetchone():
            return
    directory = Path(data) / 'migration-backups'
    directory.mkdir(exist_ok=True)
    with db() as source, sqlite3.connect(directory / ('before-account-registry-v1-' + uuid.uuid4().hex + '.sqlite3')) as dest:
        source.backup(dest)
    with db() as c:
        c.executescript('''
        BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS account_registry_migrations(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS registry_phones(id TEXT PRIMARY KEY,number TEXT NOT NULL UNIQUE,entity TEXT NOT NULL,carrier TEXT NOT NULL,holder TEXT NOT NULL,status TEXT NOT NULL,notes TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS registry_accounts(id TEXT PRIMARY KEY,source_id TEXT UNIQUE,platform TEXT NOT NULL,name TEXT NOT NULL,phone_id TEXT REFERENCES registry_phones(id),login_identifier TEXT NOT NULL,login_method TEXT NOT NULL,owner TEXT NOT NULL,operator TEXT NOT NULL,content_direction TEXT NOT NULL,kind TEXT NOT NULL,notes TEXT NOT NULL,status TEXT NOT NULL,linked_account_id TEXT REFERENCES accounts(id),created TEXT NOT NULL,updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS registry_records(id TEXT PRIMARY KEY,registry_account_id TEXT NOT NULL REFERENCES registry_accounts(id),package_id TEXT REFERENCES packages(id),title TEXT NOT NULL,content_type TEXT NOT NULL,occurred_on TEXT,url TEXT NOT NULL,note TEXT NOT NULL,source TEXT NOT NULL DEFAULT 'manual',created TEXT NOT NULL,updated TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS registry_records_account ON registry_records(registry_account_id,occurred_on);
        ''')
        # Seed only existing operational accounts once; registry edits never create
        # operational accounts or mutate connections/tasks.
        for account in c.execute('SELECT id,platform,name FROM accounts').fetchall():
            if c.execute('SELECT 1 FROM registry_accounts WHERE linked_account_id=?', (account['id'],)).fetchone():
                continue
            c.execute('INSERT INTO registry_accounts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (uuid.uuid4().hex, None, account['platform'], account['name'], None, '', '', '', '', '', 'distribution', '', 'pending_verification', account['id'], now(), now()))
        c.execute('INSERT OR IGNORE INTO account_registry_migrations VALUES(1,?)', (now(),))


def install(app, data, db, get, fail, text, now):
    if getattr(app, 'desk_account_registry_installed', False):
        return
    migrate(db, data, now)
    app.desk_account_registry_installed = True

    def payload(allowed):
        d = request.get_json()
        if not isinstance(d, dict):
            fail('请提交 JSON 对象')
        if set(d) - allowed:
            # Do not echo unknown values, which may contain credentials.
            fail('存在不支持的字段；账号库不接收密码、Token 或 Cookie')
        return d

    def reference(c, table, value):
        if value in (None, ''):
            return None
        if not isinstance(value, str):
            fail('关联记录格式不正确')
        get(c, table, value)
        return value

    def write(c, table, rid, values, creating):
        if creating:
            values = {'id': rid, **values, 'created': now(), 'updated': now()}
            c.execute('INSERT INTO ' + table + '(' + ','.join(values) + ') VALUES(' + ','.join('?' for _ in values) + ')', tuple(values.values()))
        else:
            values = {**values, 'updated': now()}
            c.execute('UPDATE ' + table + ' SET ' + ','.join(k + '=?' for k in values) + ' WHERE id=?', (*values.values(), rid))
        return get(c, table, rid)

    @app.get('/api/account-registry')
    def listing():
        with db() as c:
            c.execute('BEGIN')
            return jsonify(
                phones=[dict(r) for r in c.execute('SELECT * FROM registry_phones ORDER BY created,id')],
                accounts=[dict(r) for r in c.execute('SELECT * FROM registry_accounts ORDER BY created,id')],
                records=[dict(r) for r in c.execute('SELECT * FROM registry_records ORDER BY coalesce(occurred_on,created) DESC,id')],
                distribution_accounts=[dict(r) for r in c.execute('SELECT id,platform,name,created FROM accounts ORDER BY created,id')])

    def save_phone(rid=None):
        d = payload(PHONE_FIELDS)
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            old = get(c, 'registry_phones', rid) if rid else {}
            values = {k: text(d.get(k, old.get(k, 'active' if k == 'status' else '')), 5000 if k == 'notes' else 200) for k in PHONE_FIELDS}
            raw = text(d.get('number', old.get('number', '')), 80, True)
            number = re.sub(r'[\s()\-]', '', raw)
            if not re.fullmatch(r'\+?[0-9]{5,20}', number):
                fail('手机号请填写 5 至 20 位数字，可带国际区号')
            values['number'] = number
            duplicate = c.execute('SELECT id FROM registry_phones WHERE number=? AND id<>?', (number, rid or '')).fetchone()
            if duplicate:
                fail('这个手机号已在资源库中，请编辑已有记录', 409)
            result = write(c, 'registry_phones', rid or uuid.uuid4().hex, values, rid is None)
        return jsonify(result), 201 if rid is None else 200

    app.add_url_rule('/api/account-registry/phones', 'registry_phone_create', save_phone, methods=['POST'])
    app.add_url_rule('/api/account-registry/phones/<rid>', 'registry_phone_edit', save_phone, methods=['PATCH'])

    def save_account(rid=None):
        d = payload(ACCOUNT_FIELDS)
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            old = get(c, 'registry_accounts', rid) if rid else {}
            values = {}
            for key in ACCOUNT_FIELDS - {'source_id', 'phone_id', 'linked_account_id', 'kind'}:
                default = 'active' if key == 'status' else ''
                values[key] = text(d.get(key, old.get(key, default)), 5000 if key in {'notes', 'content_direction'} else 200, key in {'platform', 'name'})
            kind = d.get('kind', old.get('kind', 'distribution'))
            if not isinstance(kind, str) or kind not in KINDS:
                fail('请选择分发、工具、电商、邮箱或小程序账号类型')
            values['kind'] = kind
            for field, table in [('phone_id', 'registry_phones'), ('linked_account_id', 'accounts')]:
                values[field] = reference(c, table, d.get(field, old.get(field)))
            if values['linked_account_id']:
                linked = get(c, 'accounts', values['linked_account_id'])
                if kind != 'distribution' or values['platform'] != linked['platform']:
                    fail('执行账号只能关联同平台的分发账号；更改平台或类型前请解除关联')
                if c.execute('SELECT 1 FROM registry_accounts WHERE linked_account_id=? AND id<>?', (values['linked_account_id'], rid or '')).fetchone():
                    fail('该执行账号已关联其他登记记录，请编辑已有记录', 409)
            source = d.get('source_id', old.get('source_id'))
            values['source_id'] = text(source, 200, True) if source not in (None, '') else None
            if values['source_id'] and c.execute('SELECT 1 FROM registry_accounts WHERE source_id=? AND id<>?', (values['source_id'], rid or '')).fetchone():
                fail('来源编号已经存在，请编辑已有账号', 409)
            result = write(c, 'registry_accounts', rid or uuid.uuid4().hex, values, rid is None)
        return jsonify(result), 201 if rid is None else 200

    app.add_url_rule('/api/account-registry/accounts', 'registry_account_create', save_account, methods=['POST'])
    app.add_url_rule('/api/account-registry/accounts/<rid>', 'registry_account_edit', save_account, methods=['PATCH'])

    def save_record(account_id=None, rid=None):
        d = payload(RECORD_FIELDS)
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            old = get(c, 'registry_records', rid) if rid else {}
            account_id = account_id or old['registry_account_id']
            get(c, 'registry_accounts', account_id)
            values = {k: text(d.get(k, old.get(k, '')), 5000 if k == 'note' else 500, k == 'title') for k in ['title', 'content_type', 'url', 'note']}
            values['registry_account_id'] = account_id
            values['package_id'] = reference(c, 'packages', d.get('package_id', old.get('package_id')))
            occurred = d.get('occurred_on', old.get('occurred_on'))
            if occurred in (None, ''):
                occurred = None
            else:
                if not isinstance(occurred, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', occurred):
                    fail('发布时间请填写 YYYY-MM-DD 日期')
                try:
                    date.fromisoformat(occurred)
                except ValueError:
                    fail('发布日期不存在')
            values['occurred_on'] = occurred
            if values['url']:
                try:
                    url = urlparse(values['url'])
                    valid = url.scheme in {'https', 'http'} and bool(url.hostname) and not url.username and not url.password
                except ValueError:
                    valid = False
                if not valid:
                    fail('作品链接须为不含登录凭据的 HTTP(S) 地址')
            if d.get('source', 'manual') != 'manual':
                fail('历史备注只能记录为人工补记，不代表平台核验')
            values['source'] = 'manual'
            result = write(c, 'registry_records', rid or uuid.uuid4().hex, values, rid is None)
        return jsonify(result), 201 if rid is None else 200

    app.add_url_rule('/api/account-registry/accounts/<account_id>/records', 'registry_record_create', save_record, methods=['POST'])
    app.add_url_rule('/api/account-registry/records/<rid>', 'registry_record_edit', save_record, methods=['PATCH'])
