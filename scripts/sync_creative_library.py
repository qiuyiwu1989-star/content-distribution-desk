"""Refresh local previews and role profiles from their workspace-owned sources."""
import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[2]
out = root / 'content-distribution-desk/static/creative'
templates = json.loads((root / '短视频设计模板库/v1/templates.json').read_text())
editors = json.loads((root / '协作资料/技能/course-video-editing/profiles/editors/library.json').read_text())
for folder in ['previews', 'covers']:
    (out / folder).mkdir(parents=True, exist_ok=True)
for item in templates['templates']:
    item['preview'] = '/static/creative/previews/' + item['id'] + '.png'
    shutil.copy2(root / '短视频设计模板库/v1/previews' / (item['id'] + '.png'), out / 'previews' / (item['id'] + '.png'))
# Preserve the authored v2 composition set when refreshing legacy sources.
initial_path = out / 'initial-set/templates.json'
if initial_path.exists():
    initial = json.loads(initial_path.read_text())['templates']
    initial_ids = {x['id'] for x in initial}
    templates['templates'] = initial + [x for x in templates['templates'] if x['id'] not in initial_ids]
covers = []
for key, name in [('A', '黑金曲线'), ('B', '深绿观点'), ('C', '科技蓝图')]:
    shutil.copy2(root / '课程剪辑-20260915-101753/covers/C011/方案样张' / (key + '.png'), out / 'covers' / (key + '.png'))
    covers.append(dict(id='COVER-' + key, name=name, version='concept-01', preview='/static/creative/covers/' + key + '.png', use='课程观点封面', status='design-candidate', sample_clip='C011', size=[900, 1200]))
cover_design = out.parent / 'cover-design/catalog.json'
if cover_design.exists():
    new_covers = json.loads(cover_design.read_text())['templates']
    known = {x['id'] for x in new_covers}
    covers = [x for x in covers if x['id'] not in known] + new_covers
catalog = dict(schema='desk-creative-catalog.v1', templates=templates['templates'], editors=editors['editors'], coordinator=editors['coordinator'], invariants=editors['invariants'], covers=covers, sources={'templates': '短视频设计模板库/v1/templates.json', 'editors': '协作资料/技能/course-video-editing/profiles/editors/library.json'})
(out / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2))
print('Synced 6 templates, 5 editors and 3 cover concepts')
