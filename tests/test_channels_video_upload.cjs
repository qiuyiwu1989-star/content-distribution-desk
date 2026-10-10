const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
async function upload({existing=false,selected=false,transferFails=false}={}){
 let receive,result;const events=[];
 const input={accept:'video/mp4',disabled:false,files:selected?[{}]:[],closest:()=>null,value:'',dispatchEvent:e=>events.push(e.type)};
 const video={src:'blob:video',getClientRects:()=>[{}]};
 const document={querySelectorAll:s=>s==='input[type=file]'?[input]:s==='video'&&existing?[video]:[]};
 const port={onMessage:{addListener:f=>receive=f},onDisconnect:{addListener:()=>{}},postMessage:r=>result=r};
 vm.runInNewContext(fs.readFileSync('extensions/channels-assistant/frame-agent.js','utf8'),{document,chrome:{runtime:{connect:()=>port}},DeskAssetTransfer:{file:async()=>{if(transferFails)throw Error('transfer failed');return {name:'test.mp4'};}},DataTransfer:class{constructor(){this.files=[];this.items={add:f=>this.files.push(f)};}},Event:class{constructor(type){this.type=type;}},setTimeout});
 receive({id:1,op:'upload',kind:'video',asset:{id:'v'}});for(let i=0;i<20&&!result;i++)await new Promise(r=>setImmediate(r));return {result,events,input};
}
(async()=>{let r=await upload();assert(r.result.ok);assert.deepEqual(r.events,['change'],'Exactly one change event, no extra event that can remount uploader');assert.equal(r.input.files.length,1);for(const config of [{existing:true},{selected:true},{transferFails:true}]){r=await upload(config);assert.equal(r.result.ok,false);assert.deepEqual(r.events,[]);}console.log('PASS: single upload event; existing preview, selected file and transfer failure block dispatch');})().catch(e=>{console.error(e);process.exitCode=1});
