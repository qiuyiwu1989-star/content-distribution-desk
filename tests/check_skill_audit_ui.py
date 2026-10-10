"""Run with .sau-venv/bin/python; all edits use temporary test data."""
import json
from pathlib import Path
import subprocess
import sys
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
FIXTURE="""
import json,sys,tempfile,threading
from pathlib import Path
from unittest.mock import patch
from werkzeug.serving import make_server
from server import create_app
from skill_center import SkillCatalog
with tempfile.TemporaryDirectory(prefix='skill-audit-ui-') as tmp:
 root=Path(tmp); source=root/'sample';source.mkdir()
 (source/'SKILL.md').write_text('---\\nname: sample\\n---\\n# Original rule\\n')
 reg=root/'registry.json';reg.write_text(json.dumps({'skills':[dict(id='sample',label='Audit Sample',hint='Test fixture',path=str(source))]}))
 with patch('skill_center.SkillCatalog',return_value=SkillCatalog(reg)): app=create_app(root/'data')
 server=make_server('127.0.0.1',0,app,threaded=True)
 worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
 print('http://127.0.0.1:'+str(server.server_port),flush=True)
 try: sys.stdin.readline()
 finally: server.shutdown();worker.join();server.server_close()
"""

def run():
 out=ROOT/'artifacts/skill-versioning-20261009-212014'
 with (out/'ui-fixture.log').open('w') as log:
  process=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-c',FIXTURE],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True)
  try:
   url=process.stdout.readline().strip();assert url.startswith('http://127.0.0.1:'),url
   with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1000})
    errors=[]
    def editor():
     page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto(url+'/#skill-center',wait_until='domcontentloaded')
     page.locator('[data-skill-history="sample"]').click()
     page.locator('[data-skill-edit="sample"]').click()
     page.locator('#skill-edit-form').wait_for()
     return page
    a=editor();b=editor()
    for page,content in [(a,'# Revised rule\n'),(b,'# Stale draft\n')]:
     page.locator('[name="actor_name"]').fill('UI Test Agent')
     page.locator('[name="actor_type"]').select_option('agent')
     page.locator('[name="reason"]').fill('Preserve conditions in the rule')
     page.locator('[name="source_ref"]').fill('isolated-ui-fixture')
     page.locator('[name="content"]').fill(content)
    a.locator('#skill-edit-form button[type="submit"]').click()
    a.locator('.skill-audit-summary').wait_for()
    assert 'v2' in a.locator('.skill-audit-summary').inner_text()
    assert 'UI Test Agent' in a.locator('.skill-audit-summary').inner_text()
    a.locator('.skill-audit-file summary').first.click()
    assert '+# Revised rule' in a.locator('.skill-audit-code').first.inner_text()
    b.locator('#skill-edit-form button[type="submit"]').click()
    b.locator('.form-error').filter(has_text='版本已变化').wait_for()
    assert b.locator('[name="content"]').input_value()=='# Stale draft\n'
    a.locator('[data-skill-integrity]').click()
    a.locator('[data-skill-integrity]').filter(has_text='校验通过').wait_for()
    a.screenshot(path=str(out/'fixture-edit-diff.png'),full_page=True)
    a.set_viewport_size({'width':390,'height':844})
    assert not a.evaluate('document.documentElement.scrollWidth>innerWidth')
    a.screenshot(path=str(out/'fixture-edit-mobile.png'),full_page=True)
    h=context.request.get(url+'/api/skills/sample/history').json()
    assert len(h['versions'])==2
    assert not errors,errors
    browser.close()
   (out/'ui-verification.json').write_text(json.dumps(dict(managed_edit=True,author_and_reason=True,diff=True,stale_draft_preserved=True,integrity_button=True,mobile_no_overflow=True,page_errors=errors,isolated_fixture=True),indent=2))
   print('PASS: attributed save, version diff, stale edit rejection, retained draft, integrity and mobile layout')
  finally:
   if process.poll() is None:process.communicate('\n',timeout=10)
   assert process.returncode==0,process.returncode

if __name__=='__main__':run()
