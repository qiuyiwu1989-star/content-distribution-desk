const assert=require('node:assert/strict'),crypto=require('node:crypto');
const transfer=require('../asset-transfer.js');
(async()=>{
 const source=Buffer.alloc(53891636);for(let i=0;i<source.length;i++)source[i]=i%251;
 assert.ok(source.toString('base64').length>64*1024*1024,'old full-file reply exceeds the screenshot limit');
 let calls=0,largest=0,last=0;
 const asset={id:'0123456789abcdef0123456789abcdef',size:source.length,name:'video.mp4',mime:'video/mp4'};
 const result=await transfer.read(asset,{send:async m=>{assert.equal(m.type,'asset-chunk');assert.equal(m.offset,last);const part=source.subarray(m.offset,m.offset+transfer.CHUNK_BYTES);last+=part.length;calls++;const reply={ok:true,result:{offset:m.offset,total:source.length,bytes:part.length,base64:part.toString('base64'),mime:'video/mp4'}};largest=Math.max(largest,Buffer.byteLength(JSON.stringify(reply)));return reply;}});
 assert.ok(calls>1);assert.ok(largest<2*1024*1024,'every response remains below 2MiB');
 assert.equal(crypto.createHash('sha256').update(Buffer.concat(result.parts.map(p=>Buffer.from(p)))).digest('hex'),crypto.createHash('sha256').update(source).digest('hex'));
 await assert.rejects(transfer.read({size:transfer.MAX_BYTES+1}),/512/);
 await assert.rejects(transfer.read({size:3,id:'x'},{send:async()=>({ok:true,result:{offset:1,total:3,bytes:3,base64:'YWJj'}})}),/分块信息/);
 await assert.rejects(transfer.read({size:3,id:'x'},{send:async()=>({ok:true,result:{offset:0,total:3,bytes:3,base64:'YQ=='}})}),/长度/);
 await assert.rejects(transfer.read({size:3,id:'x'},{send:async()=>({ok:false,error:'读取失败'})}),/读取失败/);
 console.log(`Large-file transfer verified: ${source.length} bytes; ${calls} chunks; largest reply ${largest} bytes; identical SHA-256.`);
})().catch(e=>{console.error(e);process.exit(1)});
