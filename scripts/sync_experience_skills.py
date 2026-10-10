"""Regenerate static/experience-summary.json from its workspace-owned source skill.

正本：content-distribution-desk/skills/experience-summary/{SKILL.md,references/*}
产物：content-distribution-desk/static/experience-summary.json（装机 App 只带 static/）

与 scripts/sync_creative_library.py 同一范式：只在工作区里读正本、只写一个派生文件。
skill / lessons / mcp 三个字段逐字来自正本，界面上看到的就是文件里的内容；
skills 段是只读清单，用来说明本机技能散落在哪几处（不驱动界面）。

用法：
    在 content-distribution-desk/ 下执行
    python3 scripts/sync_experience_skills.py            # 重新生成
    python3 scripts/sync_experience_skills.py --check    # 只比对，漂移则退出码 1
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]              # 邱懿武03/
DESK = ROOT / 'content-distribution-desk'
SRC = DESK / 'skills' / 'experience-summary'            # 正本目录
OUT = DESK / 'static' / 'experience-summary.json'       # 派生产物

FIELDS = {
    'skill': SRC / 'SKILL.md',
    'lessons': SRC / 'references' / 'lessons.md',
    'mcp': SRC / 'references' / 'mcp.md',
}
# 本机技能的存放处：工作区（正本）与全局目录（部分是指回工作区的软链）
SKILL_HOMES = [(ROOT / '协作资料' / '技能', '工作区'), (Path.home() / '.agents' / 'skills', '全局')]


def sha12(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]


def frontmatter(text, key):
    """取 SKILL.md 头部 --- 之间的 key: value。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != '---':
        return ''
    for line in lines[1:]:
        if line.strip() == '---':
            break
        if line.startswith(key + ':'):
            return line.split(':', 1)[1].strip()
    return ''


def heading(text):
    for line in text.splitlines():
        if line.startswith('# '):
            return line[2:].strip()
    return ''


def label(path):
    """把绝对路径写成 ~/... 或工作区相对路径，便于人读。"""
    path = Path(path)
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        home = Path.home()
        try:
            return '~/' + str(path.relative_to(home))
        except ValueError:
            return str(path)


def inventory():
    """只读清点本机技能，不移动任何文件。软链记录它实际指向哪里。"""
    rows = []
    for home, where in SKILL_HOMES:
        if not home.is_dir():
            continue
        for entry in sorted(home.iterdir()):
            md = entry / 'SKILL.md'
            if not md.is_file():
                continue
            try:
                text = md.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                continue
            refs = entry / 'references'
            row = {
                'name': frontmatter(text, 'name') or entry.name,
                'description': frontmatter(text, 'description'),
                'home': where,
                'path': label(entry),
                'lines': text.count('\n') + 1,
                'sha256': sha12(text),
            }
            if entry.is_symlink():
                row['symlink'] = label(os.path.realpath(entry))
            if refs.is_dir():
                row['references'] = len([p for p in refs.rglob('*') if p.is_file()])
            rows.append(row)
    return rows


def build():
    missing = [str(p) for p in FIELDS.values() if not p.is_file()]
    if missing:
        raise SystemExit('正本缺失，拒绝生成半份产物：\n  ' + '\n  '.join(missing))
    bundle = {k: p.read_text(encoding='utf-8') for k, p in FIELDS.items()}
    return {
        'name': heading(bundle['skill']) or '经验总结',
        'skill': bundle['skill'],
        'lessons': bundle['lessons'],
        'mcp': bundle['mcp'],
        'skills': inventory(),
        'sources': {
            **{k: label(p) for k, p in FIELDS.items()},
            'skill_homes': [label(home) for home, _ in SKILL_HOMES],
        },
    }


def render(bundle):
    return json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def main():
    ap = argparse.ArgumentParser(description='从正本重新生成 experience-summary.json')
    ap.add_argument('--check', action='store_true', help='只比对，不写；漂移时退出码 1')
    args = ap.parse_args()

    fresh = render(build())

    if args.check:
        on_disk = OUT.read_text(encoding='utf-8') if OUT.is_file() else ''
        if on_disk == fresh:
            print('✓ 产物与正本一致：%s' % label(OUT))
            return 0
        old = json.loads(on_disk) if on_disk.strip() else {}
        new = json.loads(fresh)
        drifted = sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))
        print('✗ 产物已过期：%s' % label(OUT))
        print('  不一致字段：%s' % ', '.join(drifted))
        print('  正本在 %s，跑一次不带 --check 即可同步。' % label(SRC))
        return 1

    if OUT.is_file() and OUT.read_text(encoding='utf-8') == fresh:
        print('✓ 无需改动，产物已是最新：%s' % label(OUT))
        return 0
    OUT.write_text(fresh, encoding='utf-8')
    inv = json.loads(fresh)['skills']
    print('已从正本重新生成 %s' % label(OUT))
    print('  skill %d 字符 ｜ lessons %d 字符 ｜ mcp %d 字符'
          % (len(json.loads(fresh)['skill']), len(json.loads(fresh)['lessons']), len(json.loads(fresh)['mcp'])))
    print('  技能清单 %d 条（只读，未移动任何文件）：' % len(inv))
    for row in inv:
        mark = '→ ' + row['symlink'] if row.get('symlink') else ''
        print('    [%s] %-30s %4d 行  %s%s' % (row['home'], row['name'], row['lines'], row['path'], ('  ' + mark) if mark else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
