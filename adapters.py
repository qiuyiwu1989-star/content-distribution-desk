import base64
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from platform_rules import SAU_PLATFORMS, WECHAT_PLATFORMS

ROOT=Path(__file__).resolve().parent
SAU_ROOT=Path(os.environ.get('DESK_SAU_ROOT',ROOT/'integrations/social-auto-upload'))
SAU_PYTHON=Path(os.environ.get('DESK_SAU_PYTHON',ROOT/'.sau-venv/bin/python'))

def identity(info):
    value=info.get('uid') or info.get('userId') or info.get('username')
    return str(value) if value is not None else ''

def cookie_path(platform, reference):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',reference or ''):raise ValueError('账号连接标识只允许字母、数字、下划线和横线')
    return SAU_ROOT/'cookies'/f'{SAU_PLATFORMS[platform]}_{reference}.json'

def cookie_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ''

def runtime_status():
    return {'sau_installed':SAU_PYTHON.exists() and (SAU_ROOT/'conf.py').exists(), 'source_installed':(SAU_ROOT/'sau_cli.py').exists()}

def login_command(platform, reference):
    cookie_path(platform,reference)
    import shlex
    return shlex.join([str(SAU_PYTHON),str(SAU_ROOT/'sau_cli.py'),SAU_PLATFORMS[platform],'login','--account',reference,'--headed'])

def check_account(account, config, bridge):
    if config['adapter']=='wechatsync':
        info=bridge.request('checkAuth',{'platform':WECHAT_PLATFORMS[account['platform']]},60)
        if not isinstance(info,dict) or not info.get('isAuthenticated'):raise ValueError('该平台尚未登录，请在浏览器登录后重新检查')
        who=identity(info)
        if not who:raise ValueError('扩展未返回可核对的账号身份，暂不能绑定')
        return {'identity':who,'display_name':str(info.get('username') or who),'cookie_digest':''}
    if config['adapter']=='sau':
        p=cookie_path(account['platform'],config['reference'])
        if not p.exists():raise ValueError('没有此账号的登录文件，请先完成登录')
        cmd=[str(SAU_PYTHON),str(SAU_ROOT/'sau_cli.py'),SAU_PLATFORMS[account['platform']],'check','--account',config['reference']]
        r=subprocess.run(cmd,cwd=SAU_ROOT,capture_output=True,text=True,timeout=90)
        if r.returncode!=0 or 'valid' not in r.stdout.split():raise ValueError('账号登录检查未通过，请重新登录')
        # Upstream only returns validity, not the visible platform username.
        return {'identity':config['reference'],'display_name':account['name'],'cookie_digest':cookie_digest(p)}
    raise ValueError('人工交付无需连接检查')

def sau_command(snapshot, directory):
    t=snapshot['task'];a=snapshot['account'];o=snapshot['options'];assets=snapshot['assets'];config=snapshot['connection']
    p=SAU_PLATFORMS[a['platform']]
    cmd=[str(SAU_PYTHON),str(SAU_ROOT/'sau_cli.py'),p,'upload-note' if t['format']=='gallery' else 'upload-video','--account',config['reference']]
    paths={}
    for index,x in enumerate(assets):
        target=directory/f"{index+1:02d}-{x['name']}"
        shutil.copyfile(snapshot['files_root']+'/'+x['id'],target);paths[x['id']]=str(target)
    selected=[paths[x] for x in t['asset_ids']]
    if t['format']=='gallery':cmd+=['--images',*selected,'--note',t['body']]
    else:cmd+=['--file',selected[0],'--desc',t['body']]
    cmd+=['--title',t['title']]
    tags=','.join(x.lstrip('#') for x in re.split(r'[,，\s]+',t['tags']) if x)
    if tags:cmd+=['--tags',tags]
    if o['mode']=='draft':
        if a['platform']!='channels':raise ValueError('此上传器不支持该平台草稿模式')
        cmd+=['--draft']
    if t.get('cover_id') and t['format']=='video':cmd+=['--thumbnail',paths[t['cover_id']]]
    if o.get('landscape_cover_id') and a['platform'] in {'channels','douyin'}:cmd+=['--thumbnail-landscape',paths[o['landscape_cover_id']]]
    if a['platform']=='bilibili':cmd+=['--tid',str(o['category'])]
    if o.get('collection') and a['platform']=='channels':cmd+=['--collection',o['collection']]
    cmd+=['--headed']
    return cmd

