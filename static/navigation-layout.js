/* Group existing features; preserve their routes and data. */
(()=>{
 const publication=['queue','calendar','records','runs'];
 const resources=['resources','hotwords','oral-cases','creative-fonts','excellent-cases','brand-assets','personal-assets','creative-templates','cover-design','creative-editors','planners','delivery-standard','browser-plugins','skill-center','tool-center'];
 const resourceGroups=[
  {id:'assets',name:'素材与样式',items:[['brand-assets','品牌素材','data-brand-library'],['personal-assets','个人素材','data-personal-library'],['creative-fonts','字体库','data-font-library'],['creative-templates','内容模板','data-creative-nav="creative-templates"'],['cover-design','封面设计','data-cover-nav']]},
  {id:'methods',name:'创作方法',items:[['planners','策划师','data-resource-planners'],['creative-editors','剪辑师','data-creative-nav="creative-editors"'],['skill-center','技能中心','data-skill-nav'],['hotwords','热词库','data-hot-nav'],['oral-cases','个人口语案例库','data-oral-nav'],['excellent-cases','优秀案例库','data-case-nav'],['delivery-standard','内容交付质量标准','data-delivery-standard']]},
  {id:'tools',name:'工具与插件',items:[['tool-center','工具中心','data-tool-center'],['browser-plugins','浏览器插件','data-plugin-center']]}
 ];
 let browsedGroup=null,lastResourceView=null;
 const activeGroup=()=>resourceGroups.find(g=>g.items.some(i=>i[0]===view));
 function resourceButtons(){const selected=resourceGroups.find(g=>g.id===(browsedGroup||activeGroup()?.id))||resourceGroups[0];return `<div class="resource-group-tabs" aria-label="资源分类">${resourceGroups.map(g=>`<button data-resource-group="${g.id}" aria-pressed="${g.id===selected.id}">${g.name}</button>`).join('')}</div><div class="resource-group-items" aria-label="${selected.name}">${selected.items.map(([id,label,attr])=>`<button ${attr} ${id===view?'aria-current="page"':''}>${label}</button>`).join('')}</div>`;}
 const resourceStyle=document.createElement('link');resourceStyle.rel='stylesheet';resourceStyle.href='/static/resource-groups.css';document.head.appendChild(resourceStyle);
 const oldShell=shell,oldRender=render;
 shell=function(){let html=oldShell();const section=publication.includes(view)?'queue':resources.includes(view)?'resources':'accounts'===view?'accounts':'packages';
 const items=[['packages','box','内容工作台'],['queue','grid','发布工作台'],['accounts','users','账号管理'],['resources','grid','创作资源']];
 html=html.replace(/<nav aria-label="主要导航">[\s\S]*?<\/nav>/,`<nav aria-label="主要导航">${items.map(([id,i,name])=>`<button class="nav-item ${section===id?'active':''}" ${id==='resources'?'data-resource-home':`data-nav="${id}"`}>${icon(i)}<span>${name}</span></button>`).join('')}</nav>`);
 html=html.replace(/(<span>工作空间 <span class="slash">\/<\/span> )[^<]*/,(_,prefix)=>prefix+items.find(x=>x[0]===section)[2]);
 return html;
 };
 function home(planners=false){$('#content').innerHTML=`<div class="page-heading"><div><h1>${planners?'策划师管理':'创作资源'}</h1><p>制作内容时选择模板、角色与标准；账号关系在账号管理中维护。</p></div></div><nav id="resource-subnav" class="workspace-subnav">${resourceButtons()}</nav>${planners?'<section class="panel" style="padding:24px"><h2>当前没有独立策划师目录</h2><p>选题与策划能力目前由课程剪辑 skill 提供，可在技能中心调用。独立策划师角色尚未登记。</p><button class="primary" data-skill-nav>打开技能中心</button></section>':'<section class="panel" style="padding:24px"><h2>选择要管理的资源</h2><p>字体库管理标题与字幕字体；内容模板管理视频版式；封面设计管理视觉方案；剪辑师管理剪辑策略；质量标准定义交付格式；技能中心管理 Agent 能力与调用。</p></section>'}`;}
 render=function(){if(view==='creative-fonts'){$('#app').innerHTML=shell();$('#content').innerHTML=`<div class="page-heading"><div><h1>字体库</h1><p>四款已选字体，思源黑体与思源宋体备用。试写标题，比较字重与深浅背景。</p></div><a class="secondary" href="/static/creative/fonts/index.html" target="_blank" rel="noopener">独立打开</a></div><div id="font-library-host"></div>`;mountFonts();return;}if(view==='resources' ||view==='planners'){ $('#app').innerHTML=shell();home(view==='planners');return;}oldRender();};
 async function mountFonts(){
  const host=$('#font-library-host');
  try{const response=await fetch('/static/creative/fonts/index.html');if(!response.ok)throw new Error('字体库读取失败');const doc=new DOMParser().parseFromString(await response.text(),'text/html');if(!host.isConnected)return;
   const root=host.attachShadow({mode:'open'});let css=doc.querySelector('style').textContent.replaceAll('url("','url("/static/creative/fonts/').replaceAll('body',':host');
   if(!document.querySelector('#creative-font-faces')){const faces=document.createElement('style');faces.id='creative-font-faces';faces.textContent=(css.match(/@font-face\{[^}]+\}/g)||[]).join('');document.head.appendChild(faces);}
   root.innerHTML='<style>'+css+'main{padding:16px 0;max-width:none} header{display:none}</style><div class="dark">'+doc.querySelector('main').outerHTML+'</div>';
   root.querySelectorAll('a').forEach(a=>{const href=a.getAttribute('href');if(href&&!href.startsWith('/')&&!href.startsWith('http'))a.href='/static/creative/fonts/'+href;});
   root.querySelector('#sample-text').addEventListener('input',e=>root.querySelectorAll('.sample').forEach(n=>n.textContent=e.target.value||'输入标题预览'));
   root.querySelector('#font-size').addEventListener('input',e=>{host.style.setProperty('--sample-size',e.target.value+'px');root.querySelector('#size-value').textContent=e.target.value;});
   root.querySelector('#theme').addEventListener('click',e=>{const on=root.querySelector('.dark')?root.querySelector('.dark').classList.toggle('dark'):root.querySelector('style + div').classList.toggle('dark');e.target.textContent=on?'查看浅底效果':'查看深底效果';});
   root.querySelectorAll('.cardhead select').forEach(s=>s.addEventListener('change',()=>s.closest('article').querySelector('.specimen').style.fontWeight=s.value));
  }catch(e){host.textContent='字体库暂时未能加载，请使用上方“独立打开”。';}
 }
 function group(){
  const nav=document.querySelector('.sidebar nav');if(nav)nav.querySelectorAll('[data-experience]').forEach(b=>b.hidden=true);
  const main=$('#content');if(!main)return;
  if(publication.includes(view)){
   const h=main.querySelector('h1');if(h&&h.textContent!=='发布工作台')h.textContent='发布工作台';
   let tabs=main.querySelector('.workspace-subnav');if(tabs&&!tabs.dataset.publicationGroup){tabs.dataset.publicationGroup='1';tabs.innerHTML=[['queue','待办发布'],['calendar','发布日历'],['records','发布记录']].map(([id,label])=>`<button data-nav="${id}" class="${(view==='runs'?'records':view)===id?'selected':''}">${label}</button>`).join('');}
  }
  if(resources.includes(view)&&!main.querySelector('#resource-subnav')){const nav=document.createElement('nav');nav.id='resource-subnav';nav.className='workspace-subnav';nav.innerHTML=resourceButtons();main.querySelector('.page-heading')?.after(nav);}
  if(resources.includes(view)){
   const nav=main.querySelector('#resource-subnav');if(!nav)return;
   if(lastResourceView!==view){lastResourceView=view;browsedGroup=null;}
   const groupMarkup=resourceButtons();if(nav.dataset.groupMarkup!==groupMarkup){nav.innerHTML=groupMarkup;nav.dataset.groupMarkup=groupMarkup;}
   nav.setAttribute('aria-label','创作资源导航');
   const active={'hotwords':'[data-hot-nav]','oral-cases':'[data-oral-nav]','creative-fonts':'[data-font-library]','excellent-cases':'[data-case-nav]','brand-assets':'[data-brand-library]','personal-assets':'[data-personal-library]','creative-templates':'[data-creative-nav="creative-templates"]','cover-design':'[data-cover-nav]','creative-editors':'[data-creative-nav="creative-editors"]','planners':'[data-resource-planners]','delivery-standard':'[data-delivery-standard]','browser-plugins':'[data-plugin-center]','tool-center':'[data-tool-center]','skill-center':'[data-skill-nav]'}[view];
   nav.querySelectorAll('button').forEach(b=>{const selected=active&&b.matches(active);if(selected&&b.getAttribute('aria-current')!=='page')b.setAttribute('aria-current','page');if(!selected&&b.hasAttribute('aria-current'))b.removeAttribute('aria-current');});
   const currentGroup=activeGroup();const label=currentGroup?.items.find(i=>i[0]===view)?.[1]||'资源总览';
   let location=main.querySelector('.resource-location');if(!location){location=document.createElement('div');location.className='resource-location';nav.after(location);}const value='创作资源 / '+(currentGroup?currentGroup.name+' / ':'')+label;if(location.textContent!==value)location.textContent=value;
  }

 }
 document.addEventListener('click',e=>{const category=e.target.closest('[data-resource-group]');if(category){browsedGroup=category.dataset.resourceGroup;group();return;}if(!e.target.closest('[data-resource-home],[data-resource-planners],[data-font-library]'))return;if(Library.isDirty()||taskDirty()){toast('请先保存或撤销当前修改',true);return;}view=e.target.closest('[data-font-library]')?'creative-fonts':e.target.closest('[data-resource-planners]')?'planners':'resources';closeModal();render();});
 new MutationObserver(group).observe(document.documentElement,{childList:true,subtree:true});group();
})();
