/* Task-oriented publishing workspace. No dispatch or mutation runs during rendering. */
(function(root){
  const labels={draft:'待安排',ready:'待交付',scheduled:'已排期',queued:'等待执行',running:'执行中',delivered:'已记录平台草稿',review:'已记录送审',published:'已记录公开发布',failed:'执行失败',unknown:'上传结果待核对',blocked:'执行受阻',canceled:'已取消'};
  const groups={prepare:'待安排',execute:'待执行',verify:'待核对',complete:'已完成',history:'已取消'};
  function taskGroup(t){
    if(t.status==='canceled')return 'history';
    if(t.status==='published'||(t.status==='delivered'&&t.options?.mode==='draft'))return 'complete';
    if(['unknown','review','delivered'].includes(t.status))return 'verify';
    if(['ready','scheduled','queued','running'].includes(t.status))return 'execute';
    return 'prepare';
  }
  function taskStatus(t){
    if(t.status==='delivered')return t.options?.mode==='draft'?'已记录平台草稿（本次目标）':t.options?.mode==='publish'?'已记录草稿，发布待核对':'已记录平台草稿';
    return labels[t.status]||'状态待核对';
  }
  function taskReason(t,ctx){
    ctx=ctx||(typeof S!=='undefined'?S:{});
    if(t.status==='unknown')return '上传结果不明；先检查平台草稿与作品列表';
    if(t.status==='failed')return t.note||'查看失败原因，核对平台后再决定如何处理';
    if(t.status==='blocked')return t.note||'查看受阻原因，修复设置后重新检查';
    if(t.status==='review')return '已记录提交审核，仍需核对平台审核结果';
    if(t.status==='delivered')return t.options?.mode==='draft'?'已记录达到送入草稿的目标；查看记录说明与平台结果':t.options?.mode==='publish'?'尚无公开发布结果；请在平台核对':'人工回填的草稿记录；后续发布需继续记录结果';
    if(t.status==='published')return '已回填公开作品链接；可打开平台查看';
    if(t.status==='canceled')return '本次安排已取消，历史记录保留';
    if(t.status==='scheduled')return t.options?.mode==='manual'?'到点提醒人工交付':'按计划执行已批准版本';
    if(t.status==='running')return '正在执行已批准版本，请等待结果';
    if(t.status==='queued')return '已加入执行队列，等待执行';
    if(t.status==='ready')return t.options?.mode==='manual'?'渠道版本已确认，可前往平台交付':'渠道版本已确认，等待安排执行';
    const missing=[];
    if(!String(t.title||'').trim())missing.push('缺少发布标题');
    if(t.format==='article'&&!String(t.body||'').trim())missing.push('缺少正文');
    if(t.format==='video'&&t.asset_ids?.length!==1)missing.push('需选择一个视频');
    if(t.format==='gallery'&&!t.asset_ids?.length)missing.push('未选择图片');
    if(Array.isArray(ctx.assets)){
      const selected=(t.asset_ids||[]).map(id=>ctx.assets.find(asset=>asset.id===id));
      if(selected.some(asset=>!asset))missing.push('所选素材不可用');
      if(selected.some(asset=>asset&&asset.package_id!==t.package_id))missing.push('素材不属于当前内容');
      if(t.format==='video'&&selected.some(asset=>asset&&asset.kind!=='video'))missing.push('需选择视频文件');
      if(t.format==='gallery'&&selected.some(asset=>asset&&asset.kind!=='image'))missing.push('图文只能选择图片');
      if(t.cover_id){const cover=ctx.assets.find(asset=>asset.id===t.cover_id);if(!cover||cover.kind!=='image'||cover.package_id!==t.package_id)missing.push('所选封面不可用');}
    }
    const a=(ctx.accounts||[]).find(x=>x.id===t.account_id);
    const rule=ctx.rules?.[a?.platform]?.[t.format]||{};
    if(rule.category_required&&!t.options?.category)missing.push('缺少分区');
    if(rule.tags_required&&!String(t.tags||'').trim())missing.push('缺少话题标签');
    if(missing.length)return missing.join('、');
    if(t.format==='video'&&!t.cover_id)return '未指定封面；检查内容后确认渠道版本';
    return '检查内容、账号与交付设置，确认渠道版本';
  }
  function channelSummary(tasks){
    if(!tasks.length)return '尚未安排渠道';
    const counts={};tasks.forEach(t=>{const g=taskGroup(t);counts[g]=(counts[g]||0)+1;});
    return Object.keys(groups).filter(g=>counts[g]).map(g=>`${counts[g]} 项${groups[g]}`).join(' · ');
  }
  function unresolvedRuns(tasks,runs){
    const known=new Map(tasks.map(t=>[t.id,t]));
    return runs.filter(r=>r.status==='unknown'&&known.get(r.task_id)?.status!=='unknown');
  }
  function normalizeState(state){state.statuses={...state.statuses,...labels};return state;}
  root.DeskUX={taskGroup,taskStatus,taskReason,channelSummary,normalizeState,unresolvedRuns,labels,groups};
  if(typeof module!=='undefined')module.exports=root.DeskUX;
})(typeof window!=='undefined'?window:globalThis);

