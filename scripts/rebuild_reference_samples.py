"""Three independent compositions measured against user-supplied references."""
import base64,json,html,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[1]; O=R/'static/creative/reference-redo'; O.mkdir(exist_ok=True)
P=R.parent
photo='data:image/jpeg;base64,'+base64.b64encode((P/'短视频设计模板库/v1/assets/course.jpg').read_bytes()).decode()
def box(x,y,w,h,c,r=0):return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{c}"/>'
def t(x,y,words,size,color='#fff',weight=600,anchor='start',extra=''):
 return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}" {extra}>{html.escape(words)}</text>'
def pic(x,y,w,h,vb='0 0 1920 1080',clip=''):
 return f'<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="{vb}" preserveAspectRatio="xMidYMid slice" {clip}><image href="{photo}" width="1920" height="1080"/></svg>'
def start(bg):return '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1920" viewBox="0 0 1080 1920" font-family="PingFang SC,Microsoft YaHei,sans-serif">'+box(0,0,1080,1920,bg)
# A: reference asymmetry, slanted heavy type, actual ribbon rather than concentric arcs.
s=start('#080808')+'<defs><linearGradient id="gold"><stop stop-color="#fff3b7"/><stop offset="1" stop-color="#c99a31"/></linearGradient></defs>'
for i in range(24):
 s+=f'<path d="M {-160+i*17} -60 C {80+i*23} 290 {-170+i*23} 295 {135+i*17} 625" fill="none" stroke="#c3a568" stroke-opacity="{.12+i*.008}" stroke-width="1.6"/>'
 s+=f'<path d="M {1040+i*9} 1220 C {300+i*21} 1240 {220+i*14} 1540 {1100+i*6} 1690" fill="none" stroke="#a48340" stroke-opacity=".38" stroke-width="1.8"/>'
s+=t(80,300,'从工具到协作',78,weight=900,extra='transform="translate(42 0) skewX(-8)"')
s+=t(170,407,'重新理解 AI 产品',90,'url(#gold)',900,extra='transform="translate(57 0) skewX(-8)"')
# No personal signature
s+=pic(0,605,1080,608)
s+=t(540,1308,'带有专家知识的智能体',57,'#fff',700,'middle',extra='font-style="italic"')
s+='</svg>'; (O/'T02.svg').write_text(s)
# B: warm interview, light large title, bold subheading, identity, large presenter and dedicated wordmark footer.
s=start('#543727')+'<defs><radialGradient id="brown"><stop stop-color="#967457"/><stop offset="1" stop-color="#42291f"/></radialGradient></defs>'+box(0,0,1080,1920,'url(#brown)')
for y in range(0,1920,8):s+=f'<path d="M0 {y}H1080" stroke="#d6af84" stroke-opacity=".025"/>'
s+=t(540,277,'从工具，走向协作',100,'#fff9ef',200,'middle')
s+=t(540,385,'AI 产品的下一种形态',67,'#f6d55d',700,'middle')
# No personal identity line
s+=pic(0,540,1080,920,'930 485 550 469')
s+=t(540,1390,'带有专家知识的智能体',54,'#fff',600,'middle',extra='stroke="#251b16" stroke-width="3" paint-order="stroke"')

s+='</svg>'; (O/'T05.svg').write_text(s)
# C: measured against first PPT reference: large headline, centered 16:9 slide, compact circular presenter.
s=start('#090e10')
for i in range(22):s+=f'<ellipse cx="540" cy="{-580+i*22}" rx="{650+i*60}" ry="{650+i*69}" fill="none" stroke="#77908d" stroke-opacity=".18" stroke-width="1.5"/>'
s+=t(540,340,'人跟机器的',90,'#fff',900,'middle').replace('x="540"','x="422"')+t(647,340,'协作',90,'#d9bf84',900)+t(827,340,'，',90,'#fff',900)+t(540,456,'有多少种可能',90,'#fff',900,'middle')
s+=t(540,572,'人机协作如何体现人的主体性？',46,'#d9bf84',700,'middle')+box(465,610,150,4,'#d9bf84')
s+=box(0,750,1080,608,'#eff6fa')+t(65,839,'重新理解艺术图像创作智能交互系统',42,'#23343c',700)
s+=t(65,890,'通过创作流程的深化，让表达、生成与编辑形成协作。',24,'#51616b',400)
for x,label,lines in [(95,'意图表达',['表达创作意图','匹配输入与输出']),(410,'一键生成',['根据任务生成','对比并调整结果']),(725,'智能编辑',['结合反馈修改','保留人的判断'])]:
 s+=box(x,984,250,82,'#cce4fa',41)+t(x+125,1038,label,38,'#203b4a',700,'middle')
 for j,line in enumerate(lines):s+=t(x+125,1130+j*35,line,24,'#536673',400,'middle')
