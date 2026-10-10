/* Shared navigation and channel editing across the content and delivery views. */
window.Library = Library;
function readInlineOptions(form){
 const t=S.tasks.find(x=>x.id===form.dataset.taskId),o=t?.options||{};
 const value=(name,fallback)=>form.elements[name]?form.elements[name].value:fallback;
 return {mode:value('delivery_mode',o.mode||'manual'),collection:value('collection',o.collection||''),category:value('category',o.category)?Number(value('category',o.category)):null,landscape_cover_id:value('landscape_cover_id',o.landscape_cover_id)||null};
}
const baseTaskDirty=taskDirty;
taskDirty=function(){
 if(baseTaskDirty())return true;
 const form=$('#edit-task-form');if(!form||$('fieldset',form)?.disabled)return false;
 const t=S.tasks.find(x=>x.id===form.dataset.taskId),o=t?.options||{},n=readInlineOptions(form);
 return Object.keys(n).some(k=>n[k]!==({mode:'manual',collection:'',category:null,landscape_cover_id:null,...o})[k]);
};
const baseTaskDetail=taskDetail;
taskDetail=function(id){
 baseTaskDetail(id);
 const t=S.tasks.find(x=>x.id===id),a=account(t),o=t.options||{},r=S.rules?.[a.platform]?.[t.format]||{},form=$('#edit-task-form'),editable=!$('fieldset',form).disabled;
 const pluginChannel=a.platform==='channels'&&t.format==='video';
 const images=S.assets.filter(x=>x.package_id===t.package_id&&x.kind==='image');
 const incompatible=(t.asset_ids||[]).filter(id=>{const asset=S.assets.find(x=>x.id===id);return !asset||asset.package_id!==t.package_id||(t.format==='video'&&asset.kind!=='video')||(t.format==='gallery'&&asset.kind!=='image');});
 if(incompatible.length)$('fieldset',form).insertAdjacentHTML('afterbegin',`<div class="library-warning" id="incompatible-assets"><strong>已选素材中有 ${incompatible.length} 项不适用于此渠道类型</strong><p>${incompatible.map(id=>esc(S.assets.find(x=>x.id===id)?.name||'附件不可用')).join('、')}</p>${editable?'<button type="button" class="secondary" data-integrate="remove-incompatible">移除这些素材的发布选择</button>':''}<p>只调整本次选择，原始文件保留。</p></div>`);
 $('fieldset',form).insertAdjacentHTML('beforeend',`<section class="inline-delivery"><h3>渠道设置</h3>${a.platform==='channels'?`<label>平台合集（可选）<input name="collection" maxlength="100" value="${esc(o.collection||'')}" placeholder="填写平台中已有的合集名称"></label>`:''}${pluginChannel?'':`<label>交付方式<select name="delivery_mode">${(r.modes||['manual']).map(m=>`<option value="${m}" ${m===(o.mode||'manual')?'selected':''}>${esc(S.mode_labels[m]||m)}</option>`).join('')}</select></label>`}${r.category_required?`<label>平台分区 ID<input name="category" type="number" min="1" max="99999" value="${esc(o.category||'')}"></label>`:''}${!pluginChannel&&['channels','douyin'].includes(a.platform)&&t.format==='video'?`<label>横版封面（可选）<select name="landscape_cover_id"><option value="">不指定</option>${images.map(x=>`<option value="${esc(x.id)}" ${o.landscape_cover_id===x.id?'selected':''}>${esc(x.name)}</option>`).join('')}</select></label>`:''}<p class="form-note">${pluginChannel?'保存后在插件刷新内容，即可同步到视频号。':'文案和渠道设置一起保存。内容确认与上传执行分开进行。'}</p></section>`);
 $('.mode-summary [data-v2="options"]')?.remove();
 if(editable){$('button[type="submit"]',form).textContent='保存';form.insertAdjacentHTML('beforeend','<button class="text-button" type="button" data-integrate="discard-task">撤销未保存修改</button>');}
 if(pluginChannel){
  form.querySelectorAll('.form-note').forEach(el=>{if(el.textContent.includes('保存内容或交付设置后需重新确认'))el.textContent=t.scheduled?'保存修改后，原排期会清除；请在平台重新设置时间。':'保存后在插件刷新内容，即可使用新版本。';});
  const head=$('.task-detail-head small');if(head)head.textContent=S.formats[t.format]+' · 版本 '+t.revision;
  const panel=$('.delivery-panel'),advanced=panel.querySelector('details');
  if(advanced)advanced.remove();
  panel.innerHTML=`<h3>同步到视频号</h3><p>保存内容 → 在插件选择本条并同步 → 在平台发布 → 记录发布结果。</p><a class="primary full" href="${esc(platform(t).url)}" target="_blank" rel="noopener">打开视频号后台</a><button class="secondary full" data-action="preview" data-id="${esc(id)}">预览内容</button><button class="secondary full" data-action="copy-body" data-id="${esc(id)}">复制文案</button>${t.status==='published'?`<a class="secondary full" href="${esc(t.url)}" target="_blank" rel="noopener">查看已发布作品</a>`:''}`;
  if(advanced)panel.append(advanced);
  $('.task-actions .receipt-panel')?.remove();
  if(t.status!=='published'&&t.status!=='canceled')panel.insertAdjacentHTML('beforeend',DeskUX.publicationGroup(t)==='published'?`<p>本版本已人工确认发布。</p><button class="text-button" data-integrate="publication-undo" data-id="${esc(id)}">撤销人工发布标记</button>`:`<button class="secondary full" data-integrate="publication-confirm" data-id="${esc(id)}">我已在平台发布</button><p class="form-note">完成平台发布后点击，只记录人工确认，不操作平台。</p>`);
 }
 const p=S.packages.find(x=>x.id===t.package_id);
 if(!pluginChannel)$('.task-detail-head').insertAdjacentHTML('afterend',`<div class="task-review-context"><span>${esc(Library.reviewLabel(p))}</span><button class="text-button" data-package="${esc(p.id)}">查看内容与检查记录</button></div>`);
 const unresolved=(S.runs||[]).filter(x=>x.task_id===id&&x.status==='unknown');
 if(unresolved.length&&t.status!=='unknown')$('.task-actions').insertAdjacentHTML('afterbegin',`<section class="workspace-alert"><strong>历史执行仍待核对</strong><p>当前任务状态不能代表这次执行的结果。请在平台检查后记录。</p>${unresolved.map(x=>`<button class="secondary" data-integrate="reconcile" data-run="${esc(x.id)}">记录历史执行的核对结果</button>`).join('')}</section>`);
};

