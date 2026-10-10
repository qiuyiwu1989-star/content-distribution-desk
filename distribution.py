"""Distribution v2: explicit input, preflight, immutable jobs, and adapters."""
import hashlib
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import jsonify, request
from PIL import Image

import adapters
from platform_rules import RULES, RULES_VERSION, MODE_LABELS, SAU_PLATFORMS, WECHAT_PLATFORMS, rules_for
from wechat_bridge import Bridge


def install(app, data, db, get, fail, text, now, event, validate_task):
    bridge=Bridge(data,int(os.environ.get('DESK_BRIDGE_PORT','9537')))
    app.desk_bridge=bridge
    worker_lock=threading.Lock()
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS connections(account_id TEXT PRIMARY KEY REFERENCES accounts(id),adapter TEXT NOT NULL DEFAULT 'manual',reference TEXT NOT NULL DEFAULT '',identity TEXT NOT NULL DEFAULT '',display_name TEXT NOT NULL DEFAULT '',cookie_digest TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'unbound',checked_at TEXT,message TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS task_options(task_id TEXT PRIMARY KEY REFERENCES tasks(id),value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS package_meta(package_id TEXT PRIMARY KEY REFERENCES packages(id),value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS asset_meta(asset_id TEXT PRIMARY KEY REFERENCES assets(id),value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,task_id TEXT NOT NULL REFERENCES tasks(id),fingerprint TEXT NOT NULL,snapshot TEXT NOT NULL,status TEXT NOT NULL,not_before TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,message TEXT NOT NULL DEFAULT '',receipt_url TEXT NOT NULL DEFAULT '',attempt INTEGER NOT NULL DEFAULT 1,UNIQUE(task_id,fingerprint));
        CREATE TABLE IF NOT EXISTS checks(id TEXT PRIMARY KEY,account_id TEXT NOT NULL REFERENCES accounts(id),result TEXT NOT NULL,created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS distribution_migrations(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL);
        ''')
        c.execute('INSERT OR IGNORE INTO distribution_migrations VALUES(2,?)',(now(),))
        interrupted=c.execute("SELECT id,task_id FROM runs WHERE status='running'").fetchall()
        for r in interrupted:
            c.execute("UPDATE runs SET status='unknown',updated=?,message='服务重启中断执行，需核对平台后处理' WHERE id=?",(now(),r['id']))
            c.execute("UPDATE tasks SET status='unknown',revision=revision+1,updated=? WHERE id=?",(now(),r['task_id']))
            event(c,r['task_id'],'上次执行被中断，结果未知；没有自动重试')

    def connection(c, aid):
        row=c.execute('SELECT * FROM connections WHERE account_id=?',(aid,)).fetchone()
        return dict(row) if row else dict(account_id=aid,adapter='manual',reference='',identity='',display_name='',cookie_digest='',status='unbound',checked_at=None,message='尚未连接')

    def options(c,tid):
        row=c.execute('SELECT value FROM task_options WHERE task_id=?',(tid,)).fetchone()
        return {'mode':'manual','category':None,'collection':'','landscape_cover_id':None,**(json.loads(row['value']) if row else {})}

    def asset_info(c, a):
        row=c.execute('SELECT value FROM asset_meta WHERE asset_id=?',(a['id'],)).fetchone()
        path=data/'files'/a['id'];info={}
        if row and path.exists():
            cached=json.loads(row['value'])
            if cached.get('mtime_ns')==path.stat().st_mtime_ns and cached.get('bytes')==path.stat().st_size:return cached
        if not path.exists():return {'error':'原始文件不存在'}
        h=hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
        info.update(sha256=h.hexdigest(),bytes=path.stat().st_size,mtime_ns=path.stat().st_mtime_ns)
        if a['kind']=='image':
            try:
                with Image.open(path) as image:
                    info.update(width=image.width,height=image.height,format=image.format)
                    image.verify()
            except Exception:info['error']='图片无法解析，请重新导出为 JPG / PNG / WebP'
        c.execute('INSERT OR REPLACE INTO asset_meta VALUES(?,?)',(a['id'],json.dumps(info)))
        return info

    def snapshot(c,tid):
        t=get(c,'tasks',tid);t['asset_ids']=json.loads(t['asset_ids']);a=get(c,'accounts',t['account_id']);o=options(c,tid);co=connection(c,a['id'])
        ids=list(t['asset_ids'])
        for id in [t.get('cover_id'),o.get('landscape_cover_id')]:
            if id and id not in ids:ids.append(id)
        assets=[get(c,'assets',id) for id in ids]
        for asset in assets:asset['metadata']=asset_info(c,asset)
        # Fingerprint excludes lifecycle revision/time, includes exact bytes + identity + execution mode.
        content={k:t[k] for k in ['id','package_id','account_id','format','title','body','tags','asset_ids','cover_id']}
        content.update(options=o,account_binding={k:co[k] for k in ['adapter','reference','identity','cookie_digest']},assets=[(x['id'],x['metadata'].get('sha256')) for x in assets])
        fingerprint=hashlib.sha256(json.dumps(content,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        return {'task':t,'account':a,'options':o,'connection':co,'assets':assets,'fingerprint':fingerprint,'files_root':str(data/'files'),'rules_version':RULES_VERSION}

    def preflight(c,tid):
        s=snapshot(c,tid);t=s['task'];a=s['account'];o=s['options'];co=s['connection'];rule=rules_for(a['platform'],t['format'])
        errors=[];warnings=[]
        if not rule:errors.append('没有该平台与内容类型的适配规则');rule={}
        try:
            raw=dict(t,asset_ids=json.dumps(t['asset_ids']));validate_task(c,raw)
        except Exception as e:errors.append(getattr(e,'description',str(e)))
        if o['mode'] not in rule.get('modes',[]):errors.append('该平台不支持所选交付方式')
        if len(t['title'])>rule.get('title_max',200):errors.append(f"标题超过适配器保守上限 {rule['title_max']} 字，请调整渠道标题")
        if rule.get('body_max') and len(t['body'])>rule['body_max']:errors.append(f"正文超过当前适配规则 {rule['body_max']} 字")
        if rule.get('image_max') and len(t['asset_ids'])>rule['image_max']:errors.append(f"图片数量超过当前适配规则 {rule['image_max']} 张")
        if rule.get('cover_recommended') and not t['cover_id']:warnings.append('尚未指定封面，平台可能自动选取；建议补充')
        if rule.get('category_required') and not o.get('category'):errors.append('B 站视频需要填写分区 ID（tid），请按当前平台后台核对')
        if rule.get('tags_required') and not t['tags'].strip():errors.append('B 站视频需要至少一个标签')
        for x in s['assets']:
            if x['package_id']!=t['package_id']:errors.append('素材不属于当前发布包')
            if x['metadata'].get('error'):errors.append(x['name']+'：'+x['metadata']['error'])
            if x['kind']=='video' and Path(x['name']).suffix.lower()!='.mp4':warnings.append('建议转成 MP4 后上传，以减少平台兼容问题')
        if t['format']=='article':
            for ref in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',t['body']):
                ref=ref.strip().split(' ')[0]
                if ref.startswith('asset://'):
                    if ref[8:] not in [x['id'] for x in s['assets'] if x['kind']=='image']:errors.append('正文引用的本机图片未被选为任务附件')
                elif not ref.startswith('https://'):errors.append('正文图片请使用 HTTPS 链接或 asset://附件ID，不能使用本机路径')
            if re.search(r'(src|href)\s*=\s*["\'](?:file:|/Users/|localhost|http://127\.)',t['body'],re.I):errors.append('正文包含本机文件链接，请改为成品附件引用')
        if o['mode']!='manual':
            if co['adapter']!=rule.get('adapter'):errors.append('账号连接方式与当前内容类型不匹配')
            if co['status']!='bound' or not co['identity']:errors.append('请先检查登录，并确认绑定对应账号')
            if co['adapter']=='wechatsync' and not bridge.status()['connected']:errors.append('Wechatsync 浏览器扩展未连接')
            if co['adapter']=='sau' and not adapters.runtime_status()['sau_installed']:errors.append('视频上传运行环境未安装')
            if co['adapter']=='sau':warnings.append('此上传器未提供可靠作品回执；执行后必须核对平台结果')
            if co.get('checked_at'):
                age=(datetime.now(timezone.utc)-datetime.fromisoformat(co['checked_at'])).total_seconds()
                if age>24*3600:errors.append('账号检查已超过 24 小时，请重新检查并确认绑定')
        else:warnings.append('人工交付：到点进入待交付，不会自动操作平台')
        if a['platform']=='douyin':warnings.append('抖音精选沿用抖音内容，不单独承诺精选分发')
        return {'ok':not errors,'errors':list(dict.fromkeys(errors)),'warnings':list(dict.fromkeys(warnings)),'fingerprint':s['fingerprint'],'revision':t['revision'],'mode':o['mode'],'adapter':rule.get('adapter'),'rules_version':RULES_VERSION,'snapshot':s}

    app.desk_preflight=preflight

    def enrich(result):
        with db() as c:
            for a in result['accounts']:
                co=connection(c,a['id']);a['connection']={k:v for k,v in co.items() if k!='cookie_digest'}
            for t in result['tasks']:t['options']=options(c,t['id'])
            for a in result['assets']:a['metadata']=asset_info(c,a)
            result['runs']=[dict(r) for r in c.execute('SELECT id,task_id,status,not_before,created,updated,message,receipt_url,attempt FROM runs ORDER BY created DESC LIMIT 200')]
            result['rules']=RULES;result['rules_version']=RULES_VERSION
            result['connectors']={'wechat':bridge.status(),'sau':adapters.runtime_status()}
            result['mode_labels']=MODE_LABELS
        return result
    app.desk_enrich=enrich

    def cancel_pending(c,tid):
        c.execute("UPDATE runs SET status='canceled',message='任务内容或排期已修改，批准已失效',updated=? WHERE task_id=? AND status='queued'",(now(),tid))
    app.desk_cancel_pending=cancel_pending

    @app.post('/api/bridge/settings')
    def bridge_settings():
        bridge.start();return jsonify(bridge.settings())

    @app.put('/api/bridge/settings')
    def configure_bridge():
        token=text(request.get_json().get('token',''),512,True)
        if len(token)<16:fail('请粘贴扩展生成的完整 Token')
        with db() as c:
            if c.execute("SELECT 1 FROM runs WHERE status IN ('queued','running')").fetchone():fail('请先取消等待中的任务，再更新连接口令',409)
        bridge.configure_token(token)
        return jsonify(ok=True)

    @app.get('/api/rules')
    def rules():return jsonify(version=RULES_VERSION,platforms=RULES,modes=MODE_LABELS)

    @app.patch('/api/accounts/<aid>/connection')
    def set_connection(aid):
        d=request.get_json()
        with db() as c:
            a=get(c,'accounts',aid);adapter=d.get('adapter','manual')
            allowed={'manual'}
            if a['platform'] in SAU_PLATFORMS:allowed.add('sau')
            if a['platform'] in WECHAT_PLATFORMS:allowed.add('wechatsync')
            if adapter not in allowed:fail('此平台没有对应连接器')
            if c.execute("SELECT 1 FROM runs JOIN tasks ON tasks.id=runs.task_id WHERE tasks.account_id=? AND runs.status IN ('queued','running')",(aid,)).fetchone():fail('此账号还有已批准或执行中的任务，请先取消排期',409)
            ref=text(d.get('reference',''),64)
            if adapter=='sau':adapters.cookie_path(a['platform'],ref)
            c.execute('DELETE FROM checks WHERE account_id=?',(aid,))
            c.execute("INSERT OR REPLACE INTO connections VALUES(?,?,?,'','','','unbound',NULL,'连接设置已保存，尚未验证账号')",(aid,adapter,ref))
        return jsonify(ok=True)

    @app.post('/api/accounts/<aid>/check')
    def check(aid):
        with db() as c:
            a=get(c,'accounts',aid);co=connection(c,aid)
            if c.execute("SELECT 1 FROM runs JOIN tasks ON tasks.id=runs.task_id WHERE tasks.account_id=? AND runs.status IN ('queued','running')",(aid,)).fetchone():fail('请先取消该账号待执行的排期，再重新检查绑定',409)
        try:result=adapters.check_account(a,co,bridge)
        except Exception as e:
            # Never forward untrusted upstream output that may include credentials.
            message=str(e) if isinstance(e,(ValueError,ConnectionError,TimeoutError)) else '连接检查失败，请确认运行环境、登录状态和浏览器扩展'
            with db() as c:c.execute("UPDATE connections SET status='unbound',message=? WHERE account_id=?",(message,aid))
            fail(message)
        id=uuid.uuid4().hex
        result['config']={'adapter':co['adapter'],'reference':co['reference']}
        with db() as c:
            current=connection(c,aid)
            if current['adapter']!=co['adapter'] or current['reference']!=co['reference']:fail('连接配置已经变化，请重新检查',409)
            c.execute('INSERT INTO checks VALUES(?,?,?,?)',(id,aid,json.dumps(result),now()))
            c.execute("UPDATE connections SET status='checked',message='已完成检查，请确认账号身份后绑定' WHERE account_id=?",(aid,))
        return jsonify(check_id=id,identity=result['identity'],display_name=result['display_name'],message='请核对平台账号；上传器只验证登录文件有效，不能自动核实显示名称' if co['adapter']=='sau' else '请确认这是本次要发布的账号')

    @app.post('/api/accounts/<aid>/bind')
    def bind(aid):
        d=request.get_json()
        if d.get('confirmed') is not True:fail('请确认平台账号身份')
        with db() as c:
            r=c.execute('SELECT * FROM checks WHERE id=? AND account_id=?',(d.get('check_id'),aid)).fetchone()
            if not r or (datetime.now(timezone.utc)-datetime.fromisoformat(r['created'])).total_seconds()>600:fail('检查结果已过期，请重新检查')
            info=json.loads(r['result']);co=connection(c,aid)
            if info.get('config')!={'adapter':co['adapter'],'reference':co['reference']}:fail('连接配置已经变化，请重新检查',409)
            if c.execute("SELECT 1 FROM runs JOIN tasks ON tasks.id=runs.task_id WHERE tasks.account_id=? AND runs.status IN ('queued','running')",(aid,)).fetchone():fail('请先取消待执行任务，再绑定账号',409)
            c.execute("UPDATE connections SET identity=?,display_name=?,cookie_digest=?,status='bound',checked_at=?,message='账号已检查并由你确认绑定' WHERE account_id=?",(info['identity'],info['display_name'],info['cookie_digest'],now(),aid))
        return jsonify(ok=True)

    @app.get('/api/accounts/<aid>/login-guide')
    def login_guide(aid):
        with db() as c:a=get(c,'accounts',aid);co=connection(c,aid)
        return jsonify(command=adapters.login_command(a['platform'],co['reference']) if co['adapter']=='sau' else '',message='在本机终端执行命令，亲自完成扫码或登录；完成后回到此处检查并绑定。')

    @app.post('/api/packages/<pid>/import-text')
    def import_text(pid):
        d=request.get_json()
        with db() as c:
            p=get(c,'packages',pid);a=get(c,'assets',d.get('asset_id'))
            if a['package_id']!=pid or Path(a['name']).suffix.lower() not in {'.md','.txt'}:fail('请选择此发布包内的 Markdown 或 TXT 文件')
            if a['size']>1024*1024:fail('正文文件不能超过 1 MB')
            if p['body'] and d.get('replace') is not True:fail('已有正文，勾选确认覆盖后再导入')
            try:body=(data/'files'/a['id']).read_text(encoding='utf-8-sig')
            except UnicodeDecodeError:fail('请将文本保存为 UTF-8 编码')
            body=text(body,50000,True)
            c.execute('UPDATE packages SET body=? WHERE id=?',(body,pid))
        return jsonify(ok=True,message='已导入发布包正文；已有渠道版本保持不变')

    @app.patch('/api/packages/<pid>')
    def update_package(pid):
        d=request.get_json()
        with db() as c:
            p=get(c,'packages',pid)
            c.execute('UPDATE packages SET title=?,body=?,notes=? WHERE id=?',(text(d.get('title',p['title']),200,True),text(d.get('body',p['body'])),text(d.get('notes',p['notes']),3000),pid))
        return jsonify(ok=True)

    @app.post('/api/packages/<pid>/distribute')
    def distribute(pid):
        d=request.get_json();targets=d.get('targets')
        if not isinstance(targets,list) or not 1<=len(targets)<=30:fail('请选择 1 至 30 个渠道任务')
        created=[];skipped=[]
        with db() as c:
            c.execute('BEGIN IMMEDIATE');p=get(c,'packages',pid)
            assets=[dict(x) for x in c.execute('SELECT * FROM assets WHERE package_id=? ORDER BY created,id',(pid,))]
            images=[x['id'] for x in assets if x['kind']=='image'];videos=[x['id'] for x in assets if x['kind']=='video']
            for target in targets:
                if not isinstance(target,dict):fail('任务格式错误')
                a=get(c,'accounts',target.get('account_id'));fmt=target.get('format')
                if not rules_for(a['platform'],fmt):fail('渠道不支持此类型')
                existing=c.execute("SELECT id FROM tasks WHERE package_id=? AND account_id=? AND format=? AND status<>'canceled'",(pid,a['id'],fmt)).fetchone()
                if existing:skipped.append(existing['id']);continue
                row=c.execute('SELECT value FROM package_meta WHERE package_id=?',(pid,)).fetchone()
                defaults=json.loads(row['value']).get('content_defaults',{}) if row else {}
                canceled=c.execute("SELECT * FROM tasks WHERE package_id=? AND account_id=? AND format=? AND status='canceled'",(pid,a['id'],fmt)).fetchone()
                if canceled:
                    c.execute("UPDATE tasks SET status='draft',title=?,body=?,tags=?,scheduled=NULL,revision=revision+1,updated=? WHERE id=?",(defaults.get('short_title',p['title']) if fmt=='video' else p['title'],p['body'],defaults.get('tags',''),now(),canceled['id']))
                    event(c,canceled['id'],'用户重新选择账号，下派任务')
                    created.append(canceled['id']);continue
                ids=images if fmt=='gallery' else ([defaults['video_id']] if defaults.get('video_id') in videos else videos[:1]) if fmt=='video' else []
                tid=uuid.uuid4().hex;ts=now()
                c.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(tid,pid,a['id'],fmt,defaults.get('short_title',p['title']) if fmt=='video' else p['title'],p['body'],defaults.get('tags',''),json.dumps(ids),defaults.get('cover_id') or (images[0] if images else None),'draft',None,'','',1,ts,ts))
                event(c,tid,'批量分发创建任务；自动选取素材，请预览后确认')
                created.append(tid)
        return jsonify(created=created,skipped=skipped),201

    def validated_options(c,t,d):
        a=get(c,'accounts',t['account_id'])
        mode=d.get('mode','manual');rule=rules_for(a['platform'],t['format'])
        if mode not in rule['modes']:fail('该平台不支持此交付方式')
        category=d.get('category')
        if category is not None and (type(category) is not int or not 1<=category<=99999):fail('分区 ID 需要是有效正整数')
        cover=d.get('landscape_cover_id') or None
        if cover:
            image=get(c,'assets',cover)
            if image['package_id']!=t['package_id'] or image['kind']!='image':fail('横版封面必须是本包图片')
        value={'mode':mode,'category':category,'collection':text(d.get('collection',''),100),'landscape_cover_id':cover}
        return value

    app.desk_validate_options=validated_options

    @app.put('/api/tasks/<tid>/options')
    def set_options(tid):
        d=request.get_json()
        with db() as c:
            c.execute('BEGIN IMMEDIATE');t=get(c,'tasks',tid);a=get(c,'accounts',t['account_id'])
            if t['revision']!=d.get('revision'):fail('任务已更新，请刷新',409)
            if t['status'] not in {'draft','ready','scheduled','queued','blocked'}:fail('此任务已经执行，不能修改')
            value=validated_options(c,t,d)
            mode=value['mode']
            cancel_pending(c,tid)
            c.execute('INSERT OR REPLACE INTO task_options VALUES(?,?)',(tid,json.dumps(value)))
            c.execute("UPDATE tasks SET status='draft',scheduled=NULL,revision=revision+1,updated=? WHERE id=?",(now(),tid))
            event(c,tid,'更新平台交付方式：'+MODE_LABELS[mode]+'；原批准失效')
        return jsonify(ok=True)

    @app.get('/api/tasks/<tid>/preflight')
    def inspect_response(tid):
        with db() as c:r=preflight(c,tid)
        r.pop('snapshot');return jsonify(r)

    @app.post('/api/tasks/<tid>/dispatch')
    def dispatch(tid):
        d=request.get_json()
        with db() as c:
            c.execute('BEGIN IMMEDIATE');r=preflight(c,tid);s=r['snapshot'];t=s['task'];mode=s['options']['mode']
            if t['revision']!=d.get('revision') or r['fingerprint']!=d.get('fingerprint'):fail('成品或连接已变化，请重新检查预览',409)
            if not r['ok']:return jsonify(error='发布检查未通过',errors=r['errors']),400
            if t['status'] not in {'draft','ready','scheduled','blocked'}:fail('任务已提交或需先核对结果，不能再次分发',409)
            if d.get('confirmed') is not True:fail('请确认当前账号、版本和交付方式')
            if mode=='publish' and d.get('publish_confirmed') is not True:fail('此操作可能公开发布，需要明确确认')
            schedule=d.get('scheduled')
            due=now()
            if schedule:
                try:
                    dt=datetime.fromisoformat(schedule.replace('Z','+00:00'))
                    if not dt.tzinfo or dt<=datetime.now(timezone.utc):raise ValueError()
                    due=dt.astimezone(timezone.utc).isoformat()
                except (ValueError,TypeError):fail('请选择未来时间')
            if mode=='manual':
                c.execute('UPDATE tasks SET status=?,scheduled=?,revision=revision+1,updated=? WHERE id=?',('scheduled' if schedule else 'ready',due if schedule else None,now(),tid))
                event(c,tid,'已确认成品，'+('按计划提醒人工交付' if schedule else '等待人工交付'))
                return jsonify(ok=True,mode='manual')
            existing=c.execute('SELECT id,status FROM runs WHERE task_id=? AND fingerprint=?',(tid,r['fingerprint'])).fetchone()
            if existing and existing['status'] not in {'canceled','blocked'}:return jsonify(error='此版本已有执行记录，请查看记录或核对后重试',run_id=existing['id']),409
            cancel_pending(c,tid)
            rid=existing['id'] if existing else uuid.uuid4().hex;ts=now()
            s['approved_at']=ts;s['approval']={'mode':mode,'publish_confirmed':d.get('publish_confirmed') is True}
            if existing:
                c.execute("UPDATE runs SET snapshot=?,status='queued',not_before=?,updated=?,attempt=attempt+1,message='重新批准此版本，保留历史操作记录' WHERE id=?",(json.dumps(s,ensure_ascii=False),due,ts,rid))
            else:
                c.execute('INSERT INTO runs(id,task_id,fingerprint,snapshot,status,not_before,created,updated) VALUES(?,?,?,?,?,?,?,?)',(rid,tid,r['fingerprint'],json.dumps(s,ensure_ascii=False),'queued',due,ts,ts))
            c.execute('UPDATE tasks SET status=?,scheduled=?,revision=revision+1,updated=? WHERE id=?',('scheduled' if schedule else 'queued',due if schedule else None,ts,tid))
            event(c,tid,'批准版本 '+r['fingerprint'][:10]+' · '+MODE_LABELS[mode]+(' · 已排期' if schedule else ' · 已加入执行队列'))
        return jsonify(ok=True,run_id=rid),202

    @app.post('/api/runs/<rid>/retry')
    def retry(rid):
        d=request.get_json()
        with db() as c:
            c.execute('BEGIN IMMEDIATE');run=get(c,'runs',rid);t=get(c,'tasks',run['task_id'])
            if run['status'] not in {'blocked','unknown'} or t['status'] not in {'blocked','unknown'}:fail('此任务不能重试')
            if d.get('checked') is not True or not text(d.get('note',''),3000,True):fail('请确认没有重复作品或草稿，并记录核对说明')
            old=json.loads(run['snapshot'])
            if old['options']['mode']=='publish' and d.get('publish_confirmed') is not True:fail('重试可能公开发布，请再次确认')
            r=preflight(c,t['id'])
            if not r['ok']:return jsonify(error='请先解决发布检查问题',errors=r['errors']),400
            if r['fingerprint']!=run['fingerprint']:fail('素材或连接已变化，请编辑任务并重新确认',409)
            c.execute("UPDATE runs SET status='queued',not_before=?,updated=?,attempt=attempt+1,message=? WHERE id=?",(now(),now(),'已人工核对后重试：'+d['note'],rid))
            c.execute("UPDATE tasks SET status='queued',revision=revision+1,updated=? WHERE id=?",(now(),t['id']))
            event(c,t['id'],'人工核对未重复后重试：'+d['note'])
        return jsonify(ok=True)

    @app.post('/api/runs/<rid>/reconcile')
    def reconcile_history(rid):
        d=request.get_json()
        labels={'not_found':'未找到本次草稿或作品','draft':'已找到平台草稿','review':'已找到送审内容','published':'已找到公开作品'}
        outcome=d.get('outcome')
        if outcome not in labels:fail('请选择平台核对结果')
        if d.get('checked') is not True:fail('请先实际核对平台')
        note=text(d.get('note',''),3000,True)
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            run=get(c,'runs',rid)
            if run['status']!='unknown':fail('此执行已核对或无需核对，请刷新',409)
            task=get(c,'tasks',run['task_id'])
            if task['status']=='unknown':fail('当前任务仍在等待核对，请使用记录平台结果入口',409)
            message='人工核对历史执行：'+labels[outcome]+' · '+note
            c.execute("UPDATE runs SET status='resolved',updated=?,message=? WHERE id=?",(now(),message,rid))
            event(c,task['id'],message+'；当前渠道版本未改变')
        return jsonify(ok=True)

    def process_one():
        if not worker_lock.acquire(False):return
        try:
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                row=c.execute("SELECT * FROM runs WHERE status='queued' AND not_before<=? ORDER BY not_before LIMIT 1",(now(),)).fetchone()
                if not row:return
                run=dict(row);s=json.loads(run['snapshot']);t=get(c,'tasks',run['task_id'])
                if t['status'] not in {'queued','scheduled'}:
                    c.execute("UPDATE runs SET status='canceled',updated=? WHERE id=?",(now(),run['id']));return
                current=preflight(c,t['id'])
                if not current['ok'] or current['fingerprint']!=run['fingerprint']:
                    message='执行前检查未通过：'+('；'.join(current['errors']) or '成品或账号连接已改变')
                    c.execute("UPDATE runs SET status='blocked',message=?,updated=? WHERE id=?",(message,now(),run['id']))
                    c.execute("UPDATE tasks SET status='blocked',note=?,revision=revision+1,updated=? WHERE id=?",(message,now(),t['id']))
                    event(c,t['id'],message);return
                c.execute("UPDATE runs SET status='running',updated=?,message='正在连接平台并提交已批准版本' WHERE id=?",(now(),run['id']))
                c.execute("UPDATE tasks SET status='running',revision=revision+1,updated=? WHERE id=?",(now(),t['id']))
                event(c,t['id'],'开始执行批准版本 '+run['fingerprint'][:10])
            directory=data/'runs'/run['id'];directory.mkdir(parents=True,exist_ok=True)
            try:result=adapters.execute(s,bridge,directory)
            except Exception:result={'status':'unknown','message':'执行中断或连接超时，结果未知，请核对平台。未自动重试'}
            status=result.get('status','unknown')
            if status not in {'blocked','unknown','delivered'}:status='unknown'
            url=str(result.get('receipt_url',''))[:2000]
            from urllib.parse import urlparse
            from server import PLATFORMS
            u=urlparse(url);domains=PLATFORMS[s['account']['platform']]['domains']
            if url and (u.scheme!='https' or u.username or u.password or not u.hostname or not any(u.hostname==d or u.hostname.endswith('.'+d) for d in domains)):url=''
            with db() as c:
                c.execute("UPDATE runs SET status=?,updated=?,message=?,receipt_url=? WHERE id=?",(status,now(),result['message'],url,run['id']))
                c.execute('UPDATE tasks SET status=?,note=?,revision=revision+1,updated=? WHERE id=?',(status,result['message'],now(),t['id']))
                event(c,t['id'],result['message'])
        finally:worker_lock.release()
    app.desk_process_one=process_one

    @app.get('/api/development-plan')
    def plan():
        return jsonify(version='0.2',input_contract={'article':'标题 + UTF-8 正文 / Markdown，图片用 HTTPS 或已选附件 asset://ID','gallery':'标题 + 简介 + 按顺序排列的图片','video':'标题 + 简介 + 一个视频，建议 MP4，封面独立选择'},stages=[
            {'title':'输入与批量分发','status':'implemented','detail':'成品包、正文导入、图片校验、按账号与类型生成独立任务'},
            {'title':'平台规则与发布检查','status':'implemented','detail':'平台内容类型、交付模式、标题与素材检查、分区与封面'},
            {'title':'连接与执行','status':'implemented_unverified','detail':'扩展桥接与上传器已接入；需真实账号登录后联调'},
            {'title':'可靠执行与结果','status':'implemented','detail':'批准快照、定时队列、重复保护、重启恢复、未知结果人工核对'},
            {'title':'真实平台验收','status':'needs_account','detail':'公众号、小红书、视频号、抖音、B站和知乎逐个平台验收'},
            {'title':'接入主站','status':'planned','detail':'复用主站认证、存储与部署方式，本轮保持本机运行'}])
