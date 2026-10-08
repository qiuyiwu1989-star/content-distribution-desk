import ast
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from scripts.patch_channels_uploader import DRAFT_BRANCH, patch

class Button:
    def __init__(self, enabled): self.first=self;self.enabled=enabled;self.clicks=0
    async def wait_for(self, **kwargs): pass
    async def is_enabled(self): return self.enabled
    async def click(self, **kwargs): self.clicks+=1

class Message:
    def __init__(self, visible): self.first=self;self.visible=visible
    async def count(self): return int(self.visible)
    async def is_visible(self): return self.visible

class DraftTests(unittest.TestCase):
    def test_one_shot_submission_and_diagnostics(self):
        async def sleep(_): pass
        source='async def submit(self, page):\n    is_draft = True\n'+DRAFT_BRANCH
        # Branch belongs to a class method; remove four spaces to execute independently.
        source='async def submit(self, page):\n    is_draft = True\n'+'\n'.join(line[4:] for line in DRAFT_BRANCH.splitlines())
        ns={'asyncio':SimpleNamespace(sleep=sleep),'tencent_logger':SimpleNamespace(success=lambda *_:None)}
        exec(compile(source,'draft-branch','exec'),ns)
        async def scenario():
            for enabled,confirmed,clicks,reason in [(False,False,0,'disabled'),(True,False,1,'unconfirmed'),(True,True,1,None)]:
                button=Button(enabled);evidence=[]
                async def diagnostic(page,code,submitted):evidence.append((code,submitted))
                uploader=SimpleNamespace(desk_draft_diagnostic=diagnostic)
                page=SimpleNamespace(get_by_role=lambda *a,**k:button,get_by_text=lambda *a,**k:Message(confirmed))
                if confirmed: await ns['submit'](uploader,page)
                else:
                    with self.assertRaises(RuntimeError): await ns['submit'](uploader,page)
                self.assertEqual(button.clicks,clicks)
                self.assertEqual(evidence,[] if reason is None else [(reason,bool(clicks))])
        asyncio.run(scenario())

    def test_patch_is_idempotent_and_requires_personal_view(self):
        fixture='''import os
from pathlib import Path
class Uploader:
    async def apply_original_statement(self, page):
        label_text = getattr(self, "content_label", None) or "含AI生成内容"
    async def submit_publish(self, page: Page) -> None:
        is_draft = getattr(self, "is_draft", False)
        # 先等待并清理遮罩
        pass
'''
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'main.py';path.write_text(fixture)
            self.assertTrue(patch(path));self.assertFalse(patch(path))
            ast.parse(path.read_text());self.assertIn('or "个人观点"',path.read_text())
