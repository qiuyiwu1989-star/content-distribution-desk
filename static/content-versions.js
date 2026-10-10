/* Version snapshots belong to content, not publication status. */
(()=>{
async function loadVersions(node){
 const pid=node.dataset.lifecycle;
 if(!pid||!node.querySelector('.lifecycle-heading')||node.querySelector('[data-content-versions]'))return;
 const section=document.createElement('section');section.dataset.contentVersions=pid;
 section.innerHTML='<h3>内容版本</h3><p role="status">读取版本…</p>';node.append(section);
 try{
  const d=await api('/packages/'+encodeURIComponent(pid)+'/versions');if(!section.isConnected)return;
  section.innerHTML=`<h3>内容版本 · V${d.current.number}</h3><details><summary>查看已记录的版本（${d.versions.length}）</summary><p class="muted">${esc(d.history_boundary)}</p>${d.versions.map(v=>`<div style="padding:10px 0;border-bottom:1px solid var(--border,#e4e9e7)"><strong>V${v.number}${v.id===d.current.id?' · 当前':''}</strong> <small>${esc(date(v.created,true))}</small><button class="text-button" data-version-detail="${esc(v.id)}" data-version-package="${esc(pid)}">查看快照</button>${v.links.length?`<small> · ${v.links.length} 条版本关联</small>`:''}</div>`).join('')}</details>`;
 }catch(e){section.innerHTML=`<h3>内容版本</h3><p role="status">${esc(e.message)}</p><button class="secondary" data-version-retry>重试</button>`;}
}
new MutationObserver(()=>document.querySelectorAll('[data-lifecycle]').forEach(loadVersions)).observe(document.documentElement,{childList:true,subtree:true});
document.addEventListener('click',async e=>{
 const retry=e.target.closest('[data-version-retry]');if(retry){const section=retry.closest('[data-content-versions]'),node=section.parentElement;section.remove();loadVersions(node);return;}
 const b=e.target.closest('[data-version-detail]');if(!b)return;b.disabled=true;
 try{const v=await api('/packages/'+encodeURIComponent(b.dataset.versionPackage)+'/versions/'+encodeURIComponent(b.dataset.versionDetail));
 const s=v.snapshot;openModal('内容版本 V'+v.number,`<p>${esc(date(v.created,true))}</p><h3>${esc(s.package.title)}</h3><p style="white-space:pre-wrap">${esc(s.package.body)}</p><h3>素材（${s.assets.length}）</h3>${s.assets.map(a=>`<p>${esc(a.name)} <small>${esc(a.kind)}</small></p>`).join('')}<h3>发布文案设置</h3><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(JSON.stringify(s.content_defaults,null,2))}</pre><p class="muted">这是保存的内容快照；查看不会恢复、审阅或发布此版本。</p>`);
 }catch(err){toast(err.message,true);}finally{b.disabled=false;}
});
})();
