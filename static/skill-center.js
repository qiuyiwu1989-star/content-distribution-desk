/* Live canonical skill sources + explicit, reviewable Agent requests. */
(() => {
 let skills=[],requests=[],error='',loading=true,tab='skills',detail=null,context=null,formDraft=null;
 const names={pending:'待 Agent 接单',running:'Agent 已接单',completed:'Agent 回报完成',failed:'处理失败',canceled:'已取消'};
 const defaultInstruction={
  'video-cover-design':'根据这条内容的实际观点，先设计 3 个不同视觉方向的封面样张，提供缩略图让我选择；选定后再批量制作。',
  'course-video-editing':'站在听众角度检查这一段能否独立看懂，优化口语重复和节奏；保留原声与意思，先给出可审核的精修方案。',
  'experience-summary':'根据本批次的成片、审核意见与交付记录提炼经验，说明已验证的修正和仍待核实的事项。'
 };
 async function skillApi(path,method='GET',body){
  try{return await api(path,method,body);}catch(err){
   if(!err.message.includes('会话已刷新'))throw err;
   const response=await fetch('/',{cache:'no-store'});
   if(!response.ok)throw err;
   const page=new DOMParser().parseFromString(await response.text(),'text/html');
   const token=page.querySelector('meta[name="desk-token"]')?.content;
   if(!token)throw err;
   $('meta[name="desk-token"]').content=token;
   return api(path,method,body);
  }
 }
 const baseShell=shell,baseRender=render;
 shell=function(){return baseShell().replace('</nav>',`<button class="nav-item ${view==='skill-center'?'active':''}" data-skill-nav ${view==='skill-center'?'aria-current="page"':''}>${icon('file')}<span>技能中心</span></button></nav>`);};
 async function load(){try{const [a,b]=await Promise.all([skillApi('/skills'),skillApi('/skill-requests')]);skills=a.skills;requests=b.requests;error='';}catch(e){error=e.message;}finally{loading=false;}}
 function draw(){
  $('#content').innerHTML=`<div class="page-heading"><div><h1>技能中心</h1><p>直接读取本机技能，更新自动同步。</p></div><button class="secondary" data-agent-onboarding>Agent 接入</button><button class="secondary" data-skill-refresh>检查更新</button></div><div class="tabs skill-tabs"><button data-skill-tab="skills" class="${tab==='skills'?'selected':''}">技能</button><button data-skill-tab="requests" class="${tab==='requests'?'selected':''}">调用记录</button></div>${error?`<div class="library-warning" role="alert">${esc(error)} <button class="text-button" data-skill-refresh>重新读取</button></div>`:''}${loading?'<p>正在读取技能…</p>':tab==='skills'?`<div class="skill-grid">${skills.map(s=>`<article class="skill-card"><div class="skill-symbol">${icon(s.id==='video-cover-design'?'grid':s.id==='course-video-editing'?'external':'file')}</div><h2>${esc(s.label)}</h2><p>${esc(s.hint)}</p><small>${s.available?`已同步 · ${esc(new Date(s.updated_ns/1000000).toLocaleString('zh-CN'))}`:'原始文件不可用'}</small><div class="skill-actions"><button class="secondary" data-skill-detail="${esc(s.id)}">查看技能</button><button class="secondary" data-skill-history="${esc(s.id)}">版本历史${s.audit_head?` · v${s.audit_head.sequence}`:""}</button><button class="primary" data-skill-call="${esc(s.id)}" ${s.available?'':'disabled'}>调用技能</button></div></article>`).join('')}</div>`:`<div class="skill-request-list">${requests.length?requests.map(r=>`<button class="skill-request" data-skill-request="${esc(r.id)}"><span><strong>${esc(skills.find(s=>s.id===r.skill_id)?.label||r.skill_id)}</strong><small>${esc(r.contents.map(x=>x.title).join('、'))}</small></span><span>${names[r.status]||esc(r.status)}<small>${esc(date(r.created,true))}</small></span></button>`).join(''):'<section class="panel"><h2>还没有调用记录</h2><p>选择技能和内容后，任务会保留在这里。</p></section>'}</div>`}`;
 }
 render=function(){if(view==='skill-center'){if(!S)return;$('#app').innerHTML=shell();$('.topbar>span').textContent='工作空间 / 技能中心';draw();}else baseRender();};
 function currentPackage(){return $('[data-rmanage]')?.dataset.rmanage||Library.detailId||null;}
 function mount(){
  if(view!=='packages')return;
  const pid=currentPackage();if(!pid)return;
  const heading=$('.library-detail-heading')||$('.review-title');
  if(heading&&!heading.querySelector('[data-skill-for-content]'))heading.insertAdjacentHTML('beforeend',`<button class="secondary" data-skill-for-content="${esc(pid)}">调用技能</button>`);
 }
 function showDetail(s){
  openModal(s.label,`<p>${esc(s.hint)}</p><div class="skill-version">${s.version?'版本 '+esc(s.version)+' · ':''}内容指纹 ${esc(s.revision.slice(0,12))}</div><pre class="skill-document">${esc(s.content)}</pre><details><summary>原始文件与参考资料</summary><p>${esc(s.source_path)}</p>${s.resources.map(r=>`<p>${esc(r.path)}</p>`).join('')}</details><div class="form-footer"><button class="secondary" data-action="close">关闭</button><button class="secondary" data-skill-history="${esc(s.id)}">版本历史</button><button class="secondary" data-skill-edit="${esc(s.id)}">修改技能</button><button class="primary" data-skill-call="${esc(s.id)}">调用技能</button></div>`,true);
 }
 async function prepare(sid,pid=null){
  detail=await skillApi('/skills/'+sid);context=pid||context;
  const ps=Library.orderedPackages();
  const id=formDraft?.package_id||context||ps[0]?.id||'';
  openModal('调用'+detail.label,`<form id="skill-call-form" data-skill="${esc(sid)}" data-key="${formDraft?.key||crypto.randomUUID()}"><label>使用哪个技能<select name="skill_id">${skills.filter(s=>s.available).map(s=>`<option value="${esc(s.id)}" ${s.id===sid?'selected':''}>${esc(s.label)}</option>`).join('')}</select></label><label>处理哪条内容<select name="package_id" required><option value="">请选择内容</option>${ps.map(p=>`<option value="${esc(p.id)}" ${p.id===id?'selected':''}>${esc(p.title)}</option>`).join('')}</select></label>${Library.batch&&ps.length?`<label class="checkbox-label"><input type="checkbox" name="whole_batch" ${formDraft?.whole_batch?'checked':''}>处理当前批次全部 ${ps.length} 条内容</label>`:''}<label>这次要做什么<textarea name="instruction" rows="5" required maxlength="5000">${esc(formDraft?.instruction||defaultInstruction[sid]||'')}</textarea></label><p class="form-note">创建后等待 Agent 接单。可以复制调用文本，或通过分发 MCP 接单。</p><details><summary>本次技能版本</summary><p>内容指纹 ${esc(detail.revision.slice(0,12))}</p><p>${esc(detail.source_path)}</p></details><div class="form-error" role="alert"></div><div class="form-footer"><button type="button" class="secondary" data-action="close">取消</button><button class="primary" type="submit">创建 Agent 任务</button></div></form>`);
 }
 function invocation(r){return `请使用「${skills.find(s=>s.id===r.skill_id)?.label||r.skill_id}」技能处理任务 ${r.id}。\n通过分发台 MCP 的 desk_skill_request 读取该任务（或本机 GET http://127.0.0.1:4318/api/skill-requests/${r.id}）。按该任务保存的技能快照、所选内容和要求执行，先接单，再回报结果。\n技能版本：${r.skill_revision}\n要求：${r.instruction}\n内容：${r.contents.map(p=>p.title).join('、')}`;}
 function showRequest(r){
  openModal('技能调用任务',`<h3>${esc(skills.find(s=>s.id===r.skill_id)?.label||r.skill_id)}</h3><p class="skill-request-state">${names[r.status]||esc(r.status)}</p><p>${esc(r.contents.map(x=>x.title).join('、'))}</p><pre class="skill-document">${esc(r.instruction)}</pre>${r.result?`<h3>Agent 回报</h3><p>${esc(r.result.summary)}</p>`:''}<p class="form-note">技能版本 ${esc(r.skill_revision.slice(0,12))} · ${esc(date(r.created,true))}</p><div class="form-footer"><button class="secondary" data-skill-copy="${esc(r.id)}">复制调用文本</button><a class="secondary" href="/api/skill-requests/${encodeURIComponent(r.id)}" download="${esc(r.skill_id)}-${esc(r.id.slice(0,8))}.json">下载任务包</a>${r.status==='pending'?`<button class="text-button" data-skill-cancel="${esc(r.id)}">取消任务</button>`:''}</div>`);
 }
 document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-skill-nav],[data-skill-refresh],[data-skill-tab],[data-skill-detail],[data-skill-call],[data-skill-for-content],[data-skill-request],[data-skill-copy],[data-skill-cancel],[data-skill-reload]');if(!b)return;
  try{
   if(b.hasAttribute('data-skill-nav')){if(Library.isDirty()||taskDirty()){toast('请先保存或撤销当前修改',true);return;}closeModal();context=null;formDraft=null;view='skill-center';render();await load();draw();}
   if(b.hasAttribute('data-skill-refresh')){await load();draw();toast(error||'已读取最新技能版本',!!error);}
   if(b.dataset.skillTab){tab=b.dataset.skillTab;draw();}
   if(b.dataset.skillDetail){context=null;showDetail(await skillApi('/skills/'+b.dataset.skillDetail));}
   if(b.dataset.skillCall){formDraft=null;await prepare(b.dataset.skillCall);}
   if(b.dataset.skillForContent){formDraft=null;await load();await prepare('video-cover-design',b.dataset.skillForContent);}
   if(b.dataset.skillRequest)showRequest(await skillApi('/skill-requests/'+b.dataset.skillRequest));
   if(b.dataset.skillCopy){const r=await skillApi('/skill-requests/'+b.dataset.skillCopy);await navigator.clipboard.writeText(invocation(r));toast('调用文本已复制，可以交给 Agent');}
   if(b.dataset.skillCancel){const r=await skillApi('/skill-requests/'+b.dataset.skillCancel+'/transition','POST',{status:'canceled'});await load();showRequest(r);if(view==='skill-center')draw();toast('任务已取消');}
   if(b.dataset.skillReload){const f=$('#skill-call-form');formDraft={key:f.dataset.key,package_id:f.elements.package_id.value,instruction:f.elements.instruction.value,whole_batch:f.elements.whole_batch?.checked};await prepare(b.dataset.skillReload);}
  }catch(e){toast(e.message,true);}
 });
 document.addEventListener('change',async e=>{if(e.target.matches('#skill-call-form select[name="skill_id"]')){const f=e.target.form;formDraft={package_id:f.elements.package_id.value,whole_batch:f.elements.whole_batch?.checked};try{await prepare(e.target.value);}catch(e){toast(e.message,true);}}});
 document.addEventListener('submit',async e=>{
  const f=e.target;if(f.id!=='skill-call-form')return;e.preventDefault();e.stopImmediatePropagation();const b=$('button[type=submit]',f);b.disabled=true;
  try{const d=new FormData(f),ids=d.get('whole_batch')==='on'?Library.orderedPackages().map(p=>p.id):[d.get('package_id')];const r=await skillApi('/skill-requests','POST',{skill_id:f.dataset.skill,skill_revision:detail.revision,idempotency_key:f.dataset.key,package_ids:ids,instruction:d.get('instruction')});formDraft=null;await load();showRequest(r);if(view==='skill-center')draw();toast('Agent 任务已建立，等待接单');}
  catch(err){$('.form-error',f).innerHTML=esc(err.message)+` <button type="button" class="text-button" data-skill-reload="${esc(f.dataset.skill)}">读取最新技能并保留要求</button>`;b.disabled=false;}
 },true);

  let historyRows=[],historySkill='',historyVersion='',historyGeneration=0,editorSkill=null,editorPath='';
  const auditKinds={baseline:'初始基线',external:'外部变更',edit:'受控修改'};
  function auditWho(v){return `${v.actor.name} · ${v.actor.assurance==='self-declared'?'署名声明':'来源未知'}`;}
  async function historyDiff(vid,base=null){
   historyVersion=vid;const generation=++historyGeneration;
   const host=$('#skill-audit-diff');if(!host)return;
   host.innerHTML='<p role="status">正在读取差异…</p>';
   try{
    const d=await skillApi('/skills/'+encodeURIComponent(historySkill)+'/history/'+encodeURIComponent(vid)+(base?'?base='+encodeURIComponent(base):''));
    if(generation!==historyGeneration||historyVersion!==vid||!$('#skill-audit-diff'))return;
    const v=d.version;
    host.innerHTML=`<div class="skill-audit-summary"><h3>v${v.sequence} · ${esc(auditKinds[v.kind]||v.kind)}</h3><p>${esc(auditWho(v))} · ${esc(date(v.recorded_at,true))}</p><p>${esc(v.reason)}</p>${v.source_ref?`<p>来源：${esc(v.source_ref)}</p>`:''}<p class="skill-audit-hash">内容 ${esc(v.revision)}<br>审计 ${esc(v.event_hash)}</p><div class="skill-audit-tools"><label>对比版本<select id="skill-audit-base"><option value="" ${!d.base_id||d.base_id==='empty'?'selected':''}>空基线</option>${historyRows.filter(x=>x.id!==vid).map(x=>`<option value="${esc(x.id)}" ${x.id===d.base_id?'selected':''}>v${x.sequence} · ${esc(date(x.recorded_at,true))}</option>`).join('')}</select></label><a class="secondary" href="/api/skills/${encodeURIComponent(historySkill)}/history/${encodeURIComponent(vid)}/download">下载完整快照</a></div></div><div class="skill-audit-files">${d.changes.length?d.changes.map(x=>`<details class="skill-audit-file"><summary><span>${esc(x.path)}</span><small>${esc({added:'新增',modified:'修改',deleted:'删除'}[x.status])} · ${x.before_size} → ${x.after_size} B</small></summary>${x.binary?'<p>二进制或大文件，完整内容保存在版本快照中。</p>':`<pre class="skill-audit-code">${esc(x.diff)}</pre>${x.truncated?'<p>预览已截断，完整内容见快照。</p>':''}`}</details>`).join(''):'<p>两个版本的文件内容一致。</p>'}</div>`;
    document.querySelectorAll('[data-skill-audit-version]').forEach(b=>b.classList.toggle('selected',b.dataset.skillAuditVersion===vid));
   }catch(err){if(generation===historyGeneration)host.innerHTML=`<p role="alert">${esc(err.message)}</p>`;}
  }
  async function showHistory(sid){
   const data=await skillApi('/skills/'+encodeURIComponent(sid)+'/history');
   historyRows=data.versions;historySkill=sid;
   openModal((skills.find(x=>x.id===sid)?.label||sid)+' · 版本历史',`<div class="skill-audit-toolbar"><span>${historyRows.length} 个版本 · 作者署名与外部来源分别记录</span><button class="secondary" data-skill-integrity="${esc(sid)}">校验记录</button><button class="primary" data-skill-edit="${esc(sid)}">修改技能</button></div><div class="skill-audit-layout"><div class="skill-audit-versions">${historyRows.map(v=>`<button class="skill-audit-version" data-skill-audit-version="${esc(v.id)}"><strong>v${v.sequence} · ${esc(auditKinds[v.kind]||v.kind)}</strong><span>${esc(auditWho(v))}</span><small>${esc(date(v.recorded_at,true))}</small><span>${esc(v.reason)}</span></button>`).join('')}</div><div id="skill-audit-diff"></div></div>${(data.evidence||[]).length?`<section class="skill-audit-evidence"><h3>接入前的修改证据</h3>${data.evidence.map(e=>`<details class="skill-audit-file"><summary>${esc(e.actor.name)} · ${e.files.length} 个文件 · 历史补录</summary><p>${esc(e.reason)}</p><p>登记于 ${esc(date(e.recorded_at,true))}；署名声明，非完整历史版本。</p><p class="skill-audit-hash">${esc(e.source_ref)}<br>${esc(e.event_hash)}</p>${e.files.map(f=>`<details><summary>${esc(f.path)}</summary><h4>修改前</h4><pre class="skill-audit-code">${esc(f.before===null?'此记录中为新增文件':f.before)}</pre><h4>修改后</h4><pre class="skill-audit-code">${esc(f.after)}</pre></details>`).join('')}</details>`).join('')}</section>`:''}`,true);
   await historyDiff(historyRows[0].id);
  }


  async function showEditor(sid){
   editorSkill=await skillApi('/skills/'+encodeURIComponent(sid));editorPath='SKILL.md';
   openModal(editorSkill.label+' · 修改技能',`<form id="skill-edit-form"><div class="skill-audit-editor-meta"><label>修改者<input name="actor_name" required maxlength="120" autocomplete="off"></label><label>类型<select name="actor_type"><option value="human">本人</option><option value="agent">Agent</option></select></label></div><label>修改原因<textarea name="reason" required maxlength="5000" rows="2"></textarea></label><label>来源或会话编号<input name="source_ref" maxlength="2000"></label><label>文件<select name="path">${Object.keys(editorSkill.supporting_texts).sort((a,b)=>a==='SKILL.md'?-1:b==='SKILL.md'?1:a.localeCompare(b)).map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('')}</select></label><label>文件内容<textarea class="skill-audit-editor" name="content" rows="18" spellcheck="false">${esc(editorSkill.content)}</textarea></label><p class="skill-version">基于 v${editorSkill.audit_head.sequence} · ${esc(editorSkill.revision.slice(0,12))} · 修改者为署名声明</p><div class="form-error" role="alert"></div><div class="form-footer"><button type="button" class="secondary" data-action="close">取消</button><button class="primary" type="submit">保存为新版本</button></div></form>`,true);
  }
  document.addEventListener('click',async e=>{
   const b=e.target.closest('[data-skill-history],[data-skill-audit-version],[data-skill-edit],[data-skill-integrity]');if(!b)return;
   try{
    if(b.dataset.skillHistory)await showHistory(b.dataset.skillHistory);
    if(b.dataset.skillAuditVersion)await historyDiff(b.dataset.skillAuditVersion);
    if(b.dataset.skillEdit)await showEditor(b.dataset.skillEdit);
    if(b.dataset.skillIntegrity){b.disabled=true;try{const r=await skillApi('/skills/'+encodeURIComponent(b.dataset.skillIntegrity)+'/history-integrity');b.textContent=`校验通过 · ${r.versions} 版`;}finally{b.disabled=false;}}
   }catch(err){toast(err.message,true);}
  });
  document.addEventListener('change',e=>{
   if(e.target.id==='skill-audit-base')historyDiff(historyVersion,e.target.value||'empty');
   if(e.target.matches('#skill-edit-form select[name="path"]')){
    const f=e.target.form;
    if(f.elements.content.value!==editorSkill.supporting_texts[editorPath]&&!window.confirm('放弃当前文件尚未保存的修改？')){e.target.value=editorPath;return;}
    editorPath=e.target.value;f.elements.content.value=editorSkill.supporting_texts[editorPath];
   }
  });
  document.addEventListener('submit',async e=>{
   const f=e.target;if(f.id!=='skill-edit-form')return;e.preventDefault();e.stopImmediatePropagation();
   const b=f.querySelector('button[type="submit"]');b.disabled=true;
   const data=Object.fromEntries(new FormData(f));data.expected_revision=editorSkill.revision;data.expected_version_id=editorSkill.audit_head.id;
   try{await skillApi('/skills/'+encodeURIComponent(editorSkill.id)+'/edit','POST',data);const sid=editorSkill.id;await load();if(view==='skill-center')draw();await showHistory(sid);toast('已保存新版本与修改记录');}
   catch(err){f.querySelector('.form-error').textContent=err.message;b.disabled=false;}
  },true);

 let onboarding=null;
 document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-agent-onboarding],[data-agent-copy],[data-agent-check]');if(!b)return;
  try{
   if(b.hasAttribute('data-agent-onboarding')){
    onboarding=await skillApi('/agent/bootstrap');
    openModal('Agent 接入',`<p>规范版本 ${esc(onboarding.policy.revision.slice(0,12))} · 本机连接</p><div class="form-footer"><button class="secondary" data-agent-copy>复制接入指令</button><button class="secondary" data-skill-history="platform-onboarding">规范版本历史</button></div><details><summary>共同规范</summary><pre class="skill-document">${esc(onboarding.policy.content)}</pre></details><h3>资源目录</h3>${onboarding.resources.map(r=>`<p><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.label)}</a></p>`).join('')}<label>本次使用技能<select id="agent-check-skill">${onboarding.skills.filter(s=>s.id!=='platform-onboarding').map(s=>`<option value="${esc(s.id)}">${esc(s.label)}</option>`).join('')}</select></label><button class="secondary" data-agent-check>检查开工条件</button><div id="agent-check-result" role="status"></div>`,true);
   }
   if(b.hasAttribute('data-agent-copy')){await navigator.clipboard.writeText(onboarding.instructions+'\n平台：http://127.0.0.1:4318\nMCP：content-desk\n无 MCP 时先 GET http://127.0.0.1:4318/api/agent/bootstrap。不能连接时报告缺口，不冒充已读。');toast('已复制接入指令');}
   if(b.hasAttribute('data-agent-check')){
    const sid=$('#agent-check-skill').value;b.disabled=true;
    try{const r=await skillApi('/agent/preflight?skills='+encodeURIComponent(sid));const host=$('#agent-check-result');if(host)host.innerHTML=`<h3>${r.resource_status==='ready'?'平台资源可读取':'存在资源缺项'}</h3><p>执行环境：待核实 · 听审：未执行</p>${r.skills.map(s=>`<p>${esc(s.label||s.id)} · ${s.available?esc(s.revision.slice(0,12)):'不可用'}</p>`).join('')}${r.missing.map(s=>`<p>未登记：${esc(s)}</p>`).join('')}<ul>${r.checks_remaining.map(s=>`<li>${esc(s)}</li>`).join('')}</ul>`;}finally{b.disabled=false;}
   }
  }catch(err){toast(err.message,true);}
 });
 new MutationObserver(mount).observe($('#app'),{childList:true,subtree:true});
 document.addEventListener('DOMContentLoaded',async()=>{await load();mount();});
 setInterval(async()=>{if(view==='skill-center'){const old=JSON.stringify(skills.map(s=>s.revision));await load();if(!$('.modal'))draw();else if(old!==JSON.stringify(skills.map(s=>s.revision)))toast('技能原始文件已更新，下次调用将使用新版本');}},15000);
})();
