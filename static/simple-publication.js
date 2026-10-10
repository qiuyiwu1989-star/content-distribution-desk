/* User-reported publication is reversible and separate from platform automation. */
document.addEventListener('click',async e=>{
 const button=e.target.closest('[data-integrate="publication-confirm"],[data-integrate="publication-undo"]');
 if(!button||button.disabled)return;
 if(taskDirty()){toast('请先保存或撤销正在编辑的内容',true);return;}
 const task=S.tasks.find(t=>t.id===button.dataset.id);if(!task)return;
 button.disabled=true;
 try{
  await api('/publication-progress','POST',{task_id:task.id,revision:task.revision,status:button.dataset.integrate==='publication-confirm'?'published':'unconfirmed'});
  await refresh();taskDetail(task.id);toast(button.dataset.integrate==='publication-confirm'?'已记录人工发布结果，可随时撤销':'已撤销标记，回到待发布列表');
 }catch(error){toast(error.message,true);button.disabled=false;}
});
