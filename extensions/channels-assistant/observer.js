/* Read-only, task-bound observation. This module never operates platform controls. */
(function () {
 'use strict';
 const clean = (value, max=160) => String(value||'').replace(/\s+/g,' ').trim().slice(0,max);
 const CREATE_PATH = /\/post\/create(?:\/|$)/;
 function clickKind(text) {
  const t=clean(text,30);
  if (/^(发表|发布|确认发表|确认发布|定时发表|定时发布)$/.test(t)) return 'submit_clicked';
  if (/^(保存草稿|存为草稿|保存到草稿箱)$/.test(t)) return 'draft_clicked';
  return null;
 }
 function resultKind(text) {
  const t=clean(text,100).replace(/[！!。.]$/,'');
  if (/^(发表成功|发布成功|已成功发表|已成功发布|视频发表成功|视频发布成功|定时发表成功|定时发布成功|已设置定时发表|已设置定时发布|提交成功，等待审核|发表成功，审核中|发布成功，审核中)$/.test(t)) return 'submit_clicked';
  if (/^(草稿保存成功|保存草稿成功|已保存至草稿箱|已保存到草稿箱|已存入草稿箱)$/.test(t)) return 'draft_clicked';
  return null;
 }
 function scheduleValue(meta,value) {
  if(!/定时|发表时间|发布时间|schedule/i.test(clean(meta,160)))return '';
  const v=clean(value,80);
  return /\d/.test(v)&&/\d{1,4}[-/年月日:.时分]|\d{1,2}:\d{2}/.test(v)?v:'';
 }
 function validTopURL(value){try{const u=new URL(value);return u.protocol==='https:'&&u.hostname==='channels.weixin.qq.com'&&/^\/platform\/post\/create(?:\/|$)/.test(u.pathname)&&!u.username&&!u.password?u.origin+u.pathname:'';}catch{return '';}}
 function validContext(payload) {
  return !!payload&&/^[a-zA-Z0-9_-]{1,100}$/.test(payload.task_id||'')&&Number.isInteger(payload.revision)&&payload.revision>=1&&['fill_started','manual_adoption'].includes(payload.binding_reason);
 }
 function createEngine({emit,now=()=>Date.now(),id=()=>Math.random().toString(36).slice(2),restore=null,persist=()=>{}}) {
  let binding=restore?.binding||null,pending=restore?.pending||null,last={};
  const save=()=>persist({binding,pending});
  function bind(payload){if(!validContext(payload))return false;binding={task_id:payload.task_id,revision:payload.revision};pending=null;last={};save();return true;}
  function clear(){binding=null;pending=null;last={};save();}
  function observation(event_kind,details={}){if(!binding)return false;emit({...binding,event_id:id(),event_kind,observed_account:clean(details.observed_account,100),page_url:details.page_url||'',scheduled_text:clean(details.scheduled_text,80),result_text:clean(details.result_text,160),source:'session_observer'});return true;}
  function click(text,trusted,details={}){const kind=clickKind(text);if(!trusted||!binding||!kind)return false;const n=now();if(last[kind]!=null&&n-last[kind]<1800)return false;last[kind]=n;pending={kind,at:n,observed_account:clean(details.observed_account,100)};save();return observation(kind,details);}
  function schedule(meta,value,trusted,details={}){const text=scheduleValue(meta,value);if(!trusted||!binding||!text||last.schedule===text)return false;last.schedule=text;return observation('schedule_changed',{...details,scheduled_text:text});}
  function result(text,details={}){const kind=resultKind(text);if(!binding||!pending||pending.kind!==kind||now()-pending.at>120000||now()<pending.at)return false;const clickedAccount=pending.observed_account||'',resultAccount=clean(details.observed_account,100),mismatch=clickedAccount&&resultAccount&&clickedAccount!==resultAccount;pending=null;save();return observation('result_observed',{...details,observed_account:resultAccount||clickedAccount,result_text:mismatch?'账号变化待核对（提交时：'+clickedAccount+'）；平台提示：'+text:!resultAccount&&clickedAccount?'沿用提交时身份，当前页面未识别账号；平台提示：'+text:text});}
  return {bind,clear,click,schedule,result,snapshot:()=>({binding,pending})};
 }
 const pure={clean,clickKind,resultKind,scheduleValue,validContext,validTopURL,createEngine};
 if(typeof module!=='undefined'&&module.exports){module.exports=pure;return;}
 if(location.hostname!=='channels.weixin.qq.com'||!globalThis.chrome?.runtime)return;
 const isTop=window.top===window;
 const KEY='desk.channels.observation.v2.'+(isTop?'top':'frame')+':'+location.pathname;
 const topPath=()=>{try{return window.top.location.pathname;}catch{return '';}};
 let route=location.pathname,lastTopPath=topPath(),boundTopURL='',boundAccount='',restored=null;
 try{restored=JSON.parse(sessionStorage.getItem(KEY)||'null');}catch{}
 // A new create route reached from another page is a fresh composition, never the old task.
 // Reloading a create form is not evidence it still contains the same composition.
 if(restored&&(!isTop||CREATE_PATH.test(route)))restored=null;
 if(restored&&Date.now()-(restored.saved_at||0)>4*60*60*1000)restored=null;
 if(restored){boundTopURL=validTopURL(restored.top_page_url);boundAccount=clean(restored.observed_account,100);}
 function reportWriteFailure(error){let doc=document;try{if(!isTop)doc=window.top.document;}catch{}const root=doc.querySelector('#desk-channels-assistant')?.shadowRoot;if(!root)return;let output=root.querySelector('#page-observation');if(!output){output=document.createElement('p');output.id='page-observation';output.setAttribute('role','status');(root.querySelector('#panel-body')||root).append(output);}output.textContent='页面观察尚未写回：'+clean(error?.message||error||'本机服务未确认接收',180);}
 const send=payload=>{try{Promise.resolve(chrome.runtime.sendMessage({type:'observation',payload})).then(r=>{if(!r?.ok)reportWriteFailure(r?.error||'本机服务未确认接收');},reportWriteFailure);}catch(e){reportWriteFailure(e);}};
 const engine=createEngine({restore:restored,emit:send,id:()=>crypto.randomUUID(),persist:value=>{try{sessionStorage.setItem(KEY,JSON.stringify({...value,route,top_page_url:boundTopURL,observed_account:boundAccount,saved_at:Date.now()}));}catch{}}});
 function visible(el){return el instanceof Element&&!el.closest('[hidden],[aria-hidden="true"],#desk-channels-assistant')&&el.getClientRects().length>0;}
 function observedAccount(){
  // Only account-labelled header elements; never scan body text or infer from an avatar.
  const names=[...document.querySelectorAll('header [data-testid="account-name"],header [data-e2e="account-name"],header .account-name,header .finder-nickname,[role="banner"] [data-testid="account-name"]')].filter(visible).map(el=>clean(el.textContent,100)).filter(Boolean);
  const unique=[...new Set(names)];return unique.length===1?unique[0]:'';
 }
 const details=(result=false)=>({observed_account:observedAccount()||(!result?boundAccount:''),page_url:boundTopURL||location.origin+location.pathname});
 const onCreate=()=>CREATE_PATH.test(topPath()||route)&&!!boundTopURL;
 function checkRoute(){const next=location.pathname,nextTop=topPath();if(next===route&&nextTop===lastTopPath)return;if((next!==route&&CREATE_PATH.test(next))||(nextTop!==lastTopPath&&CREATE_PATH.test(nextTop))){engine.clear();boundTopURL='';boundAccount='';}route=next;lastTopPath=nextTop;try{sessionStorage.setItem(KEY,JSON.stringify({...engine.snapshot(),route,top_page_url:boundTopURL,observed_account:boundAccount,saved_at:Date.now()}));}catch{}}
 chrome.runtime.onMessage.addListener((message,sender,reply)=>{
  if(message?.type==='observation-probe'){
   if(sender?.id!==chrome.runtime.id){reply({ok:false,error:'观察消息来源无效'});return;}
   checkRoute();const context=engine.snapshot().binding;
   reply({ok:!!context,task_id:context?.task_id,revision:context?.revision,top_page_url:boundTopURL,observed_account:observedAccount()});return;
  }
  if(message?.type==='observation-explicit-context'){
   if(sender?.id!==chrome.runtime.id){reply({ok:false,error:'观察消息来源无效'});return;}
   checkRoute();
   if(message.payload?.event_kind!=='draft_clicked'||!onCreate()||!engine.snapshot().binding){reply({ok:false,error:'草稿操作尚未关联当前内容'});return;}
   const recorded=engine.click('保存草稿',true,details());reply({ok:true,recorded});return;
  }
  if(message?.type==='observation-clear'){if(sender?.id!==chrome.runtime.id){reply({ok:false});return;}engine.clear();boundTopURL='';boundAccount='';reply({ok:true});return;}
  if(message?.type!=='observation-context')return;
  if(sender?.id!==chrome.runtime.id){reply({ok:false,error:'观察消息来源无效'});return;}
  checkRoute();
  const topURL=validTopURL(message.payload?.top_page_url);
  if(!topURL||!CREATE_PATH.test(topPath()||route)){reply({ok:false,error:'请先进入发表页面后绑定当前内容'});return;}
  const ok=engine.bind(message.payload);if(ok){boundTopURL=topURL;boundAccount=clean(message.payload.observed_account,100);}
  reply({ok,observed_account:observedAccount(),error:ok?undefined:'绑定须由实际填写开始或明确接管当前页面触发'});
 });
 document.addEventListener('click',event=>{checkRoute();if(!onCreate()||!event.isTrusted)return;const el=event.target instanceof Element?event.target.closest('button,[role="button"],input[type="submit"]'):null;if(!el||!visible(el)||el.disabled||el.getAttribute('aria-disabled')==='true')return;engine.click(el.getAttribute('aria-label')||el.value||el.textContent,true,details());},true);
 function onSchedule(event){checkRoute();if(!onCreate()||!event.isTrusted)return;const el=event.target;if(!(el instanceof HTMLInputElement)||!visible(el)||['password','file','hidden'].includes(el.type))return;const labels=[...(el.labels||[])].map(x=>x.textContent).join(' ');const meta=[labels,el.getAttribute('aria-label'),el.placeholder,el.name].join(' ');engine.schedule(meta,el.value,true,details());}
 document.addEventListener('change',onSchedule,true);
 let inputTimer;document.addEventListener('input',event=>{clearTimeout(inputTimer);inputTimer=setTimeout(()=>onSchedule(event),500);},true);
 const RESULT_SELECTOR='[role="alert"],[role="status"],.weui-desktop-toast,.el-message,.ant-message-notice,.weui-toast,.weui-desktop-dialog__bd';
 const candidates=new Set();let timer;
 function queue(el){if(!(el instanceof Element))return;const enclosing=el.closest(RESULT_SELECTOR);if(enclosing)candidates.add(enclosing);el.querySelectorAll(RESULT_SELECTOR).forEach(x=>candidates.add(x));}
 new MutationObserver(records=>{checkRoute();if(!engine.snapshot().pending)return;for(const record of records){if(record.type==='characterData')queue(record.target.parentElement);else for(const node of record.addedNodes)queue(node);}if(!candidates.size)return;clearTimeout(timer);timer=setTimeout(()=>{for(const el of candidates){if(visible(el))engine.result(clean(el.textContent,160),details(true));}candidates.clear();},400);}).observe(document.documentElement,{subtree:true,childList:true,characterData:true});
 window.addEventListener('popstate',checkRoute);
 window.addEventListener('pagehide',()=>{try{sessionStorage.setItem(KEY,JSON.stringify({...engine.snapshot(),route:location.pathname,top_page_url:boundTopURL,observed_account:boundAccount,saved_at:Date.now()}));}catch{}});
 // Checks URL only, and supports SPA navigation that makes no DOM changes.
 setInterval(checkRoute,1500);
})();
