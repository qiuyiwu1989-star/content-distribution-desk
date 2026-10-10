"""Recorded production work; this module never executes tools or approves content."""
import json
import uuid
from flask import jsonify, request

TRANSITIONS = {'queued': {'running', 'canceled'}, 'running': {'completed', 'failed', 'canceled'}}

def install(app, db, get, fail, text, now):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS production_tasks(
            id TEXT PRIMARY KEY, package_id TEXT NOT NULL REFERENCES packages(id),
            idempotency_key TEXT NOT NULL UNIQUE, input_version_id TEXT NOT NULL,
            input_fingerprint TEXT NOT NULL, capability_kind TEXT NOT NULL,
            capability_id TEXT NOT NULL, capability_version TEXT NOT NULL,
            instruction TEXT NOT NULL, status TEXT NOT NULL, worker TEXT NOT NULL,
            result TEXT NOT NULL, revision INTEGER NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS production_task_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL REFERENCES production_tasks(id),
            status TEXT NOT NULL, worker TEXT NOT NULL, summary TEXT NOT NULL, created TEXT NOT NULL)''')

    def current(c, pid):
        get(c, 'packages', pid)
        helper = getattr(app, 'desk_content_version', None)
        if helper is None:
            fail('内容版本模块尚未安装', 503)
        return helper(c, pid)

    def row(c, tid):
        value = c.execute('SELECT * FROM production_tasks WHERE id=?', (tid,)).fetchone()
        if value is None:
            fail('制作任务不存在', 404)
        return value

    def record(c, r, events=False):
        d = dict(r)
        d['result'] = json.loads(d['result'])
        v = current(c, d['package_id'])
        d['input_stale'] = v['id'] != d['input_version_id'] or v['fingerprint'] != d['input_fingerprint']
        d['current_version_id'] = v['id']
        if events:
            d['events'] = [dict(x) for x in c.execute('SELECT * FROM production_task_events WHERE task_id=? ORDER BY id', (d['id'],))]
        return d

    @app.get('/api/packages/<pid>/production-tasks')
    def list_tasks(pid):
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            v = current(c, pid)
            tasks = [record(c, r) for r in c.execute('SELECT * FROM production_tasks WHERE package_id=? ORDER BY created DESC,id DESC', (pid,))]
        return jsonify(tasks=tasks, input_version={'id': v['id'], 'fingerprint': v['fingerprint'], 'number': v.get('number')})

    @app.get('/api/production-tasks/<tid>')
    def task_detail(tid):
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            result = record(c, row(c, tid), True)
        return jsonify(result)

    @app.post('/api/packages/<pid>/production-tasks')
    def create_task(pid):
        d = request.get_json(silent=True)
        if not isinstance(d, dict):
            fail('任务输入需要对象')
        fields = {k: text(d.get(k), limit, True) for k, limit in [('idempotency_key', 100), ('input_version_id', 100), ('input_fingerprint', 100), ('capability_id', 120), ('capability_version', 120), ('instruction', 5000)]}
        kind = d.get('capability_kind')
        if kind not in {'tool', 'skill', 'manual'}:
            fail('能力类型需要 tool、skill 或 manual')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            get(c, 'packages', pid)
            previous = c.execute('SELECT * FROM production_tasks WHERE idempotency_key=?', (fields['idempotency_key'],)).fetchone()
            if previous:
                if previous['package_id'] != pid or previous['capability_kind'] != kind or any(previous[k] != value for k, value in fields.items()):
                    fail('重试编号与原任务输入不一致', 409)
                return jsonify(record(c, previous, True))
            v = current(c, pid)
            if fields['input_version_id'] != v['id'] or fields['input_fingerprint'] != v['fingerprint']:
                fail('内容版本已变化，请读取当前版本后创建任务', 409)
            tid, stamp = uuid.uuid4().hex, now()
            c.execute('INSERT INTO production_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (tid, pid, fields['idempotency_key'], v['id'], v['fingerprint'], kind,
                       fields['capability_id'], fields['capability_version'], fields['instruction'],
                       'queued', '', '{}', 1, stamp, stamp))
            c.execute('INSERT INTO production_task_events(task_id,status,worker,summary,created) VALUES(?,?,?,?,?)', (tid, 'queued', '', '创建制作任务', stamp))
            result = record(c, row(c, tid), True)
        return jsonify(result), 201

    @app.post('/api/production-tasks/<tid>/transition')
    def production_transition(tid):
        d = request.get_json(silent=True)
        if not isinstance(d, dict):
            fail('任务更新需要对象')
        status = d.get('status')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            r = row(c, tid)
            if type(d.get('revision')) is not int or d['revision'] != r['revision']:
                fail('任务已更新，请刷新后重试', 409)
            if status not in TRANSITIONS.get(r['status'], set()):
                fail('不允许此任务状态转换', 409)
            v = current(c, r['package_id'])
            # Starting stale work is blocked. Existing workers can still record their
            # historical result honestly; no result is applied to current content.
            if status == 'running' and (v['id'] != r['input_version_id'] or v['fingerprint'] != r['input_fingerprint']):
                fail('输入版本已变化，请针对新版本另建任务', 409)
            worker = r['worker']
            capability_kind, capability_id, capability_version = r['capability_kind'], r['capability_id'], r['capability_version']
            if status == 'running':
                worker = text(d.get('worker'), 120, True)
                if capability_version == 'unassigned':
                    capability_kind = d.get('capability_kind')
                    if capability_kind not in {'tool', 'skill', 'manual'}:
                        fail('接单时需要登记实际使用的能力类型')
                    capability_id = text(d.get('capability_id'), 120, True)
                    capability_version = text(d.get('capability_version'), 120, True)
                    if capability_version == 'unassigned':
                        fail('接单时需要登记实际能力版本')
            elif r['status'] == 'running' and status != 'canceled' and d.get('worker') != worker:
                fail('仅接单 Agent 可以登记执行结果', 409)
            summary = text(d.get('summary', ''), 5000, status in {'completed', 'failed'})
            artifacts = d.get('artifacts', [])
            if not isinstance(artifacts, list) or len(artifacts) > 100:
                fail('结果文件需要清单，最多 100 项')
            clean = []
            for a in artifacts:
                if not isinstance(a, dict):
                    fail('结果文件格式不正确')
                item = {'name': text(a.get('name'), 300, True), 'reference': text(a.get('reference'), 2000, True)}
                if item['reference'].lower().startswith(('javascript:', 'data:', 'vbscript:')):
                    fail('结果引用格式不安全')
                clean.append(item)
            result = json.dumps({'summary': summary, 'artifacts': clean, 'reported_by': worker}, ensure_ascii=False) if status in {'completed', 'failed'} else r['result']
            stamp = now()
            c.execute('UPDATE production_tasks SET status=?,worker=?,result=?,capability_kind=?,capability_id=?,capability_version=?,revision=revision+1,updated=? WHERE id=?', (status, worker, result, capability_kind, capability_id, capability_version, stamp, tid))
            c.execute('INSERT INTO production_task_events(task_id,status,worker,summary,created) VALUES(?,?,?,?,?)', (tid, status, worker, summary, stamp))
            value = record(c, row(c, tid), True)
        return jsonify(value)
