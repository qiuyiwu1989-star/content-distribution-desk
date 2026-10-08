(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.DeskRunner=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const clone=v=>v===undefined?undefined:JSON.parse(JSON.stringify(v));
const stable=v=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.keys(x).sort().reduce((o,k)=>(o[k]=x[k],o),{}):x);
class BoundaryError extends Error{constructor(status){super(status==='stopped'?'执行已停止':'执行已暂停');this.name='BoundaryError';this.code='RUN_'+status.toUpperCase();}}
function createRun({identity,restored,persist=async()=>{},onChange=()=>{}}){
 if(!identity||typeof identity!=='object')throw new Error('Run identity is required');
 if(restored&&stable(restored.identity)!==stable(identity))throw new Error('Run identity mismatch');
 const now=()=>new Date().toISOString();
 let state=restored?clone(restored):{version:1,id:typeof crypto!=='undefined'&&crypto.randomUUID?crypto.randomUUID():'run-'+Date.now()+'-'+Math.random().toString(36).slice(2),identity:clone(identity),status:'idle',steps:{},created_at:now(),updated_at:now(),needsValidation:false};
 if(restored){
  if(state.version!==1||!state.steps)throw new Error('Unsupported run snapshot');
  for(const step of Object.values(state.steps))if(step.status==='running')step.status='interrupted';
  if(!['stopped','completed'].includes(state.status))state.status='paused';
  state.needsValidation=true;state.pauseRequested=false;
 }
 let active=false,writes=Promise.resolve();
 const snapshot=()=>clone(state);
 function save(){state.updated_at=now();const data=snapshot();const next=writes.catch(()=>{}).then(()=>persist(data));writes=next;onChange(data);return next;}
 async function checkpoint(){
  if(state.status==='stopped')throw new BoundaryError('stopped');
  if(state.pauseRequested||state.needsValidation||state.status==='paused'){state.status='paused';await save();throw new BoundaryError('paused');}
  if(state.status==='completed')throw new Error('Run already completed');
 }
 async function executeStep(id,fn){
  if(active)throw new Error('Another step is running');
  active=true;
  try{
   await checkpoint();
   // A UI stop can arrive while the asynchronous boundary yields.
   if(state.status==='stopped')throw new BoundaryError('stopped');
   if(state.pauseRequested)throw new BoundaryError('paused');
   if(state.steps[id]&&state.steps[id].status==='done')return clone(state.steps[id].result);
   const previous=clone(state.steps[id]);
   state.status='running';state.steps[id]={status:'running',attempts:(previous&&previous.attempts||0)+1,started_at:now()};
   try{
    // Persist intent before action: an interrupted upload must never look untouched.
    await save();
    if(state.pauseRequested||state.status==='stopped'){state.steps[id]=previous||{status:'pending',attempts:0};await checkpoint();}
    const result=await fn({previous,snapshot:snapshot()});
    state.steps[id]={...state.steps[id],status:'done',result:clone(result),completed_at:now()};
    if(state.status!=='stopped')state.status=state.pauseRequested?'paused':'running';
    await save();return result;
   }catch(error){
    if(!(error instanceof BoundaryError)){
     state.steps[id]={...state.steps[id],status:'failed',error:'step_failed',failed_at:now()};
     if(state.status!=='stopped')state.status='paused';
     // Error text may contain private platform data; persist only a generic code.
     try{await save();}catch(_){}
    }
    throw error;
   }
  }finally{active=false;}
 }
 async function pause(){if(['stopped','completed'].includes(state.status))return;state.pauseRequested=true;if(!active)state.status='paused';await save();}
 async function stop(){if(state.status==='completed')return;state.status='stopped';state.pauseRequested=false;await save();}
 async function resume(options={}){
  if(active)throw new Error('Wait for the current action to finish');
  if(['stopped','completed'].includes(state.status))throw new Error('Run cannot resume');
  if(options.identity&&stable(options.identity)!==stable(state.identity))throw new Error('Run identity mismatch');
  if(state.needsValidation&&(options.verified!==true||!options.identity))throw new Error('Restored run requires verified page preflight');
  state.needsValidation=false;state.pauseRequested=false;state.status='idle';await save();
 }
 async function invalidate(ids){if(active||!['idle','paused'].includes(state.status))throw new Error('Pause before invalidating steps');for(const id of ids)if(state.steps[id])state.steps[id].status='invalidated';await save();}
 async function finish(){if(active)throw new Error('A step is still running');await checkpoint();if(Object.values(state.steps).some(s=>s.status!=='done'))throw new Error('Run has unfinished steps');state.status='completed';await save();}
 return{executeStep,runNext:executeStep,checkpoint,pause,resume,stop,finish,invalidate,snapshot};
}
return{createRun,BoundaryError};
});
