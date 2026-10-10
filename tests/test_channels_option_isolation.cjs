const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('extensions/channels-assistant/content.js','utf8');
const code=source.slice(source.indexOf(' async function applyOptions()'),source.indexOf('\n',source.indexOf(' async function applyOptions()')));
const calls=[];const ctx={collectionTarget:()=> '企业AI',root:{querySelector:()=>({checked:true})},task:{options:{collection:'企业AI'}},field:async kind=>{calls.push(kind);if(kind==='original')throw Error('0 个候选');return {selected:true,value:'企业AI'};}};
vm.createContext(ctx);vm.runInContext(code,ctx);
(async()=>{const notes=await ctx.applyOptions();assert.deepEqual(calls,['label','original','collection']);assert.match(notes[1],/未能识别/);assert.match(notes[2],/已回读.*企业AI/);console.log('PASS: original detection failure does not skip collection; outcomes stay separate');})().catch(e=>{console.error(e);process.exitCode=1});
