"""Build editable SVG composition templates. Photos remain embedded original assets."""
import base64, json, html
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'static/creative/initial-set'; OUT.mkdir(exist_ok=True)
PHOTO=ROOT.parent/'短视频设计模板库/v1/assets/course.jpg'
photo='data:image/jpeg;base64,'+base64.b64encode(PHOTO.read_bytes()).decode()
# Each family deliberately changes reading hierarchy and/or source adaptation.
rows=[
('T01','留白原声','横版完整保留','#090b0c','#ffffff','#d7d9da',[0,600,1080,608],'plain','course',76,52,False,'马兆远 / 笔记侠：黑底、完整横画面','人物、现场与背景共同交代语境'),
('T02','黑金圆窗','横版完整保留','#101110','#f8f4e8','#d8b979',[40,600,1000,563],'curve','course',76,50,True,'领羊圆角窗口 + 黑金曲线','商业演讲与访谈，保留完整横版构图'),
('T03','网格访谈','人物主讲','#101215','#ffffff','#ebcf79',[0,550,1080,740],'grid','portrait',78,52,True,'网易科技：网格、双层标题','人物近景与稳定的字幕阅读区'),
('T04','浅纸讲堂','横版完整保留','#edf3ec','#284b3c','#547c65',[0,620,1080,608],'paper','course',74,50,True,'混沌文理院：浅底、宋体、来源说明','课程、研究与完整现场画面'),
('T05','暖棕会客厅','人物主讲','#37251e','#fff6e9','#e1bc81',[0,470,1080,900],'warm','portrait',76,52,True,'天真一代：暖棕分区、人物大画面','人物访谈，保留手势和表情'),
('T06','蓝色人物专访','人物主讲','#123958','#ffffff','#b6ddec',[0,540,1080,810],'blue','portrait',78,54,True,'蓝色嘉宾访谈：身份区与大画面','单人讲述，标题与身份清晰分层'),
('T07','PPT主讲·圆形小窗','PPT与人物','#101211','#ffffff','#d5bb83',[32,490,1016,650],'plain','slidepip',74,50,True,'用户首张示例：PPT主导、人物圆窗','解释PPT时材料放大，人物保留存在感'),
('T08','PPT上下讲解','PPT与人物','#eaf0f3','#163442','#26728b',[40,400,1000,600],'paper','stack',70,48,False,'PPT主导规则扩展：材料与人物独立分区','PPT不能被遮挡，同时需要看讲者动作'),
('T09','资料阅读台','材料解读','#f1eee6','#272d32','#a44b38',[48,530,984,720],'paper','document',72,48,True,'AI纪年 / 文档解读：材料、标注、摘要','文档或案例解读，突出当前阅读段落'),
('T10','科技演示窗','录屏演示','#0b1833','#f4f7ff','#6ccbdc',[40,560,1000,650],'tech','screen',74,50,True,'Tech Daily：界面窗口与讲解重点','软件操作、工具演示；焦点区域可放大'),
('T11','竖屏沉浸','原生竖构图','#101215','#ffffff','#ebd399',[0,0,1080,1920],'plain','native',80,56,False,'原生竖屏现场：满幅画面、文字叠加','竖拍或可安全重构的人物素材'),
('T12','双区对照','上下对照','#172720','#f5f1e5','#d5ce8b',[48,540,984,450],'grid','compare',72,50,True,'参考中的材料解读延伸为双区对照','步骤前后、两种方案与不同产品形态比较'),
]
items=[]
def rect(x,y,w,h,fill,rx=0,extra=''):
 return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" {extra}/>'
def text(x,y,s,size=50,fill='currentColor',anchor='start',weight=600,family='sans'):
 font='Source Han Serif CN,Songti SC,serif' if family=='serif' else 'Source Han Sans CN,PingFang SC,Microsoft YaHei,sans-serif'
 return f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" font-family="{font}">{html.escape(s)}</text>'
def img(x,y,w,h,portrait=False,radius=0):
 ph=min(1080,640*h/w); pw=ph*w/h
 box=f'{1140-pw/2} {min(440,1080-ph)} {pw} {ph}' if portrait else '0 0 1920 1080'
 key=f'clip{x}_{y}_{w}_{h}'
 return f'<defs><clipPath id="{key}">{rect(x,y,w,h,"white",radius)}</clipPath></defs><g clip-path="url(#{key})"><svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="{box}" preserveAspectRatio="xMidYMid slice"><image href="{photo}" width="1920" height="1080"/></svg></g>'
