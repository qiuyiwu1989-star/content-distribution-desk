/* Keep every extension message small; assemble the File in the receiving frame. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.DeskAssetTransfer=api;})(globalThis,()=>{
 const CHUNK_BYTES=1024*1024,MAX_BYTES=512*1024*1024;
 async function read(asset,{send=message=>chrome.runtime.sendMessage(message),onProgress=()=>{}}={}){
  if(!asset||!Number.isSafeInteger(asset.size)||asset.size<=0||asset.size>MAX_BYTES)throw Error('素材大小不正确，分块传输支持不超过512MiB的素材');
  const parts=[];let offset=0,mime=asset.mime;
  while(offset<asset.size){
   const response=await send({type:'asset-chunk',id:asset.id,offset});
   if(!response?.ok)throw Error(response?.error||'素材分块传输失败');
   const r=response.result;
   if(r.offset!==offset||r.total!==asset.size||!Number.isSafeInteger(r.bytes)||r.bytes<=0||r.bytes>CHUNK_BYTES||r.bytes!==Math.min(CHUNK_BYTES,asset.size-offset)||typeof r.base64!=='string'||r.base64.length>Math.ceil(CHUNK_BYTES/3)*4)throw Error('素材分块信息不一致，请刷新分发台内容后重试');
   const raw=atob(r.base64);if(raw.length!==r.bytes)throw Error('素材分块长度不一致');
   const bytes=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);
   parts.push(bytes);offset+=bytes.length;mime=mime||r.mime;onProgress({loaded:offset,total:asset.size});
  }
  return {parts,bytes:offset,mime};
 }
 async function file(asset,options){const r=await read(asset,options);return new File(r.parts,asset.name,{type:asset.mime||r.mime||'application/octet-stream'});}
 return {read,file,CHUNK_BYTES,MAX_BYTES};
});
