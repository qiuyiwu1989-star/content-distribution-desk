/* Production records live with their content. Registration never starts a tool. */
(()=>{
const labels={queued:'待接单',running:'制作中',completed:'已完成',failed:'失败',canceled:'已取消'};
async function load(node){
 const pid=node.dataset.lifecycle;
 if(!node.querySelector('.lifecycle-heading')||node.querySelector('[data-production-section]'))return;
 const section=document.createElement('section');section.dataset.productionSection=pid;section.style.cssText='border-top:1px solid #e3e9e6;margin-top:24px;padding-top:16px';node.append(section);
 try{const d=await api('/packages/'+pid+'/production-tasks');if(!section.isConnected)return;
 section.innerHTML=`<div style="display:flex;align-items:center;gap:12px;justify-content:space-between"><h3>制作任务</h3><button class="secondary" data-production-create="${esc(pid)}">新建任务</button></div>${d.tasks.map(t=>`<article style="padding:12px 0;border-bottom:1px solid #edf0ee"><strong>${esc(t.instruction)}</strong><div class="muted">${esc(labels[t.status])} · ${t.capability_version==='unassigned'?(t.status==='queued'?'等待 Agent 选择工具':'未指定工具'):esc(t.capability_id)+' · '+esc(t.capability_version)}${t.worker?' · '+esc(t.worker):''}${t.input_stale?' · 输入为历史版本':''} · ${t.input_version_id===d.input_version.id?'内容 V'+d.input_version.number:'绑定历史内容版本'}</div>${t.result.summary?`<p>${esc(t.result.summary)}</p>`:''}${(t.result.artifacts||[]).map(a=>`<div>${esc(a.name)} <small>${esc(a.reference)}</small></div>`).join('')}${t.status==='queued'?`<button class="text-button" data-production-cancel="${esc(t.id)}" data-revision="${t.revision}">取消任务</button>`:''}</article>`).join('')||'<p class="muted">尚无制作任务</p>'}`;
 section._inputVersion=d.input_version;
 }catch(e){section.innerHTML=`<h3>制作任务</h3><p>${esc(e.message)}</p><button class="secondary" data-production-retry>重新读取</button>`;}
}
new MutationObserver(()=>document.querySelectorAll('[data-lifecycle]').forEach(load)).observe(document.documentElement,{childList:true,subtree:true});
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-production-create],[data-production-cancel],[data-production-retry]');if(!b)return;
 const section=b.closest('[data-production-section]');
 if(b.hasAttribute('data-production-retry')){const n=section.parentElement;section.remove();load(n);return;}
 if(b.dataset.productionCancel){b.disabled=true;try{await api('/production-tasks/'+b.dataset.productionCancel+'/transition','POST',{revision:Number(b.dataset.revision),status:'canceled'});const n=section.parentElement;section.remove();load(n);toast('任务已取消');}catch(err){toast(err.message,true);b.disabled=false;}return;}
 const v=section._inputVersion;
 openModal('新建制作任务',`<form data-production-new="${esc(b.dataset.productionCreate)}" data-version="${esc(v.id)}" data-fingerprint="${esc(v.fingerprint)}"><label>要做什么<textarea name="instruction" required maxlength="5000" rows="3" placeholder="例如：检查这一版剪辑的来源区间，并把发现的问题记录下来。"></textarea></label><p class="muted">保存为待接单任务，之后由 Agent 选择合适的工具处理。</p><button class="primary">保存任务</button></form>`);
});
document.addEventListener('submit',async e=>{
 const f=e.target.closest('[data-production-new]');if(!f)return;e.preventDefault();e.stopImmediatePropagation();const b=f.querySelector('button');b.disabled=true;
 try{await api('/packages/'+f.dataset.productionNew+'/production-tasks','POST',{instruction:new FormData(f).get('instruction'),input_version_id:f.dataset.version,input_fingerprint:f.dataset.fingerprint,capability_kind:'manual',capability_id:'agent-assigned',capability_version:'unassigned',idempotency_key:f.dataset.key||(f.dataset.key=crypto.randomUUID())});closeModal();const n=document.querySelector('[data-lifecycle="'+CSS.escape(f.dataset.productionNew)+'"]');n?.querySelector('[data-production-section]')?.remove();if(n)load(n);toast('任务已保存，等待 Agent 接单');}catch(err){toast(err.message,true);b.disabled=false;}
},true);
})();
