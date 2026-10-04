"""Local distribution desk. External writes require explicit approved jobs."""
import io
import json
import os
import secrets
import sqlite3
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_file, send_from_directory
from werkzeug.exceptions import HTTPException

ROOT = Path(__file__).resolve().parent
PLATFORMS = {
    'wechat': {'name': '微信公众号', 'short': '公', 'color': '#17835d', 'formats': ['article', 'gallery'], 'url': 'https://mp.weixin.qq.com/', 'domains': ['mp.weixin.qq.com']},
    'channels': {'name': '微信视频号', 'short': '视', 'color': '#d88516', 'formats': ['video'], 'url': 'https://channels.weixin.qq.com/', 'domains': ['channels.weixin.qq.com', 'weixin.qq.com']},
    'rednote': {'name': '小红书', 'short': '红', 'color': '#e04859', 'formats': ['gallery', 'video'], 'url': 'https://creator.xiaohongshu.com/', 'domains': ['xiaohongshu.com', 'xhslink.com']},
    'douyin': {'name': '抖音', 'short': '抖', 'color': '#303448', 'formats': ['gallery', 'video'], 'url': 'https://creator.douyin.com/', 'domains': ['douyin.com', 'iesdouyin.com']},
    'bilibili': {'name': 'B 站', 'short': 'B', 'color': '#2384ad', 'formats': ['video', 'article'], 'url': 'https://member.bilibili.com/', 'domains': ['bilibili.com', 'b23.tv']},
    'zhihu': {'name': '知乎', 'short': '知', 'color': '#3875cd', 'formats': ['article'], 'url': 'https://www.zhihu.com/creator', 'domains': ['zhihu.com']},
}
FORMATS = {'article': '文章', 'gallery': '图文', 'video': '视频'}
STATUSES = {'draft': '待完善', 'scheduled': '已排期', 'ready': '待交付', 'delivered': '已存草稿', 'review': '平台审核中', 'published': '已发布', 'failed': '需处理', 'canceled': '已取消'}
STATUSES.update(queued='等待执行',running='执行中',unknown='待核对结果',blocked='连接或素材受阻')
TRANSITIONS = {
    'draft': {'scheduled', 'ready', 'canceled'},
    'scheduled': {'draft', 'ready', 'canceled'},
    'ready': {'draft', 'delivered', 'review', 'published', 'failed', 'canceled'},
    'delivered': {'review', 'published', 'failed', 'canceled'},
    'review': {'published', 'failed', 'canceled'},
    'failed': {'draft','ready', 'canceled'},
    'published': set(), 'canceled': set(),
    'queued': {'draft','canceled'},'running':set(),
    'unknown': {'delivered','review','published','failed'},
    'blocked': {'draft','canceled'},
}

def now():
    return datetime.now(timezone.utc).isoformat()

def ident():
    return uuid.uuid4().hex