s+='<defs><clipPath id="speaker"><circle cx="94" cy="1260" r="76"/></clipPath></defs><g clip-path="url(#speaker)">'+pic(18,1184,152,152,'980 480 380 380')+'</g><circle cx="94" cy="1260" r="76" fill="none" stroke="#d9bf84" stroke-width="4"/>'
brand='data:image/png;base64,'+base64.b64encode((P/'协作资料/品牌素材/造物云/设计系统原稿/zaowuyun-lockup.png').read_bytes()).decode()
s+=f'<image x="800" y="1260" width="220" height="76" href="{brand}"/>'
s+=t(540,1470,'有意图表达这四个字',62,'#fff',800,'middle')+t(540,1555,'我们又重新去理解',62,'#fff',800,'middle')+'</svg>'; (O/'T07.svg').write_text(s)
refs={'T02':'codex-clipboard-cf9637c6-6856-4eac-b726-a478908874f6.jpg','T05':'codex-clipboard-848446c5-68ff-44a6-8b9f-36eff696c3e1.jpg','T07':'codex-clipboard-71cc5ec7-bfd5-4283-8a6e-6b3414cc619d.png'}
notes={'T02':'黑金演讲：左上白字、下行金字错位；斜体粗字；贯穿上下的曲线带；横画面全宽。','T05':'暖棕访谈：细体大标题、粗体副标题、人物身份；大画面；底部手写感栏目字。','T07':'PPT讲解：两行大标题、金色问题；16:9材料区；左下圆形人物小窗；下方双行字幕。'}
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>参考复刻 · 三套重做</title><style>*{box-sizing:border-box}body{background:#eceeeb;color:#21362b;font:16px/1.7 system-ui;margin:0;padding:28px}header{max-width:1150px;margin:auto}h1{font-size:28px;margin:0}section{max-width:1150px;margin:36px auto 70px}h2{font-size:22px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px}figure{margin:0}img{display:block;width:100%;max-height:900px;object-fit:contain;object-position:top;background:#dce0db}figcaption{font-weight:650;margin-bottom:10px}.note{font-size:14px;color:#506156}a{color:inherit}@media(max-width:650px){body{padding:12px}.pair{gap:8px}h1{font-size:22px}}</style><header><h1>参考复刻 · 三套重做</h1><p>左边是你提供的参考，右边是重新制作的模板。对照标题比例、画面分区、底纹和署名位置。</p><p class="note">右侧为静态复刻样张；照片来自既有课程，文字与PPT为版式示例，不作为讲者原话。参考截图含平台界面，右侧不复制平台控件。</p></header>'''
for id,filename in refs.items():
 src=Path('/var/folders/q4/wh3_qyn50cj1nfbkl412yzxw0000gn/T')/filename
 shutil.copy2(src,O/('ref-'+id+src.suffix))
 page+=f'<section><h2>{notes[id]}</h2><div class="pair"><figure><figcaption>参考原图</figcaption><img src="ref-{id}{src.suffix}"></figure><figure><figcaption>重做样张 · {id}</figcaption><a href="{id}.svg"><img src="{id}.svg"></a></figure></div></section>'
page+='</html>'; (O/'index.html').write_text(page)
print('3 reference-specific templates and side-by-side review created')
