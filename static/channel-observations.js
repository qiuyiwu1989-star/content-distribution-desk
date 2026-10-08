/* Page observations are evidence notes, never replacements for confirmed task results. */
(()=>{
 const original=renderRecords;
 const labels={schedule_changed:'检测到时间修改',submit_clicked:'检测到点击发布 · 结果待核对',draft_clicked:'检测到点击保存草稿 · 结果待核对',result_observed:'检测到平台提示 · 待核对',manual_confirmation:'人工核对说明'};
 const identity={matched:'页面名称与目标一致',mismatch:'账号名称不一致，需核对',unverified:'页面账号未识别'};
 renderRecords=function(){original();const panel=document.createElement('section');panel.className='panel';panel.id='channel-observation-records';panel.innerHTML='<h2>插件页面观察</h2><p class="muted">记录页面操作与平台提示，点击发布不等于发布成功。</p><p>正在读取…</p>';$('#content').append(panel);
 api('/channel-observations').then(data=>{if(!panel.isConnected)return;const records=data.observations||[];panel.innerHTML='<h2>插件页面观察</h2><p class="muted">按时间显示最近的页面观察。目标账号与页面识别账号分别保留；公开发布仍以核对结果和作品链接为准。</p>'+(records.length?records.map(r=>`<details class="panel" style="margin:12px 0;padding:16px"><summary><strong>${esc(r.task_snapshot?.title||r.binding_snapshot?.title||r.task_id)}</strong> · ${esc(labels[r.event_kind]||r.event_kind)} · ${esc(date(r.created,true))}</summary><p>目标账号：${esc(r.target_account_name)} · 页面账号：${esc(r.observed_account||'未识别')} · ${esc(identity[r.identity_match]||'待核对')}</p>${r.scheduled_text?`<p>页面时间：${esc(r.scheduled_text)}（页面原文）</p>`:''}${r.result_text?`<p>${esc(r.result_text)}</p>`:''}<button class="secondary small" data-task="${esc(r.task_id)}">打开关联任务</button></details>`).join(''):'<p>还没有页面观察记录。插件加载当前内容后，后续操作会按支持的页面控件记录。</p>');}).catch(e=>{if(panel.isConnected)panel.innerHTML='<h2>插件页面观察</h2><p>'+esc(e.message)+'</p>';});
 };
})();
