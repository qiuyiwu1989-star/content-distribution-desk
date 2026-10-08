const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const tick=()=>new Promise(r=>setImmediate(r));
const settle=async(n=25)=>{for(let i=0;i<n;i++)await tick();};
const until=async check=>{for(let i=0;i<200;i++){if(check())return;await tick();}throw Error('Expected asynchronous step did not start');};
async function fixture({storage={},session={},existing=0,uploadMode='ok',observed='示例账号',confirm=true,cover=false,failStorage=false,titleMode='ok'}={}){
let doc;const all=[],messages=[],confirmations=[];
class E{
 constructor(tag='div'){this.tag=tag;this.style={};this.children=[];this.attrs={};this.value='';this.disabled=false;this.hidden=false;this.isConnected=false;this.textContent='';this.map=new Map();all.push(this);}
 set id(v){this._id=v;}get id(){return this._id;}
 set innerHTML(v){this.html=v;for(const m of v.matchAll(/<(\w+)([^>]*\bid="([^"]+)"[^>]*)>/g)){const e=new E(m[1]);e.id=m[3];e.parent=this;if(m[2].includes('data-picker'))e.attrs['data-picker']='';e.disabled=/\bdisabled\b/.test(m[2]);e.checked=/\bchecked\b/.test(m[2]);this.map.set(e.id,e);}if(v.includes('<section'))this.map.set('section',new E('section'));}
 get innerHTML(){return this.html;}attachShadow(){this.shadowRoot=new E('shadow');return this.shadowRoot;}
 querySelector(s){if(s==='section')return this.map.get('section');if(s[0]==='#'){let e=this.map.get(s.slice(1));if(e)return e;for(const c of [...this.children,...this.map.values()]){if(c.id===s.slice(1))return c;e=c.querySelector(s);if(e)return e;}}return null;}
 querySelectorAll(s){if(s==='button:not([disabled])')return this.children.filter(e=>e.tag==='button'&&!e.disabled);return [...all].filter(e=>'data-picker'in e.attrs);}
 append(...els){for(const e of els){this.children.push(e);e.parent=this;e.isConnected=this.isConnected;}}prepend(e){this.children.unshift(e);e.parent=this;}
 before(e){this.parent?.append(e);}after(e){this.parent?.append(e);}replaceChildren(...els){this.children=[];this.append(...els);if(els.length&&this.tag==='select')this.value=els[0].value;}
 setAttribute(k,v){this.attrs[k]=v;}getAttribute(k){return this.attrs[k];}getBoundingClientRect(){return {left:500,top:50,width:350,height:650};}
 remove(){this.isConnected=false;if(doc.host===this)doc.host=null;}setPointerCapture(){}closest(){return null;}focus(){}click(){this.onclick?.();}
 set src(v){this._src=v;queueMicrotask(()=>this.onload?.());}get src(){return this._src;}
}
doc={host:null,createElement:t=>new E(t),querySelector:s=>s==='#desk-channels-assistant'?doc.host:null,querySelectorAll:()=>[],documentElement:new E('html')};doc.documentElement.append=e=>{doc.host=e;e.isConnected=true;};
const task={id:'t1',revision:1,title:'测试内容',account:'示例账号',body:'正文',tags:'',asset_ids:['v1'],cover_id:cover?'c1':null,sequence:1,batch_id:'b',status:'draft',options:{collection:'企业AI'}};
const assets=[{id:'v1',kind:'video',name:'video.mp4'},...(cover?[{id:'c1',kind:'image',name:'cover.png'}]:[])];
let releaseUpload,releaseTitle,listener,interval;
const env={storage,session,messages,confirmations,existing,uploadMode,observed,confirm,failStorage,titleMode};
const ctx={document:doc,location:{pathname:'/platform/post/create',href:'https://channels.weixin.qq.com/platform/post/create'},sessionStorage:{getItem:k=>session[k]||null,setItem:(k,v)=>session[k]=v},localStorage:{getItem:()=>null,setItem(){}},innerWidth:1400,innerHeight:1000,ResizeObserver:class{observe(){}disconnect(){}},MutationObserver:class{observe(){}disconnect(){}},setTimeout:f=>setImmediate(f),clearTimeout:clearImmediate,setInterval:f=>interval=f,Option:class extends E{constructor(text,value){super('option');this.textContent=text;this.value=value;}},chrome:{storage:{local:{get:async k=>({[k]:storage[k]}),set:async o=>{if(env.failStorage)throw Error('模拟进度存储失败');Object.assign(storage,JSON.parse(JSON.stringify(o)));}}},runtime:{onMessage:{addListener:f=>listener=f},sendMessage:async m=>{
 messages.push(m);
 if(m.type==='state')return{ok:true,result:{batches:[{id:'b',name:'测试'}],tasks:[task],assets}};
 if(m.type==='asset')return{ok:true,result:{base64:'AQID',mime:'video/mp4'}};
 if(m.type==='frames')return{ok:true,result:[{counts:{video:1,body:1,title:1,existingVideo:env.existing,coverEdit:0,cover:cover?1:0}}]};
 if(m.type==='observation-bind'||m.type==='observation-check')return{ok:true,result:{task_id:task.id,revision:task.revision,observed_account:env.observed}};
 if(m.type==='field'){
  assert(!['save','publish'].includes(m.kind),'Preparation must never save or publish');
  if(m.kind==='cover')return{ok:true,result:{previewReady:false,reason:'模拟封面预览尚未更新'}};
  if(m.kind==='title'&&env.titleMode==='defer')await new Promise(r=>releaseTitle=r);
  if(m.kind==='video'){
   if(env.uploadMode==='defer')await new Promise(r=>releaseUpload=r);
   env.existing=1;
   if(env.uploadMode==='timeout')return{ok:false,error:'模拟上传响应超时'};
   if(env.uploadMode==='account-change')env.observed='其他账号';
  }
  return{ok:true,result:{filled:true,checked:true,selected:true,scheduled:true,value:m.value}};
 }
 throw Error('Unexpected message '+m.type);
}}},confirm:m=>{confirmations.push(m);return env.confirm;},console,Date,Math,Promise,Error,URL,Number,String,Uint8Array,File,atob};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('extensions/channels-assistant/runner.js','utf8'),ctx);vm.runInContext(fs.readFileSync('extensions/channels-assistant/content.js','utf8'),ctx);
await settle();doc.host.shadowRoot.querySelector('#picker-list').children[0].onclick();await settle();
env.root=doc.host.shadowRoot;env.click=id=>env.root.querySelector('#'+id).onclick();env.status=()=>env.root.querySelector('#status').textContent;
env.releaseTitle=()=>releaseTitle?.();env.hasTitle=()=>!!releaseTitle;env.navigate=path=>{ctx.location.pathname=path;ctx.location.href='https://channels.weixin.qq.com'+path;interval();};env.release=()=>releaseUpload?.();env.hasRelease=()=>!!releaseUpload;env.actions=kind=>messages.filter(m=>m.type==='field'&&(!kind||m.kind===kind));env.record=()=>Object.values(storage)[0];return env;
}
(async()=>{
 const timeout=await fixture({uploadMode:'timeout'});
 await timeout.click('fill');assert.match(timeout.status(),/响应超时/);assert.equal(timeout.actions('video').length,1);assert.equal(timeout.actions('body').length,0);
 await timeout.click('run-resume');assert.equal(timeout.actions('video').length,1,'Uncertain upload response must never cause a repeat upload');assert.equal(timeout.record().engine.status,'completed');
 const paused=await fixture({uploadMode:'defer'});const filling=paused.click('fill');
 await until(paused.hasRelease);await paused.click('run-pause');paused.release();await filling;
 assert.equal(paused.actions('body').length,0,'Pause during upload must stop before writing copy');assert.equal(paused.record().engine.status,'paused');
 await paused.click('run-resume');assert.equal(paused.actions('video').length,1);assert.equal(paused.record().engine.status,'completed');
 const origin=await fixture({uploadMode:'timeout'});await origin.click('fill');
 const restored=await fixture({storage:origin.storage,session:origin.session,existing:1,confirm:false});
 assert.equal(restored.actions().length,0,'Restoring a panel must not operate platform');
 await restored.click('run-resume');assert.equal(restored.actions().length,0,'Declining restored-page confirmation must not operate');assert(restored.confirmations.some(s=>s.includes('重新打开')));
 restored.confirm=true;restored.existing=0;await restored.click('run-resume');assert.match(restored.status(),/恰有一个/);assert.equal(restored.actions().length,0);
 restored.existing=2;await restored.click('run-resume');assert.match(restored.status(),/恰有一个/);assert.equal(restored.actions().length,0);
 restored.existing=1;await restored.click('run-resume');assert.equal(restored.actions('video').length,0,'Restored interrupted upload is adopted, never sent again');assert.equal(restored.record().engine.status,'completed');
 const changed=await fixture({uploadMode:'account-change'});await changed.click('fill');assert.match(changed.status(),/账号已改变/);assert.equal(changed.actions('body').length,0,'Changed account stops before copy');assert.equal(changed.record().engine.status,'paused');
 const coverFlow=await fixture({cover:true});await coverFlow.click('fill');
 assert.equal(coverFlow.record().engine.status,'paused');assert.match(coverFlow.status(),/封面尚未确认/);assert.equal(coverFlow.actions('cover').length,1);assert.equal(coverFlow.actions('original').length,0);
 await coverFlow.click('confirm-cover');await coverFlow.click('run-resume');assert.equal(coverFlow.record().engine.status,'completed');assert.equal(coverFlow.actions('video').length,1);assert.equal(coverFlow.actions('cover').length,1,'Manual cover review resumes without repeating cover upload');
 const newRun=await fixture({cover:true});await newRun.click('fill');await newRun.click('confirm-cover');await newRun.click('run-stop');newRun.click('fill-only');await settle(100);
 assert.equal(newRun.record().engine.status,'paused');assert.equal(newRun.actions('cover').length,2,'New manual-adoption run must clear prior cover confirmation');assert.match(newRun.status(),/封面尚未确认/);
 const disk=await fixture({failStorage:true});await disk.click('fill');assert.equal(disk.actions('video').length,0,'Storage failure must prevent upload dispatch');assert.match(disk.status(),/存储失败/);
 const titlePause=await fixture({titleMode:'defer'});const titleWork=titlePause.click('fill');await until(titlePause.hasTitle);await titlePause.click('run-pause');titlePause.releaseTitle();await titleWork;
 assert.equal(titlePause.actions('body').length,0,'Pause while title is being written must stop before body');assert.equal(titlePause.record().engine.status,'paused');
 const routed=await fixture({uploadMode:'defer'});const routeWork=routed.click('fill');await until(routed.hasRelease);routed.navigate('/platform/post/list');routed.navigate('/platform/post/create');routed.release();await routeWork;
 assert.match(routed.status(),/页面已变化/);assert.equal(routed.actions('body').length,0,'Leaving and returning to create page invalidates previous document context');
 console.log('PASS: real runner/content integration, uncertain upload resume, pause boundary, restored-page consent and preview guard, account-change stop, cover confirmation reset, persistence failure, title pause and route generation; no save/publish');
})().catch(e=>{console.error(e);process.exitCode=1});
