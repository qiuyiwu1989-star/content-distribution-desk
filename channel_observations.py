"""Append-only local observations; button clicks are never publication evidence."""
import hashlib
import json
import re
import sqlite3
import uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from flask import jsonify, request

EVENTS = {'schedule_changed', 'submit_clicked', 'draft_clicked', 'result_observed', 'manual_confirmation'}
SOURCES = {'session_observer', 'manual'}
ALLOWED_PATHS = {'/platform/post', '/platform/post/create', '/platform/post/list', '/platform/post/edit', '/platform/home'}
FIELDS = {'task_id', 'revision', 'event_id', 'event_kind', 'observed_account', 'page_url', 'scheduled_text', 'result_text', 'source'}


def migrate(db, data, now):
    with db() as c:
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='channel_observations'").fetchone():
            return
    directory = Path(data) / 'migration-backups'
    directory.mkdir(exist_ok=True)
    with db() as source, sqlite3.connect(directory / ('before-channel-observations-v1-' + uuid.uuid4().hex + '.sqlite3')) as dest:
        source.backup(dest)
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS channel_observations(
            id TEXT PRIMARY KEY,event_id TEXT NOT NULL UNIQUE,payload_hash TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES tasks(id),revision INTEGER NOT NULL,
            account_id TEXT NOT NULL REFERENCES accounts(id),target_account_name TEXT NOT NULL,
            observed_account TEXT NOT NULL,identity_match TEXT NOT NULL,page_url TEXT NOT NULL,
            event_kind TEXT NOT NULL,scheduled_text TEXT NOT NULL,result_text TEXT NOT NULL,
            source TEXT NOT NULL,
            binding_snapshot TEXT NOT NULL,task_snapshot TEXT NOT NULL,created TEXT NOT NULL)''')


def install(app, data, db, get, fail, text, now):
    if getattr(app, 'desk_channel_observations_installed', False):
        return
    migrate(db, data, now)
    app.desk_channel_observations_installed = True

    def public(row):
        value = dict(row)
        value.pop('payload_hash', None)
        value['binding_snapshot'] = json.loads(value['binding_snapshot'])
        value['task_snapshot'] = json.loads(value['task_snapshot'])
        return value

    @app.get('/api/channel-observations')
    def observations():
        tid = request.args.get('task_id')
        with db() as c:
            if tid:
                get(c, 'tasks', tid)
                rows = c.execute('SELECT * FROM channel_observations WHERE task_id=? ORDER BY created DESC,id LIMIT 200', (tid,)).fetchall()
            else:
                rows = c.execute('SELECT * FROM channel_observations ORDER BY created DESC,id LIMIT 200').fetchall()
            return jsonify(observations=[public(r) for r in rows])

    @app.post('/api/channel-observations')
    def observe():
        if request.content_length and request.content_length > 24000:
            fail('观察记录过大')
        d = request.get_json()
        if not isinstance(d, dict) or set(d) - FIELDS:
            fail('观察记录字段不正确')
        value = {}
        for key, limit in [('task_id', 100), ('event_id', 150), ('observed_account', 200), ('scheduled_text', 500), ('result_text', 4000)]:
            value[key] = text(d.get(key, ''), limit, key in {'task_id', 'event_id'})
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,150}', value['event_id']):
            fail('观察事件编号格式不正确')
        revision = d.get('revision')
        if type(revision) is not int or revision < 1:
            fail('观察记录需要当前任务版本号')
        kind, source = d.get('event_kind'), d.get('source')
        if not isinstance(kind, str) or kind not in EVENTS or not isinstance(source, str) or source not in SOURCES:
            fail('观察事件类型或来源不正确')
        if kind == 'manual_confirmation' and source != 'manual':
            fail('人工确认必须由人工记录，页面观察不能代替')
        if kind in {'result_observed', 'manual_confirmation'} and not value['result_text']:
            fail('请填写实际观察到的结果')
        page = text(d.get('page_url', ''), 2000, True)
        try:
            url = urlparse(page)
            valid = url.scheme == 'https' and url.hostname == 'channels.weixin.qq.com' and url.port in (None, 443) and not url.username and not url.password and url.path.rstrip('/') in ALLOWED_PATHS
        except ValueError:
            valid = False
        if not valid:
            fail('只接受视频号助手发布页面的观察记录')
        # Do not persist query parameters, which may contain session identifiers.
        value.update(page_url=urlunparse(('https', 'channels.weixin.qq.com', url.path, '', '', '')), revision=revision, event_kind=kind, source=source)
        digest = hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            prior = c.execute('SELECT * FROM channel_observations WHERE event_id=?', (value['event_id'],)).fetchone()
            if prior:
                if prior['payload_hash'] != digest:
                    fail('同一观察编号不能用于不同记录', 409)
                return jsonify(observation=public(prior), duplicate=True)
            task = get(c, 'tasks', value['task_id'])
            account = get(c, 'accounts', task['account_id'])
            if account['platform'] != 'channels':
                fail('该任务不属于微信视频号')
            if task['revision'] != revision:
                fail('任务版本已变化，请重新选择当前任务', 409)
            connection = c.execute('SELECT identity,display_name,status FROM connections WHERE account_id=?', (account['id'],)).fetchone()
            binding = dict(connection) if connection else {'identity': '', 'display_name': '', 'status': 'unbound'}
            normalize = lambda v: ' '.join(v.split()).casefold()
            observed = normalize(value['observed_account'])
            identities = {normalize(binding[k]) for k in ['identity', 'display_name'] if binding[k]}
            match = 'matched' if observed and observed in identities else 'mismatch' if observed and identities else 'unverified'
            snapshot = {k: task[k] for k in ['id', 'package_id', 'account_id', 'format', 'title', 'body', 'tags', 'cover_id', 'revision']}
            snapshot['asset_ids'] = json.loads(task['asset_ids'])
            option = c.execute('SELECT value FROM task_options WHERE task_id=?', (task['id'],)).fetchone()
            snapshot['options'] = json.loads(option['value']) if option else {}
            row = dict(id=uuid.uuid4().hex, event_id=value['event_id'], payload_hash=digest, task_id=task['id'], revision=revision,
                       account_id=account['id'], target_account_name=account['name'], observed_account=value['observed_account'], identity_match=match,
                       page_url=value['page_url'], event_kind=kind, scheduled_text=value['scheduled_text'], result_text=value['result_text'], source=source,
                       binding_snapshot=json.dumps(binding, ensure_ascii=False),
                       task_snapshot=json.dumps(snapshot, ensure_ascii=False), created=now())
            c.execute('INSERT INTO channel_observations(' + ','.join(row) + ') VALUES(' + ','.join('?' for _ in row) + ')', tuple(row.values()))
            return jsonify(observation=public(row), duplicate=False), 201
