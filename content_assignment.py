"""Account-neutral content defaults and explicit manual publication registration."""
import json,uuid
from datetime import datetime, timezone
from flask import request,jsonify

def install(app,db,get,fail,text,now,event):
    from pathlib import Path
    with db() as c:app.desk_content_data=Path(c.execute('PRAGMA database_list').fetchone()[2]).parent
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS content_trash(package_id TEXT PRIMARY KEY REFERENCES packages(id),deleted_at TEXT NOT NULL,was_archived INTEGER NOT NULL DEFAULT 0)')

    # Recover missing content fields from legacy task storage without selecting an account.
    with db() as c:
        migration_history=app.desk_publication_progress(c) if hasattr(app,'desk_publication_progress') else {}
        for package in c.execute('SELECT * FROM packages').fetchall():
            row=c.execute('SELECT value FROM package_meta WHERE package_id=?',(package['id'],)).fetchone()
            meta=json.loads(row['value']) if row else {}
            defaults=meta.get('content_defaults',{})
            candidates=c.execute("SELECT * FROM tasks WHERE package_id=? ORDER BY (status='canceled'),updated DESC,id",(package['id'],)).fetchall()
            candidate=next((t for t in candidates if t['body']==package['body']),candidates[0] if candidates else None)
            if not candidate:continue
            assets={a['id']:dict(a) for a in c.execute('SELECT * FROM assets WHERE package_id=?',(package['id'],))}
            changed=False;filled_tags=False
            legacy_tags=candidate['tags']
            if legacy_tags:
                tokens=legacy_tags.split()
                for required in ['#造物云','#FDE']:
                    if required not in tokens:tokens.append(required)
                legacy_tags=' '.join(tokens)
            values={'tags':legacy_tags,'short_title':candidate['title']}
            ids=json.loads(candidate['asset_ids'])
            values['video_id']=next((aid for aid in ids if aid in assets and assets[aid]['kind']=='video'),None)
            values['cover_id']=candidate['cover_id'] if candidate['cover_id'] in assets else None
            for key,value in values.items():
                if key not in defaults and value is not None:
                    defaults[key]=value;changed=True
                    if key=='tags':filled_tags=True
            if changed:
                meta.update(content_defaults=defaults,legacy_content_source_task=candidate['id'],legacy_tag_baseline=candidate['tags'])
                c.execute('INSERT OR REPLACE INTO package_meta VALUES(?,?)',(package['id'],json.dumps(meta)))
                latest=next((x for x in reversed(migration_history.get(candidate['id'],[])) if x['revision']==candidate['revision'] and x['account_id']==candidate['account_id']),None)
                if filled_tags and candidate['status']=='draft' and candidate['tags']!=defaults.get('tags') and not (latest and latest['status']=='published'):
                    c.execute('UPDATE tasks SET tags=?,revision=revision+1,updated=? WHERE id=?',(defaults['tags'],now(),candidate['id']))
                    event(c,candidate['id'],'话题结构补回内容工作台；未发布任务同步规范话题')

    @app.get('/api/packages/<pid>/content-bundle')
    def content_bundle(pid):
        import io,zipfile,hashlib
        from pathlib import Path
        from flask import send_file
        with db() as c:
            p=get(c,'packages',pid)
            row=c.execute('SELECT value FROM package_meta WHERE package_id=?',(pid,)).fetchone()
            meta=json.loads(row['value']) if row else {};defaults=meta.get('content_defaults',{})
            assets=[dict(a) for a in c.execute('SELECT * FROM assets WHERE package_id=? ORDER BY created,id',(pid,))]
            library=c.execute('SELECT b.name,l.sequence FROM library_packages l JOIN library_batches b ON b.id=l.batch_id WHERE l.package_id=?',(pid,)).fetchone()
        # The server owns the configured asset directory; client paths are never opened.
        root=app.desk_content_data
        roles={};files=[];seen={};attachments=[]
        for a in assets:
            path=root/'files'/a['id']
            if not path.is_file():fail('素材文件缺失，无法完整导出',409)
            relative='content/'+a['id']+Path(a['name']).suffix
            h=hashlib.sha256()
            with path.open('rb') as source:
                for chunk in iter(lambda:source.read(1024*1024),b''):h.update(chunk)
            digest=h.hexdigest()
            if digest in seen:relative=seen[digest]
            value={'path':relative,'name':a['name'],'sha256':digest,'bytes':a['size'],'kind':a['kind']}
            attachments.append(value)
            if digest not in seen:
                files.append((path,relative,value));seen[digest]=relative
            for role in ['video','cover']:
                if a['id']==defaults.get(role+'_id'):roles[role]=value
        item={'content_id':next((line.split('=',1)[1] for line in p['notes'].splitlines() if line.startswith('content_id=')),'desk/'+pid),'sequence':library['sequence'] if library and library['sequence'] else 1,'title':p['title'],'short_title':defaults.get('short_title',p['title']),'body':p['body'],'tags':[tag.lstrip('#') for tag in defaults.get('tags','').split()],'assets':{'video':roles.get('video'),'cover':roles.get('cover')},'attachments':attachments,'publication_state':'unpublished','source':{'desk_package_id':pid},'revision':str(meta.get('copy_revision',0))}
        manifest={'schema':'distribution.delivery.v1','storage_profile':'portable','batch_id':'desk-export','batch_name':library['name'] if library else '内容导出','created_at':now(),'items':[item]}
        import tempfile,os
        temporary=tempfile.NamedTemporaryFile(suffix='.zip',delete=False);name=temporary.name;temporary.close()
        try:
            with zipfile.ZipFile(name,'w',zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('batch.json',json.dumps(manifest,ensure_ascii=False,indent=2))
                for path,relative,_ in files:archive.write(path,relative)
            # Read a completed archive into the response file handle, then unlink safely on Unix.
            result=send_file(name,mimetype='application/zip',as_attachment=True,download_name='内容-'+pid[:8]+'.zip')
            result.call_on_close(lambda:os.path.exists(name) and os.unlink(name))
            return result
        except Exception:
            os.unlink(name);raise

    def trash_contents(ids):
        if not isinstance(ids,list) or not 1<=len(ids)<=1000 or any(not isinstance(x,str) for x in ids) or len(ids)!=len(set(ids)):fail('请选择要删除的内容')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            for pid in ids:
                get(c,'packages',pid)
                if c.execute("SELECT 1 FROM tasks WHERE package_id=? AND status='running'",(pid,)).fetchone():fail('所选内容正在执行，请完成后再删除',409)
            history=app.desk_publication_progress(c) if hasattr(app,'desk_publication_progress') else {}
            for pid in ids:
                if c.execute('SELECT 1 FROM content_trash WHERE package_id=?',(pid,)).fetchone():continue
                old=c.execute('SELECT * FROM library_packages WHERE package_id=?',(pid,)).fetchone()
                c.execute('INSERT INTO content_trash VALUES(?,?,?)',(pid,now(),old['archived'] if old else 0))
                c.execute("INSERT INTO library_packages VALUES(?,'unassigned',NULL,1,NULL) ON CONFLICT(package_id) DO UPDATE SET archived=1",(pid,))
                for t in c.execute('SELECT * FROM tasks WHERE package_id=?',(pid,)).fetchall():
                    latest=next((x for x in reversed(history.get(t['id'],[])) if x['revision']==t['revision'] and x['account_id']==t['account_id']),None)
                    if t['status'] in {'draft','ready','scheduled','queued','blocked','failed'} and not (latest and latest['status']=='published'):
                        app.desk_cancel_pending(c,t['id'])
                        c.execute("UPDATE tasks SET status='canceled',scheduled=NULL,revision=revision+1,updated=? WHERE id=?",(now(),t['id']))
                        event(c,t['id'],'内容已移入回收站；取消待发布安排')
        return jsonify(ok=True,deleted=ids)

    @app.delete('/api/packages/<pid>')
    def delete_content(pid):return trash_contents([pid])

    @app.post('/api/library/trash')
    def delete_contents():return trash_contents((request.get_json() or {}).get('package_ids'))

    @app.get('/api/library/trash')
    def list_trash():
        with db() as c:
            return jsonify(items=[dict(r) for r in c.execute('SELECT p.id,p.title,t.deleted_at FROM content_trash t JOIN packages p ON p.id=t.package_id ORDER BY t.deleted_at DESC')])

    @app.post('/api/packages/<pid>/restore')
    def restore_content(pid):
        with db() as c:
            get(c,'packages',pid);old=c.execute('SELECT * FROM content_trash WHERE package_id=?',(pid,)).fetchone()
            if old:
                c.execute('UPDATE library_packages SET archived=? WHERE package_id=?',(old['was_archived'],pid))
                c.execute('DELETE FROM content_trash WHERE package_id=?',(pid,))
        return jsonify(ok=True)

    @app.before_request
    def protect_deleted_content():
        if request.method not in {'POST','PUT','PATCH'}:return
        import re
        m=re.match(r'^/api/packages/([^/]+)(?:/(.*))?$',request.path)
        pid=m.group(1) if m else None
        if m and m.group(2)=='restore':return
        if request.path=='/api/tasks':pid=(request.get_json(silent=True) or {}).get('package_id')
        task_match=re.match(r'^/api/tasks/([^/]+)',request.path)
        if task_match:
            with db() as c:pid=get(c,'tasks',task_match.group(1))['package_id']
        if pid:
            with db() as c:
                if c.execute('SELECT 1 FROM content_trash WHERE package_id=?',(pid,)).fetchone():fail('内容已删除，请先从回收站恢复',409)

    @app.route('/api/packages/<pid>/defaults',methods=['GET','PUT'])
    def defaults(pid):
        with db() as c:
            get(c,'packages',pid)
            row=c.execute('SELECT value FROM package_meta WHERE package_id=?',(pid,)).fetchone()
            meta=json.loads(row['value']) if row else {}
            if request.method=='PUT':
                d=request.get_json() or {}
                if set(d)-{'tags','video_id','cover_id','short_title'}:fail('通用内容不接受账号或渠道字段')
                previous=meta.get('content_defaults',{})
                value={**previous,'tags':text(d.get('tags',previous.get('tags','')),500),'video_id':d.get('video_id',previous.get('video_id')),'cover_id':d.get('cover_id',previous.get('cover_id'))}
                for field,kind in [('video_id','video'),('cover_id','image')]:
                    if value[field]:
                        a=get(c,'assets',value[field])
                        if a['package_id']!=pid or a['kind']!=kind:fail('素材不属于此内容或类型不正确')
                if 'short_title' in d:value['short_title']=text(d['short_title'],16,True)
                meta['content_defaults']=value
                c.execute('INSERT OR REPLACE INTO package_meta VALUES(?,?)',(pid,json.dumps(meta)))
            return jsonify(meta.get('content_defaults',{}))

    @app.route('/api/packages/<pid>/copy',methods=['GET','PATCH'])
    def edit_copy(pid):
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            p=get(c,'packages',pid)
            row=c.execute('SELECT value FROM package_meta WHERE package_id=?',(pid,)).fetchone()
            meta=json.loads(row['value']) if row else {}
            defaults=meta.get('content_defaults',{})
            current={'video_id':defaults.get('video_id'),'cover_id':defaults.get('cover_id'),'short_title':defaults.get('short_title',p['title']),'body':p['body'],'tags':defaults.get('tags',''),'revision':meta.get('copy_revision',0)}
            if request.method=='GET':return jsonify(current)
            d=request.get_json() or {}
            if set(d)-{'short_title','body','tags','revision','video_id','cover_id'}:fail('文案字段不正确')
            if type(d.get('revision')) is not int or d['revision']!=current['revision']:fail('文案已被其他窗口修改，请重新读取',409)
            title=text(d.get('short_title',current['short_title']),16,True)
            body=text(d.get('body',current['body']),50000)
            tags=text(d.get('tags',current['tags']),500)
            if (title,body,tags,d.get('video_id',current['video_id']),d.get('cover_id',current['cover_id']))==(current['short_title'],current['body'],current['tags'],current['video_id'],current['cover_id']):return jsonify(**current,updated_tasks=[],preserved_tasks=[])
            for field,kind in [('video_id','video'),('cover_id','image')]:
                if field in d:
                    if d[field]:
                        asset=get(c,'assets',d[field])
                        if asset['package_id']!=pid or asset['kind']!=kind:fail('素材不属于此内容或类型不正确')
                    defaults[field]=d[field] or None
            defaults.update(short_title=title,tags=tags)
            meta.update(content_defaults=defaults,copy_revision=current['revision']+1)
            c.execute('UPDATE packages SET body=? WHERE id=?',(body,pid))
            c.execute('INSERT OR REPLACE INTO package_meta VALUES(?,?)',(pid,json.dumps(meta)))
            updated=[];preserved=[]
            history=app.desk_publication_progress(c) if hasattr(app,'desk_publication_progress') else {}
            for t in c.execute('SELECT * FROM tasks WHERE package_id=?',(pid,)).fetchall():
                publication=next((x for x in reversed(history.get(t['id'],[])) if x['revision']==t['revision'] and x['account_id']==t['account_id']),None)
                if t['status'] not in {'draft','canceled','ready','scheduled','queued','blocked'} or publication and publication['status']=='published':
                    preserved.append(t['id']);continue
                # Keep a channel-specific edit; refresh fields that still inherit the library copy.
                new_title=title if t['format']=='video' and t['title'] in {p['title'],current['short_title']} else t['title']
                new_body=body if t['body']==current['body'] else t['body']
                new_tags=tags if t['tags'] in {current['tags'],meta.get('legacy_tag_baseline',current['tags'])} else t['tags']
                ids=json.loads(t['asset_ids'])
                new_ids=([defaults['video_id']] if defaults.get('video_id') else []) if t['format']=='video' and ids==([current['video_id']] if current['video_id'] else []) else ids
                new_cover=defaults.get('cover_id') if t['cover_id']==current['cover_id'] else t['cover_id']
                if new_body!=body or new_tags!=tags or (t['format']=='video' and new_title!=title):preserved.append(t['id'])
                if (new_title,new_body,new_tags,new_ids,new_cover)==(t['title'],t['body'],t['tags'],ids,t['cover_id']):
                    if t['id'] not in preserved and (t['title'],t['body'],t['tags'])!=(title,body,tags):preserved.append(t['id'])
                    continue
                app.desk_cancel_pending(c,t['id'])
                status='canceled' if t['status']=='canceled' else 'draft'
                c.execute('UPDATE tasks SET title=?,body=?,tags=?,asset_ids=?,cover_id=?,status=?,scheduled=NULL,revision=revision+1,updated=? WHERE id=?',(new_title,new_body,new_tags,json.dumps(new_ids),new_cover,status,now(),t['id']))
                event(c,t['id'],'内容库文案更新；未执行任务已同步')
                updated.append(t['id'])
            return jsonify(video_id=defaults.get('video_id'),cover_id=defaults.get('cover_id'),short_title=title,body=body,tags=tags,revision=meta['copy_revision'],updated_tasks=updated,preserved_tasks=preserved)

    @app.post('/api/packages/<pid>/publication-record')
    def record(pid):
        from server import PLATFORMS
        d=request.get_json() or {};rid=d.get('request_id')
        try:rid=str(uuid.UUID(rid))
        except (ValueError,TypeError,AttributeError):fail('登记请求编号不正确')
        published_at=text(d.get('published_at',''),100,True)
        try:
            date=datetime.fromisoformat(published_at.replace('Z','+00:00'))
            if date.tzinfo is None or date>datetime.now(timezone.utc):raise ValueError()
        except ValueError:fail('请选择有效的实际发布时间')
        url=text(d.get('url',''),2000)
        if url and not url.startswith('https://'):fail('作品链接应为 https 地址')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');p=get(c,'packages',pid);a=get(c,'accounts',d.get('account_id'));fmt=d.get('format')
            if fmt not in PLATFORMS[a['platform']]['formats']:fail('请选择该平台支持的内容类型')
            prior=c.execute('SELECT * FROM tasks WHERE id=?',(rid,)).fetchone()
            if prior:
                if prior['package_id']!=pid or prior['account_id']!=a['id'] or prior['format']!=fmt:fail('请求编号已用于其他记录',409)
                return jsonify(id=rid)
            existing=c.execute('SELECT * FROM tasks WHERE package_id=? AND account_id=? AND format=?',(pid,a['id'],fmt)).fetchone()
            marker='登记编号：'+rid
            if existing and marker in existing['note']:
                return jsonify(id=existing['id'])
            if existing and existing['status'] not in {'draft','canceled'}:
                fail('该账号已有执行或发布记录，请在原任务核对结果',409)
            row=c.execute('SELECT value FROM package_meta WHERE package_id=?',(pid,)).fetchone()
            defaults=json.loads(row['value']).get('content_defaults',{}) if row else {}
            note=marker+'；人工补登记；实际发布时间：'+published_at+'；'+text(d.get('note',''),1000)
            ids=[defaults['video_id']] if fmt=='video' and defaults.get('video_id') else []
            if existing:
                tid=existing['id'];c.execute("UPDATE tasks SET status='published',url=?,note=?,revision=revision+1,updated=? WHERE id=?",(url,note,now(),tid))
                event(c,tid,note+'；未调用平台发布')
                return jsonify(id=tid),201
            ts=now();c.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(rid,pid,a['id'],fmt,p['title'],p['body'],defaults.get('tags',''),json.dumps(ids),defaults.get('cover_id'),'published',None,url,note,1,ts,ts))
            event(c,rid,note+'；未调用平台发布')
        return jsonify(id=rid),201
