/* Choosing a production brief does not modify footage, cover assets or approvals. */
(() => {
 let catalog=null,loadError='',tab='video',search='',family='initial',context=null,choice=null,previous=null;
 const routes=['creative-templates','creative-editors'];
 const label=id=>id==='creative-editors'?'剪辑师':'模板中心';
 const baseShell=shell,baseRender=render;
 shell=function(){
  let html=baseShell();
  const navigation=routes.map(id=>`<button class="nav-item ${view===id?'active':''}" data-creative-nav="${id}" ${view===id?'aria-current="page"':''}>${icon(id==='creative-editors'?'users':'grid')}<span>${label(id)}</span></button>`).join('');
  return html.replace('</nav>',navigation+'</nav>');
 };
 async function load(){try{catalog=await api('/creative/catalog');loadError='';}catch(e){loadError=e.message;}}
 function item(field,id){return catalog?.[({template_id:'templates',editor_id:'editors',cover_id:'covers'})[field]].find(x=>x.id===id);}
 function summary(c){return [['template_id','画面'],['editor_id','剪辑师'],['cover_id','封面方向']].map(([f,l])=>`${l}：${item(f,c[f])?.persona?.name||item(f,c[f])?.name||'未选择'}`).join(' · ');}
 function renderCatalog(){
  const main=$('#content');
  if(!catalog){main.innerHTML=`<section class="panel"><h1>${label(view)}</h1><p>${esc(loadError||'正在读取…')}</p>${loadError?'<button class="secondary" data-creative-retry>重新读取</button>':''}</section>`;return;}
  const editors=view==='creative-editors',items=editors?catalog.editors:tab==='cover'?catalog.covers:catalog.templates;
  const filtered=items.filter(x=>editors||tab==='cover'||(family==='initial'?x.collection==='initial-12':family==='legacy'?x.collection!=='initial-12':true)).filter(x=>[x.name,x.tag,x.persona?.name,x.use,x.suitable].join(' ').toLowerCase().includes(search.toLowerCase()));
  main.innerHTML=`<div class="page-heading"><div><h1>${label(view)}</h1>${editors?`<p>${esc(catalog.coordinator.name)} · ${esc(catalog.coordinator.role)}　${esc(catalog.coordinator.catchphrase)}</p>`:''}</div>${context?`<button class="secondary" data-creative-return>返回制作方案</button>`:''}</div>${context?`<div class="creative-context">正在为 <strong>${esc(S.packages.find(x=>x.id===context)?.title||'当前内容')}</strong> 挑选</div>`:''}<div class="creative-toolbar">${editors?'':`<div class="tabs"><button data-creative-tab="video" class="${tab==='video'?'selected':''}">视频模板</button><button data-creative-tab="cover" class="${tab==='cover'?'selected':''}">封面方案</button></div>`}<label>查找${editors?'剪辑师':'模板'}<input id="creative-search" placeholder="名称或适用内容" value="${esc(search)}"></label></div>${!editors&&tab==='video'?`<div class="template-collection"><div><strong>首批 12 套 · 画面模板</strong><p>按画面结构选模板，再查看字体、字幕、底纹、署名与尺寸。当前为静态版式样张，动态成片待验证。</p><p><a href="/static/creative/reference-redo/index.html" target="_blank" rel="noopener">查看三套重做：参考原图与复刻并排对照</a> · <a href="/static/creative/fonts/index.html" target="_blank" rel="noopener">字体库：输入标题比较六种字体</a></p></div><label>模板范围<select id="template-family"><option value="initial" ${family==='initial'?'selected':''}>新模板 · 12 套</option><option value="legacy" ${family==='legacy'?'selected':''}>早期风格 · 6 套</option><option value="all" ${family==='all'?'selected':''}>全部模板</option></select></label></div>`:''}<div class="creative-grid ${editors?'creative-editors':''}">${filtered.map(x=>editors?editorCard(x):templateCard(x)).join('')}</div>${filtered.length?'':'<p>没有匹配的结果，请换个关键词。</p>'}`;
 }
 function templateCard(x){return `<article class="creative-card"><button class="creative-preview" data-creative-detail="${esc(x.id)}" data-creative-type="${tab==='cover'?'covers':'templates'}"><img src="${esc(x.preview)}" alt="${esc(x.name)}预览" loading="lazy"></button><div class="creative-copy"><h2>${esc(x.name)}</h2>${x.collection==='initial-12'?`<p><a class="secondary" href="/static/layout-editor/index.html?base=${esc(x.id)}" target="_blank" rel="noopener">编辑模板</a></p>`:''}${x.collection?`<p class="template-kind">${esc(x.id)} · ${esc(x.tag)}</p>`:''}<p>${esc(x.use)}</p><button class="secondary" data-creative-detail="${esc(x.id)}" data-creative-type="${tab==='cover'?'covers':'templates'}">查看与选择</button></div></article>`;}
 function editorCard(x){const p=x.persona;return `<article class="creative-card"><div class="creative-copy"><div class="creative-persona" style="--persona:${esc(p.color)}">${p.avatar?`<img class="creative-avatar" src="${esc(p.avatar)}" alt="${esc(p.name)}的3D人物头像">`:`<span>${esc(p.monogram)}</span>`}<div><h2>${esc(p.name)}</h2><p>${esc(p.role)}</p></div></div><p class="creative-promise">${esc(x.promise)}</p><p>${esc(x.suitable)}</p>${x.tags?`<p><small>${[...x.tags.content,...x.tags.method].map(esc).join(" · ")}</small></p>`:""}<blockquote>${esc(p.catchphrase)}</blockquote><button class="secondary" data-creative-detail="${esc(x.id)}" data-creative-type="editors">查看与选择</button></div></article>`;}
 render=function(){if(routes.includes(view)){if(!S)return;$('#app').innerHTML=shell();const crumb=$('.topbar>span');if(crumb)crumb.textContent='工作空间 / '+label(view);renderCatalog();}else{baseRender();augment();}};
 function augment(){
  if(view!=='packages'||!Library.detailId||$('#creative-content-brief'))return;
  const heading=$('.library-detail-heading');if(!heading)return;
  heading.insertAdjacentHTML('afterend',`<section id="creative-content-brief" class="creative-brief"><div><strong>制作方案</strong><p id="creative-brief-summary">查看或选择视频模板、剪辑师与封面方向</p></div><button class="secondary" data-creative-brief="${esc(Library.detailId)}">选择制作方案</button></section>`);
  const pid=Library.detailId;
  api('/packages/'+pid+'/creative').then(c=>{if(Library.detailId===pid&&$('#creative-brief-summary'))$('#creative-brief-summary').textContent=summary(c)+([c.template_id,c.editor_id,c.cover_id].some(Boolean)?' · 已保存，待制作':'');}).catch(()=>{});
 }
 async function brief(pid){
  context=pid;choice=await api('/packages/'+pid+'/creative');previous=null;showBrief();
 }
 function showBrief(){
  const p=S.packages.find(x=>x.id===context);if(!p)return;
  if(!catalog){toast(loadError||'模板库尚未读取，请稍后重试',true);return;}
  openModal('选择制作方案',`<form id="creative-brief-form" data-package-id="${esc(context)}"><p><strong>${esc(p.title)}</strong></p><label>视频模板<select name="template_id"><option value="">暂不选择</option>${catalog.templates.map(x=>`<option value="${esc(x.id)}" ${choice.template_id===x.id?'selected':''}>${esc(x.name)}</option>`).join('')}</select></label><button type="button" class="text-button" data-creative-browse="creative-templates">浏览视频模板</button><label>剪辑师<select name="editor_id"><option value="">暂不选择</option>${catalog.editors.map(x=>`<option value="${esc(x.id)}" ${choice.editor_id===x.id?'selected':''}>${esc(x.persona.name)} · ${esc(x.name)}</option>`).join('')}</select></label><button type="button" class="text-button" data-creative-browse="creative-editors">浏览剪辑师</button><label>封面方向<select name="cover_id"><option value="">暂不选择</option>${catalog.covers.map(x=>`<option value="${esc(x.id)}" ${choice.cover_id===x.id?'selected':''}>${esc(x.name)}（方案样张）</option>`).join('')}</select></label><p class="form-note">保存后作为 Agent 的制作要求。现有视频与封面需另行制作、审核。</p><div class="form-error" role="alert"></div><div class="form-footer"><button type="button" class="secondary" data-action="close">取消</button><button type="submit" class="primary">保存制作方案</button></div></form>`);
 }
 function rememberForm(){const f=$('#creative-brief-form');if(f)for(const k of ['template_id','editor_id','cover_id'])choice[k]=f.elements[k].value||null;}
 function detail(type,id){
  const x=catalog[type].find(x=>x.id===id);if(!x)return;
  const editors=type==='editors',field=editors?'editor_id':type==='covers'?'cover_id':'template_id';
  const body=editors?`<div class="creative-persona" style="--persona:${esc(x.persona.color)}">${x.persona.avatar?`<img class="creative-avatar" src="${esc(x.persona.avatar)}" alt="${esc(x.persona.name)}的3D人物头像">`:`<span>${esc(x.persona.monogram)}</span>`}<div><h2>${esc(x.persona.name)}</h2><p>${esc(x.name)}</p></div></div><p>${esc(x.persona.personality)}</p>${x.tags?`<p><strong>内容标签：</strong>${x.tags.content.map(esc).join("、")}</p><p><strong>剪法标签：</strong>${x.tags.method.map(esc).join("、")}</p>`:""}${x.fit_profile?`<p><strong>优先判断：</strong>${esc(x.fit_profile.decision_rule)}</p>`:""}<p><strong>适合：</strong>${esc(x.suitable)}</p><p><strong>不适合：</strong>${esc(x.avoid)}</p><h3>怎么剪</h3><ol>${x.structure.map(v=>`<li>${esc(v)}</li>`).join('')}</ol>${x.skill_pack?`<h3>技能包</h3><p><strong>目标：</strong>${esc(x.skill_pack.goal)}</p><p><strong>开头：</strong>${esc(x.skill_pack.opening_strategy)}</p><p><strong>收尾：</strong>${esc(x.skill_pack.ending_strategy)}</p><p><strong>优先技能：</strong>${x.skill_pack.frequent_skills.map(id=>x.skill_pack.steps.find(s=>s.skill_id===id)?.label||id).map(esc).join('、')}</p><details><summary>查看技能组合与使用条件</summary><ol>${x.skill_pack.steps.map(s=>`<li><strong>${esc(s.label)}</strong>：${esc(s.goal)}<br><small>${esc(s.when)}</small></li>`).join('')}</ol><p>${esc(x.skill_pack.adaptation)}</p><p class="form-note">推荐策略包，尚未完成效果对照验证</p></details>`:''}<p><strong>口语优化：</strong>${esc(x.oral_editing)}</p><p><strong>节奏：</strong>${esc(x.rhythm)}</p><p><strong>声音：</strong>${esc(x.sound)}</p><p><strong>推荐模板：</strong>${x.suggested_templates.map(id=>catalog.templates.find(v=>v.id===id)?.name||id).map(esc).join('、')}</p><p class="form-note">虚拟剪辑角色 · 策略已定义，尚未完成样片验证</p>`:`<div class="creative-detail-preview"><img src="${esc(x.preview)}" alt="${esc(x.name)}"></div><p>${esc(x.use)}</p>${type==='templates'?`${x.design_spec?`<p class="form-note">${esc(x.preview_disclaimer)}</p><p><strong>参考方向：</strong>${esc(x.reference_note)}</p><dl class="template-spec">${Object.entries(x.design_spec).map(([key,value])=>`<dt>${esc(key)}</dt><dd>${esc(value)}</dd>`).join('')}</dl><a class="text-button" href="${esc(x.preview)}" target="_blank" rel="noopener">打开完整尺寸样张</a>`:`<p>画面：${x.window_mode==='full-width'?'中间全宽':'小圆角窗口'} · 字幕 ${esc(x.subtitle_size)} px · 保留原声</p>`}`:'<p>3:4 封面样张 · 尚未选定</p>'}`;
  const packages=Library.orderedPackages();
  openModal(editors?x.persona.name:x.name,`${body}<form id="creative-pick-form" data-field="${field}" data-item="${esc(id)}"><label>用于哪条内容<select name="package_id" required><option value="">请选择内容</option>${packages.map(p=>`<option value="${esc(p.id)}" ${p.id===context?'selected':''}>${esc(p.title)}</option>`).join('')}</select></label><div class="form-error" role="alert"></div><div class="form-footer"><button type="button" class="secondary" data-action="close">关闭</button><button type="submit" class="primary">加入制作方案</button></div></form>`);
 }
 document.addEventListener('click',async e=>{
  const nav=e.target.closest('[data-creative-nav]'),browse=e.target.closest('[data-creative-browse]'),b=e.target.closest('[data-creative-brief]'),d=e.target.closest('[data-creative-detail]');
  try{
   if(nav||browse){if(Library.isDirty()||taskDirty()){toast('请先保存或撤销当前修改',true);return;}if(browse)rememberForm();else{context=null;choice=null;}closeModal();view=(nav||browse).dataset[nav?'creativeNav':'creativeBrowse'];search='';render();}
   if(b)await brief(b.dataset.creativeBrief);
   if(d)detail(d.dataset.creativeType,d.dataset.creativeDetail);
   if(e.target.closest('[data-creative-tab]')){tab=e.target.closest('[data-creative-tab]').dataset.creativeTab;renderCatalog();}
   if(e.target.closest('[data-creative-return]'))showBrief();
   if(e.target.closest('[data-creative-retry]')){await load();renderCatalog();}
   if(e.target.closest('[data-creative-undo]')){const pid=e.target.closest('[data-creative-undo]').dataset.creativeUndo;choice=await api('/packages/'+pid+'/creative','PUT',{...previous,revision:choice.revision});previous=null;closeModal();Library.open(pid);$('#creative-content-brief')?.remove();augment();toast('已恢复之前的制作方案');}
  }catch(err){toast(err.message,true);}
 });
 document.addEventListener('change',e=>{if(e.target.id==='template-family'){family=e.target.value;renderCatalog();}});
 document.addEventListener('input',e=>{if(e.target.id==='creative-search'){search=e.target.value;const pos=e.target.selectionStart;renderCatalog();const input=$('#creative-search');input.focus();input.setSelectionRange(pos,pos);}});
 document.addEventListener('submit',async e=>{
  const f=e.target;if(!['creative-brief-form','creative-pick-form'].includes(f.id))return;e.preventDefault();e.stopImmediatePropagation();const btn=$('button[type="submit"]',f);btn.disabled=true;
  try{
   if(f.id==='creative-pick-form'){const fd=new FormData(f),pid=fd.get('package_id');if(context!==pid||!choice){context=pid;choice=await api('/packages/'+pid+'/creative');}choice[f.dataset.field]=f.dataset.item;showBrief();return;}
   const fd=new FormData(f);previous=await api('/packages/'+context+'/creative');
   choice=await api('/packages/'+context+'/creative','PUT',{revision:choice.revision,...Object.fromEntries(['template_id','editor_id','cover_id'].map(k=>[k,fd.get(k)||null]))});
   openModal('制作方案已保存',`<p><strong>${esc(S.packages.find(p=>p.id===context)?.title)}</strong></p><p>${esc(summary(choice))}</p><p>待制作</p><div class="form-footer"><button class="secondary" data-creative-undo="${esc(context)}">撤销本次选择</button><button class="primary" data-library-open="${esc(context)}">返回内容</button></div>`);toast('制作方案已保存');
  }catch(err){$('.form-error',f).textContent=err.message;}finally{btn.disabled=false;}
 },true);
 new MutationObserver(()=>augment()).observe($('#app'),{childList:true,subtree:true});
 document.addEventListener('DOMContentLoaded',async()=>{await load();if(routes.includes(view))render();else augment();});
})();
