(()=>{
 let busy=false,catalog=null,pickerBatch='',pickerQuery='',currentTaskId=null,currentSelection=null,currentHost=null,lastPath=location.pathname,dismissed=false,boundTaskId=null,boundTaskTitle='',routeGeneration=0;
 const UI_KEY='desk-channels-panel-v1';
 const documentId='doc-'+Date.now()+'-'+Math.random().toString(36).slice(2);
 let runSession=documentId;try{runSession=sessionStorage.getItem('desk.prepare.session')||documentId;sessionStorage.setItem('desk.prepare.session',runSession);}catch{}

 const readUI=()=>{try{return JSON.parse(localStorage.getItem(UI_KEY)||'{}');}catch{return {};}};
 function setBusy(value){busy=value;currentHost?.shadowRoot?.querySelectorAll('[data-picker]').forEach(el=>el.disabled=value);if(!value)currentHost?.refreshPicker?.();}
 async function request(message,ms=15000){let timer;try{return await Promise.race([chrome.runtime.sendMessage(message),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('页面连接超时，请刷新视频号页面再试')),ms);})]);}finally{clearTimeout(timer);}}
 async function loadCatalog(){const r=await request({type:'state'});if(!r?.ok)throw Error(r?.error||'分发台未返回内容');catalog=r.result;return catalog;}
 const taskOrder=t=>Number.isInteger(t.sequence)?t.sequence:999999;
 function orderedTasks(){return (catalog?.tasks||[]).filter(t=>!['published','canceled','running','queued'].includes(t.status)&&t.publication_progress?.status!=='published'&&!t.title.includes('分发流程测试')&&(!pickerBatch||t.batch_id===pickerBatch)&&(!pickerQuery||[t.title,t.account,taskOrder(t)===999999?'':String(taskOrder(t))].join(' ').toLowerCase().includes(pickerQuery.toLowerCase()))).sort((a,b)=>taskOrder(a)-taskOrder(b)||a.title.localeCompare(b.title,'zh-CN'));}
 function selectTask(t){if(busy)throw Error('当前操作尚未完成，请等待后再换条');if(!t)return;currentTaskId=t.id;currentSelection=t;panel(t,(catalog?.assets||[]).filter(a=>t.asset_ids.includes(a.id)||a.id===t.cover_id));}

 const field=async(kind,op,extra={})=>{const r=await chrome.runtime.sendMessage({type:'field',kind,op,...extra});if(!r.ok)throw Error(r.error);return r.result;};
 const scan=async()=>{const r=await request({type:'frames'});if(!r.ok)throw Error(r.error);return r.result;};
 const preflight=async(manual)=>{
  const report=await scan();
  if(!report.length||report.some(f=>f.error))throw Error('页面扫描不完整，请重试；未执行上传或填写');
  if(report.some(f=>f.agent_version&&f.agent_version!=='0.7.10'))throw Error('页面仍有旧版插件脚本，请先保存当前平台编辑，重载扩展并刷新页面');
  for(const kind of (manual?['body','title']:['video'])){
   const count=report.reduce((n,f)=>n+(f.counts?.[kind]||0),0);
   if(count!==1)throw Error('检查未通过：'+kind+'候选='+count+'，扫描frame='+report.length+'；请导出结构诊断');
  }
  return report;
 };
 async function file(asset){return DeskAssetTransfer.file(asset);}
 function upload(input,f){const dt=new DataTransfer();dt.items.add(f);input.files=dt.files;input.dispatchEvent(new Event('change',{bubbles:true}));}
 function panel(task=null,assets=[],autoStart=false){
 if(location.pathname!==lastPath){lastPath=location.pathname;routeGeneration++;dismissed=false;}
 const panelGeneration=routeGeneration;const selected=!!task?.id;task=task||{title:'',body:'',tags:'',account:'',asset_ids:[],options:{}};
 if(busy)throw Error('当前操作尚未完成');
 const previousHost=document.querySelector('#desk-channels-assistant');previousHost?.dispose?.();previousHost?.remove();
 const host=document.createElement('div');host.id='desk-channels-assistant';currentHost=host;host.style.cssText='position:fixed;right:16px;top:90px;width:auto;z-index:2147483647';
 const root=host.attachShadow({mode:'open'});let disposed=false,copyConfirmed=false,coverChecked=!task.cover_id;const ownedURLs=new Set();host.dispose=()=>{disposed=true;for(const url of ownedURLs)URL.revokeObjectURL(url);ownedURLs.clear();};root.innerHTML='<style>:host{font:14px/1.6 system-ui;color:#284039}section{box-sizing:border-box;resize:both;min-width:280px;width:340px;height:650px;min-height:160px;max-width:90vw;max-height:80vh;background:white;border:2px solid #284039;padding:16px;border-radius:12px;box-shadow:0 4px 24px #0003;max-height:75vh;overflow:auto}button{padding:10px;margin:5px 0;width:100%;cursor:pointer}img{max-height:180px;max-width:100%;object-fit:contain}pre{white-space:pre-wrap;font:13px/1.5 system-ui}small{color:#65786b}</style><section><div id="panel-bar" style="display:flex;align-items:center;justify-content:space-between;cursor:move;touch-action:none;user-select:none"><strong>分发台 0.7.10 · 拖动移动</strong><button id="smaller" style="width:auto;padding:4px">−</button><button id="larger" style="width:auto;padding:4px">＋</button><button id="collapse" style="width:auto;padding:4px">收起</button></div><div id="panel-body"><button id="diagnose">检查页面并下载结构诊断</button><p id="title"></p><img id="cover" hidden><pre id="copy"></pre><button id="fill">一键准备</button><button id="fill-only">页面已有本条视频，继续准备</button><button id="sync-title">重新同步短标题</button><button id="upload-cover">补上传封面</button><button id="save" disabled>人工核对后，保存草稿一次</button><button id="close">关闭辅助面板</button><pre id="status"></pre><small>公开发布由你点击平台“发表”。本扩展不点击该按钮，不自动回填成功状态。</small></div></section>';
 root.querySelector('#title').textContent=task.title+' · '+task.account;root.querySelector('#copy').textContent=task.body+'\n'+task.tags;const copyBox=root.querySelector('#copy');const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent='查看完整文案';copyBox.before(details);details.append(summary,copyBox);const plan=document.createElement('p');plan.textContent='合集：'+(task.options?.collection||'未指定')+' · 标注：个人观点 · 时间：'+((task.assistScheduled||task.scheduled)?new Date(task.assistScheduled||task.scheduled).toLocaleString('zh-CN'):'未安排');details.before(plan);
 root.querySelector('#close').onclick=()=>{if(!busy){dismissed=true;host.dispose();host.remove();}};
 const style=document.createElement('style');style.textContent='*{box-sizing:border-box}button,input,select{font:inherit}button{border:1px solid #d5dfd9;border-radius:5px;background:#f7faf8}button:disabled{opacity:.48;cursor:default}input,select{width:100%;padding:8px;border:1px solid #cbd8d0;border-radius:5px;background:white;margin:4px 0 8px}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #548570;outline-offset:2px}label{display:block;font-size:12px}#picker-controls{border-bottom:1px solid #e3eae5;padding:12px 0;margin-bottom:12px}.picker-row{display:flex;gap:7px}.picker-row button{flex:1;padding:7px 2px;font-size:12px}#fill{background:#284b40;color:white}#page-observation{background:#f0f5f1;padding:8px;border-radius:5px;font-size:12px}#picker-status,#status{overflow-wrap:anywhere}section{max-width:calc(100vw - 16px);max-height:calc(100vh - 16px)}[hidden]{display:none!important}#picker-task{text-align:left;background:white;display:flex;justify-content:space-between;align-items:center}#picker-list{max-height:320px;overflow:auto;border:1px solid #d5dfd9;border-radius:7px;padding:5px;background:#f9fbf9}.picker-choice{display:flex;align-items:center;gap:10px;text-align:left;background:white;padding:7px;margin:3px 0;min-height:62px}.picker-choice[aria-pressed=true]{border-color:#284b40;background:#edf5ef}.picker-thumb{width:42px;height:56px;flex-shrink:0;background:#edf1ee;display:grid;place-items:center;overflow:hidden;border-radius:4px;font-size:10px;color:#607366}.picker-thumb img{width:100%;height:100%;object-fit:contain}.picker-choice-copy{min-width:0}.picker-choice-copy strong{font-size:12px;display:block;font-weight:600;overflow-wrap:anywhere}.picker-choice-copy small{font-size:11px;display:block;overflow-wrap:anywhere}.cover-tools{margin:8px 0 14px;padding:9px;background:#f2f6f2;border-radius:6px}.cover-tools button{font-size:12px}.cover-tools small{display:block}#cover-status{margin:7px 0;font-size:12px;line-height:1.7;color:#765126}#cover-status.ready{color:#3c614c}';root.append(style);
 const picker=document.createElement('div');picker.id='picker-controls';picker.innerHTML='<label>内容批次<select id="picker-batch" data-picker aria-label="内容批次"><option value="">所有批次</option></select></label><label>搜索内容<input id="picker-search" data-picker placeholder="标题、序号或账号" aria-label="搜索内容"></label><span id="picker-label">选择本次内容</span><button id="picker-task" data-picker aria-expanded="false" aria-controls="picker-list" aria-labelledby="picker-label picker-task"><span>展开内容与封面</span><span aria-hidden="true">⌄</span></button><div id="picker-list" role="group" aria-label="按封面选择内容" hidden></div><div class="picker-row"><button id="picker-prev" data-picker>上一条</button><button id="picker-next" data-picker>下一条</button><button id="picker-refresh" data-picker>刷新内容</button></div><small id="picker-status">正在连接本机分发台…</small>';
 root.querySelector('#panel-body').prepend(picker);
 const observation=document.createElement('div');observation.id='page-observation';observation.setAttribute('aria-live','polite');observation.textContent=boundTaskId?'页面仍关联：'+boundTaskTitle+'。当前选择仅供预览，加载后才更新关联。':'页面尚未关联内容。选择只预览，加载后才关联本次操作。';picker.after(observation);
 root.querySelector('#close').setAttribute('data-picker','');
 root.querySelector('#status').setAttribute('aria-live','polite');root.querySelector('#status').setAttribute('role','status');
 const preview=document.createElement('div');preview.id='selected-preview';preview.hidden=!selected;observation.after(preview);
 for(const el of [root.querySelector('#title'),root.querySelector('#cover'),plan,details,root.querySelector('#fill'),root.querySelector('#fill-only'),root.querySelector('#sync-title'),root.querySelector('#upload-cover'),root.querySelector('#save')])preview.append(el);
 const repairs=document.createElement('details'),repairSummary=document.createElement('summary');repairSummary.textContent='修复与页面诊断';repairs.append(repairSummary,root.querySelector('#sync-title'),root.querySelector('#diagnose'));root.querySelector('#save').before(repairs);
 const coverTools=document.createElement('div');coverTools.className='cover-tools';const coverNote=document.createElement('small');coverNote.textContent='只补本条封面，不重新上传视频或改文案。';const downloadCover=document.createElement('button');downloadCover.id='download-cover';downloadCover.textContent='下载本条封面';const coverStatus=document.createElement('p');coverStatus.id='cover-status';coverStatus.setAttribute('role','status');coverStatus.setAttribute('aria-live','polite');coverStatus.textContent=task.cover_id?'平台封面尚未确认，请检查上传后的平台预览。':'本条尚未指定封面。';const confirmCover=document.createElement('button');confirmCover.id='confirm-cover';confirmCover.textContent='封面已核对';confirmCover.disabled=!task.cover_id;coverTools.append(root.querySelector('#upload-cover'),downloadCover,coverNote,coverStatus,confirmCover);root.querySelector('#cover').after(coverTools);
 const collectionKey='desk.collection.'+(task.batch_id||'unassigned')+'.'+(task.account_id||'unknown');let collectionValue='AI与组织';try{collectionValue=localStorage.getItem(collectionKey)??collectionValue;}catch{}const collectionTarget=()=>collectionValue;
 const choices=document.createElement('div');choices.innerHTML='<label style="display:flex;gap:8px;align-items:center"><input id="declare-original" type="checkbox" checked style="width:auto;margin:0">本条声明原创</label><small>仅适用于你拥有原创权利的内容；平台条款由你阅读处理。</small><button id="apply-options">应用标注、原创与合集</button>';repairs.before(choices);const collectionInput=document.createElement('input');collectionInput.id='batch-collection';collectionInput.value=collectionValue;collectionInput.setAttribute('data-picker','');collectionInput.setAttribute('aria-label','本批次合集');const collectionLabel=document.createElement('label');collectionLabel.textContent='本批次合集（平台已有名称）';collectionLabel.append(collectionInput);choices.prepend(collectionLabel);collectionInput.onchange=()=>{if(busy)return;collectionValue=collectionInput.value.trim();try{localStorage.setItem(collectionKey,collectionValue);}catch{}plan.textContent='合集：'+(collectionValue||'不选择')+' · 标注：个人观点';};plan.textContent='合集：'+collectionValue+' · 标注：个人观点';
 async function applyOptions(){const notes=[];try{const r=await field('label','select');notes.push(r.selected?'视频标注：个人观点，仅供参考':'视频标注：未确认');}catch(e){notes.push('视频标注：未填入。'+e.message);}if(root.querySelector('#declare-original').checked){try{const r=await field('original','select',{value:{confirmTerms:true}});notes.push(r.checked?'原创：已回读为勾选':'原创：状态未确认');}catch(e){notes.push('原创：未能识别或操作，请保留平台当前选择。'+e.message);}}else notes.push('原创：本次不自动处理，保留平台当前选择');if(collectionTarget()){try{const r=await field('collection','select',{value:collectionTarget()});notes.push(r.selected?'合集：已回读为「'+r.value+'」':'合集：未确认');}catch(e){notes.push('合集：目标「'+collectionTarget()+'」，未确认。'+e.message);}}else notes.push('合集：任务未指定，保留平台当前选择');return notes;}

 root.querySelector('#apply-options').onclick=async()=>{if(busy||!selected)return;if(boundTaskId!==task.id){status.textContent='请先加载本条内容，或用仅填写入口确认页面视频属于本条。';return;}setBusy(true);try{await checkBinding();status.textContent=(await applyOptions()).join('\n');}catch(e){status.textContent='选项待核对：'+e.message;}finally{setBusy(false);}};
 let listOpen=!selected,listLimit=30,listEpoch=0,thumbActive=0,thumbQueue=[];
 const thumbCache=new Map();
 async function pumpThumbs(){
  while(thumbActive<3&&thumbQueue.length&&!disposed){
   const item=thumbQueue.shift();if(item.epoch!==listEpoch||!listOpen)continue;thumbActive++;
   file(item.asset).then(f=>{if(disposed||item.epoch!==listEpoch||!listOpen)return;const url=URL.createObjectURL(f);ownedURLs.add(url);thumbCache.set(item.asset.id,url);const image=document.createElement('img');image.alt='';image.onload=()=>{item.slot.textContent='';item.slot.append(image);};image.onerror=()=>{item.slot.textContent='预览未加载';URL.revokeObjectURL(url);ownedURLs.delete(url);thumbCache.delete(item.asset.id);};image.src=url;}).catch(()=>{if(!disposed&&item.epoch===listEpoch)item.slot.textContent='预览未加载';}).finally(()=>{thumbActive--;pumpThumbs();});
  }
 }
 function renderChoices(tasks){
  const list=root.querySelector('#picker-list');listEpoch++;thumbQueue=[];list.replaceChildren();list.hidden=!listOpen;root.querySelector('#picker-task').setAttribute('aria-expanded',String(listOpen));if(!listOpen)return;
  for(const t of tasks.slice(0,listLimit)){
   const choice=document.createElement('button');choice.type='button';choice.className='picker-choice';choice.setAttribute('data-picker','');choice.setAttribute('data-task-choice',t.id);choice.setAttribute('aria-pressed',String(t.id===currentTaskId));choice.disabled=busy;
   const thumb=document.createElement('span');thumb.className='picker-thumb';thumb.textContent=t.cover_id?'封面加载中':'无封面';
   const copy=document.createElement('span');copy.className='picker-choice-copy';const title=document.createElement('strong');title.textContent=(taskOrder(t)===999999?'':'第 '+String(taskOrder(t)).padStart(2,'0')+' 条 · ')+t.title;const account=document.createElement('small');account.textContent=t.account;copy.append(title,account);choice.append(thumb,copy);choice.onclick=()=>{if(!busy)selectTask(t);};list.append(choice);
   const asset=(catalog?.assets||[]).find(a=>a.id===t.cover_id&&a.kind==='image');if(asset){const cached=thumbCache.get(asset.id);if(cached){const image=document.createElement('img');image.alt='';image.src=cached;thumb.textContent='';thumb.append(image);}else thumbQueue.push({asset,slot:thumb,epoch:listEpoch});}else if(t.cover_id)thumb.textContent='封面不可用';
  }
  if(tasks.length>listLimit){const more=document.createElement('button');more.type='button';more.setAttribute('data-picker','');more.textContent='再显示 '+Math.min(30,tasks.length-listLimit)+' 条（共 '+tasks.length+' 条）';more.disabled=busy;more.onclick=()=>{if(!busy){listLimit+=30;renderChoices(orderedTasks());}};list.append(more);}
  if(!tasks.length){const note=document.createElement('p');note.textContent='没有匹配内容，请切换批次或关键词。';list.append(note);}
  pumpThumbs();
 }
 function renderPicker(){const batches=root.querySelector('#picker-batch');batches.replaceChildren(new Option('所有批次',''),...(catalog?.batches||[]).map(b=>new Option(b.name,b.id)));batches.value=pickerBatch;const tasks=orderedTasks(),current=catalog?.tasks.find(t=>t.id===currentTaskId)||currentSelection;root.querySelector('#picker-task').textContent=current?(taskOrder(current)===999999?'':'第 '+String(taskOrder(current)).padStart(2,'0')+' 条 · ')+current.title+' ▾':'展开内容与封面 ▾';root.querySelector('#picker-search').value=pickerQuery;root.querySelector('#picker-status').textContent=tasks.length+' 条匹配。'+(selected&&!tasks.some(t=>t.id===task.id)?'当前预览不在此筛选中；请从列表选择内容。':'选条仅预览，不上传。');root.querySelector('#picker-prev').disabled=busy||!neighbor(-1);root.querySelector('#picker-next').disabled=busy||!neighbor(1);renderChoices(tasks);}
 root.querySelector('#picker-batch').onchange=e=>{pickerBatch=e.target.value;pickerQuery='';listLimit=30;listOpen=true;renderPicker();};
 root.querySelector('#picker-search').oninput=e=>{pickerQuery=e.target.value;listLimit=30;listOpen=true;renderPicker();};
 root.querySelector('#picker-task').onclick=()=>{if(busy)return;listOpen=!listOpen;renderChoices(orderedTasks());};
 root.querySelector('#picker-list').onkeydown=e=>{const buttons=[...root.querySelector('#picker-list').querySelectorAll('button:not([disabled])')],index=buttons.indexOf(e.target);if(e.key==='Escape'){e.preventDefault();listOpen=false;renderChoices(orderedTasks());root.querySelector('#picker-task').focus();}if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();buttons[Math.max(0,Math.min(buttons.length-1,index+(e.key==='ArrowDown'?1:-1)))]?.focus();}};
 function neighbor(direction){const all=orderedTasks(),anchor=catalog?.tasks.find(t=>t.id===currentTaskId)||currentSelection;const scoped=anchor?all.filter(t=>t.batch_id===anchor.batch_id&&t.account_id===anchor.account_id):all;if(!anchor)return direction>0?scoped[0]:null;const index=scoped.findIndex(t=>t.id===anchor.id);if(index>=0)return scoped[index+direction];const later=scoped.filter(t=>direction>0?taskOrder(t)>taskOrder(anchor):taskOrder(t)<taskOrder(anchor));return direction>0?later[0]:later.at(-1);}
 for(const [id,step] of [['picker-prev',-1],['picker-next',1]])root.querySelector('#'+id).onclick=()=>{if(busy)return;const next=neighbor(step);if(next)selectTask(next);else root.querySelector('#picker-status').textContent=step>0?'本批次已到最后一条。':'本批次没有更早的未发布内容。';};
 root.querySelector('#picker-refresh').onclick=async()=>{if(busy)return;try{await loadCatalog();if(host.isConnected)renderPicker();}catch(e){root.querySelector('#picker-status').textContent=e.message;}};
 host.refreshPicker=renderPicker;
 if(catalog)renderPicker();else loadCatalog().then(()=>{if(host.isConnected)renderPicker();}).catch(e=>{if(host.isConnected)root.querySelector('#picker-status').textContent=e.message+'；请保持分发台打开，再点刷新内容。';});
 const status=root.querySelector('#status');const save=root.querySelector('#save');const fillButton=root.querySelector('#fill');
 const manualTools=document.createElement('details');manualTools.open=false;manualTools.id='manual-tools';manualTools.innerHTML='<summary>单独同步与备用工具</summary><button id="manual-copy-fill" data-picker>仅同步短标题与文案</button><button id="manual-video-download" data-picker>备用：下载视频</button><button id="manual-copy-clipboard">复制完整文案</button><button id="manual-title-clipboard">复制短标题</button><button id="manual-refresh" data-picker>刷新本条内容</button><small>主按钮直接加载视频、文案与封面，无需先下载。页面已有视频时可仅同步文案；封面可单独补上传。</small>';fillButton.after(manualTools);
 function publicationText(){const body=String(task.body||'').trim(),tags=String(task.tags||'').trim();return body+(tags&&!body.includes(tags)?'\n\n'+tags:'');}
 const runControls=document.createElement('div');runControls.id='run-controls';runControls.innerHTML='<p id="run-summary" role="status" aria-live="polite">准备视频、文案、封面与选项，完成后由你核对草稿。</p><div class="picker-row"><button id="run-pause" disabled>暂停</button><button id="run-resume" disabled>继续准备</button><button id="run-stop" disabled>停止</button></div><details><summary>自动执行步骤</summary><ol id="run-steps"></ol></details>';fillButton.after(runControls);

 confirmCover.onclick=()=>{if(busy)return; coverChecked=true;coverStatus.className='ready';coverStatus.textContent='已记录你对平台封面的人工核对，可继续应用标注、原创与合集。';save.disabled=!copyConfirmed;};
 document.documentElement.append(host);
 const bar=root.querySelector('#panel-bar'),section=root.querySelector('section'),ui=readUI();
 let expandedHeight=Number(ui.height)||650,collapsed=!!ui.collapsed,persistTimer;
 const clamp=()=>{const rect=host.getBoundingClientRect();host.style.right='auto';host.style.left=Math.max(8,Math.min(innerWidth-Math.min(rect.width,innerWidth-16)-8,rect.left))+'px';host.style.top=Math.max(8,Math.min(innerHeight-Math.min(rect.height,innerHeight-16)-8,rect.top))+'px';};
 const persist=()=>{clearTimeout(persistTimer);persistTimer=setTimeout(()=>{if(!host.isConnected)return;const r=host.getBoundingClientRect();if(!collapsed)expandedHeight=section.getBoundingClientRect().height;try{localStorage.setItem(UI_KEY,JSON.stringify({left:r.left,top:r.top,width:section.getBoundingClientRect().width,height:expandedHeight,collapsed}));}catch{}},120);};
 section.style.width=Math.max(280,Math.min(innerWidth-16,Number(ui.width)||350))+'px';section.style.height=Math.max(160,Math.min(innerHeight-16,expandedHeight))+'px';if(Number.isFinite(ui.left)){host.style.left=ui.left+'px';host.style.right='auto';}if(Number.isFinite(ui.top))host.style.top=ui.top+'px';
 const applyCollapse=()=>{root.querySelector('#panel-body').hidden=collapsed;if(root.querySelector('#panel-actions'))root.querySelector('#panel-actions').hidden=collapsed||!selected;section.style.height=collapsed?'auto':Math.max(160,Math.min(innerHeight-16,expandedHeight))+'px';section.style.minHeight=collapsed?'0':'160px';section.style.resize=collapsed?'none':'both';root.querySelector('#collapse').textContent=collapsed?'展开':'收起';clamp();persist();};applyCollapse();
 bar.onpointerdown=e=>{if(e.target.closest('button'))return;const rect=host.getBoundingClientRect(),dx=e.clientX-rect.left,dy=e.clientY-rect.top;bar.setPointerCapture(e.pointerId);bar.onpointermove=ev=>{host.style.right='auto';host.style.left=ev.clientX-dx+'px';host.style.top=ev.clientY-dy+'px';clamp();};bar.onpointerup=()=>{bar.onpointermove=null;persist();};};
 for(const [id,step] of [['smaller',-80],['larger',80]])root.querySelector('#'+id).onclick=()=>{const r=section.getBoundingClientRect();section.style.width=Math.max(280,Math.min(innerWidth-16,r.width+step))+'px';if(!collapsed){expandedHeight=Math.max(160,Math.min(innerHeight-16,r.height+step));section.style.height=expandedHeight+'px';}clamp();persist();};
 root.querySelector('#collapse').onclick=()=>{if(!collapsed)expandedHeight=section.getBoundingClientRect().height;collapsed=!collapsed;applyCollapse();};
 const resizeObserver=new ResizeObserver(()=>{clamp();persist();});resizeObserver.observe(section);
 const cleanup=new MutationObserver(()=>{if(!host.isConnected){host.dispose();resizeObserver.disconnect();cleanup.disconnect();clearTimeout(persistTimer);}});cleanup.observe(document.documentElement,{childList:true});
 root.querySelector('#sync-title').onclick=async()=>{if(busy||!selected)return;if(boundTaskId!==task.id){status.textContent='请先加载本条内容，或通过仅填写入口确认页面视频是本条内容。';return;}setBusy(true);try{await field('title','fill',{value:task.title});status.textContent='短标题已重新填写并回读：'+task.title;}catch(e){status.textContent='短标题未完成：'+e.message;}finally{setBusy(false);}};

 root.querySelector('#diagnose').onclick=async()=>{
  try{
   const report={version:'0.7.10',frames:await scan(),iframes:[...document.querySelectorAll('iframe')].map(f=>{try{const u=new URL(f.src,location.href);return {host:u.hostname,path:u.pathname};}catch{return {host:'unknown'};}})};
   status.textContent=report.frames.map(f=>'frame '+f.frameId+' '+f.path+' '+JSON.stringify(f.counts||f.error)).join('\n')||'没有frame代理连接，请重新加载扩展并刷新平台';
   const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='视频号页面结构诊断.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){status.textContent=e.message;}
 };
 const cover=assets.find(a=>a.id===task.cover_id);let coverFilePromise;
 const getCoverFile=()=>coverFilePromise||(coverFilePromise=file(cover).catch(e=>{coverFilePromise=null;throw e;}));
 if(cover)getCoverFile().then(f=>{if(disposed)return;const url=URL.createObjectURL(f);ownedURLs.add(url);const image=root.querySelector('#cover');image.src=url;image.hidden=false;image.alt='当前内容封面';}).catch(e=>{if(!disposed)coverStatus.textContent='本地封面预览未加载：'+e.message;});
 downloadCover.disabled=!cover;
 downloadCover.onclick=async()=>{if(!cover)return;downloadCover.disabled=true;try{const f=await getCoverFile(),url=URL.createObjectURL(f),a=document.createElement('a');ownedURLs.add(url);a.href=url;a.download=cover.name;a.click();setTimeout(()=>{URL.revokeObjectURL(url);ownedURLs.delete(url);},1000);coverStatus.textContent=(coverChecked?'':'封面尚未确认。')+'已发起本条封面下载，可在平台原生上传入口选择该文件。';}catch(e){coverStatus.textContent='封面下载失败：'+e.message;}finally{downloadCover.disabled=!cover;}};
 async function ensureCoverInput(){
  let reports=await scan();const count=()=>reports.reduce((n,f)=>n+(f.counts?.cover||0),0);
  if(count()===1)return;if(count()>1)throw Error('发现多个封面上传入口，请在平台只保留当前封面编辑框');
  const edits=reports.reduce((n,f)=>n+(f.counts?.coverEdit||0),0);if(edits===1)await field('coverEdit','click');
  // Never click “上传封面”: it may open the OS file chooser. An existing input is enough.
  for(let i=0;i<15;i++){reports=await scan();if(count()===1)return;if(count()>1)throw Error('封面上传入口不唯一，请手动核对');await new Promise(r=>setTimeout(r,200));}
  throw Error('请先在平台打开封面编辑，再点「补上传封面」；也可下载本条封面后使用平台原生上传');
 }
 root.querySelector('#upload-cover').onclick=async()=>{
  if(!cover){coverStatus.textContent='任务没有指定封面，请先在分发台选择封面';return;}
  if(busy)return;
  if(boundTaskId!==task.id&&!confirm('确认当前页面的视频就是「'+task.title+'」，目标账号是「'+task.account+'」？本次只补上传这条封面，不修改视频和文案。'))return;
  setBusy(true);coverChecked=false;save.disabled=true;coverStatus.className='';coverStatus.textContent='正在准备本条封面…';
  try{
   if(!location.pathname.includes('/post/create'))throw Error('请进入发表视频页面再补封面');
   if(boundTaskId!==task.id){const binding=await chrome.runtime.sendMessage({type:'observation-bind',task_id:task.id,revision:task.revision,binding_reason:'manual_adoption'});if(!binding?.ok)throw Error('未能关联本次操作：'+(binding?.error||'请重试'));boundTaskId=task.id;boundTaskTitle=task.title;observation.textContent='本次仅补封面，页面关联：'+task.title+'；账号：'+(binding.result?.observed_account||'请手动核对');}
   await ensureCoverInput();const result=await field('cover','upload',{asset:cover});coverStatus.textContent=result.previewReady?'已检测到新的封面预览，请在平台核对裁切并确认。':'封面尚未确认：'+(result.reason||'文件已传入，但替换结果未确认')+'。请检查平台预览；也可下载本条封面后原生上传。';status.textContent='本次仅处理封面，没有重新上传视频或填写文案。';
  }catch(e){coverStatus.textContent='封面暂停：'+e.message;status.textContent='封面尚未确认；可下载本条封面后手动上传。';}finally{setBusy(false);}
 };
 let uploaded=false,runner=null,restoredRecord=null,runManual=false,accountSeen='',originalChoice=true,runError='',runPhase='',manualAction=false,starting=false,loadingRun=selected;
 const runKey='desk.prepare.'+runSession+'.'+(task.id||'none');
 const identity={task_id:task.id||'',revision:task.revision||0,page:new URL(location.href).origin+location.pathname,account_id:task.account_id||'',asset_ids:task.asset_ids,cover_id:task.cover_id||'',collection:collectionTarget()||'',scheduled:task.assistScheduled||task.scheduled||''};
 const stepNames={video:'视频文件传入',video_ready:'等待视频处理',copy:'填写并回读文案',cover:'处理封面',cover_review:'核对平台最终封面',options:'原创、合集与发布选项',final:'再次回读文案'};
 const stepText={pending:'尚未执行',running:'处理中',done:'已完成此步骤',failed:'待处理',interrupted:'中断，需核对',invalidated:'需重新核对'};
 function renderRun(){
  if(disposed)return;const state=runner?.snapshot();if(runError)manualTools.open=true;root.querySelector('#run-summary').style.color=runError?'#a33b2b':'#284039';
  root.querySelector('#run-summary').textContent=loadingRun?'正在读取执行进度…':busy&&manualAction?'正在'+runPhase+'…':busy&&starting?'正在启动：'+(runPhase||'检查当前页面')+'…':runError?'操作未完成：'+runError:!state?'准备视频、文案、封面与选项，完成后由你核对草稿。':state.status==='completed'?'准备流程已完成；尚未保存草稿或发布。':state.status==='stopped'?'执行已停止，已经传入平台的内容会保留。':state.pauseRequested&&busy?'暂停已请求，当前操作返回后停止后续步骤。':state.status==='paused'?'已暂停。核对当前页面后，点击继续准备。':'正在准备本条内容…';
  const list=root.querySelector('#run-steps');list.replaceChildren();for(const [id,name] of Object.entries(stepNames)){const row=document.createElement('li');row.textContent=name+' · '+(stepText[state?.steps[id]?.status]||'尚未执行');list.append(row);}
  root.querySelector('#run-pause').disabled=!busy||!runner||state?.pauseRequested||state?.status==='stopped';
  root.querySelector('#run-resume').disabled=busy||loadingRun||!state||!['paused','idle'].includes(state.status);
  root.querySelector('#run-stop').disabled=!state||['stopped','completed'].includes(state.status);
  fillButton.disabled=busy||loadingRun||!!state&&!['paused','idle','stopped'].includes(state.status);
  root.querySelector('#fill-only').disabled=busy||loadingRun;
  root.querySelector('#declare-original').disabled=busy||!!state&&!['stopped','completed'].includes(state.status);
 }
 function makeRunner(record=null){
  runManual=record?.manual||false;accountSeen=record?.account_seen||'';originalChoice=record?.original??root.querySelector('#declare-original').checked;
  root.querySelector('#declare-original').checked=originalChoice;
  runner=DeskRunner.createRun({identity,restored:record?.engine,persist:engine=>chrome.storage.local.set({[runKey]:{engine,document_id:documentId,route_generation:panelGeneration,manual:runManual,original:originalChoice,account_seen:accountSeen}}),onChange:()=>renderRun()});
  uploaded=!!record?.engine?.steps?.video?.attempts&&!runManual;renderRun();
 }
 const restoreReady=(async()=>{if(!selected)return;try{
  const data=await chrome.storage.local.get(runKey),record=data[runKey];if(record){restoredRecord=record;makeRunner(record);status.textContent='发现本条执行记录。点击一键上传后会检查页面：空白页面重新传入，有视频则继续准备。';}
 }catch(e){runError='执行进度不可用：'+e.message;status.textContent=runError;fillButton.disabled=true;}finally{loadingRun=false;renderRun();}})();
 const routeOK=()=>{if(disposed||!host.isConnected||panelGeneration!==routeGeneration||new URL(location.href).origin+location.pathname!==identity.page||!location.pathname.includes('/post/create'))throw Error('页面已变化，执行已暂停；请回到本条视频编辑页后核对');};
 async function checkBinding(){
  routeOK();const r=await chrome.runtime.sendMessage({type:'observation-check'});if(!r?.ok)throw Error(r?.error||'页面关联无法核对，请重新接管当前内容');
  if(r.result.task_id!==task.id||r.result.revision!==task.revision)throw Error('当前页面已关联其他内容，已停止填写');
  const seen=r.result.observed_account||'';if(accountSeen&&seen&&accountSeen!==seen)throw Error('页面账号已改变，请核对账号后重新开始');
 }
 async function waitVideo(){
  for(let i=0;i<90;i++){await runner.checkpoint();routeOK();const reports=await scan();const count=reports.reduce((n,f)=>n+(f.counts?.existingVideo||0),0);if(count>1)throw Error('页面出现多个视频，请手动核对');if(count===1&&!reports.some(f=>f.error||f.videoProcessing))return {preview:true};await new Promise(r=>setTimeout(r,1000));}
  throw Error('视频预览尚未就绪。请等待平台处理后继续；不会重新上传视频');
 }
 async function step(id,action){await runner.checkpoint();await checkBinding();status.textContent=stepNames[id]+'…';return runner.executeStep(id,action);}
 const runFill=async(manual,continuing=false)=>{
  if(busy||!selected)return;runError='';runPhase='读取本条执行进度';root.querySelector('#run-summary').textContent='正在启动：读取本条执行进度…';await restoreReady;if(busy)return;
  if(task.status==='unknown'&&!confirm('这条内容上传结果不明。请先检查平台没有重复草稿或作品，再继续加载。'))return;
  setBusy(true);save.disabled=true;runError='';starting=true;runPhase='检查上传入口';renderRun();
  try{
   routeOK();if(task.title.length>16)throw Error('短标题超过16字符，请先在分发台修改');
   if(!manual&&!continuing&&(task.asset_ids.length!==1||!assets.some(a=>a.id===task.asset_ids[0]&&a.kind==='video')))throw Error('本条内容需在分发台选择一个有效视频文件');
   const old=runner?.snapshot(),issued=!!old?.steps.video?.attempts&&!runManual;
   const report=await preflight(manual),existing=report.reduce((n,f)=>n+(f.counts?.existingVideo||0),0);
   const pendingVideo=report.some(f=>f.selectedVideoFiles||f.videoProcessing);
   // An attempt is intent, not proof that the file reached the platform.
   // An explicit click can restart only when all frames show an empty upload page.
   if(continuing&&!manual&&!runManual&&existing===0&&!pendingVideo){
    await runner?.stop();continuing=false;uploaded=false;restoredRecord=null;
    runPhase='页面没有视频，重新传入本条文件';renderRun();
   }
   if(manual||continuing&&(issued||runManual)){if(existing!==1)throw Error('继续准备需要页面上恰有一个当前视频。请等待预览出现并核对；不会自动重传');}
   else if(existing||report.some(f=>f.selectedVideoFiles||f.videoProcessing))throw Error('页面已有视频或正在处理文件，请等待预览并使用页面已有视频入口，不重复上传');
   if(continuing&&restoredRecord&&(restoredRecord.document_id!==documentId||restoredRecord.route_generation!==panelGeneration)){if(!confirm('页面已重新打开。确认当前视频就是「'+task.title+'」，并且当前账号正确？继续只检查和填写剩余内容，不重传视频。'))return;coverChecked=!task.cover_id;}
   runPhase='关联当前账号与内容';renderRun();
   const b=await request({type:'observation-bind',task_id:task.id,revision:task.revision,binding_reason:manual||continuing?'manual_adoption':'fill_started'});if(!b?.ok)throw Error(b?.error||'当前任务无法关联');
   const observed=b.result.observed_account||'';if(continuing&&accountSeen&&observed&&observed!==accountSeen)throw Error('页面账号与上次执行不同，请核对后重新开始');
   if(!continuing){copyConfirmed=false;coverChecked=!task.cover_id;makeRunner();runManual=manual;originalChoice=root.querySelector('#declare-original').checked;accountSeen=observed;}
   else {await runner.resume({identity,verified:true});await runner.invalidate(['video_ready','copy','cover_review','options','final']);}
   boundTaskId=task.id;boundTaskTitle=task.title;accountSeen=observed||accountSeen;restoredRecord=null;
   observation.textContent='本次内容：'+task.title+'；目标账号：'+task.account+'；页面账号：'+(observed||'尚未识别，请核对');
   renderRun();
   starting=false;
   await step('video',async({previous})=>{if(runManual)return {manual:true};if(previous?.attempts){uploaded=true;return {previous_request:true};}uploaded=true;await field('video','upload',{asset:assets.find(a=>a.id===task.asset_ids[0])});return {requested:true};});
   await step('video_ready',waitVideo);
   const tags=String(task.tags||'').trim(),copy=String(task.body||'').trim()+(tags&&!String(task.body||'').includes(tags)?'\n\n'+tags:'');
   const fillCopy=async()=>{copyConfirmed=false;await field('title','fill',{value:task.title});await runner.checkpoint();await checkBinding();await field('body','fill',{value:copy});copyConfirmed=true;return {readback:true};};
   await step('copy',fillCopy);
   await runner.checkpoint();await checkBinding();
   try{await field('label','select');status.textContent='视频标注已选择：个人观点，仅供参考';}catch(e){status.textContent='视频标注未填入：'+e.message+'；可点应用标注、原创与合集重试';}
   await step('cover',async({previous})=>{
    if(!task.cover_id)return {not_required:true};if(coverChecked)return {manual_review:true};
    if(!cover)throw Error('任务指定的封面文件不可用，请在分发台检查');
    if(previous?.attempts)throw Error('封面上次已尝试，结果待核对。请用“补上传封面”处理并核对后继续');
    await ensureCoverInput();await runner.checkpoint();await checkBinding();const result=await field('cover','upload',{asset:cover});
    if(!result.previewReady)throw Error('封面尚未确认：'+(result.reason||'未检测到裁切预览'));
    const reports=await scan();if(reports.reduce((n,f)=>n+(f.counts?.coverConfirm||0),0)!==1)throw Error('请在平台完成封面裁切确认，再核对后继续');
    await runner.checkpoint();await field('coverConfirm','click');
    let closed=false;for(let i=0;i<12;i++){if((await scan()).reduce((n,f)=>n+(f.counts?.coverConfirm||0),0)===0){closed=true;break;}await new Promise(r=>setTimeout(r,200));}
    if(!closed)throw Error('封面编辑框仍未关闭，请在平台完成确认');
    coverStatus.textContent='已执行封面确认，请核对平台最终缩略图，再点“封面已核对”。';return {crop_confirmed:true};
   });
   await step('cover_review',async()=>{if(!coverChecked)throw Error('封面尚未确认。请核对平台最终缩略图，点“封面已核对”后继续');return {manual_review:!!task.cover_id};});
   await step('options',async()=>{
    const notes=[],failures=[];
    const option=async(name,kind,op,extra={})=>{await runner.checkpoint();await checkBinding();try{const r=await field(kind,op,extra);if(kind==='original'&&!r.checked||kind==='collection'&&!r.selected||kind==='schedule'&&!r.scheduled)throw Error('结果未回读确认');notes.push(name+'：已执行'+(kind==='label'?'，请核对平台显示':'并回读'));}catch(e){failures.push(name+'：'+e.message);}status.textContent=[...notes,...failures].join('\n');};
    await option('视频标注','label','select');if(originalChoice)await option('原创','original','select',{value:{confirmTerms:true}});if(collectionTarget())await option('合集','collection','select',{value:collectionTarget()});
    if(identity.scheduled)await option('定时','schedule','schedule',{value:identity.scheduled});
    if(failures.length)throw Error(failures.join('\n'));return {options_checked:true};
   });
   await step('final',fillCopy);await runner.finish();
   status.textContent='准备步骤已完成。请核对平台视频、封面、话题、标注与时间，再保存草稿。尚未保存或发布。';save.disabled=!(copyConfirmed&&coverChecked);
  }catch(e){runError=e.code==='RUN_PAUSED'?'当前步骤已结束，可继续准备。':e.code==='RUN_STOPPED'?'已停止；平台已有内容保留。':e.message;status.textContent='暂停：'+runError+(uploaded?'\n已有视频上传请求，不会自动重复上传。':'');if(runner&&!['paused','stopped','completed'].includes(runner.snapshot().status))await runner.pause().catch(()=>{});}
  finally{starting=false;setBusy(false);renderRun();}
 };
 root.querySelector('#manual-refresh').onclick=async()=>{if(busy)return;root.querySelector('#run-summary').textContent='正在刷新本条内容…';try{const fresh=(await loadCatalog()).tasks.find(t=>t.id===task.id);if(!fresh)throw Error('本条已移除或不再待发布');selectTask(fresh);}catch(e){runError=e.message;renderRun();}};
 root.querySelector('#manual-title-clipboard').onclick=async()=>{try{await navigator.clipboard.writeText(task.title);root.querySelector('#run-summary').textContent='短标题已复制：'+task.title;}catch(e){root.querySelector('#run-summary').textContent='复制失败，短标题：'+task.title;}};
 root.querySelector('#manual-copy-clipboard').onclick=async()=>{const text=publicationText();try{await navigator.clipboard.writeText(text);root.querySelector('#run-summary').textContent='已复制文案，短标题：'+task.title;}catch(e){root.querySelector('#run-summary').textContent='复制失败，请展开完整文案后手动复制。';}};
 root.querySelector('#manual-video-download').onclick=async()=>{if(busy||!selected)return;const asset=assets.find(a=>a.kind==='video');if(!asset){runError='本条没有视频素材';renderRun();return;}setBusy(true);manualAction=true;runPhase='下载视频';runError='';renderRun();try{const video=await file(asset),url=URL.createObjectURL(video);ownedURLs.add(url);const a=document.createElement('a');a.href=url;a.download=asset.name;a.click();root.querySelector('#run-summary').textContent='视频已下载，请在平台选择该文件上传。';}catch(e){runError=e.message;status.textContent=e.message;}finally{setBusy(false);manualAction=false;if(runError)renderRun();}};
 root.querySelector('#manual-copy-fill').onclick=async()=>{if(busy||!selected)return;setBusy(true);manualAction=true;copyConfirmed=false;save.disabled=true;runPhase='仅同步文案';runError='';renderRun();try{routeOK();if(task.title.length>16)throw Error('短标题超过16字符，请在内容工作台修改');await preflight(true);const b=await request({type:'observation-bind',task_id:task.id,revision:task.revision,binding_reason:'manual_adoption'});if(!b?.ok)throw Error(b?.error||'未能关联当前账号');boundTaskId=task.id;boundTaskTitle=task.title;accountSeen=b.result?.observed_account||'';await field('title','fill',{value:task.title});await field('body','fill',{value:publicationText()});copyConfirmed=true;save.disabled=!(copyConfirmed&&coverChecked);root.querySelector('#run-summary').textContent='短标题与文案已同步，请核对平台内容。';status.textContent='仅同步文案完成';}catch(e){runError=e.message;status.textContent='文案未同步：'+e.message;}finally{setBusy(false);manualAction=false;if(runError)renderRun();}};
 fillButton.onclick=()=>runFill(false,!!runner&&['paused','idle'].includes(runner.snapshot().status));
 root.querySelector('#run-pause').onclick=async()=>{try{await runner?.pause();}catch(e){status.textContent='暂停状态未保存：'+e.message;}renderRun();};
 root.querySelector('#run-stop').onclick=async()=>{try{await runner?.stop();uploaded=false;save.disabled=true;}catch(e){status.textContent='停止状态未保存：'+e.message;}renderRun();};
 root.querySelector('#run-resume').onclick=()=>runFill(runManual,true);
 // Selecting and restoring progress never operates the platform without a click.
 root.querySelector('#fill-only').onclick=()=>{if(busy)return;if(confirm('确认页面上的视频就是「'+task.title+'」？将开始新的准备流程，保留视频并重新填写文案与选项。'))runFill(true);};
 renderRun();
 const publicationBox=document.createElement('div');publicationBox.innerHTML='<p id="publication-status"></p><button id="publication-confirm">已发布，下一条</button><button id="publication-undo">撤销已发布标记</button><button id="publication-next">下一条</button>';
 publicationBox.id='publication-box';preview.append(publicationBox);
 function renderPublication(){const done=task.publication_progress?.status==='published';root.querySelector('#publication-status').textContent=done?'已发布（人工确认） · '+new Date(task.publication_progress.confirmed_at).toLocaleString('zh-CN'):'尚未记录发布成功；上传或点击发表不等于发布完成。';root.querySelector('#publication-confirm').hidden=done;root.querySelector('#publication-undo').hidden=!done;}
 for(const action of ['confirm','undo'])root.querySelector('#publication-'+action).onclick=async()=>{if(busy||!selected)return;setBusy(true);try{const r=await chrome.runtime.sendMessage({type:'publication-'+action,task_id:task.id,revision:task.revision});if(!r.ok)throw Error(r.error);task.publication_progress=r.result;renderPublication();await loadCatalog();status.textContent=action==='confirm'?'已保存人工发布标记。下次待发布列表会跳过本条。':'已撤销标记，本条回到待发布列表。';if(r.result.sync_error)status.textContent+=' 分发台同步待处理：'+r.result.sync_error;}catch(e){status.textContent=e.message;}finally{setBusy(false);}if(action==='confirm'&&task.publication_progress?.status==='published'&&!task.publication_progress?.sync_error)await root.querySelector('#publication-next').onclick();};
 root.querySelector('#publication-next').onclick=async()=>{if(busy)return;try{await loadCatalog();const tasks=orderedTasks().filter(t=>t.account_id===task.account_id&&t.batch_id===task.batch_id&&t.id!==task.id);const next=tasks.find(t=>taskOrder(t)>taskOrder(task));if(next)selectTask(next);else status.textContent='当前账号和批次没有其他未发布内容。';}catch(e){status.textContent=e.message;}};renderPublication();
 const compactStyle=document.createElement('style');compactStyle.textContent='section{display:flex;flex-direction:column;padding:10px;height:650px;font-size:13px;overflow:hidden}#panel-bar{flex-shrink:0;padding:0 0 8px;border-bottom:1px solid #e0e8e2}#panel-bar strong{font-size:12px}#panel-body{overflow:auto;min-height:0;flex:1;padding-top:8px}button{padding:6px 9px;min-height:32px;margin:3px 0;font-size:12px}#selected-preview>#cover{max-height:90px;width:68px;float:left;margin:0 10px 8px 0;border-radius:5px}#title{font-weight:600;margin:8px 0;font-size:13px}#picker-controls{padding:6px 0;margin-bottom:8px}#picker-controls label{font-size:11px}#page-observation{padding:6px;font-size:11px}#selected-preview>p{font-size:12px;margin:8px 0}#panel-actions{flex-shrink:0;clear:both;border-top:1px solid #dce5df;padding-top:8px;background:white;display:grid;grid-template-columns:1fr 1fr;gap:6px}#panel-actions button{margin:0;min-height:34px}#panel-actions #fill{background:#284b40;color:white}#panel-actions #publication-confirm{background:#e7f1eb;color:#284b40}#panel-actions #confirm-cover{background:#f3f6f3}#panel-actions #publication-next{background:white}#status{font-size:12px;margin:8px 0;max-height:100px;overflow:auto}#run-controls p{font-size:12px;margin:8px 0}details{margin:8px 0}summary{font-size:12px;cursor:pointer}.cover-tools{margin:8px 0;padding:8px}#publication-status{font-size:12px}#publication-undo{width:auto}';root.append(compactStyle);
 const coverDetails=document.createElement('details');const coverSummary=document.createElement('summary');coverSummary.textContent='封面补传与下载';coverDetails.append(coverSummary,coverTools);manualTools.append(coverDetails,choices,repairs,save);
 const footer=document.createElement('div');footer.id='panel-actions';footer.hidden=collapsed||!selected;footer.setAttribute('aria-label','常用操作');footer.append(fillButton,root.querySelector('#publication-next'),confirmCover,root.querySelector('#publication-confirm'));section.append(footer);
 root.querySelector('#confirm-cover').title='确认你已在平台核对本条封面';root.querySelector('#publication-confirm').title='记录当前内容已发布，再选择同批次下一条；不会点击平台发表';
 save.onclick=async()=>{
  if(busy)return;
  if(!confirm('确认视频上传已完成，封面、话题、描述、短标题和个人观点均已核对？本次仅保存草稿，不公开发布。'))return;
  try{setBusy(true);save.disabled=true;await field('save','click');const recorded=await chrome.runtime.sendMessage({type:'observation-explicit',event_kind:'draft_clicked'});if(!recorded?.ok)observation.textContent='草稿点击已执行，但观察未记录：'+(recorded?.error||'请核对本机连接');status.textContent='已点击保存草稿一次。请到草稿列表重新打开核对；这还不代表保存成功。';}catch(e){status.textContent='暂停：'+e.message;}finally{setBusy(false);}
 };
 }
 chrome.runtime.onMessage.addListener((m,sender,reply)=>{if(m.type==='observation-feedback'){const el=currentHost?.shadowRoot?.querySelector('#page-observation');if(el)el.textContent=[m.observed_account?'页面账号：'+m.observed_account:'账号尚未识别',({schedule_changed:'检测到时间修改',submit_clicked:'检测到点击发布，结果待核对',draft_clicked:'检测到点击保存草稿，结果待核对',result_observed:'检测到平台提示'})[m.event_kind]||'',m.scheduled_text||'',m.result_text||'',m.recorded?'已记录观察（不等于发布成功）':m.queued?'记录已保存在插件，等待同步':'',m.error?'记录提示：'+m.error:''].filter(Boolean).join(' · ');return;}if(m.type!=='prepare')return;try{if(busy)throw Error('当前操作尚未完成');currentTaskId=m.task.id;currentSelection=m.task;dismissed=false;panel(m.task,m.assets,false);reply({ok:true});}catch(e){reply({ok:false,error:e.message});}});
 const ensurePanel=()=>{const path=location.pathname,changed=path!==lastPath;if(changed){lastPath=path;routeGeneration++;dismissed=false;}if(path.includes('/post/create')&&!dismissed&&!busy&&(changed||!document.querySelector('#desk-channels-assistant'))){const task=catalog?.tasks.find(t=>t.id===currentTaskId)||currentSelection;panel(task,task?(catalog?.assets||[]):[]);}};
 if(typeof window!=='undefined')window.addEventListener('popstate',ensurePanel);
 ensurePanel();setInterval(ensurePanel,1200);
})();
