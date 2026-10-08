/* Synthetic DOM lifecycle; does not operate a real browser or platform account. */
const assert=require('node:assert/strict');
const {uploadCover}=require('../frame-agent.js');
function fixture({ambiguous=false,unlabelled=false,noCrop=false,noSelection=false,remountAfterClear=false,noCandidate=false}={}){
 let thumbs=[],crop=[],deleteClicks=0,mainDeleteClicks=0,selectionClicks=0,uploadInputs=[],findCalls=0,input,remountPending=false;
 const scope={contains:x=>x.scope===scope,querySelectorAll:s=>s==='img'?thumbs:deletes};
 const button=(text,click)=>({scope,textContent:text,disabled:false,getClientRects:()=>[{}],getAttribute:()=>null,closest:()=>null,click});
 const mainVideoDelete=button('删除',()=>mainDeleteClicks++);mainVideoDelete.scope={};
 function newInput(){return {isConnected:true,disabled:false,value:'same-file.png',closest:()=>scope,set files(f){this.file=f;},dispatchEvent(e){if(e.type==='input'){this.isConnected=false;input=newInput();throw Error('input event would remount uploader before change');}if(e.type==='change'){assert.equal(this.value,'','input reset for same file');uploadInputs.push(this);if(!noCandidate)thumbs=[newThumb()];}}};}
 const candidate=button('封面候选',()=>{selectionClicks++;if(!noCrop)crop=[{src:'blob:same-retry'}];});
 function newThumb(){return {scope,complete:true,naturalWidth:1080,src:'blob:same-retry',getClientRects:()=>[{}],closest:()=>noSelection?null:candidate,click:()=>{throw Error('must click selection container, not img');}};}
 const oldInput=input=newInput();thumbs=[newThumb()];
 const remove=button(unlabelled?'×':'删除封面',()=>{deleteClicks++;thumbs=[];input.isConnected=false;input=newInput();remountPending=remountAfterClear?2:0;});
 const deletes=ambiguous?[remove,button('移除封面',()=>deleteClicks++)]:[remove];
 return {run:()=>uploadCover('same-file.png',{findInput:()=>{findCalls++;return input;},pause:async()=>{if(remountPending&&!--remountPending){input.isConnected=false;input=newInput();}},makeTransfer:f=>[f],event:type=>({type}),findCrop:()=>crop}),inspect:()=>({deleteClicks,mainDeleteClicks,selectionClicks,uploadInputs,oldInput,input,findCalls}),mainVideoDelete};
}
(async()=>{
 const f=fixture();const r=await f.run(),s=f.inspect();
 assert.equal(r.previewReady,true,'same src retry succeeds only after remove and selection');
 assert.equal(s.deleteClicks,1);assert.equal(s.mainDeleteClicks,0);assert.equal(s.selectionClicks,1);
 assert.equal(s.uploadInputs.length,1);assert.notEqual(s.uploadInputs[0],s.oldInput,'reacquire replacement input');assert.equal(s.uploadInputs[0],s.input);
 assert.ok(s.findCalls>=3);
 const a=fixture({ambiguous:true});await assert.rejects(a.run(),/删除按钮无法唯一识别/);assert.equal(a.inspect().deleteClicks,0);assert.equal(a.inspect().uploadInputs.length,0);
 const u=fixture({unlabelled:true});await assert.rejects(u.run(),/请手动移除旧封面/);assert.equal(u.inspect().deleteClicks,0);
 const canvas=fixture({noCrop:true});assert.equal((await canvas.run()).previewReady,false,'canvas or unrelated big image cannot prove crop');
 const inert=fixture({noSelection:true});assert.equal((await inert.run()).previewReady,false);assert.equal(inert.inspect().selectionClicks,0);
 assert.equal(canvas.inspect().mainDeleteClicks,0);assert.equal(inert.inspect().mainDeleteClicks,0);
 const remount=fixture({remountAfterClear:true});assert.equal((await remount.run()).previewReady,true);assert.equal(remount.inspect().uploadInputs[0],remount.inspect().input,'late remount uses stable final input');
 const absent=fixture({noCandidate:true});const absentResult=await absent.run();assert.equal(absentResult.submitted,false);assert.equal(absentResult.phase,'candidate_missing');assert.match(absentResult.reason,/已清除旧候选.*下载本条封面.*手动选择/);assert.equal(absent.inspect().uploadInputs.length,1,'no repeated uploads after missing candidate');
 console.log('cover retry synthetic lifecycle tests passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