def create_app(data_dir=None):
    data = Path(data_dir or os.environ.get('DESK_DATA_DIR', Path.home() / 'Library/Application Support/内容分发台/data'))
    data.mkdir(parents=True, exist_ok=True)
    (data / 'files').mkdir(exist_ok=True)
    app = Flask(__name__, static_folder=str(ROOT / 'static'))
    app.config.update(MAX_CONTENT_LENGTH=512 * 1024 * 1024, TESTING=False)
    app.json.sort_keys = False
    token = secrets.token_urlsafe(32)

    def db():
        c = sqlite3.connect(data / 'desk.sqlite3', timeout=15)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        return c

    with db() as c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS packages(id TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,notes TEXT NOT NULL,created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,package_id TEXT NOT NULL REFERENCES packages(id),name TEXT NOT NULL,mime TEXT NOT NULL,size INTEGER NOT NULL,kind TEXT NOT NULL,created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,platform TEXT NOT NULL,name TEXT NOT NULL,created TEXT NOT NULL,UNIQUE(platform,name));
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,package_id TEXT NOT NULL REFERENCES packages(id),account_id TEXT NOT NULL REFERENCES accounts(id),format TEXT NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL,tags TEXT NOT NULL,asset_ids TEXT NOT NULL,cover_id TEXT,status TEXT NOT NULL,scheduled TEXT,url TEXT NOT NULL,note TEXT NOT NULL,revision INTEGER NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,UNIQUE(package_id,account_id,format));
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES tasks(id),message TEXT NOT NULL,created TEXT NOT NULL);
        ''')

    def event(c, task, message):
        c.execute('INSERT INTO events VALUES(?,?,?,?)', (ident(), task, message, now()))

    def fail(message, code=400):
        from werkzeug.exceptions import BadRequest, Conflict, NotFound
        cls = {400: BadRequest, 404: NotFound, 409: Conflict}.get(code, BadRequest)
        raise cls(message)

    def get(c, table, id):
        row = c.execute(f'SELECT * FROM {table} WHERE id=?', (id,)).fetchone()
        if not row:
            fail('记录不存在', 404)
        return dict(row)

    def text(value, maxlen=50000, required=False):
        if not isinstance(value, str) or len(value) > maxlen:
            fail('文字格式或长度不正确')
        value = value.strip()
        if required and not value:
            fail('请填写必填信息')
        return value

    def validate_task(c, t):
        a = get(c, 'accounts', t['account_id'])
        if t['format'] not in PLATFORMS[a['platform']]['formats']:
            fail('该渠道不支持所选内容类型')
        text(t['title'], 200, True)
        assets = [get(c, 'assets', x) for x in json.loads(t['asset_ids'])]
        if any(x['package_id'] != t['package_id'] for x in assets):
            fail('附件不属于此发布包')
        if t['format'] == 'article' and not t['body'].strip():
            fail('文章需要正文')
        if t['format'] == 'gallery' and (not assets or any(x['kind'] != 'image' for x in assets)):
            fail('图文请选择至少一张图片，且只能选择图片')
        if t['format'] == 'video' and (len(assets) != 1 or assets[0]['kind'] != 'video'):
            fail('视频任务需要选择一个视频文件')
        if t.get('cover_id'):
            cover = get(c, 'assets', t['cover_id'])
            if cover['kind'] != 'image' or cover['package_id'] != t['package_id']:
                fail('封面必须是此发布包内的图片')

    def tick():
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            due = c.execute("SELECT id FROM tasks WHERE status='scheduled' AND scheduled<=? AND NOT EXISTS(SELECT 1 FROM runs WHERE runs.task_id=tasks.id AND runs.status='queued')", (now(),)).fetchall()
            for t in due:
                c.execute("UPDATE tasks SET status='ready',revision=revision+1,updated=? WHERE id=?", (now(), t['id']))
                event(c, t['id'], '已到计划时间，等待人工交付；未自动发布')

    app.desk_tick = tick

    @app.before_request
    def guard():
        if request.host.split(':')[0] not in {'127.0.0.1', 'localhost'}:
            return jsonify(error='此工作台仅允许本机访问'), 403
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            if request.headers.get('X-Desk-Token') != token:
                return jsonify(error='会话已刷新，请重新打开页面'), 403
            if request.headers.get('Origin') and request.headers['Origin'] != request.host_url.rstrip('/'):
                return jsonify(error='不允许跨站写入'), 403
            if request.is_json and not isinstance(request.get_json(), dict):
                return jsonify(error='请求必须是 JSON 对象'), 400

    @app.after_request
    def headers(r):
        r.headers['X-Content-Type-Options'] = 'nosniff'
        r.headers['X-Frame-Options'] = 'DENY'
        r.headers['Cache-Control'] = 'no-store'
        r.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        return r

    @app.errorhandler(HTTPException)
    def error(e):
        return jsonify(error=e.description), e.code

    @app.errorhandler(sqlite3.IntegrityError)
    def integrity(e):
        return jsonify(error='此账号或渠道任务已经存在，请编辑已有记录'), 409

    @app.get('/')
    def index():
        return (ROOT / 'static/index.html').read_text().replace('__TOKEN__', token)

    @app.get('/api/state')
    def state():
        tick()
        with db() as c:
            result = {k: [dict(r) for r in c.execute(f'SELECT * FROM {k} ORDER BY created DESC')] for k in ['packages', 'assets', 'accounts', 'tasks', 'events']}
        for t in result['tasks']:
            t['asset_ids'] = json.loads(t['asset_ids'])
        result=app.desk_enrich(result)
        return jsonify(**result, platforms=PLATFORMS, formats=FORMATS, statuses=STATUSES, server_time=now(), delivery_mode='mixed')

    @app.post('/api/accounts')
    def account():
        d = request.get_json()
        platform = d.get('platform')
        if platform not in PLATFORMS:
            fail('请选择平台')
        id = ident()
        with db() as c:
            c.execute('INSERT INTO accounts VALUES(?,?,?,?)', (id, platform, text(d.get('name'), 80, True), now()))
        return jsonify(id=id), 201

    @app.post('/api/packages')
    def package():
        d = request.get_json()
        id = ident()
        with db() as c:
            c.execute('INSERT INTO packages VALUES(?,?,?,?,?)', (id, text(d.get('title'), 200, True), text(d.get('body', '')), text(d.get('notes', ''), 3000), now()))
        return jsonify(id=id), 201

    @app.post('/api/packages/<id>/assets')
    def upload(id):
        with db() as c:
            get(c, 'packages', id)
        f = request.files.get('file')
        if not f or not f.filename:
            fail('请选择文件')
        name = Path(f.filename.replace('\\', '/')).name[:200]
        ext = Path(name).suffix.lower()
        types = {'.jpg': ('image', 'image/jpeg'), '.jpeg': ('image', 'image/jpeg'), '.png': ('image', 'image/png'), '.webp': ('image', 'image/webp'), '.mp4': ('video', 'video/mp4'), '.mov': ('video', 'video/quicktime'), '.webm': ('video', 'video/webm'), '.md': ('document', 'text/plain'), '.txt': ('document', 'text/plain'), '.pdf': ('document', 'application/pdf')}
        if ext not in types:
            fail('支持 JPG、PNG、WebP、MP4、MOV、WebM、MD、TXT 和 PDF')
        aid = ident()
        target = data / 'files' / aid
        f.save(target)
        size = target.stat().st_size
        if not size:
            target.unlink()
            fail('文件为空')
        kind, mime = types[ext]
        try:
            with db() as c:
                c.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?)', (aid, id, name, mime, size, kind, now()))
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return jsonify(id=aid), 201

    @app.get('/api/assets/<id>')
    def asset(id):
        with db() as c:
            a = get(c, 'assets', id)
        return send_file(data / 'files' / a['id'], mimetype=a['mime'], download_name=a['name'], as_attachment=a['kind'] == 'document')

    @app.post('/api/tasks')
    def task():
        d = request.get_json()
        with db() as c:
            p = get(c, 'packages', d.get('package_id'))
            a = get(c, 'accounts', d.get('account_id'))
            fmt = d.get('format')
            if fmt not in PLATFORMS[a['platform']]['formats']:
                fail('请选择该平台支持的内容类型')
            id, ts = ident(), now()
            c.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (id, p['id'], a['id'], fmt, p['title'], p['body'], '', '[]', None, 'draft', None, '', '', 1, ts, ts))
            event(c, id, '创建渠道任务')
        return jsonify(id=id), 201

    @app.patch('/api/tasks/<id>')
    def edit_task(id):
        d = request.get_json()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            t = get(c, 'tasks', id)
            if d.get('revision') != t['revision']:
                fail('任务已发生变化，请刷新后再操作', 409)
            if t['status'] not in {'draft', 'ready', 'scheduled', 'queued', 'blocked'}:
                fail('已交付的版本不可修改，请保留发布记录')
            assets = d.get('asset_ids', json.loads(t['asset_ids']))
            if not isinstance(assets, list) or len(assets) > 100 or any(not isinstance(x, str) for x in assets) or len(set(assets)) != len(assets):
                fail('附件列表不正确')
            for x in assets:
                if get(c, 'assets', x)['package_id'] != t['package_id']:
                    fail('附件不属于此发布包')
            cover = d.get('cover_id') or None
            if cover:
                ca = get(c, 'assets', cover)
                if ca['kind'] != 'image' or ca['package_id'] != t['package_id']:
                    fail('封面不正确')
            app.desk_cancel_pending(c,id)
            c.execute("UPDATE tasks SET title=?,body=?,tags=?,asset_ids=?,cover_id=?,status='draft',scheduled=NULL,revision=revision+1,updated=? WHERE id=?", (text(d.get('title', t['title']), 200, True), text(d.get('body', t['body'])), text(d.get('tags', t['tags']), 500), json.dumps(assets), cover, now(), id))
            event(c, id, '保存新版本；原排期已清除，需重新确认交付')
        return jsonify(ok=True)

    @app.post('/api/tasks/<id>/transition')
    def transition(id):
        d = request.get_json()
        target = d.get('status')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            t = get(c, 'tasks', id)
            if d.get('revision') != t['revision']:
                fail('任务已发生变化，请刷新后再操作', 409)
            if target not in TRANSITIONS[t['status']]:
                fail('当前状态不能执行此操作')
            if target in {'scheduled', 'ready', 'delivered', 'review', 'published'}:
                validate_task(c, t)
            if target in {'scheduled','ready'}:
                check=app.desk_preflight(c,id)
                if not check['ok']:fail('；'.join(check['errors']))
                if check['mode']!='manual':fail('自动交付请使用发布检查后的确认入口')
            schedule = t['scheduled']
            if target == 'scheduled':
                try:
                    dt = datetime.fromisoformat(d.get('scheduled', '').replace('Z', '+00:00'))
                    if dt.tzinfo is None or dt <= datetime.now(timezone.utc):
                        raise ValueError()
                    schedule = dt.astimezone(timezone.utc).isoformat()
                except (ValueError, TypeError):
                    fail('请选择未来的发布时间')
            if target == 'draft':
                schedule = None
            if target in {'draft','canceled'}:app.desk_cancel_pending(c,id)
            url = text(d.get('url', t['url']), 2000)
            note = text(d.get('note', ''), 3000)
            if target == 'published':
                p = PLATFORMS[get(c, 'accounts', t['account_id'])['platform']]
                u = urlparse(url)
                if u.scheme != 'https' or not u.hostname or not any(u.hostname == x or u.hostname.endswith('.' + x) for x in p['domains']) or u.username or u.password:
                    fail('请填写该平台的 HTTPS 作品链接')
                if not note:
                    fail('请填写人工核对说明，例如作品 ID 或核对时间')
            if target in {'failed', 'delivered', 'review'} and not note:
                fail('请填写平台结果或需要处理的问题')
            if t['status'] == 'failed' and target in {'draft','ready'} and d.get('checked') is not True:
                fail('请先核对平台，确认未重复发布')
            if t['status']=='unknown':
                c.execute("UPDATE runs SET status='resolved',updated=?,message=? WHERE task_id=? AND status='unknown'",(now(),'人工核对：'+STATUSES[target]+' · '+note,id))
            c.execute('UPDATE tasks SET status=?,scheduled=?,url=?,note=?,revision=revision+1,updated=? WHERE id=?', (target, schedule, url, note, now(), id))
            msg = '人工记录：' + STATUSES[target] if target in {'published', 'delivered', 'review'} else STATUSES[target]
            event(c, id, msg + (' · ' + note if note else ''))
        return jsonify(ok=True)

    @app.get('/api/tasks/<id>/bundle')
    def bundle(id):
        with db() as c:
            t = get(c, 'tasks', id)
            validate_task(c, t)
            a = get(c, 'accounts', t['account_id'])
            ids = json.loads(t['asset_ids'])
            if t['cover_id'] and t['cover_id'] not in ids:
                ids.append(t['cover_id'])
            assets = [get(c, 'assets', x) for x in ids]
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('正文.md', t['body'])
            z.writestr('发布信息.txt', f"平台：{PLATFORMS[a['platform']]['name']}\n账号：{a['name']}\n标题：{t['title']}\n话题：{t['tags']}\n计划时间（UTC）：{t['scheduled'] or '未排期'}\n此文件包不代表已发布，请在平台完成交付后回填结果。\n")
            manifest = dict(t, account=a, assets=assets, exported_at=now())
            z.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
            for i, f in enumerate(assets):
                z.write(data / 'files' / f['id'], f"素材/{i+1:02d}-{f['name']}")
        b.seek(0)
        return send_file(b, mimetype='application/zip', download_name=f"发布包-{id[:8]}.zip", as_attachment=True)

    @app.get('/api/backup')
    def backup():
        # SQLite backup API yields a consistent snapshot, including WAL records.
        target = data / ('backup-' + ident() + '.sqlite3')
        try:
            with db() as source, sqlite3.connect(target) as dest:
                source.backup(dest)
            b = io.BytesIO()
            with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
                z.write(target, 'desk.sqlite3')
                for f in (data / 'files').iterdir():
                    if f.is_file():
                        z.write(f, 'files/' + f.name)
            b.seek(0)
            return send_file(b, mimetype='application/zip', download_name='分发台完整备份.zip', as_attachment=True)
        finally:
            target.unlink(missing_ok=True)

    from distribution import install
    install(app,data,db,get,fail,text,now,event,validate_task)
    from site_import import install as install_site_import
    install_site_import(app,db,fail,text,now)
    return app

if __name__ == '__main__':
    app = create_app()
    app.desk_bridge.start()
    def clock():
        while True:
            try:
                app.desk_tick()
                app.desk_process_one()
            except Exception:
                app.logger.exception('排期检查失败')
            time.sleep(20)
    threading.Thread(target=clock, daemon=True).start()
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', 4318)), debug=False, threaded=True)
