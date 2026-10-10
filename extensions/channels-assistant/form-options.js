/* Conservative, idempotent handling of original declarations and existing collections. */
(function(root){
 'use strict';
 const normalize=value=>String(value??'').replace(/\u00a0/g,' ').replace(/\u200b/g,'').replace(/\s+/g,' ').trim();
 const isVisible=el=>!!el&&el.getClientRects().length>0;
 function deepQuery(selector){
  const roots=[document],seen=new Set(roots),result=[];
  for(let i=0;i<roots.length;i++){
   for(const el of roots[i].querySelectorAll('*'))if(el.shadowRoot&&el.id!=='desk-channels-assistant'&&!seen.has(el.shadowRoot)){seen.add(el.shadowRoot);roots.push(el.shadowRoot);}
   result.push(...roots[i].querySelectorAll(selector));
  }
  return result;
 }
 function create(config={}){
  const query=config.query||deepQuery,visible=config.visible||isVisible,wait=config.wait||(ms=>new Promise(resolve=>setTimeout(resolve,ms)));
  const checkboxSelector='input[type="checkbox"],[role="checkbox"]';
  const widgetSelector='select,[role="combobox"],[aria-haspopup="listbox"],input[readonly],.weui-desktop-dropdown__switch';
  const enabled=el=>!el.disabled&&el.getAttribute('aria-disabled')!=='true';
  const exact=(el,value)=>normalize(el.textContent)===value;
  const unique=items=>[...new Set(items)];
  function exactLeaves(value){return query('label,span,div,button').filter(el=>visible(el)&&exact(el,value)&&![...(el.children||[])].some(child=>exact(child,value)));}
  function scopedWidgets(label,selector){
   if(label.control?.matches(selector))return [label.control];
   const parentLabel=label.closest?.('label');
   if(parentLabel?.control?.matches(selector))return [parentLabel.control];
   for(let el=parentLabel||label.parentElement,depth=0;el&&depth<4;el=el.parentElement,depth++){
    // Never widen the search to an entire form or settings page.
    if(normalize(el.textContent).length>240||el.matches?.('form,body,html,[role="dialog"],dialog'))break;
    const found=[...el.querySelectorAll(selector)].filter(item=>!item.closest?.('[role="option"],[role="listbox"]'));
    if(found.length)return found.length===1?found:[];
   }
   return [];
  }
  function originalCandidates(){
   const labels=exactLeaves('声明原创'),result=[];
   for(const input of query(checkboxSelector)){
    if(input.closest?.('[role="dialog"],dialog'))continue;
    const named=normalize(input.getAttribute('aria-label'))==='声明原创';
    const labelled=[...(input.labels||[])].some(label=>visible(label)&&exact(label,'声明原创'));
    const refs=String(input.getAttribute('aria-labelledby')||'').split(/\s+/).filter(Boolean);
    const referenced=refs.length>0&&refs.every(id=>labels.some(label=>label.id===id));
    if((named&&visible(input))||labelled||referenced)result.push(input);
   }
   for(const label of labels){
    if(label.closest?.('[role="dialog"],dialog'))continue;
    const candidates=scopedWidgets(label,checkboxSelector);
    if(candidates.length===1)result.push(candidates[0]);
   }
   return unique(result);
  }
  function collectionCandidates(){
   const result=query(widgetSelector).filter(el=>visible(el)&&!/option|listbox/.test(el.getAttribute('role')||'')&&/^(?:选择|添加到)?合集$/.test(normalize(el.getAttribute('aria-label'))));
   for(const label of [...exactLeaves('合集'),...exactLeaves('添加到合集'),...exactLeaves('选择合集')]){
    if(label.closest?.('[role="option"],[role="listbox"]'))continue;
    if(exact(label,'选择合集')){
     const trigger=label.closest?.(widgetSelector+',button');
     if(trigger&&visible(trigger))result.push(trigger);
     else result.push(label);
    }else result.push(...scopedWidgets(label,widgetSelector+',button').filter(visible));
   }
   return unique(result).filter(el=>!result.some(other=>other!==el&&other.contains?.(el)&&other.matches?.(widgetSelector)));
  }
  function candidates(kind){if(kind==='original')return originalCandidates();if(kind==='collection')return collectionCandidates();return [];}
  function single(kind){const found=candidates(kind);if(found.length!==1)throw Error((kind==='original'?'声明原创':'合集')+'控件未唯一识别（'+found.length+'），请在平台手动处理');return found[0];}
  function readChecked(el){
   if(el.matches('input[type="checkbox"]'))return typeof el.checked==='boolean'?el.checked:null;
   const value=el.getAttribute('aria-checked');return value==='true'?true:value==='false'?false:null;
  }
  function termsDialog(){return query('[role="dialog"],dialog,.weui-desktop-dialog').find(el=>visible(el)&&/原创/.test(normalize(el.textContent))&&/(?:同意|阅读|确认声明|承诺|协议|须知|条款)/.test(normalize(el.textContent)));}
  function assertNoTerms(){if(termsDialog())throw Error('平台出现原创条款，请人工阅读并处理；辅助不会接受条款');}
  async function original(options={}){
   async function handleTerms(){const dialog=termsDialog();if(!dialog)return;if(!options.confirmTerms)assertNoTerms();
    const checks=[...dialog.querySelectorAll('input[type="checkbox"],[role="checkbox"]')];if(checks.length!==1)throw Error('原创协议勾选框不唯一，请人工处理');const agree=checks[0];if(readChecked(agree)!==true){if(!enabled(agree))throw Error('原创协议不可勾选');agree.click();await wait(150);}if(readChecked(agree)!==true)throw Error('原创协议未勾选');
    const buttons=[...dialog.querySelectorAll('button,[role="button"]')].filter(el=>visible(el)&&enabled(el)&&['声明原创','确认','确认声明'].includes(normalize(el.textContent)));if(buttons.length!==1)throw Error('原创声明确认按钮不唯一，请人工处理');buttons[0].click();await wait(150);if(termsDialog())throw Error('原创声明弹窗仍未关闭，请人工核对');
   }
   await handleTerms();
   assertNoTerms();let el=single('original');const before=readChecked(el);
   if(before===null)throw Error('无法确认声明原创的勾选状态，未进行点击，请手动核对');
   if(before===true)return {checked:true,already:true};
   if(!enabled(el))throw Error('声明原创控件不可用，请在平台核对');
   el.click(); // Exactly one click; never toggle a checked declaration off.
   for(let i=0;i<12;i++){
    await wait(100);await handleTerms();el=single('original');
    if(readChecked(el)===true){await wait(180);assertNoTerms();if(readChecked(single('original'))===true)return {checked:true,already:false};}
   }
   throw Error('已点击声明原创，但未回读到已勾选状态，请在平台核对');
  }
  function plainControlText(el){
   // Ignore a popup's text even when it is mounted inside the trigger element.
   if(el.matches?.('[role="option"],[role="listbox"],[role="menu"],ul,ol'))return '';
   if(el.nodeType===3)return el.textContent||'';
   if(el.childNodes?.length)return [...el.childNodes].map(plainControlText).join(' ');
   return el.textContent||'';
  }
  function readCollection(el){
   if(el.matches('select')){
    const options=[...(el.selectedOptions||[])];return options.length===1?normalize(options[0].textContent):'';
   }
   const aria=el.getAttribute('aria-valuetext');if(aria!==null)return normalize(aria);
   if(el.matches('input'))return normalize(el.value);
   return normalize(plainControlText(el)).replace(/^合集[ :：]+/,'');
  }
  async function readback(value){
   for(let i=0;i<15;i++){
    await wait(100);const found=candidates('collection');
    if(found.length===1&&readCollection(found[0])===value){
     await wait(150);const stable=candidates('collection');
     if(stable.length===1&&readCollection(stable[0])===value)return {selected:true,value,already:false};
    }
   }
   throw Error('已选择合集，但页面回读与「'+value+'」不一致，请手动核对');
  }
  function exactOptions(value,trigger){
   const all=query('[role="option"],li,button,span,div').filter(el=>visible(el)&&el!==trigger&&exact(el,value));
   const roleOptions=all.filter(el=>el.getAttribute('role')==='option');
   if(roleOptions.length)return unique(roleOptions);
   return unique(all.filter(el=>![...(el.children||[])].some(child=>exact(child,value))));
  }
  async function collection(raw){
   assertNoTerms();
   const value=normalize(raw);if(!value)return {skipped:true};
   const el=single('collection');
   if(readCollection(el)===value)return {selected:true,value,already:true};
   if(!enabled(el))throw Error('合集控件不可用，请在平台核对');
   if(el.matches('select')){
    const options=[...(el.options||[])].filter(option=>normalize(option.textContent)===value&&!option.disabled);
    if(options.length!==1)throw Error('目标合集「'+value+'」未唯一找到，未修改当前合集');
    el.value=options[0].value;
    const EventCtor=el.ownerDocument?.defaultView?.Event||Event;
    el.dispatchEvent(new EventCtor('input',{bubbles:true}));el.dispatchEvent(new EventCtor('change',{bubbles:true}));
    return readback(value);
   }
   el.click();let choices=[];
   for(let i=0;i<20;i++){await wait(100);choices=exactOptions(value,el);if(choices.length===1)break;if(choices.length>1)throw Error('目标合集出现多个同名选项，请手动选择');}
   if(choices.length!==1)throw Error('未找到精确匹配的已有合集「'+value+'」，未选择其他合集');
   if(!enabled(choices[0]))throw Error('目标合集不可用，请在平台核对');
   choices[0].click();return readback(value);
  }
  function diagnostics(){
   const shape=el=>({tag:el.tagName,className:String(el.className||'').slice(0,200),role:el.getAttribute('role'),type:el.getAttribute('type'),ariaChecked:el.getAttribute('aria-checked'),checked:typeof el.checked==='boolean'?el.checked:null,visible:visible(el)});
   return ['声明原创','添加到合集','选择合集'].map(label=>({label,regions:exactLeaves(label).slice(0,3).map(el=>{const levels=[];for(let p=el,depth=0;p&&depth<4;p=p.parentElement,depth++){if(p.matches?.('body,html,form'))break;levels.push({node:shape(p),children:[...p.children].slice(0,12).map(shape),controls:[...p.querySelectorAll('input,select,[role="checkbox"],[role="combobox"]')].slice(0,8).map(shape)});}return levels;})}));
  }
  return {candidates,diagnostics,perform:(kind,value)=>{if(kind==='original')return original(value||{});if(kind==='collection')return collection(value);return Promise.reject(Error('不支持的表单选项'));},readChecked,readCollection};
 }
 root.DeskFormOptions={...create(),create};
 if(typeof module!=='undefined')module.exports=root.DeskFormOptions;
})(typeof globalThis!=='undefined'?globalThis:this);
