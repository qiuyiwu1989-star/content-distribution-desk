"""Versioned deterministic layout documents shared by UI and local agents."""
import json, math, re, uuid
from flask import request, jsonify

def validate(d):
    if not isinstance(d,dict) or d.get('schema')!='desk-layout.v1': raise ValueError('模板格式应为 desk-layout.v1')
    if not re.fullmatch(r'T(?:0[1-9]|1[0-2])',str(d.get('base',''))): raise ValueError('请选择首批 12 套模板')
    if not isinstance(d.get('name'),str) or not 1<=len(d['name'])<=120: raise ValueError('请填写模板名称（最多120字）')
    layers=d.get('layers')
    if not isinstance(layers,list) or len(layers)>150: raise ValueError('图层最多150个')
    seen=set()
    for l in layers:
        if not isinstance(l,dict) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,70}',str(l.get('id',''))) or l['id'] in seen: raise ValueError('图层编号无效或重复')
        seen.add(l['id'])
        if l.get('kind') not in ['source','text','subtitle','image']: raise ValueError('图层类型无效')
        if l['kind']=='source' and (type(l.get('index')) is not int or not 0<=l['index']<150): raise ValueError('来源图层无效')
        for k,lo,hi in [('x',-10000,10000),('y',-10000,10000),('scale',.01,20),('width',1,10000),('height',1,10000),('fontSize',1,500),('opacity',0,1)]:
            if k in l and (type(l[k]) not in [int,float] or not math.isfinite(l[k]) or not lo<=l[k]<=hi): raise ValueError(k+' 超出有效范围')
        for k in ['fill','stroke']:
            if k in l and not re.fullmatch(r'#[0-9a-fA-F]{6}',l[k]): raise ValueError('颜色应为六位十六进制')
        if 'hidden' in l and type(l['hidden']) is not bool: raise ValueError('隐藏状态无效')
        if 'weight' in l and l['weight'] not in [400,700,900]: raise ValueError('字重无效')
        if 'label' in l and (not isinstance(l['label'],str) or len(l['label'])>200): raise ValueError('图层名称无效')
        if 'text' in l and (not isinstance(l['text'],str) or len(l['text'])>5000): raise ValueError('文字最多5000字')
        if 'font' in l and l['font'] not in ['smiley-sans','harmonyos-sans','alimama-shuhei','alibaba-puhuiti','source-han-sans','source-han-serif']: raise ValueError('字体不在字体库中')
        if 'src' in l and not re.fullmatch(r'(?:/api/brand-assets/[a-f0-9]{32}/file|/static/creative/logos/[a-zA-Z0-9_-]+\.(?:png|svg))',l['src']): raise ValueError('图片请从品牌与个人素材库选择')
    return d

def install(app,db,fail,now):
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS layout_documents(id TEXT PRIMARY KEY,document TEXT NOT NULL,revision INTEGER NOT NULL,updated TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS layout_history(id TEXT,revision INTEGER,document TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(id,revision))')
    @app.get('/api/layouts')
    def layouts():
        with db() as c: rows=c.execute('SELECT * FROM layout_documents ORDER BY updated DESC').fetchall()
        return jsonify(items=[dict(id=r['id'],name=json.loads(r['document'])['name'],revision=r['revision'],updated=r['updated']) for r in rows])
    @app.get('/api/layouts/<lid>')
    def read_layout(lid):
        with db() as c:r=c.execute('SELECT * FROM layout_documents WHERE id=?',(lid,)).fetchone()
        if not r:fail('模板不存在',404)
        return jsonify(id=lid,document=json.loads(r['document']),revision=r['revision'],updated=r['updated'])
    @app.post('/api/layouts')
    def create_layout():return write(None)
    @app.put('/api/layouts/<lid>')
    def update_layout(lid):return write(lid)
    def write(lid):
        body=request.get_json() or {}
        if not isinstance(body,dict):fail('请求应为对象',400)
        try:d=validate(body.get('document'))
        except (ValueError,TypeError) as e:fail(str(e),400)
        encoded=json.dumps(d,ensure_ascii=False)
        if len(encoded)>1000000:fail('模板数据过大',400)
        with db() as c:
            c.execute('BEGIN IMMEDIATE');old=c.execute('SELECT * FROM layout_documents WHERE id=?',(lid,)).fetchone() if lid else None
            if lid and not old:fail('模板不存在',404)
            if old and (type(body.get('revision')) is not int or body['revision']!=old['revision']):fail('模板已被其他编辑更新，请导出当前 JSON 后重新打开，避免覆盖',409)
            lid=lid or uuid.uuid4().hex;rev=old['revision']+1 if old else 1;stamp=now()
            c.execute('INSERT INTO layout_documents VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET document=excluded.document,revision=excluded.revision,updated=excluded.updated',(lid,encoded,rev,stamp))
            c.execute('INSERT INTO layout_history VALUES(?,?,?,?)',(lid,rev,encoded,stamp))
        return jsonify(id=lid,revision=rev,updated=stamp,document=d)
