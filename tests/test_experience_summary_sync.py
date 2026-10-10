"""经验产物必须与正本一致。

正本：content-distribution-desk/skills/experience-summary/
产物：content-distribution-desk/static/experience-summary.json

界面读产物里的 skill / lessons / mcp；正本改了而产物没同步，就是"改一处、界面还是旧的"。
这个测试把那种漂移变成红灯。产物由 scripts/sync_experience_skills.py 生成，测试不写任何文件。
"""
import importlib.util
import json
import unittest
from pathlib import Path

DESK = Path(__file__).resolve().parents[1]
MODULE_PATH = DESK / 'scripts' / 'sync_experience_skills.py'
UI_FIELDS = ('name', 'skill', 'lessons', 'mcp')


def load_module():
    spec = importlib.util.spec_from_file_location('sync_experience_skills', MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExperienceSummarySyncTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()
        self.bundle = json.loads(self.mod.OUT.read_text(encoding='utf-8'))

    def test_artifact_matches_source(self):
        fresh = self.mod.render(self.mod.build())
        on_disk = self.mod.OUT.read_text(encoding='utf-8')
        self.assertEqual(
            on_disk, fresh,
            'experience-summary.json 与正本漂移；跑 python3 scripts/sync_experience_skills.py 同步')

    def test_ui_fields_present(self):
        for key in UI_FIELDS:
            self.assertTrue(self.bundle.get(key), '界面要读的字段 %s 不能为空' % key)

    def test_source_files_exist(self):
        for key, path in self.mod.FIELDS.items():
            self.assertTrue(path.is_file(), '正本缺失：%s（%s）' % (path, key))

    def test_inventory_rows_are_honest(self):
        rows = self.bundle['skills']
        self.assertGreaterEqual(len(rows), 4, '技能清单至少应含工作区里的几个')
        for row in rows:
            for field in ('name', 'path', 'home', 'sha256'):
                self.assertTrue(row.get(field), '清单行缺 %s：%r' % (field, row))
            if row['path'].startswith('~/'):
                continue  # 全局项只登记，不在这里复算哈希
            skill_md = self.mod.ROOT / row['path'] / 'SKILL.md'
            self.assertTrue(skill_md.is_file(), '清单指向的 SKILL.md 不存在：%s' % skill_md)
            self.assertEqual(
                row['sha256'], self.mod.sha12(skill_md.read_text(encoding='utf-8')),
                '清单里的哈希与文件不符：%s' % row['path'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
