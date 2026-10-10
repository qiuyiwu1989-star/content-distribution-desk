"""Reusable local images; separate from per-publication assets."""
import json,uuid
from pathlib import Path
from flask import request,jsonify,send_file
from PIL import Image,UnidentifiedImageError

def install(app,data,db,get,fail,text,now):
 folder=Path(data)/'brand-assets';folder.mkdir(exist_ok=True)
 with db() as c:c.execute('CREATE TABLE IF NOT EXISTS brand_assets(id TEXT PRIMARY KEY,name TEXT NOT NULL,category TEXT NOT NULL,brand TEXT NOT NULL,tags TEXT NOT NULL,usage_note TEXT NOT NULL,mime TEXT NOT NULL,width INTEGER,height INTEGER,archived INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL)')
 categories={'logo','portrait','brand','other'}
 def serialize(row):
  a=dict(row);a['tags']=json.loads(a['tags']);a['url']='/api/brand-assets/'+a['id']+'/file';return a
 @app.get('/api/brand-assets')
 def brand_listing():
  category=request.args.get('category');q=request.args.get('q','').strip().casefold()
  with db() as c:rows=[serialize(r) for r in c.execute('SELECT * FROM brand_assets WHERE archived=? ORDER BY created DESC',(1 if request.args.get('archived')=='1' else 0,))]
  return jsonify(items=[a for a in rows if (not category or a['category']==category) and (not q or q in ' '.join([a['name'],a['brand'],*a['tags']]).casefold())])
 @app.post('/api/brand-assets')
 def brand_upload():
  f=request.files.get('file');d=request.form
  if not f:fail('请选择图片')
  category=d.get('category','other')
  if category not in categories:fail('请选择素材分类')
  name=text(d.get('name') or f.filename,200,True);brand=text(d.get('brand',''),200);note=text(d.get('usage_note',''),3000);tags=[x.strip() for x in text(d.get('tags',''),1000).replace('，',',').split(',') if x.strip()]
  aid=uuid.uuid4().hex;path=folder/aid;f.save(path)
  try:
   if path.stat().st_size>20*1024*1024:raise ValueError('图片最大20MB')
   with Image.open(path) as im:
    fmt=im.format;width,height=im.size;im.verify()
   mime={'PNG':'image/png','JPEG':'image/jpeg','WEBP':'image/webp'}.get(fmt)
   if not mime:raise ValueError('支持PNG、JPEG、WebP图片')
  except (OSError,ValueError,UnidentifiedImageError,Image.DecompressionBombError) as e:
   path.unlink(missing_ok=True);fail(str(e))
  with db() as c:c.execute('INSERT INTO brand_assets VALUES(?,?,?,?,?,?,?,?,?,0,?)',(aid,name,category,brand,json.dumps(tags,ensure_ascii=False),note,mime,width,height,now()))
  return jsonify(id=aid),201
 @app.get('/api/brand-assets/<aid>/file')
 def brand_file(aid):
  with db() as c:a=get(c,'brand_assets',aid)
  return send_file(folder/a['id'],mimetype=a['mime'],download_name=a['name'],as_attachment=False)
 @app.patch('/api/brand-assets/<aid>')
 def brand_edit(aid):
  d=request.get_json() or {}
  with db() as c:
   a=get(c,'brand_assets',aid);category=d.get('category',a['category'])
   if category not in categories:fail('请选择素材分类')
   archived=d.get('archived',bool(a['archived']))
   if type(archived) is not bool:fail('归档标记格式不正确')
   tags=d.get('tags',json.loads(a['tags']))
   if not isinstance(tags,list) or not all(isinstance(x,str) and len(x)<=100 for x in tags):fail('标签格式不正确')
   c.execute('UPDATE brand_assets SET name=?,category=?,brand=?,tags=?,usage_note=?,archived=? WHERE id=?',(text(d.get('name',a['name']),200,True),category,text(d.get('brand',a['brand']),200),json.dumps(tags,ensure_ascii=False),text(d.get('usage_note',a['usage_note']),3000),int(archived),aid))
  return jsonify(ok=True)
