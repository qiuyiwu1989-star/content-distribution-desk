from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import subprocess, sys, tempfile

target=Path(sys.argv[1]);iconset=target.parent/'DistributionDesk.iconset';iconset.mkdir(exist_ok=True)
base=Image.new('RGBA',(1024,1024),(0,0,0,0));draw=ImageDraw.Draw(base)
draw.rounded_rectangle((75,75,949,949),radius=210,fill='#284b40')
font_path='/System/Library/Fonts/PingFang.ttc'
try:font=ImageFont.truetype(font_path,560)
except OSError:font=ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',560)
draw.text((512,495),'分',font=font,fill='#f9fbf7',anchor='mm')
for n in (16,32,128,256,512):
    base.resize((n,n),Image.Resampling.LANCZOS).save(iconset/f'icon_{n}x{n}.png')
    base.resize((n*2,n*2),Image.Resampling.LANCZOS).save(iconset/f'icon_{n}x{n}@2x.png')
subprocess.run(['/usr/bin/iconutil','-c','icns',str(iconset),'-o',str(target)],check=True)
import shutil
shutil.rmtree(iconset)