def slide(x,y,w,h):
 # Original diagram specimen; not a reconstructed source PPT.
 s=rect(x,y,w,h,'#edf4f6',12)+text(x+50,y+78,'从工具到协作',46,'#243e4c')+text(x+50,y+124,'结构示意 · 替换为当前课程的真实 PPT',24,'#61757c',weight=400)
 cw=(w-140)/3
 for i,(a,b) in enumerate([('输入','表达任务'),('协作','调整过程'),('结果','检查交付')]):
  xx=x+40+i*(cw+30)
  s+=rect(xx,y+210,cw,160,'#d6e4e9',22)+text(xx+cw/2,y+270,a,38,'#243e4c','middle')+text(xx+cw/2,y+325,b,28,'#516b76','middle',400)
  if i<2:s+=text(xx+cw+15,y+305,'→',28,'#607b87','middle')
 return s
for ident,name,kind,bg,ink,accent,media,texture,mode,ts,ss,logo,ref,use in rows:
 x,y,w,h=media; family='serif' if ident in ['T04','T05'] else 'sans'
 s=f'<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1920" viewBox="0 0 1080 1920" role="img" aria-label="{name}版式样张"><defs><linearGradient id="shade" x2="0" y2="1"><stop stop-color="#000" stop-opacity=".85"/><stop offset=".55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".9"/></linearGradient></defs>'+rect(0,0,1080,1920,bg)
 if texture=='curve':
  for i in range(14):s+=f'<path d="M {-500+i*45} 1920 Q {100+i*40} 1150 1250 {1400+i*32}" fill="none" stroke="{accent}" stroke-opacity=".14" stroke-width="2"/>'
 if texture in ['grid','tech']:
  for z in range(0,1920,100):s+=f'<path d="M 0 {z} H 1080" stroke="{accent}" stroke-opacity=".08"/>'
  for z in range(0,1080,100):s+=f'<path d="M {z} 0 V 1920" stroke="{accent}" stroke-opacity=".08"/>'
 if texture in ['blue','warm']:s+=f'<path d="M 700 0 H 1080 V 1920 H 120 Z" fill="{accent}" opacity=".06"/>'
 if mode=='native':s+=img(*media,True)+rect(0,0,1080,1920,'url(#shade)')
 elif mode in ['course','portrait']:s+=img(*media,mode=='portrait',36 if ident=='T02' else 0)
 elif mode=='slidepip':
  s+=slide(*media)+img(62,930,210,210,True,105)
  s+=f'<circle cx="167" cy="1035" r="105" stroke="{accent}" fill="none" stroke-width="6"/>'
 elif mode=='stack':s+=slide(*media)+img(280,1040,520,390,True,12)
 elif mode=='document':
  s+=rect(*media,'#fff',8)+text(95,615,'材料阅读 / 示例',28,'#7e8588')
  for yy,tt in [(710,'先确定要解释的问题'),(820,'再选择支撑它的材料'),(930,'让证据与判断对应'),(1100,'出处与时间随材料保留')]:
   if yy==820:s+=rect(85,770,895,75,'#f1dfaa')
   s+=text(100,yy,tt,43,'#263c44',weight=500)
  s+=text(100,1180,'示意材料，非引用原文',27,'#879296',weight=400)
 elif mode=='screen':
  s+=rect(*media,'#eef3fa',30)+rect(x,y,w,70,'#cfdae8',22)+text(x+35,y+47,'工作台 / 演示界面',26,'#294962')
  s+=rect(70,670,230,500,'#e0e9f2',14)
  for j,t in enumerate(['素材','制作方案','预览','交付']):s+=text(100,740+j*92,t,31,'#315270')
  s+=rect(340,700,655,240,'#c5ddea',14)+text(665,805,'当前操作区域',45,'#24435a','middle')+text(665,865,'根据讲解局部放大',28,'#476a81','middle')
  s+=rect(720,1010,240,85,'#225a7d',16)+text(840,1065,'查看结果',33,'white','middle')
 elif mode=='compare':
  s+=slide(x,y,w,h)+rect(48,1040,984,370,'#294438',16)+text(90,1125,'对照区域',40,accent)
  s+=text(90,1220,'展示另一方案或下一步骤',42,ink)+text(90,1300,'同尺度 · 同条件 · 明确差异',30,ink,weight=400)
 # Title and optional second title keep their roles distinct.
 left=ident in ['T06','T09','T10']; ax=72 if left else 540; anchor='start' if left else 'middle'
 title_y=285 if ident!='T08' else 260
 title_lines=['从工具到协作','重新理解 AI 产品']
 s+=text(ax,title_y,title_lines[0],ts,ink,anchor,800,family)+text(ax,title_y+105,title_lines[1],ts,accent if ident in ['T02','T03','T06','T10'] else ink,anchor,800,family)
 secondary_y=title_y+175
 if ident not in ['T08','T11']:s+=''
 subtitle_y={'T05':1455,'T08':1500,'T11':1400,'T12':1500}.get(ident,y+h+105)
 if ident in ['T09','T10']:s+=rect(138,subtitle_y-60,804,90,accent,12)
 subfill=bg if ident in ['T09','T10'] else ink
 s+=text(540,subtitle_y,'这里展示与原声同步的字幕',ss,subfill,'middle',600)
 if ident in ['T04','T09']:
  brand='data:image/png;base64,'+base64.b64encode((ROOT.parent/'协作资料/品牌素材/造物云/设计系统原稿/zaowuyun-lockup.png').read_bytes()).decode()
  s+=f'<image x="430" y="1580" width="220" height="76" href="{brand}"/>'
 s+=text(72,1845,ident+' / '+name,23,ink,weight=400)+text(1008,1845,'版式示例 · 非成片',23,ink,'end',400)+'</svg>'
 (OUT/(ident+'.svg')).write_text(s)
 spec={
 '字幕与字体':f'{"思源宋体标题＋思源黑体字幕" if family=="serif" else "思源黑体"}；标题 {ts}px，字幕 {ss}px；字幕最多两行，按语义断句；'+('实色字幕底板' if ident in ['T09','T10'] else '独立字幕区' if mode!='native' else '画面内字幕，暗部渐变托底'),
 '底纹':{'plain':'纯色底','curve':'低对比金色曲线','grid':'低对比细网格','paper':'浅色净底','warm':'暖棕斜面','blue':'深蓝斜面','tech':'深蓝细网格'}[texture]+f'，背景 {bg}，正文 {ink}，强调色 {accent}',
 'Logo':'造物云设计系统SVG导出的透明PNG Logo，保持原色原比例；位置(430,1580)，220×76' if ident in ['T04','T09'] else '不显示个人姓名；默认无Logo',
 '标题与辅助元素':f'主标题最多两行，{ts}px；副标题为可选栏目或身份信息，30px；超长标题先精简，禁止无限缩小；示例文案不作为讲者原话',
 '构图适配':'原生竖版优先；本样张用横版课程照片裁切模拟，实际竖拍素材仍待验证' if mode=='native' else '横版源素材重排为 9:16；'+('人物画面允许裁切，保护脸部、手势' if mode=='portrait' else '材料保持比例，不拉伸，不裁掉论证信息'),
 '播放画面':f'1080×1920 画布；主窗口 x={x}, y={y}, w={w}, h={h}；'+('圆角 36px' if ident=='T02' else '原比例适配窗口'),
 '动态规则':'讲到PPT时切入材料；人物小窗可换角或隐藏；重点太小时局部放大；解释结束后回人物' if mode in ['slidepip','stack'] else '按完整语义切换素材；标题和字幕位置保持稳定；字幕与原声同步，不自动生成音轨',
 '验收':'检查手机尺寸可读性、长标题和双行字幕、脸部与材料遮挡；叠加目标平台界面复核；当前仅静态版式已制作，动态样片待验证',
 }
 item=dict(id=ident,name=name,version='2.0.0',collection='initial-12',tag=kind,use=use,preview=f'/static/creative/initial-set/{ident}.svg',canvas=[1080,1920],media=media,bg=bg,ink=ink,accent=accent,subtitle_size=ss,title_size=ts,window_mode=kind,fit='cover' if mode in ['portrait','native'] else 'contain',brand_visible=ident in ['T04','T09'],status='layout-prototype',reference_note=ref,design_spec=spec,subtitle={'x':540,'first_baseline':subtitle_y,'size_px':ss,'max_lines':2},title={'x':ax,'baselines':[title_y,title_y+105],'size_px':ts,'alignment':anchor},speaker_window=([62,930,210,210] if mode=='slidepip' else [280,1040,520,390] if mode=='stack' else None),safe_area={'note':'平台遮挡须按目标界面复核；底部样张编号不属于正式成片'},sound_default='original_voice',preview_disclaimer='课程照片来自既有素材；PPT、文档与软件界面为自制结构示意，文字不代表讲者原话。')
 items.append(item)
(OUT/'templates.json').write_text(json.dumps({'schema':'content-layouts.v2','templates':items},ensure_ascii=False,indent=2))
path=ROOT/'static/creative/catalog.json'; catalog=json.loads(path.read_text()); catalog['templates']=items+[i for i in catalog['templates'] if i['id'] not in {r['id'] for r in items}];path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2))
print('Built 12 SVG layout prototypes and merged catalog')
