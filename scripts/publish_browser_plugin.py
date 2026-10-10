#!/usr/bin/env python3
"""Publish immutable browser-extension ZIPs into the local download catalog."""
import argparse,hashlib,io,json,re,zipfile,os,tempfile
from pathlib import Path
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/'static/browser-plugins'
def write_json(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 fd,name=tempfile.mkstemp(dir=str(path.parent),prefix='.catalog-',suffix='.tmp')
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as stream:json.dump(data,stream,ensure_ascii=False,indent=2)
  os.replace(name,path)
 finally:
  if os.path.exists(name):os.unlink(name)
def build(source):
 output=io.BytesIO()
 with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
  for path in sorted(source.rglob('*')):
   relative=path.relative_to(source)
   if not path.is_file() or any(part.startswith('.') or part in {'tests','node_modules','__pycache__'} for part in relative.parts):continue
   if path.is_symlink():raise ValueError('发布包不能包含符号链接')
   if path.suffix.lower() not in {'.js','.html','.css','.json','.md','.png','.jpg','.jpeg','.svg','.webp'}:continue
   info=zipfile.ZipInfo(source.name+'/'+relative.as_posix(),(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16
   archive.writestr(info,path.read_bytes())
 return output.getvalue()
def inspect(blob):
 if len(blob)>20*1024*1024:raise ValueError('插件发布包超过20MB')
 with zipfile.ZipFile(io.BytesIO(blob)) as archive:
  for entry in archive.infolist():
   path=Path(entry.filename)
   if path.is_absolute() or '..' in path.parts or '\\' in entry.filename:raise ValueError('归档路径不正确')
  manifests=[name for name in archive.namelist() if name.endswith('/manifest.json') or name=='manifest.json']
  if len(manifests)!=1:raise ValueError('发布包必须有一个manifest.json')
  manifest=json.loads(archive.read(manifests[0]));version=manifest.get('version','')
  if not re.fullmatch(r'\d+(?:\.\d+){1,3}',version):raise ValueError('Chrome插件版本号不正确')
  if any(int(part)>65535 for part in version.split('.')):raise ValueError('版本号超出Chrome范围')
  prefix=manifests[0][:-len('manifest.json')]
  refs=[manifest.get('background',{}).get('service_worker'),manifest.get('action',{}).get('default_popup')]
  for content in manifest.get('content_scripts',[]):refs.extend(content.get('js',[]));refs.extend(content.get('css',[]))
  for ref in refs:
   if ref and prefix+ref not in archive.namelist():raise ValueError('插件引用文件缺失：'+ref)
  return manifest

def _publish_locked(plugin_id,blob,notes,name=None,recommend=False,public=PUBLIC):
 if not re.fullmatch(r'[a-z][a-z0-9-]{1,63}',plugin_id):raise ValueError('插件标识不正确')
 manifest=inspect(blob);version=manifest['version'];digest=hashlib.sha256(blob).hexdigest()
 index=public/'catalog.json';catalog=json.loads(index.read_text()) if index.exists() else {'schema':'desk.browser-plugins.v1','plugins':[]}
 plugin=next((p for p in catalog['plugins'] if p['id']==plugin_id),None)
 target=public/'releases'/plugin_id/(version+'.zip')
 if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=digest:raise ValueError('同一版本已有不同内容，必须提升manifest版本，不能覆盖旧包')
 old=next((r for r in plugin['releases'] if r['version']==version),None) if plugin else None
 if old and old['sha256']!=digest:raise ValueError('目录中的同版本指纹不同，禁止覆盖')
 if old and (old['notes']!=notes or name and plugin['name']!=name):raise ValueError('已发布版本的说明不可静默覆盖；请创建新版本或单独追加勘误')
 if not plugin:
  plugin={'id':plugin_id,'name':name or manifest['name'],'description':manifest.get('description',''),'current_version':None,'releases':[]};catalog['plugins'].append(plugin)
 if not target.exists():
  target.parent.mkdir(parents=True,exist_ok=True)
  fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
  with os.fdopen(fd,'wb') as stream:stream.write(blob)
 if not old:
  plugin['releases'].append({'version':version,'archived_at':datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),'url':'/static/browser-plugins/releases/'+plugin_id+'/'+version+'.zip','sha256':digest,'bytes':len(blob),'notes':notes,'minimum_chrome_version':manifest.get('minimum_chrome_version',''),'permissions':manifest.get('permissions',[])})
 plugin['releases'].sort(key=lambda r:tuple(int(part) for part in r['version'].split('.')),reverse=True)
 if recommend:plugin['current_version']=version
 write_json(index,catalog)
 return {'id':plugin_id,'version':version,'sha256':digest,'current_version':plugin['current_version']}
def publish(plugin_id,blob,notes,name=None,recommend=False,public=PUBLIC):
 import fcntl
 public.mkdir(parents=True,exist_ok=True)
 with (public/'.publish.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  return _publish_locked(plugin_id,blob,notes,name,recommend,public)
def install_local(public=PUBLIC):
 import shutil,subprocess
 project=Path.home()/'Applications/内容分发台.app/Contents/Resources/Project'
 if not project.is_dir():raise ValueError('未找到本机已安装分发台，请使用项目打包流程')
 target=project/'static/browser-plugins';target.mkdir(parents=True,exist_ok=True)
 for source in public.rglob('*.zip'):
  destination=target/source.relative_to(public)
  if destination.exists() and hashlib.sha256(destination.read_bytes()).digest()!=hashlib.sha256(source.read_bytes()).digest():raise ValueError('已安装目录存在同版本不同包，禁止覆盖')
 for source in public.rglob('*'):
  if not source.is_file() or source.name.startswith('.'):continue
  destination=target/source.relative_to(public);destination.parent.mkdir(parents=True,exist_ok=True)
  if source.name=='catalog.json' and destination.exists():
   # Keep catalog snapshots next to local download metadata, outside the runtime catalog.
   backup=Path.home()/'Library/Application Support/内容分发台/backups/plugin-catalogs'
   backup.mkdir(parents=True,exist_ok=True)
   shutil.copy2(destination,backup/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.json'))
  shutil.copy2(source,destination)
 subprocess.run(['codesign','--force','--deep','--sign','-',str(project.parents[2])],check=True,capture_output=True)
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--id',default='channels-assistant');parser.add_argument('--name');group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--source',type=Path);group.add_argument('--archive',type=Path);parser.add_argument('--notes-file',required=True,type=Path);parser.add_argument('--recommend',action='store_true');parser.add_argument('--install-local',action='store_true');args=parser.parse_args()
 blob=args.archive.read_bytes() if args.archive else build(args.source)
 result=publish(args.id,blob,args.notes_file.read_text().strip(),args.name,args.recommend)
 if args.install_local:install_local()
 print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
