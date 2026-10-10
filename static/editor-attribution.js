/* Recorded production credits bind to an immutable video asset, not a chosen role. */
(() => {
 let credits={},editors=[],error='',pending=false;
 function currentVideo(pid){return document.querySelector('#review-copy-form[data-id="'+pid+'"] select[name=video_id]')?.value||credits[pid]?.selected_video_id||S?.assets.find(a=>a.package_id===pid&&a.kind==='video')?.id;}
 function creditFor(pid){return credits[pid]?.history.find(h=>h.video_id===currentVideo(pid));}
 function label(pid){const c=creditFor(pid);if(c)return c.contributors.map(x=>x.role+' '+x.name).join(' · ');const id=credits[pid]?.selected_editor_id;return id?'已选 '+(editors.find(e=>e.id===id)?.persona.name||id)+' · 待制作':'剪辑师待记录';}
 function paint(){
  if(!S)return;
  document.querySelectorAll('[data-ropen]').forEach(b=>{if(!b.dataset.ropen||!b.querySelector('strong'))return;let s=b.querySelector('.editor-credit-label');if(!s){s=document.createElement('small');s.className='editor-credit-label';b.append(s);}const value=error?'剪辑归属读取失败':label(b.dataset.ropen);if(s.textContent)s.textContent='';const state=creditFor(b.dataset.ropen)?'recorded':error?'error':'pending';if(s.dataset.state!==state)s.dataset.state=state;if(s.title!==value){s.title=value;s.setAttribute('aria-label',value);}});
  const pid=document.querySelector('[data-rmanage]')?.dataset.rmanage||Library.detailId;
  const heading=document.querySelector('.review-title')||document.querySelector('.library-detail-heading');
  if(!pid||!heading)return;
  let box=document.querySelector('#editor-credit-display');
  if(box?.dataset.pid!==pid){box?.remove();box=null;}
  if(!box){box=document.createElement('div');box.id='editor-credit-display';box.dataset.pid=pid;heading.insertAdjacentElement('afterend',box);}
  const c=creditFor(pid),html=`<span class="editor-credit-dot" title="${esc(label(pid))}" aria-label="${esc(label(pid))}"></span><span class="editor-credit-context">${esc(error?'剪辑归属读取失败':label(pid))}</span> <button class="text-button" data-editor-credit="${esc(pid)}">${c?'查看制作归属':'记录制作归属'}</button>`;
  if(box.innerHTML!==html)box.innerHTML=html;
 }
 async function load(){if(pending)return;pending=true;try{const [c,d]=await Promise.all([api('/creative/attributions'),api('/creative/catalog')]);credits=c.contents;editors=d.editors;error='';}catch(e){error=e.message;}finally{pending=false;paint();}}
 async function form(pid){const d=await api('/packages/'+pid+'/editor-credit');credits[pid]=d;const vs=S.assets.filter(a=>a.package_id===pid&&a.kind==='video');const vid=currentVideo(pid),c=d.history.find(h=>h.video_id===vid);const options=(role)=>`<option value="">暂不记录</option>`+editors.map(e=>`<option value="${esc(e.id)}" ${c?.contributors.some(x=>x.editor_id===e.id&&x.role===role)?'selected':''}>${esc(e.persona.name)} · ${esc(e.name)}</option>`).join('');
  openModal('制作归属',`<form id="editor-credit-form" data-pid="${esc(pid)}" data-revision="${d.revision}"><p><strong>${esc(S.packages.find(p=>p.id===pid)?.title||'当前内容')}</strong></p><p class="form-note">按制作依据记录实际采用的虚拟剪辑师策略。推荐、选定与实际制作分开；此记录不代表成片审核通过。</p><label>对应视频<select name="video_id" required>${vs.map(v=>`<option value="${esc(v.id)}" ${vid===v.id?'selected':''}>${esc(v.name)}</option>`).join('')}</select></label><label>主剪<select name="primary">${options('主剪')}</select></label><label>精修<select name="refiner">${options('精修')}</select></label><label>成片版本<input name="output_revision" maxlength="120" required value="${esc(c?.output_revision||'')}"></label><label>制作依据<textarea name="evidence" maxlength="3000" required placeholder="填写实际制作计划、交付记录或任务编号；不要只填推荐理由。">${esc(c?.evidence||'')}</textarea></label><label>记录者<input name="recorded_by" maxlength="120" required value="${esc(c?.recorded_by||'')}"></label><details><summary>历史记录 ${d.history.length} 条</summary>${d.history.map(h=>`<p>${esc(h.video_name)} · ${esc(h.output_revision)} · ${h.contributors.map(x=>esc(x.role+' '+x.name)).join('、')}<br>${esc(h.evidence)}<br><small>${esc(h.recorded_by)} · ${esc(date(h.created,true))}</small></p>`).join('')}</details><p class="form-note">保存新记录会保留历史；换视频后需对新版本另行记录。</p><div class="form-error" role="alert"></div><div class="form-footer"><button class="secondary" type="button" data-action="close">关闭</button><button class="primary" ${vs.length?'':'disabled'}>保存归属记录</button></div></form>`);
 }
 document.addEventListener('click',async e=>{const b=e.target.closest('[data-editor-credit]');if(b)try{await form(b.dataset.editorCredit);}catch(e){toast(e.message,true);}});
 document.addEventListener('submit',async e=>{const f=e.target;if(f.id!=='editor-credit-form')return;e.preventDefault();e.stopImmediatePropagation();const d=new FormData(f),contributors=[];if(d.get('primary'))contributors.push({editor_id:d.get('primary'),role:'主剪'});if(d.get('refiner'))contributors.push({editor_id:d.get('refiner'),role:'精修'});const b=f.querySelector('button.primary');b.disabled=true;
  try{const value=await api('/packages/'+f.dataset.pid+'/editor-credit','POST',{revision:Number(f.dataset.revision),video_id:d.get('video_id'),contributors,output_revision:d.get('output_revision'),evidence:d.get('evidence'),recorded_by:d.get('recorded_by')});credits[f.dataset.pid]=value;closeModal();paint();toast('制作归属已记录，历史已保留');}catch(err){f.querySelector('.form-error').textContent=err.message;b.disabled=false;}
 });
 document.addEventListener('change',e=>{if(e.target.matches('#review-copy-form select[name=video_id]'))paint();});
 new MutationObserver(paint).observe(document.querySelector('#app'),{childList:true,subtree:true});
 document.addEventListener('DOMContentLoaded',load);
})();
