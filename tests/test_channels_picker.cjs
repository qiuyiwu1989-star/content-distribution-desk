const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
let doc,listener,messages=[],bindResolve,bindMode='defer',coverOpen=true,existingVideo=0,currentBinding=null,assetActive=0,maxAssets=0;const all=[],revoked=[];
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
const tasks=Array.from({length:35},(_,i)=>({id:'t'+(i+1),revision:1,title:'第'+(i+1)+'条',account:'示例账号',body:'正文',tags:'',asset_ids:['v'+(i+1)],cover_id:'c'+(i+1),sequence:i+1,batch_id:'b',status:'draft',options:{collection:'企业AI'}}));
const assets=tasks.flatMap((t,i)=>[{id:'v'+(i+1),kind:'video',name:'video.mp4'},{id:'c'+(i+1),kind:'image',name:'封面'+(i+1)+'.png'}]);
let urlCounter=0;
const ctx={document:doc,location:{pathname:'/platform/post/create',href:'https://channels.weixin.qq.com/platform/post/create'},localStorage:{getItem:()=>null,setItem(){}},innerWidth:1400,innerHeight:1000,ResizeObserver:class{observe(){}disconnect(){}},MutationObserver:class{observe(){}disconnect(){}},setTimeout:()=>1,clearTimeout(){},setInterval(){},Option:class extends E{constructor(text,value){super('option');this.textContent=text;this.value=value;}},chrome:{storage:{local:{get:async()=>({}),set:async()=>{}}},runtime:{onMessage:{addListener:f=>listener=f},sendMessage:async m=>{
 messages.push(m);
 if(m.type==='state')return {ok:true,result:{batches:[{id:'b',name:'测试批次'}],tasks,assets}};
 if(m.type==='asset'){assetActive++;maxAssets=Math.max(maxAssets,assetActive);await new Promise(r=>setImmediate(r));assetActive--;return {ok:true,result:{base64:'AQID',mime:'image/png'}};}
 if(m.type==='frames')return {ok:true,result:[{counts:{video:1,body:1,title:1,existingVideo,cover:coverOpen?1:0,coverEdit:1,original:0}}]};
 if(m.type==='observation-check')return {ok:true,result:{task_id:currentBinding.task_id,revision:currentBinding.revision,observed_account:'示例账号'}};
 if(m.type==='observation-bind'){currentBinding=m;return bindMode==='defer'?await new Promise(r=>bindResolve=r):{ok:true,result:{observed_account:'示例账号'}};}
 if(m.type==='field'){if(m.kind==='coverEdit')coverOpen=true;return {ok:true,result:m.kind==='cover'?{previewReady:false,reason:'未确认预览'}:{filled:true,clicked:true}};}
 throw Error('Unexpected message '+m.type);
 }}},confirm:()=>true,console,Date,Promise,Error,URL:class extends URL{static createObjectURL(){return `blob:test-${++urlCounter}`;}static revokeObjectURL(u){revoked.push(u);}},Number,String,Uint8Array,File,atob};
vm.createContext(ctx);vm.runInContext(fs.readFileSync('extensions/channels-assistant/runner.js','utf8'),ctx);vm.runInContext(fs.readFileSync('extensions/channels-assistant/content.js','utf8'),ctx);
const tick=()=>new Promise(r=>setImmediate(r));
const settle=async(n=40)=>{for(let i=0;i<n;i++)await tick();};
(async()=>{
 await settle();assert(doc.host);let root=doc.host.shadowRoot,list=root.querySelector('#picker-list');
 assert.equal(root.querySelector('#picker-task').tag,'button','Picker is a semantic expandable button, not a native text-only select');
 assert.equal(list.children.filter(x=>x.attrs['data-task-choice']).length,30);assert.equal(messages.filter(m=>m.type==='asset').length,30);assert(maxAssets<=3,'Thumbnail fetching must limit concurrency');
 assert.equal(messages.filter(m=>m.type==='field'||m.type==='observation-bind').length,0,'Opening panel and fetching thumbnails must not act on platform');
 list.children.at(-1).onclick();await settle();assert.equal(list.children.filter(x=>x.attrs['data-task-choice']).length,35);assert.equal(messages.filter(m=>m.type==='asset').length,35,'More button loads only the next thumbnail page');
 list.children[0].onclick();await settle();root=doc.host.shadowRoot;assert.match(root.querySelector('#title').textContent,/第1条/);assert(revoked.length>=35,'Changing the panel revokes thumbnail blob URLs');
 assert.equal(messages.filter(m=>m.type==='field'||m.type==='observation-bind').length,0,'Selecting task must not bind or upload');
 root.querySelector('#picker-next').onclick();await settle();root=doc.host.shadowRoot;assert.match(root.querySelector('#title').textContent,/第2条/);assert.equal(messages.filter(m=>m.type==='field'||m.type==='observation-bind').length,0,'Next only previews');
 const filling=root.querySelector('#fill').onclick();await settle(4);assert.equal(messages.at(-1).type,'observation-bind');assert.equal(messages.at(-1).binding_reason,'fill_started');let reply;listener({type:'prepare',task:tasks[0],assets:[]},{},r=>reply=r);assert.equal(reply.ok,false);assert(root.querySelector('#picker-task').disabled);bindResolve({ok:false,error:'模拟绑定失败'});await filling;assert.equal(messages.filter(m=>m.type==='field').length,0);assert.match(root.querySelector('#status').textContent,/模拟绑定失败/);assert.equal(root.querySelector('#picker-task').disabled,false);
 bindMode='ok';let start=messages.length;await root.querySelector('#upload-cover').onclick();let actions=messages.slice(start).filter(m=>m.type==='field');assert.deepEqual(actions.map(m=>[m.kind,m.op]),[['cover','upload']],'Existing input: only cover upload, no video/copy/options/OS chooser');assert.equal(messages.slice(start).find(m=>m.type==='observation-bind').binding_reason,'manual_adoption');assert.match(root.querySelector('#cover-status').textContent,/尚未确认/);
 coverOpen=false;start=messages.length;await root.querySelector('#upload-cover').onclick();actions=messages.slice(start).filter(m=>m.type==='field');assert.deepEqual(actions.map(m=>[m.kind,m.op]),[['coverEdit','click'],['cover','upload']],'Closed editor: open edit only, never invoke the upload chooser');
 start=messages.length;await root.querySelector('#download-cover').onclick();assert.equal(messages.slice(start).filter(m=>m.type==='field'||m.type==='observation-bind').length,0,'Downloading cover never uploads or binds');
 existingVideo=1;start=messages.length;root.querySelector('#fill-only').onclick();await settle();actions=messages.slice(start).filter(m=>m.type==='field');assert(actions.some(m=>m.kind==='body'));assert(actions.some(m=>m.kind==='cover'));assert(!actions.some(m=>['original','collection','schedule','label'].includes(m.kind)),'Unconfirmed cover must stop later form options');assert.equal(root.querySelector('#save').disabled,true);assert.match(root.querySelector('#status').textContent,/封面尚未确认/);
 root.querySelector('#confirm-cover').onclick();assert.equal(root.querySelector('#save').disabled,false,'Explicit manual cover review plus copy readback permits the separately confirmed save');
 console.log('PASS: thumbnail pagination/concurrency/cleanup, preview-only selection, busy bind protection, cover-only/download paths and cover failure pause');
})().catch(e=>{console.error(e);process.exitCode=1});