def execute(snapshot, bridge, directory):
    a=snapshot['account'];c=snapshot['connection'];t=snapshot['task'];o=snapshot['options']
    for asset in snapshot['assets']:
        path=Path(snapshot['files_root'])/asset['id']
        if not path.exists() or cookie_digest(path)!=asset['metadata'].get('sha256'):
            return {'status':'blocked','message':'批准后的素材文件发生变化或丢失；没有提交内容'}
    adapter=c['adapter']
    if adapter=='wechatsync':
        pid=WECHAT_PLATFORMS[a['platform']]
        info=bridge.request('checkAuth',{'platform':pid},60)
        if not isinstance(info,dict) or not info.get('isAuthenticated') or identity(info)!=c['identity']:
            return {'status':'blocked','message':'浏览器当前账号与批准的账号不一致，已停止；没有提交内容'}
        article={'title':t['title'],'markdown':t['body']}
        if t.get('cover_id'):
            cover=next(x for x in snapshot['assets'] if x['id']==t['cover_id'])
            article['cover']='data:'+cover['mime']+';base64,'+base64.b64encode((Path(snapshot['files_root'])/cover['id']).read_bytes()).decode()
        # Resolve only explicitly attached images, no hidden filesystem reads.
        for asset in snapshot['assets']:
            if asset['kind']=='image':
                ref='asset://'+asset['id']
                if ref in article['markdown']:
                    uri='data:'+asset['mime']+';base64,'+base64.b64encode((Path(snapshot['files_root'])/asset['id']).read_bytes()).decode()
                    article['markdown']=article['markdown'].replace(ref,uri)
        response=bridge.request('syncArticle',{'platforms':[pid],'article':article},360)
        result=next((r for r in (response or {}).get('results',[]) if r.get('platform')==pid),None)
        if not result or not result.get('success'):
            return {'status':'unknown','message':'扩展没有给出可确认的成功结果。请先核对平台草稿，避免重复提交'}
        if result.get('draftOnly') is True:
            return {'status':'delivered','message':'扩展返回草稿保存成功；请打开平台检查排版','receipt_url':result.get('postUrl','')}
        return {'status':'unknown','message':'扩展返回成功，但未明确声明草稿状态；请核对平台','receipt_url':result.get('postUrl','')}
    if adapter=='sau':
        p=cookie_path(a['platform'],c['reference'])
        if not c.get('cookie_digest') or cookie_digest(p)!=c['cookie_digest']:
            return {'status':'blocked','message':'登录文件发生变化或缺失，请重新检查并绑定账号；没有提交内容'}
        cmd=sau_command(snapshot,directory)
        # Upstream logs stay in a private local file; never include them in API responses.
        with open(directory/'private-output.log','wb') as out:
            os.chmod(directory/'private-output.log',0o600)
            try:
                r=subprocess.Popen(cmd,cwd=SAU_ROOT,stdout=out,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
                code=r.wait(timeout=900)
            except subprocess.TimeoutExpired:
                try:os.killpg(r.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                r.wait()
                return {'status':'unknown','message':'上传器超时，平台结果未知。请先核对平台，禁止直接重复执行'}
        if code!=0:return {'status':'unknown','message':f'上传器退出码 {code}，可能已产生平台内容。请先核对平台结果'}
        return {'status':'unknown','message':'上传器执行结束，但没有结构化平台回执。请核对草稿或作品链接后回填；未标记已发布'}
    return {'status':'blocked','message':'未配置自动执行器，请使用人工交付'}
