const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
async function scan(editable,shown=true){
 let message,receive;
 const editor={tagName:'DIV',isContentEditable:editable!=='false',getClientRects:()=>shown?[{}]:[],getAttribute:k=>k==='contenteditable'?editable:k==='data-placeholder'?'添加描述':null,matches:()=>false};
 const doc={querySelectorAll:selector=>selector==='*'?[]:selector.includes('contenteditable')?[editor]:[]};
 const port={onMessage:{addListener:f=>receive=f},onDisconnect:{addListener:()=>{}},postMessage:m=>message=m};
 vm.runInNewContext(fs.readFileSync('extensions/channels-assistant/frame-agent.js','utf8'),{document:doc,location:{pathname:'/platform/post/create'},chrome:{runtime:{connect:()=>port}},setTimeout});
 receive({id:1,op:'scan'});await new Promise(r=>setImmediate(r));return message.result.counts.body;
}
(async()=>{assert.equal(await scan(''),1);assert.equal(await scan('true'),1);assert.equal(await scan('plaintext-only'),1);assert.equal(await scan('false'),0);assert.equal(await scan('',false),0);console.log('PASS: empty editable attribute, true, plaintext-only, disabled and hidden editors');})().catch(e=>{console.error(e);process.exitCode=1});
