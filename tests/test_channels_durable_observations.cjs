const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context={};vm.runInNewContext(fs.readFileSync('extensions/channels-assistant/durable-observations.js','utf8'),context);
const create=context.DeskDurableObservations.create;
let disk={},time=1000,writes=0,offline=true,notifications=[];
const storage={get:async key=>structuredClone({[key]:disk[key]}),set:async value=>{disk={...disk,...structuredClone(value)};}};
const payload={event_id:'one',task_id:'task',revision:1,source:'session_observer',event_kind:'submit_clicked'};
const post=async p=>{writes++;if(offline)throw Error('offline');return {observation:{event_id:p.event_id,event_kind:p.event_kind}};};
(async()=>{
 let store=create({storage,post,now:()=>time,onDelivery:async(item,data)=>notifications.push(data)});
 await store.setBinding(8,{task_id:'task',document_id:'original-document'});
 await Promise.all([store.enqueue(payload,8),store.enqueue({...payload,event_id:'two'},8)]);
 await store.flush();assert.equal(writes,2);assert.equal((await store.getEvent('one')).status,'queued');assert.equal(notifications[0].queued,true);
 // Entire worker recreated; queued records and document identity survive.
 store=create({storage,post,now:()=>time,onDelivery:async(item,data)=>notifications.push(data)});
 assert.equal((await store.getBinding(8)).document_id,'original-document');
 await store.flush();assert.equal(writes,2,'backoff persists through worker restart');
 offline=false;time+=60000;await Promise.all([store.flush(),store.flush()]);assert.equal(writes,4);
 assert.equal((await store.getEvent('one')).status,'confirmed');assert.equal(notifications.at(-1).recorded,true);
 await store.enqueue(payload,8);await store.flush();assert.equal(writes,4,'same event acknowledged without duplicate POST');
 await assert.rejects(store.enqueue({...payload,revision:2},8),/不同内容/);
 // Transport delivers but worker dies before saving receipt: same event id is retained for server idempotency.
 const crashStore=create({storage,now:()=>time,post:async()=>{throw Error('connection lost after commit');}});
 await crashStore.enqueue({...payload,event_id:'ambiguous'},8);await crashStore.flush();
 assert.equal((await crashStore.getEvent('ambiguous')).payload.event_id,'ambiguous');
 time+=60000;const recovered=create({storage,post,now:()=>time});await recovered.flush();assert.equal((await recovered.getEvent('ambiguous')).status,'confirmed');
 let upgraded=false;
 const upgradeStore=create({storage,now:()=>time,post:async p=>{if(!upgraded){const error=Error('old app endpoint');error.status=404;throw error;}return {observation:{event_id:p.event_id}};}});
 await upgradeStore.enqueue({...payload,event_id:'old-app'},8);await upgradeStore.flush();assert.equal((await upgradeStore.getEvent('old-app')).status,'queued','404 means application upgrade pending, not permanent loss');
 upgraded=true;time+=60000;await upgradeStore.flush();assert.equal((await upgradeStore.getEvent('old-app')).status,'confirmed','record is delivered after app update');
 const rejected=create({storage,now:()=>time,post:async()=>{const e=Error('revision changed');e.status=409;throw e;}});
 await rejected.enqueue({...payload,event_id:'stale'},8);await rejected.flush();assert.equal((await rejected.getEvent('stale')).status,'failed');
 time+=100000;await rejected.flush();assert.equal((await rejected.getEvent('stale')).attempts,1,'terminal stale revision never retried');
 await store.clearBinding(8);assert.equal(await store.getBinding(8),undefined);assert.equal((await store.getEvent('one')).status,'confirmed','closing tab does not erase delivery history');
 console.log('PASS: durable queue, worker recovery, backoff, idempotency, terminal rejection and binding cleanup');
})().catch(error=>{console.error(error);process.exitCode=1;});
