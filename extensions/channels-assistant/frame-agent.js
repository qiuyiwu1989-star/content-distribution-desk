(()=>{
 const visible=el=>el.getClientRects().length>0;
 function query(selector){const roots=[document];for(let i=0;i<roots.length;i++)for(const el of roots[i].querySelectorAll('*'))if(el.shadowRoot&&el.id!=='desk-channels-assistant')roots.push(el.shadowRoot);return roots.flatMap(root=>[...root.querySelectorAll(selector)]);}
 function candidates(kind){
  if(['original','collection'].includes(kind)&&globalThis.DeskFormOptions)return globalThis.DeskFormOptions.candidates(kind);
  if(kind==='video'){
   const all=query('input[type=file]').filter(x=>!x.disabled&&!x.closest('.single-cover-uploader-wrap')&&!/image|png|jpg|jpeg|webp/i.test(x.accept));
   const explicit=all.filter(x=>/video|mp4|mov|webm/i.test(x.accept));return explicit.length?explicit:all.filter(x=>!x.accept||x.accept==='*/*');
  }
  if(kind==='cover')return query('.single-cover-uploader-wrap input[type=file]').filter(x=>!x.disabled&&visible(x.closest('.single-cover-uploader-wrap'))&&!/video|mp4|mov/i.test(x.accept));
  if(kind==='coverEdit')return query('span,div,button').filter(x=>visible(x)&&x.textContent.trim()==='编辑'&&![...x.children].some(c=>c.textContent.trim()==='编辑')&&(()=>{let a=x;for(let i=0;i<5&&a;i++,a=a.parentElement)if(/封面预览/.test(a.textContent)&&a.textContent.length<600)return true;return false;})());
  if(kind==='coverUpload')return query('span,div,button').filter(x=>visible(x)&&x.textContent.trim()==='上传封面'&&![...x.children].some(c=>c.textContent.trim()==='上传封面'));
  if(kind==='coverConfirm')return query('button').filter(x=>visible(x)&&x.textContent.trim()==='确认'&&(()=>{let a=x;for(let i=0;i<8&&a;i++,a=a.parentElement)if(/编辑封面|封面预览/.test(a.textContent)&&a.textContent.length<1500)return true;return false;})());
  if(kind==='existingVideo')return query('video').filter(x=>visible(x)&&!!(x.currentSrc||x.src||x.querySelector('source[src]')||x.readyState>=1&&x.videoWidth>0));
  if(kind==='body'){
   const all=query('[contenteditable],textarea,[role="textbox"]').filter(x=>visible(x)&&(x.isContentEditable||x.tagName==='TEXTAREA'||x.tagName==='INPUT'));
   const explicit=all.filter(x=>x.matches('.input-editor')||/添加描述|视频描述/.test((x.getAttribute('data-placeholder')||'')+(x.getAttribute('placeholder')||'')+(x.getAttribute('aria-label')||'')));
   return explicit.length?explicit:all.filter(x=>x.isContentEditable||x.tagName==='TEXTAREA');
  }
  if(kind==='title')return query('input,textarea').filter(x=>visible(x)&&/短标题/.test((x.placeholder||'')+(x.getAttribute('aria-label')||'')));
  const text=kind==='collection'?'选择合集':kind==='schedule'?'定时':kind==='save'?'保存草稿':kind==='label'?'选择视频标注':'个人观点';
  return query(kind==='save'?'button':'span,div,li,button').filter(x=>visible(x)&&x.textContent.trim()===text&&![...x.children].some(c=>c.textContent.trim()===text));
 }
 function get(kind){const all=candidates(kind);if(all.length!==1)throw Error(kind+'候选数量='+all.length);return all[0];}
 function normalizeText(value){return String(value||'').replace(/\r\n?/g,'\n').replace(/\u00a0/g,' ').replace(/\u200b/g,'').trim();}
 function readText(el){return el.isContentEditable?(el.innerText??el.textContent):el.value;}
 function write(el,value){el.focus();if(el.isContentEditable){const selection=el.ownerDocument.getSelection();const range=el.ownerDocument.createRange();range.selectNodeContents(el);selection.removeAllRanges();selection.addRange(range);const inserted=el.ownerDocument.execCommand('insertText',false,value);if(!inserted)el.textContent=value;el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:value}));}else{const proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(el,value);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}return el.isContentEditable?el.textContent:el.value;}
 const coverScope=el=>el?.closest('.single-cover-uploader-wrap');
 const existingThumbs=scope=>[...scope.querySelectorAll('img')].filter(x=>visible(x)&&!!(x.currentSrc||x.src));
 const readyThumbs=scope=>[...scope.querySelectorAll('img')].filter(x=>visible(x)&&x.complete&&x.naturalWidth>0);
 function coverDeleteButtons(scope){
  const labels=/^(删除|移除|删除封面|移除封面|删除图片|移除图片|remove|delete|remove cover|delete cover)$/i;
  const options=[...scope.querySelectorAll('button,[role="button"],[aria-label],[title]')].filter(x=>visible(x)&&!x.disabled&&x.getAttribute('aria-disabled')!=='true'&&[x.getAttribute('aria-label'),x.getAttribute('title'),x.textContent].some(v=>labels.test(String(v||'').trim()))).map(x=>x.closest('button,[role="button"]')||x).filter(x=>scope.contains(x));
  return [...new Set(options)];
 }
 function coverSelectionTarget(img,scope){
  const el=img.closest('button,[role="button"],label,[tabindex],.cover-item,.cover-image-item,.cover-uploader-item,.image-item');
  return el&&el!==img&&scope.contains(el)&&!el.disabled&&el.getAttribute('aria-disabled')!=='true'?el:null;
 }
 function cropImages(scope){
  // Only explicit crop/cover-preview surfaces within this cover editor count as evidence.
  let editor=scope.closest('[role="dialog"],.cover-editor,.cover-editor-dialog,.weui-desktop-dialog');
  if(!editor){let p=scope.parentElement;for(let i=0;i<5&&p&&p!==document.body;i++,p=p.parentElement){if(/编辑封面|封面预览/.test(p.textContent)&&p.textContent.length<2500){editor=p;break;}}}
  return editor?[...editor.querySelectorAll('[data-testid="cover-crop-preview"] img,img[data-testid="cover-crop-preview"],.cover-cropper img,.cropper-canvas img,.cropper-view-box img,.cropper-container img')].filter(x=>!scope.contains(x)&&visible(x)&&x.complete&&x.naturalWidth>0):[];
 }
 async function uploadCover(file,{findInput=()=>get('cover'),pause=ms=>new Promise(r=>setTimeout(r,ms)),makeTransfer=f=>{const dt=new DataTransfer();dt.items.add(f);return dt.files;},event=name=>new Event(name,{bubbles:true}),findCrop=cropImages}={}){
  let removedPrevious=false,input=findInput(),scope=coverScope(input);if(!scope)throw Error('未唯一识别封面上传区域，请手动上传封面');
  if(existingThumbs(scope).length){
   const deletes=coverDeleteButtons(scope);
   if(deletes.length!==1)throw Error('旧封面尚在上传候选中，删除按钮无法唯一识别，请手动移除旧封面后重试');
   deletes[0].click();removedPrevious=true;let cleared=false;
   for(let i=0;i<30;i++){await pause(150);try{input=findInput();scope=coverScope(input);if(scope&&existingThumbs(scope).length===0){cleared=true;break;}}catch{}}
   if(!cleared)throw Error('旧封面候选尚未清除，请手动移除旧封面后重试');
  }
  // A framework may remount after removal or after value reset. Require one live input
  // to survive two event-loop checks after reset; never assign to a detached candidate.
  let stable=false;
  for(let attempt=0;attempt<12;attempt++){
   try{input=findInput();scope=coverScope(input);if(!scope||input.isConnected!==true||input.disabled){await pause(150);continue;}input.value='';
    await pause(150);if(findInput()!==input||input.isConnected!==true||input.disabled)continue;
    await pause(150);if(findInput()!==input||input.isConnected!==true||input.disabled)continue;
    stable=true;break;
   }catch{await pause(150);}
  }
  if(!stable)throw Error('封面上传输入框仍在更新，请先下载本条封面，再点击平台“上传封面”手动选择下载文件');
  // File inputs are consumed via change; an extra input event can synchronously
  // remount the uploader before change reaches its current node. Dispatch once.
  input.files=makeTransfer(file);input.dispatchEvent(event('change'));
  let thumb;
  for(let i=0;i<60;i++){await pause(250);try{scope=coverScope(findInput());}catch{continue;}if(!scope)continue;const all=readyThumbs(scope);if(all.length>1)throw Error('封面上传区域有多个候选，请手动核对本条封面');if(all.length===1){thumb=all[0];break;}}
  if(!thumb)return {submitted:false,fileAssigned:true,previewReady:false,phase:'candidate_missing',removedPrevious,reason:(removedPrevious?'已清除旧候选，':'')+'平台未生成新封面候选；请先下载本条封面，再点击平台“上传封面”手动选择下载文件'};
  const target=coverSelectionTarget(thumb,scope);if(!target)return {submitted:true,previewReady:false,reason:'封面候选的选择按钮无法识别，请手动点击候选并核对裁切预览'};
  const src=thumb.currentSrc||thumb.src;target.click();
  for(let i=0;i<40;i++){await pause(250);if(src&&findCrop(scope).some(x=>(x.currentSrc||x.src)===src))return {submitted:true,thumbnailSelected:true,previewReady:true};}
  return {submitted:true,thumbnailSelected:true,previewReady:false,reason:'封面候选已选择，裁切图未能确认切换（canvas 或平台裁切地址无法核实），请手动核对'};
 }
 function coverDiagnostics(){return query('.single-cover-uploader-wrap').slice(0,6).map(scope=>({
  tag:scope.tagName,className:String(scope.className||'').slice(0,180),visible:visible(scope),
  inputs:[...scope.querySelectorAll('input[type=file]')].slice(0,6).map(x=>({tag:x.tagName,type:x.type,accept:x.accept,disabled:!!x.disabled,connected:!!x.isConnected,multiple:!!x.multiple,className:String(x.className||'').slice(0,180)})),
  thumbnails:[...scope.querySelectorAll('img')].slice(0,6).map(x=>({tag:x.tagName,className:String(x.className||'').slice(0,180),visible:visible(x),complete:!!x.complete,width:x.naturalWidth||0,height:x.naturalHeight||0,parentTag:x.parentElement?.tagName||'',parentClass:String(x.parentElement?.className||'').slice(0,180)})),
  buttons:[...scope.querySelectorAll('button,[role="button"],[aria-label],[title]')].slice(0,12).map(x=>({tag:x.tagName,className:String(x.className||'').slice(0,180),label:(x.getAttribute('aria-label')||x.getAttribute('title')||x.textContent||'').trim().slice(0,80),visible:visible(x),disabled:!!x.disabled})),
  childStructure:[...scope.children].slice(0,12).map(x=>({tag:x.tagName,className:String(x.className||'').slice(0,180),role:x.getAttribute('role')||'',childTags:[...x.children].slice(0,8).map(y=>y.tagName)}))
 }));}
 async function perform(m){
  if(m.op==='scan')return {agent_version:'0.7.1',path:location.pathname,coverUploaders:coverDiagnostics(),formOptions:globalThis.DeskFormOptions?.diagnostics?.()||[],counts:Object.fromEntries(['video','cover','body','title','original','label','personal','save','collection','schedule','coverEdit','coverUpload','coverConfirm','existingVideo'].map(k=>[k,candidates(k).length])),inputs:query('input[type=file]').map(x=>({accept:x.accept,disabled:x.disabled})),editors:query('[contenteditable],textarea').map(x=>({tag:x.tagName,editable:x.getAttribute('contenteditable'),placeholder:x.getAttribute('data-placeholder')||x.getAttribute('placeholder')||'',visible:visible(x)}))};
  if(m.op==='select'&&['original','collection'].includes(m.kind)){if(!globalThis.DeskFormOptions)throw Error('表单选项模块未连接，请重载扩展');return globalThis.DeskFormOptions.perform(m.kind,m.value);}
  if(m.op==='select'){
   if(!['label','collection'].includes(m.kind))throw Error('不支持的选择');
   const value=m.kind==='label'?'个人观点，仅供参考':m.value;
   if(m.kind==='collection'&&!value)return {skipped:true};
   const exact=()=>query('span,div,li,button,[role=option]').filter(x=>visible(x)&&x.textContent.trim()===value&&![...x.children].some(c=>c.textContent.trim()===value));
   get(m.kind).click();
   let options=[];for(let i=0;i<20;i++){await new Promise(r=>setTimeout(r,150));options=exact();if(options.length===1)break;}
   if(options.length!==1)throw Error('选项 '+value+' 未唯一识别，请在平台手动选择');
   options[0].click();return {selected:true,value};
  }
  if(m.op==='schedule'){
   const date=new Date(m.value);if(!Number.isFinite(date.getTime())||date<=new Date())throw Error('计划时间无效或已经过去');
   get('schedule').click();await new Promise(r=>setTimeout(r,300));
   const inputs=query('input[type=datetime-local]').filter(visible);
   if(inputs.length!==1)throw Error('平台日期控件需要手动设置：'+date.toLocaleString('zh-CN'));
   const local=new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16);
   if(write(inputs[0],local)!==local)throw Error('定时时间回读失败');return {scheduled:local};
  }
  const el=get(m.kind);
  if(m.op==='fill'){
   if(!['body','title'].includes(m.kind))throw Error('不能写入此字段');
   for(let attempt=0;attempt<3;attempt++){
    const current=get(m.kind);write(current,m.value);current.blur();await new Promise(r=>setTimeout(r,600));
    const retained=get(m.kind);
    if(normalizeText(readText(retained))===normalizeText(m.value))return {filled:true};
   }
   throw Error((m.kind==='title'?'短标题':'视频描述')+'未完整保留，请核对页面内容');
  }
  if(m.op==='upload'){
   if(!['video','cover'].includes(m.kind))throw Error('非法素材类型');
   const r=await chrome.runtime.sendMessage({type:'asset',id:m.asset.id});if(!r.ok)throw Error(r.error);
   const bytes=Uint8Array.from(atob(r.result.base64),c=>c.charCodeAt(0));
   const f=new File([bytes],m.asset.name,{type:m.asset.mime||r.result.mime});
   if(m.kind==='cover')return uploadCover(f);
   const dt=new DataTransfer();dt.items.add(f);const target=get(m.kind);target.value='';target.files=dt.files;target.dispatchEvent(new Event('input',{bubbles:true}));target.dispatchEvent(new Event('change',{bubbles:true}));
   return {submitted:true};
  }
  if(m.op==='click'){
   if(!['label','personal','save','coverEdit','coverUpload','coverConfirm'].includes(m.kind))throw Error('禁止公开发布操作');
   if(el.disabled||el.getAttribute('aria-disabled')==='true')throw Error('按钮禁用');el.click();return {clicked:true};
  }
  throw Error('未知操作');
 }
 function connect(){const port=chrome.runtime.connect({name:'desk-frame'});port.onMessage.addListener(m=>perform(m).then(result=>port.postMessage({id:m.id,ok:true,result}),error=>port.postMessage({id:m.id,ok:false,error:error.message})));port.onDisconnect.addListener(()=>setTimeout(connect,1000));}
 if(typeof module!=='undefined'&&module.exports){module.exports={uploadCover,coverDeleteButtons,coverSelectionTarget};return;}
 connect();
})();
