importScripts('durable-observations.js');
const frames=new Map();let counter=0;
chrome.runtime.onConnect.addListener(port=>{
 if(port.name!=='desk-frame'||!port.sender.tab)return;
 const tabId=port.sender.tab.id,frameId=port.sender.frameId,key=tabId+':'+frameId,pending=new Map();
 const entry={tabId,frameId,documentId:port.sender.documentId,port,ask:message=>new Promise((resolve,reject)=>{const id=++counter;const timeout=setTimeout(()=>{pending.delete(id);reject(Error('frame操作超时，结果待核对'));},60000);pending.set(id,{resolve,reject,timeout});port.postMessage({...message,id});})};
 frames.set(key,entry);
 port.onMessage.addListener(m=>{const request=pending.get(m.id);if(!request)return;clearTimeout(request.timeout);pending.delete(m.id);m.ok?request.resolve(m.result):request.reject(Error(m.error));});
 port.onDisconnect.addListener(()=>{if(frames.get(key)===entry)frames.delete(key);for(const r of pending.values()){clearTimeout(r.timeout);r.reject(Error('页面frame已离开，结果待核对'));}});
});
function videoIds(task,assets){return (task.asset_ids||[]).filter(id=>{const a=assets.find(a=>a.id===id);return a&&(a.kind==='video'||a.mime?.startsWith('video/'));});}
const BASE='http://127.0.0.1:4318';
const delivery=DeskDurableObservations.create({storage:chrome.storage.local,post:postObservation,onDelivery:async(item,data)=>{
 // Delayed delivery concerns the original task; never relabel a newly selected task.
 const binding=await delivery.getBinding(item.tabId);
 if(binding&&binding.task_id===item.payload.task_id&&binding.revision===item.payload.revision)await feedback({tab:{id:item.tabId}},data);
}});
async function checkBinding(sender){
 if(!sender.tab)throw Error('页面观察器来源无效');
 const binding=await delivery.getBinding(sender.tab.id);
 if(!binding?.document_id)throw Error('页面关联已失效，请重新加载当前内容后记录');
 if(sender.frameId===0&&sender.documentId!==binding.document_id)throw Error('页面文档已改变，请重新关联当前内容');
 const tab=await chrome.tabs.get(sender.tab.id);
 if(!tab.url||new URL(tab.url).origin+new URL(tab.url).pathname!==binding.top_page_url)throw Error('页面已离开当前内容，请重新关联');
 let probe;try{probe=await chrome.tabs.sendMessage(sender.tab.id,{type:'observation-probe'},{documentId:binding.document_id});}catch{throw Error('原页面文档已关闭，请重新关联当前内容');}
 if(!probe?.ok||probe.task_id!==binding.task_id||probe.revision!==binding.revision||probe.top_page_url!==binding.top_page_url)throw Error('页面关联已改变，请重新加载当前内容');
 return {...binding,observed_account:probe.observed_account||''};
}
chrome.tabs.onRemoved.addListener(tabId=>{delivery.clearBinding(tabId).catch(()=>{});for(const [key,frame]of frames)if(frame.tabId===tabId)frames.delete(key);});
chrome.tabs.onUpdated.addListener((tabId,change)=>{if(change.status==='loading'||change.url)delivery.clearBinding(tabId).catch(()=>{});});
chrome.alarms.onAlarm.addListener(alarm=>{if(alarm.name==='desk-observation-delivery')delivery.flush().catch(()=>{});});
chrome.alarms.create('desk-observation-delivery',{periodInMinutes:1});
delivery.flush().catch(()=>{});
function assertAccountMatch(task,observed){
 const normalized=value=>String(value||'').normalize('NFKC').replace(/\s+/g,'').toLowerCase();
 const expected=normalized(task.account_display_name),actual=normalized(observed);
 if(expected&&actual&&expected!==actual)throw Error('账号不匹配：已绑定账号为「'+task.account_display_name+'」，当前页面为「'+observed+'」。请切换到正确账号后继续。');
}
function isTop(sender){try{return !!sender.tab&&sender.frameId===0&&new URL(sender.url).origin==='https://channels.weixin.qq.com';}catch{return false;}}
function allowedReader(sender){if(isTop(sender))return true;if(!sender.tab)return true;try{const u=new URL(sender.url),own=new URL(chrome.runtime.getURL('popup.html'));return u.origin===own.origin&&u.protocol==='chrome-extension:'&&u.host===own.host&&u.pathname==='/popup.html';}catch{return false;}}
async function readState(){
 let response;try{response=await fetch(BASE+'/api/state',{cache:'no-store'});}catch{throw Error('无法连接本机分发台，请保持应用打开后刷新内容。');}
 if(!response.ok)throw Error('分发台返回错误 HTTP '+response.status);
 const state=await response.json(),r=await fetch(BASE+'/api/library',{cache:'no-store'});
 if(!r.ok)throw Error('无法读取当前内容批次，请更新并重启分发台；未使用旧批次表。');
 const catalog=await r.json();if(!Array.isArray(catalog.batches)||!catalog.packages)throw Error('批次数据不完整，请刷新分发台');
 const snapshot=catalog.snapshot||state;const progress=(await chrome.storage.local.get('desk.publication.progress'))['desk.publication.progress']||{};
 return {batches:catalog.batches,tasks:snapshot.tasks.filter(t=>t.format==='video'&&state.accounts.find(a=>a.id===t.account_id)?.platform==='channels'&&!['published','canceled','running','queued'].includes(t.status)&&!catalog.packages[t.package_id]?.archived&&!catalog.packages[t.package_id]?.superseded_by).map(t=>({...t,publication_progress:progress[t.id]?.revision===t.revision?progress[t.id]:null,asset_ids:videoIds(t,snapshot.assets),batch_id:catalog.packages[t.package_id]?.batch_id||'unassigned',sequence:catalog.packages[t.package_id]?.sequence,account:state.accounts.find(a=>a.id===t.account_id).name,account_display_name:state.accounts.find(a=>a.id===t.account_id).connection?.status==='bound'?(state.accounts.find(a=>a.id===t.account_id).connection.display_name||''):''})),assets:snapshot.assets.map(a=>({id:a.id,name:a.name,size:a.size,mime:a.mime,kind:a.kind}))};
}
async function postObservation(payload){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);try{
 const page=await fetch(BASE+'/',{cache:'no-store',signal:controller.signal});if(!page.ok)throw Error('分发台不可用，请保持应用打开');
 const token=(await page.text()).match(/name="desk-token" content="([^"]+)"/)?.[1];if(!token)throw Error('无法建立本机会话，请重启分发台');
 const r=await fetch(BASE+'/api/channel-observations',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json','X-Desk-Token':token},body:JSON.stringify(payload)});
 if(r.status===404){const error=Error('请先保存编辑并重新打开分发台；记录留在插件等待同步');error.status=404;throw error;}
 let value;try{value=await r.json();}catch{if(r.ok)throw Error('观察记录响应无法确认，保留队列等待重试');value={};}if(!r.ok){const error=Error(value.error||'观察记录写回失败 HTTP '+r.status);error.status=r.status;throw error;}return value;
 }finally{clearTimeout(timer);}
}
async function feedback(sender,data){try{await chrome.tabs.sendMessage(sender.tab.id,{type:'observation-feedback',...data},{frameId:0});}catch{}}
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
 (async()=>{
  if(message.type==='frames'||message.type==='field'){
   if(!sender.tab||new URL(sender.url).hostname!=='channels.weixin.qq.com'||sender.frameId!==0)throw Error('只允许顶部辅助面板请求');
   const all=[...frames.values()].filter(f=>f.tabId===sender.tab.id);
   const scans=await Promise.all(all.map(async f=>{try{return {...await f.ask({op:'scan'}),frameId:f.frameId};}catch(e){return {frameId:f.frameId,error:e.message};}}));
   if(message.type==='frames')return scans;
   const found=scans.filter(f=>f.counts?.[message.kind]===1);
   const total=scans.reduce((n,f)=>n+(f.counts?.[message.kind]||0),0);
   if(found.length!==1||total!==1)throw Error(message.kind+'：'+all.length+'个frame中找到'+total+'个候选，请查看结构诊断');
   return all.find(f=>f.frameId===found[0].frameId).ask({op:message.op,kind:message.kind,value:message.value,asset:message.asset});
  }
  if(['publication-confirm','publication-undo'].includes(message.type)){
   if(!allowedReader(sender))throw Error('仅插件可记录发布进度');
   const state=await readState(),task=state.tasks.find(t=>t.id===message.task_id&&t.revision===message.revision);if(!task)throw Error('任务已变化，请刷新后核对');
   const key='desk.publication.progress',progress=(await chrome.storage.local.get(key))[key]||{};
   const previous=progress[task.id],value={task_id:task.id,account_id:task.account_id,revision:task.revision,status:message.type==='publication-confirm'?'published':'unconfirmed',source:'manual',confirmed_at:new Date().toISOString(),previous_status:previous?.status||null};
   progress[task.id]=value;await chrome.storage.local.set({[key]:progress});
   const event={event_id:crypto.randomUUID(),task_id:task.id,revision:task.revision,source:'manual',event_kind:'manual_confirmation',page_url:'https://channels.weixin.qq.com/platform/post/create',observed_account:'',result_text:message.type==='publication-confirm'?'用户人工确认本条已发布；非平台自动验证':'用户撤销本条已发布标记；需重新核对',scheduled_text:''};
   try{await delivery.enqueue(event,sender.tab?.id||0);delivery.flush().catch(()=>{});}catch(e){return {...value,sync_error:e.message};}return value;
  }
  if(message.type==='state'){
   if(!allowedReader(sender))throw Error('仅扩展窗口或视频号顶部面板可读取任务清单');
   return readState();
  }
  if(message.type==='observation-bind'){
   if(!isTop(sender)||!sender.documentId||!/^\/platform\/post\/create\/?$/.test(new URL(sender.url).pathname))throw Error('只允许视频号发表页面绑定当前文档');
   if(!['fill_started','manual_adoption'].includes(message.binding_reason))throw Error('选择预览不会绑定发布记录');
   const state=await readState(),task=state.tasks.find(t=>t.id===message.task_id&&t.revision===message.revision);if(!task)throw Error('内容版本已改变，请刷新后重新加载');
   const initialProbe=await chrome.tabs.sendMessage(sender.tab.id,{type:'observation-probe'},{documentId:sender.documentId});
   assertAccountMatch(task,initialProbe?.observed_account);
   const result=await chrome.tabs.sendMessage(sender.tab.id,{type:'observation-context',payload:{task_id:task.id,revision:task.revision,binding_reason:message.binding_reason,top_page_url:new URL(sender.url).origin+new URL(sender.url).pathname}},{documentId:sender.documentId});
   if(!result?.ok)throw Error(result?.error||'页面观察器未连接，请在保存当前编辑后刷新页面');
   const context={task_id:task.id,revision:task.revision,binding_reason:message.binding_reason,top_page_url:new URL(sender.url).origin+new URL(sender.url).pathname,observed_account:result.observed_account||''};
   const connected=[...frames.values()].filter(f=>f.tabId===sender.tab.id&&f.frameId!==0);const failures=[];
   for(const frame of connected){try{const ack=await chrome.tabs.sendMessage(sender.tab.id,{type:'observation-context',payload:context},{frameId:frame.frameId});if(!ack?.ok)failures.push(frame.frameId);}catch{failures.push(frame.frameId);}}
   await delivery.setBinding(sender.tab.id,{...context,document_id:sender.documentId});return {bound:true,title:task.title,account:task.account,observed_account:result.observed_account||'',warning:failures.length?'部分页面未连接观察器，发布记录可能不完整，请保存编辑后刷新页面。':''};
  }
  if(message.type==='observation-check'){
   if(!isTop(sender))throw Error('只允许顶部辅助面板检查绑定');
   const binding=await checkBinding(sender),state=await readState();
   const task=state.tasks.find(t=>t.id===binding.task_id&&t.revision===binding.revision);
   if(!task)throw Error('内容版本已改变，请刷新后重新加载');
   assertAccountMatch(task,binding.observed_account);
   return binding;
  }
  if(message.type==='observation-explicit'){
   if(!isTop(sender)||message.event_kind!=='draft_clicked')throw Error('不支持此页面操作记录');
   await checkBinding(sender);
   const result=await chrome.tabs.sendMessage(sender.tab.id,{type:'observation-explicit-context',payload:{event_kind:'draft_clicked'}},{frameId:0});
   if(!result?.ok)throw Error(result?.error||'页面未关联当前任务');return result;
  }
  if(message.type==='observation'){
   try{
    const p=message.payload;
    const frame=frames.get(sender.tab?.id+':'+sender.frameId);
    const knownFrame=sender.frameId!==0&&frame&&frame.documentId===sender.documentId&&(/^https:\/\/channels\.weixin\.qq\.com\//.test(sender.url||'')||['about:blank','about:srcdoc'].includes(sender.url));
    if(!sender.tab||(!isTop(sender)&&!knownFrame))throw Error('页面观察器来源无效');
    if(!p||p.source!=='session_observer')throw Error('观察来源无效');
    const binding=await checkBinding(sender);
    if(!binding||binding.task_id!==p.task_id||binding.revision!==p.revision)throw Error('页面关联已失效，请重新加载当前内容后记录');
    if(p.page_url!==binding.top_page_url)throw Error('观察页面与绑定页面不一致');
    // The binding revision is immutable; the server revalidates it on delivery, including after an offline interval.
    const event=await delivery.enqueue(p,sender.tab.id);
    if(event.status==='confirmed'){await feedback(sender,{recorded:true,queued:false,...event.result.observation,event_id:p.event_id});return {recorded:true,queued:false,...event.result};}
    if(event.status==='failed'){await feedback(sender,{recorded:false,queued:false,event_id:p.event_id,error:event.error});return {recorded:false,queued:false,event_id:p.event_id,error:event.error};}
    // The local receipt is durable before HTTP delivery. Offline events survive worker restarts.
    await feedback(sender,{recorded:false,queued:true,event_id:p.event_id,error:'记录已保存在插件，正在同步分发台'});
    delivery.flush().catch(()=>{});
    return {recorded:false,queued:true,event_id:p.event_id,error:''};
   }catch(error){if(sender.tab)await feedback(sender,{recorded:false,error:error.message});throw error;}
  }
  if(message.type==='asset'){
   if(new URL(sender.url).hostname!=='channels.weixin.qq.com'&&!['about:blank','about:srcdoc'].includes(sender.url))throw Error('非法页面');
   if(!/^[a-f0-9]{32}$/.test(message.id))throw Error('非法素材编号');
   const r=await fetch(BASE+'/api/assets/'+message.id);if(!r.ok)throw Error('素材不存在');
   const bytes=new Uint8Array(await r.arrayBuffer());
   if(bytes.length>64*1024*1024)throw Error('首版自动传输上限64MB，请在平台手动选择该视频');
   let binary='';for(let i=0;i<bytes.length;i+=16384)binary+=String.fromCharCode(...bytes.subarray(i,i+16384));
   return {base64:btoa(binary),mime:r.headers.get('Content-Type')};
  }
  throw Error('未知请求');
 })().then(result=>reply({ok:true,result}),error=>reply({ok:false,error:error.message}));return true;
});
