const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
async function fixture({duplicate=false,retain=true,selected=false}={}){
 let receive,result,open=false,clicked=0,opened=0;
 const el=(text,click,option=false)=>({textContent:text,children:[],getClientRects:()=>[{}],closest:()=>option?{}:null,click});
 const trigger=el(selected?'个人观点，仅供参考':'选择视频标注',()=>{open=true;opened++;});
 const option=el('个人观点，仅供参考',()=>{clicked++;open=false;if(retain)trigger.textContent='个人观点，仅供参考';},true);
 const document={querySelectorAll:s=>s==='*'?[]:(s==='span,div,li,button'||s.includes('role=option'))?[trigger,...(open?[option,...(duplicate?[option]:[])]:[])]:[]};
 const port={onMessage:{addListener:f=>receive=f},onDisconnect:{addListener:()=>{}},postMessage:m=>result=m};
 vm.runInNewContext(fs.readFileSync('extensions/channels-assistant/frame-agent.js','utf8'),{document,chrome:{runtime:{connect:()=>port}},setTimeout:f=>setImmediate(f)});
 async function select(){result=null;receive({id:1,op:'select',kind:'label'});for(let i=0;i<80&&!result;i++)await new Promise(r=>setImmediate(r));return result;}
 return {select,counts:()=>({clicked,opened})};
}
(async()=>{const good=await fixture();assert.equal((await good.select()).ok,true);assert.equal((await good.select()).ok,true);assert.deepEqual(good.counts(),{clicked:1,opened:1},'Repeated selection is idempotent');const prior=await fixture({selected:true});assert.equal((await prior.select()).result.alreadySelected,true);assert.equal(prior.counts().clicked,0);const bad=await fixture({duplicate:true});assert.equal((await bad.select()).ok,false);assert.equal(bad.counts().clicked,0);const dropped=await fixture({retain:false});assert.equal((await dropped.select()).ok,false,'Click without retained selection is not success');console.log('PASS: label selection/readback, repeat, existing choice, ambiguity and dropped state');})().catch(e=>{console.error(e);process.exitCode=1});
