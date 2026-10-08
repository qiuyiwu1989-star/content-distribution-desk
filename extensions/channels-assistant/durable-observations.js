/* Durable delivery stores observations, never platform login data or publication state. */
(function(root){
 const KEY='desk.observations.v1';
 const canonical=value=>JSON.stringify(value,(key,item)=>item&&typeof item==='object'&&!Array.isArray(item)?Object.keys(item).sort().reduce((out,k)=>(out[k]=item[k],out),{}):item);
 function create({storage,post,now=Date.now,onDelivery=async()=>{}}){
  let chain=Promise.resolve(),flushing;
  const serial=fn=>{const result=chain.then(fn);chain=result.catch(()=>{});return result;};
  const read=async()=>{const value=(await storage.get(KEY))[KEY];return value&&value.version===1?value:{version:1,bindings:{},outbox:{},receipts:{}};};
  const mutate=fn=>serial(async()=>{const state=await read(),result=await fn(state);await storage.set({[KEY]:state});return result;});
  async function enqueue(payload,tabId){
   if(!payload||typeof payload.event_id!=='string'||!payload.event_id||payload.event_id.length>200)throw Error('观察事件编号无效');
   const encoded=canonical(payload);if(encoded.length>20000)throw Error('观察记录过大，未加入队列');
   return mutate(state=>{
    const previous=state.outbox[payload.event_id]||state.receipts[payload.event_id];
    if(previous){if(previous.encoded!==encoded)throw Error('相同事件编号包含不同内容，已停止写入');return previous;}
    if(Object.keys(state.outbox).length>=1000)throw Error('观察记录队列已满，请先恢复本机分发台连接');
    const item={payload:JSON.parse(encoded),encoded,tabId,status:'queued',attempts:0,nextAttempt:0,createdAt:now()};state.outbox[payload.event_id]=item;return item;
   });
  }
  async function flush(){
   if(flushing)return flushing;
   flushing=(async()=>{
    const ids=await serial(async()=>Object.keys((await read()).outbox));
    for(const id of ids){
     const item=await mutate(state=>{const entry=state.outbox[id];if(!entry||entry.status==='failed'||entry.nextAttempt>now())return null;entry.attempts++;entry.nextAttempt=now()+Math.min(15*60*1000,30000*2**Math.min(entry.attempts-1,5));return {...entry};});
     if(!item)continue;
     let result;
     try{result=await post(item.payload);}catch(error){
      const terminal=error.status>=400&&error.status<500&&![401,403,404,408,429].includes(error.status);
      await mutate(state=>{const entry=state.outbox[id];if(entry){entry.error=String(error.message).slice(0,400);entry.status=terminal?'failed':'queued';}});
      await onDelivery(item,{recorded:false,queued:!terminal,event_id:id,error:error.message});continue;
     }
     await mutate(state=>{delete state.outbox[id];state.receipts[id]={encoded:item.encoded,status:'confirmed',confirmedAt:now(),result};const old=Object.keys(state.receipts).sort((a,b)=>state.receipts[a].confirmedAt-state.receipts[b].confirmedAt);for(const key of old.slice(0,Math.max(0,old.length-500)))delete state.receipts[key];});
     await onDelivery(item,{recorded:true,queued:false,...result.observation,event_id:id});
    }
   })().finally(()=>{flushing=null;});return flushing;
  }
  return {
   enqueue,flush,
   getEvent:id=>serial(async()=>{const state=await read();return state.outbox[id]||state.receipts[id];}),
   getBinding:tabId=>serial(async()=>(await read()).bindings[tabId]),
   setBinding:(tabId,value)=>mutate(state=>{state.bindings[tabId]=value;}),
   clearBinding:tabId=>mutate(state=>{delete state.bindings[tabId];}),
  };
 }
 root.DeskDurableObservations={create};
})(globalThis);