if(typeof document!=='undefined'){
  let workspaceGroup='all',workspaceBatch=localStorage.getItem('desk-workspace-batch')||'',recordGroup='all',recordQuery='';
  const family={calendar:'queue',runs:'records',rules:'accounts'};
  const primaryNav=[['packages','box','内容库'],['queue','grid','发布工作台'],['records','history','发布记录'],['accounts','users','账号与设置']];
  const subtabs=(items)=>`<nav class="workspace-subnav" aria-label="当前工作区视图">${items.map(([id,label])=>`<button data-nav="${id}" class="${view===id?'selected':''}" ${view===id?'aria-current="page"':''}>${label}</button>`).join('')}</nav>`;
  const titleBlock=(title,sub,action)=>`<div class="page-heading workspace-heading"><div><h1>${title}</h1><p>${sub}</p></div>${action||''}</div>`;
  shell=function(){
    const route=family[view]||view,name=primaryNav.find(n=>n[0]===route)?.[2]||'内容库';
    const needed=S.tasks.filter(t=>['prepare','execute','verify'].includes(DeskUX.taskGroup(t))).length;
    return `<aside class="sidebar"><a class="brand" href="#packages" data-nav="packages"><span class="brand-mark">分</span><span>分发台<small>QIU YIWU / STUDIO</small></span></a><div class="workspace"><span class="avatar">邱</span><div>个人内容工作台<small>本机工作空间</small></div></div><div class="nav-caption">内容分发</div><nav aria-label="主要导航">${primaryNav.map(([id,i,label])=>`<button class="nav-item ${route===id?'active':''}" data-nav="${id}" ${route===id?'aria-current="page"':''}>${icon(i)}<span>${label}</span>${id==='queue'&&needed?`<b aria-label="${needed} 项未完成任务">${needed}</b>`:''}</button>`).join('')}</nav><div class="sidebar-bottom"><div class="local-label"><span></span>本机保存 · 版本受控</div><p>内容、安排与操作记录<br>保存在这台电脑。</p><a class="backup" href="/api/backup">${icon('download')} 下载完整备份</a><div class="owner">邱懿武 <span>内容编辑部</span></div></div></aside><div class="main"><header class="topbar"><span>工作空间 <span class="slash">/</span> ${name}</span><div><span class="date-now">${new Date().toLocaleDateString('zh-CN',{timeZone:'Asia/Singapore',month:'long',day:'numeric',weekday:'long'})}</span><button class="icon-button" data-action="refresh" title="刷新" aria-label="刷新">${icon('history')}</button><span class="mini-avatar">邱</span></div></header><main id="content"></main><footer>内容准备好，下一站是读者。<span>内容审核与平台交付分别记录</span></footer></div>`;
  };
  function metadata(){return (typeof Library!=='undefined'?Library.meta:null)||batchCatalog||{batches:[],packages:{}};}
  function info(id){return metadata().packages?.[id]||{};}
  function batchControl(){const batches=metadata().batches||[];if(workspaceBatch&&!batches.some(b=>b.id===workspaceBatch))workspaceBatch='';return `<label class="workspace-batch">内容批次<select id="workspace-batch"><option value="">所有批次</option>${batches.map(b=>`<option value="${esc(b.id)}" ${workspaceBatch===b.id?'selected':''}>${esc(b.name)}</option>`).join('')}</select></label>`;}
  function scopeTasks(){return S.tasks.filter(t=>!workspaceBatch||info(t.package_id).batch_id===workspaceBatch);}
  function ordered(tasks){return [...tasks].sort((a,b)=>{const ai=info(a.package_id),bi=info(b.package_id);return String(ai.batch_id||'~').localeCompare(String(bi.batch_id||'~'))||(ai.sequence??Infinity)-(bi.sequence??Infinity)||String(a.created||'').localeCompare(String(b.created||''))||a.id.localeCompare(b.id);});}
  function matches(t,q){return !q||[t.title,account(t)?.name,S.packages.find(p=>p.id===t.package_id)?.title].join(' ').toLocaleLowerCase().includes(q.toLocaleLowerCase());}
  function rows(tasks){return tasks.map(t=>{const p=platform(t),a=account(t),pkg=S.packages.find(x=>x.id===t.package_id),seq=info(t.package_id).sequence,g=DeskUX.taskGroup(t);return `<button class="workspace-task" data-task="${esc(t.id)}"><span class="workspace-task-content">${t.cover_id?`<img src="/api/assets/${encodeURIComponent(t.cover_id)}" alt="" loading="lazy">`:`<span class="workspace-file">${icon(t.format==='video'?'external':'file')}</span>`}<span>${seq!=null?`<small class="workspace-sequence">第 ${String(seq).padStart(2,'0')} 条</small>`:''}<strong>${esc(pkg?.title||t.title)}</strong><small>发布标题：${esc(t.title)}</small></span></span><span class="workspace-task-account">${esc(p?.name||'账号待检查')}<small>${esc(a?.name||'账号不可用')}</small>${t.scheduled?`<small>计划 ${esc(date(t.scheduled,true))}</small>`:''}</span><span class="workspace-task-state"><b class="workspace-status ${g}">${esc(DeskUX.taskStatus(t))}</b><small>${esc(DeskUX.taskReason(t))}</small></span><span class="workspace-next">${{prepare:'检查任务',execute:t.status==='running'?'查看进度':'查看安排',verify:'核对结果',complete:'查看结果',history:'查看历史'}[g]} ${icon('chevron')}</span></button>`;}).join('');}
  function unknownNotice(){const runs=DeskUX.unresolvedRuns(S.tasks,S.runs||[]).filter(r=>!workspaceBatch||info(S.tasks.find(t=>t.id===r.task_id)?.package_id).batch_id===workspaceBatch);return runs.length?`<section class="workspace-alert" role="status"><strong>${runs.length} 次执行仍有未知结果</strong><p>这些执行的结果与当前任务状态不同。先核对平台，避免重复上传。</p>${runs.map(r=>{const t=S.tasks.find(t=>t.id===r.task_id);return t?`<button class="secondary small" data-task="${esc(t.id)}">核对：${esc(t.title)}</button>`:`<span>关联任务不可用 · ${esc(r.message||r.id)}</span>`;}).join('')}</section>`:'';}
  renderQueue=function(){
    const batch=batchControl(),all=scopeTasks(),tasks=ordered(all.filter(t=>(workspaceGroup==='all'?['prepare','execute','verify'].includes(DeskUX.taskGroup(t)):DeskUX.taskGroup(t)===workspaceGroup)&&matches(t,query)));
    const groups=[['all','全部待办'],['prepare','待安排'],['execute','待执行'],['verify','待核对']];
    $('#content').innerHTML=titleBlock('发布工作台','按当前需要处理的事情查看渠道任务。',`<button class="secondary" data-nav="packages">从内容库安排渠道</button>`)+subtabs([['queue','待办列表'],['calendar','发布日历']])+batch+unknownNotice()+`<section class="panel workspace-panel"><div class="workspace-toolbar"><div class="workspace-tabs" aria-label="任务进度">${groups.map(([g,label])=>{const count=all.filter(t=>g==='all'?['prepare','execute','verify'].includes(DeskUX.taskGroup(t)):DeskUX.taskGroup(t)===g).length;return `<button data-workspace-group="${g}" class="${workspaceGroup===g?'selected':''}" aria-pressed="${workspaceGroup===g}">${label}<b>${count}</b></button>`;}).join('')}</div><label class="search">${icon('search')}<input id="search" value="${esc(query)}" placeholder="搜索内容或账号" aria-label="搜索内容或账号"></label></div><p class="workspace-list-note">${workspaceBatch?'当前批次':'所有批次'} · ${tasks.length} 项任务 · 按内容顺序排列</p>${tasks.length?rows(tasks):`<div class="workspace-empty"><h2>当前没有${workspaceGroup==='all'?'待办':DeskUX.groups[workspaceGroup]}任务</h2><p>${query?'尝试其他关键词，或切换批次。':'可以切换进度查看其他任务，或从内容库安排渠道。'}</p><button class="secondary" data-nav="packages">查看内容库</button></div>`}</section><p class="workspace-footnote">待安排表示尚未确认交付设置，不代表内容尚未整理；发布检查会进一步核对文件与账号。已完成和已取消的安排保留在发布记录。</p>`;
  };
  renderRecords=function(){
    const batch=batchControl(),all=scopeTasks().filter(t=>['complete','history','verify'].includes(DeskUX.taskGroup(t))||['failed','blocked'].includes(t.status)),tasks=ordered(all.filter(t=>(recordGroup==='all'||DeskUX.taskGroup(t)===recordGroup)&&matches(t,recordQuery)));
    $('#content').innerHTML=titleBlock('发布记录','按渠道查看已记录的结果、作品链接与历史安排。')+subtabs([['records','渠道结果'],['runs','执行记录']])+batch+unknownNotice()+`<section class="panel workspace-panel"><div class="workspace-toolbar"><div class="workspace-tabs" aria-label="记录筛选">${[['all','全部记录'],['complete','已完成'],['verify','待核对'],['history','已取消']].map(([g,l])=>`<button data-record-group="${g}" class="${recordGroup===g?'selected':''}" aria-pressed="${recordGroup===g}">${l}<b>${all.filter(t=>g==='all'||DeskUX.taskGroup(t)===g).length}</b></button>`).join('')}</div><label class="search">${icon('search')}<input id="workspace-record-search" value="${esc(recordQuery)}" placeholder="搜索内容或账号" aria-label="搜索记录"></label></div><p class="workspace-list-note">送入草稿与公开发布分别记录；人工回填以记录说明为依据。</p>${tasks.length?rows(tasks):'<div class="workspace-empty"><h2>当前没有匹配的记录</h2><p>切换批次或筛选条件，交付后的记录会保留在这里。</p></div>'}</section>`;
  };
  const baseCalendar=renderCalendar,baseRuns=renderRuns,baseAccounts=renderAccounts,baseRules=renderRules;
  function replaceHeading(title,sub,tabs){const content=$('#content'),old=$('.page-heading',content);if(old)old.outerHTML=titleBlock(title,sub)+tabs;}
  renderCalendar=function(){baseCalendar();replaceHeading('发布工作台','日历显示已安排的交付时间；未排期内容在待办列表处理。',subtabs([['queue','待办列表'],['calendar','发布日历']]));};
  renderRuns=function(){
    // Keep execution records visible even when an imported/deleted task is unavailable.
    const all=S.runs||[],valid=all.filter(r=>S.tasks.some(t=>t.id===r.task_id));
    S.runs=valid;try{baseRuns();}finally{S.runs=all;}
    replaceHeading('发布记录','批准版本的执行过程与平台回执。',subtabs([['records','渠道结果'],['runs','执行记录']]));
    const orphan=all.filter(r=>!S.tasks.some(t=>t.id===r.task_id));if(orphan.length)$('#content').insertAdjacentHTML('beforeend',`<section class="workspace-alert"><strong>${orphan.length} 条执行记录的关联任务不可用</strong>${orphan.map(r=>`<p>${esc(runStatus(r.status))} · ${esc(r.message||r.id)}</p>`).join('')}</section>`);
  };
  renderAccounts=function(){baseAccounts();const h=$('.page-heading');if(h)h.outerHTML=titleBlock('账号与设置','每个平台账号独立连接、独立安排。',`<button class="primary" data-action="new-account">${icon('plus')}添加账号</button>`)+subtabs([['accounts','渠道账号'],['rules','平台规则']]);};
  renderRules=function(){baseRules();replaceHeading('账号与设置','查看当前支持的内容类型、交付方式与检查要求。',subtabs([['accounts','渠道账号'],['rules','平台规则']]));};
  document.addEventListener('click',e=>{const g=e.target.closest('[data-workspace-group]'),r=e.target.closest('[data-record-group]');if(g){workspaceGroup=g.dataset.workspaceGroup;renderQueue();}if(r){recordGroup=r.dataset.recordGroup;renderRecords();}});
  document.addEventListener('change',e=>{if(e.target.id==='workspace-batch'){workspaceBatch=e.target.value;localStorage.setItem('desk-workspace-batch',workspaceBatch);view==='records'?renderRecords():renderQueue();}});
  document.addEventListener('input',e=>{if(e.target.id==='workspace-record-search'){recordQuery=e.target.value;const pos=e.target.selectionStart;renderRecords();const input=$('#workspace-record-search');input.focus();input.setSelectionRange(pos,pos);}});
}