document.addEventListener('click',e=>{
 const target=e.target.closest('[data-nav],[data-package],[data-task],[data-action="close"],[data-action="refresh"],[data-library-open]');
 if(target&&taskDirty()){e.preventDefault();e.stopImmediatePropagation();toast('渠道内容有未保存的修改，请保存或撤销修改后再离开',true);return;}
 if(target&&Library.organizeDirty){e.preventDefault();e.stopImmediatePropagation();toast('批次整理有未保存的修改，请先保存或撤销修改',true);return;}
 if(target?.hasAttribute('data-nav')&&target.dataset.nav==='packages')Library.detailId=null;
},true);
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('.modal')&&taskDirty()){e.preventDefault();e.stopImmediatePropagation();toast('请先保存或撤销渠道修改',true);}},true);
window.addEventListener('beforeunload',e=>{if(taskDirty()||Library.isDirty()){e.preventDefault();e.returnValue='';}});

document.addEventListener('click',e=>{
 const b=e.target.closest('[data-integrate]');if(!b)return;
 if(b.dataset.integrate==='discard-task'){taskDetail($('#edit-task-form').dataset.taskId);toast('已恢复到上次保存的渠道版本');}
 if(b.dataset.integrate==='remove-incompatible'){
  const form=$('#edit-task-form'),t=S.tasks.find(x=>x.id===form.dataset.taskId);
  form.dataset.order=JSON.stringify(JSON.parse(form.dataset.order).filter(id=>{const a=S.assets.find(x=>x.id===id);return a&&a.package_id===t.package_id&&(t.format==='article'||a.kind===(t.format==='video'?'video':'image'));}));
  $('#incompatible-assets')?.remove();toast('素材选择已调整，请保存渠道内容与设置');
 }
 if(b.dataset.integrate==='reconcile'){
  const r=S.runs.find(x=>x.id===b.dataset.run);
  openModal('核对历史执行',`<form id="reconcile-form" data-run="${esc(r.id)}"><p>${esc(r.message)}</p><p>只补记本次历史执行的核对结果，不改变当前渠道版本，不重新上传。</p><label>平台核对结果<select name="outcome"><option value="not_found">已检查，未找到本次草稿或作品</option><option value="draft">已找到平台草稿</option><option value="review">已找到送审内容</option><option value="published">已找到公开作品</option></select></label><label>核对说明<textarea name="note" required rows="4" placeholder="记录检查的账号、内容和结果"></textarea></label><label class="checkbox-label"><input type="checkbox" name="checked" required>已实际检查平台草稿与作品</label><div class="form-error" role="alert"></div><button class="primary" type="submit">保存核对记录</button></form>`);
 }
});
document.addEventListener('submit',async e=>{
 if(e.target.id!=='reconcile-form')return;e.preventDefault();e.stopImmediatePropagation();
 const form=e.target,b=$('button',form),d=new FormData(form);b.disabled=true;
 try{await api('/runs/'+form.dataset.run+'/reconcile','POST',{outcome:d.get('outcome'),note:d.get('note'),checked:d.get('checked')==='on'});closeModal();await refresh();toast('历史执行核对已记录，当前渠道版本未改变');}
 catch(err){$('.form-error',form).textContent=err.message;}finally{b.disabled=false;}
},true);
