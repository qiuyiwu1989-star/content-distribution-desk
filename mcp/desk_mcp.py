#!/usr/bin/env python3
"""Stdio MCP bridge using the desk environment; protocol only on stdout."""
import json, sys, subprocess
from urllib.parse import quote
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from desk_cli import DeskClient
from library_import import run as import_library
from agent_onboarding import INSTRUCTIONS
TOOLS=[
 {'name':'desk_status','description':'读取本机内容库批次和数量，不写入','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
 {'name':'preview_production_batch','description':'通过现有生产交付脚本导出并预演批次，不写分发库；会更新生产发布包','inputSchema':{'type':'object','properties':{'batch':{'type':'string'},'only':{'type':'string'}},'required':['batch'],'additionalProperties':False}},
 {'name':'sync_production_batch','description':'导出并导入已登记生产批次，创建指定账号的待完善任务，不提交发布','inputSchema':{'type':'object','properties':{'batch':{'type':'string'},'account':{'type':'string'},'only':{'type':'string'}},'required':['batch','account'],'additionalProperties':False}}]
TOOLS.extend([{'name':name,'description':description,'inputSchema':{'type':'object','properties':{'manifest_path':{'type':'string'}},'required':['manifest_path'],'additionalProperties':False}} for name,description in [('preview_library_batch','检查任意批次清单与素材，不写入'),('import_library_batch','导入纯内容库，保留批次顺序与交付元数据，不创建渠道任务')]])
TOOLS.extend([
 {'name':'desk_list_skills','description':'读取技能原始文件的最新版本与同步状态','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
 {'name':'desk_read_skill','description':'读取当前技能全文与参考文件','inputSchema':{'type':'object','properties':{'skill_id':{'type':'string'}},'required':['skill_id'],'additionalProperties':False}},
 {'name':'desk_skill_requests','description':'查看待接单与已记录的技能任务','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
 {'name':'desk_skill_request','description':'读取任务固定的技能快照、内容和用户要求','inputSchema':{'type':'object','properties':{'request_id':{'type':'string'}},'required':['request_id'],'additionalProperties':False}},
 {'name':'desk_create_skill_request','description':'为指定内容创建待 Agent 接单任务；不自动运行或发布','inputSchema':{'type':'object','properties':{'skill_id':{'type':'string'},'skill_revision':{'type':'string'},'idempotency_key':{'type':'string'},'package_ids':{'type':'array','items':{'type':'string'},'minItems':1,'maxItems':200},'instruction':{'type':'string'}},'required':['skill_id','skill_revision','idempotency_key','package_ids','instruction'],'additionalProperties':False}},
 {'name':'desk_update_skill_request','description':'Agent 接单或回报结果；仅待接单任务可取消，运行任务由接单者回报','inputSchema':{'type':'object','properties':{'request_id':{'type':'string'},'status':{'type':'string','enum':['running','completed','failed','canceled']},'worker':{'type':'string'},'summary':{'type':'string'}},'required':['request_id','status'],'additionalProperties':False}}
])
TOOLS.extend([
 {'name':'desk_cover_templates','description':'读取封面设计能力规范与模板库，包含真实示例和可复制要求；只读','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
 {'name':'desk_cover_template','description':'按稳定ID读取封面模板规则、版本、示例和skill全文；只读','inputSchema':{'type':'object','properties':{'template_id':{'type':'string'}},'required':['template_id'],'additionalProperties':False}}
])
TOOLS.append({'name':'find_brand_assets','description':'按分类与关键词查找本机品牌个人素材，返回使用备注和文件地址','inputSchema':{'type':'object','properties':{'q':{'type':'string'},'category':{'type':'string','enum':['logo','portrait','brand','other']}},'additionalProperties':False}})
TOOLS.append({'name':'desk_content_history','description':'读取内容的渠道去向、发布记录、批注与策划评价数据；只读','inputSchema':{'type':'object','properties':{'package_id':{'type':'string'}},'required':['package_id'],'additionalProperties':False}})
TOOLS.append({'name':'desk_add_content_record','description':'为内容写入策划、评价或数据记录，保留作者与来源；不改变审核或发布状态','inputSchema':{'type':'object','properties':{'package_id':{'type':'string'},'kind':{'type':'string','enum':['planning','evaluation','metrics']},'author':{'type':'string'},'note':{'type':'string'},'url':{'type':'string'}},'required':['package_id','kind','author','note'],'additionalProperties':False}})
TOOLS.extend([
 {'name':'desk_skill_history','description':'读取技能版本历史及有证据的历史补录','inputSchema':{'type':'object','properties':{'skill_id':{'type':'string'}},'required':['skill_id'],'additionalProperties':False}},
 {'name':'desk_skill_version','description':'读取指定技能版本及相对父版本的文件差异','inputSchema':{'type':'object','properties':{'skill_id':{'type':'string'},'version_id':{'type':'string'}},'required':['skill_id','version_id'],'additionalProperties':False}},
 {'name':'desk_edit_skill','description':'保存一个技能文本文件为新版本；必须记录真实署名、原因及读取时的版本。不可代签用户，不发布内容。','inputSchema':{'type':'object','properties':{**{k:{'type':'string'} for k in ['skill_id','expected_revision','expected_version_id','path','content','actor_name','reason','source_ref']},'actor_type':{'type':'string','enum':['human','agent']}},'required':['skill_id','expected_revision','expected_version_id','path','content','actor_name','actor_type','reason'],'additionalProperties':False}}
])
TOOLS.extend([
 {'name':'desk_source_provenance','description':'读取指定内容和视频的已登记原片区间；缺记录返回空，不猜来源','inputSchema':{'type':'object','properties':{'package_id':{'type':'string'},'video_id':{'type':'string'}},'required':['package_id','video_id'],'additionalProperties':False}},
 {'name':'desk_check_edit_plan','description':'只读检查原速硬切方案的原片边界、输出顺序、时长与重复区间；不代替语义和听审','inputSchema':{'type':'object','properties':{'plan':{'type':'object','properties':{'sources':{'type':'array','items':{'type':'object','properties':{'id':{'type':'string'},'duration_ms':{'type':'integer','minimum':1}},'required':['id','duration_ms']}},'segments':{'type':'array','minItems':1,'maxItems':2000,'items':{'type':'object','properties':{'source_id':{'type':'string'},**{k:{'type':'integer','minimum':0} for k in ['source_start_ms','source_end_ms','output_start_ms','output_end_ms']}},'required':['source_id','source_start_ms','source_end_ms','output_start_ms','output_end_ms']}}},'required':['sources','segments']}},'required':['plan'],'additionalProperties':False}}
])
TOOLS.extend([
 {'name':'desk_agent_bootstrap','description':'创作任务开工入口：读取共同接入规范、资源目录与技能版本；只读，不要求多 Agent 接单','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
 {'name':'desk_agent_preflight','description':'检查指定技能及链接依赖的可用性和版本；不证明执行环境或听审通过','inputSchema':{'type':'object','properties':{'skill_ids':{'type':'array','items':{'type':'string'},'maxItems':32}},'required':['skill_ids'],'additionalProperties':False}},
 {'name':'desk_find_cases','description':'检索个人口语或优秀案例；返回记录不代表已观看或用户认可','inputSchema':{'type':'object','properties':{'kind':{'type':'string','enum':['oral','excellent']},'q':{'type':'string'}},'required':['kind'],'additionalProperties':False}},
 {'name':'desk_read_case','description':'按 ID 读取案例、版本和证据；只读','inputSchema':{'type':'object','properties':{'kind':{'type':'string','enum':['oral','excellent']},'case_id':{'type':'string'}},'required':['kind','case_id'],'additionalProperties':False}}
])
def call(name,args):
 if name=='desk_agent_bootstrap':return DeskClient().request('/api/agent/bootstrap')
 if name=='desk_agent_preflight':
  ids=args.get('skill_ids')
  if not isinstance(ids,list) or len(ids)>32 or any(not isinstance(x,str) or not x or len(x)>100 or not all(c.isascii() and (c.isalnum() or c in '_-') for c in x) for x in ids):raise ValueError('技能 ID 无效')
  return DeskClient().request('/api/agent/preflight?skills='+quote(','.join(ids),safe=''))
 if name in ['desk_find_cases','desk_read_case']:
  kind=args.get('kind')
  if kind not in ['oral','excellent']:raise ValueError('未知案例类型')
  path='/api/'+{'oral':'oral-cases','excellent':'excellent-cases'}[kind]
  return DeskClient().request(path+('/'+quote(args['case_id'],safe='') if name=='desk_read_case' else '?q='+quote(args.get('q',''),safe='')))
 if name=='desk_check_edit_plan':
  from editing_tools import check_plan
  return check_plan(args['plan'])
 if name=='desk_source_provenance':return DeskClient().request('/api/packages/'+quote(args['package_id'],safe='')+'/provenance?video_id='+quote(args['video_id'],safe=''))
 if name=='desk_skill_history':return DeskClient().request('/api/skills/'+quote(args['skill_id'],safe='')+'/history')
 if name=='desk_skill_version':return DeskClient().request('/api/skills/'+quote(args['skill_id'],safe='')+'/history/'+quote(args['version_id'],safe=''))
 if name=='desk_edit_skill':return DeskClient().request('/api/skills/'+quote(args['skill_id'],safe='')+'/edit','POST',{k:v for k,v in args.items() if k!='skill_id'})
 if name=='desk_add_content_record':return DeskClient().request('/api/packages/'+quote(args['package_id'],safe='')+'/feedback','POST',{k:v for k,v in args.items() if k!='package_id'})
 if name=='desk_content_history':return DeskClient().request('/api/packages/'+quote(args['package_id'],safe='')+'/lifecycle')
 if name=='find_brand_assets':
  import urllib.parse
  return DeskClient().request('/api/brand-assets?'+urllib.parse.urlencode(args))
 if name in ['desk_cover_templates','desk_cover_template']:
  data=DeskClient().request('/api/cover-design/catalog')
  skill=DeskClient().request('/api/skills/video-cover-design')
  import hashlib
  data.update(skill_text=skill['content'],skill_sha256=hashlib.sha256(skill['content'].encode()).hexdigest(),skill_revision=skill['revision'],source_skill=skill['source_path'])
  if name=='desk_cover_templates':return data
  item=next((x for x in data['templates'] if x['id']==args.get('template_id')),None)
  if item is None:raise ValueError('封面模板不存在')
  return {'template':item,'skill_text':data['skill_text'],'skill_sha256':data['skill_sha256'],'workflow':data['workflow'],'boundaries':data['boundaries']}

 if name=='desk_list_skills':return DeskClient().request('/api/skills')
 if name=='desk_read_skill':return DeskClient().request('/api/skills/'+quote(args['skill_id'],safe=''))
 if name=='desk_skill_requests':return DeskClient().request('/api/skill-requests')
 if name=='desk_skill_request':return DeskClient().request('/api/skill-requests/'+quote(args['request_id'],safe=''))
 if name=='desk_create_skill_request':return DeskClient().request('/api/skill-requests','POST',args)
 if name=='desk_update_skill_request':return DeskClient().request('/api/skill-requests/'+quote(args['request_id'],safe='')+'/transition','POST',{k:v for k,v in args.items() if k!='request_id'})
 if name in ['preview_library_batch','import_library_batch']:return import_library(args['manifest_path'],name=='import_library_batch')
 if name=='desk_status':
  j=DeskClient().request('/api/library');return {'batches':j['batches'],'contents':len(j['snapshot']['packages']),'tasks':len(j['snapshot']['tasks'])}
 if name not in ['preview_production_batch','sync_production_batch']:raise ValueError('未知工具')
 batch=args.get('batch');account=args.get('account')
 if not isinstance(batch,str) or not batch.strip() or batch.startswith('-'):raise ValueError('批次ID必填')
 if name=='sync_production_batch' and (not isinstance(account,str) or not account.strip() or account.startswith('-')):raise ValueError('明确指定目标账号')
 cmd=[sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/sync_production.py'),'--batch',batch]
 if args.get('only'):cmd+=['--only',str(args['only'])]
 if name=='sync_production_batch':cmd+=['--account',account,'--apply']
 r=subprocess.run(cmd,capture_output=True,text=True,timeout=600)
 return {'exit_code':r.returncode,'output':r.stdout[-16000:],'error':r.stderr[-4000:],'success':r.returncode==0,'published':False}
def respond(m):
 method=m.get('method');p=m.get('params',{})
 if method=='initialize':return {'protocolVersion':p.get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'instructions':INSTRUCTIONS,'serverInfo':{'name':'content-distribution-desk','version':'0.2.0'}}
 if method=='ping':return {}
 if method=='tools/list':return {'tools':TOOLS}
 if method=='tools/call':
  try:
   result=call(p['name'],p.get('arguments',{}));return {'content':[{'type':'text','text':json.dumps(result,ensure_ascii=False)}],'isError':result.get('success') is False}
  except Exception as e:return {'content':[{'type':'text','text':str(e)}],'isError':True}
 raise ValueError('未知方法')
if __name__=='__main__':
 for line in sys.stdin:
  try:
   m=json.loads(line)
   if 'id' not in m:continue
   try:out={'jsonrpc':'2.0','id':m['id'],'result':respond(m)}
   except Exception as e:out={'jsonrpc':'2.0','id':m['id'],'error':{'code':-32601,'message':str(e)}}
   print(json.dumps(out,ensure_ascii=False),flush=True)
  except Exception as e:print(str(e),file=sys.stderr)
