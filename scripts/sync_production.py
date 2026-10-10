#!/usr/bin/env python3
"""Export finished production items and send them through the established importer."""
import argparse
from pathlib import Path
import subprocess
import sys


def commands(args):
    toolkit = Path(__file__).resolve().parents[2] / '协作资料/工具/审阅工作台'
    export = [sys.executable, str(toolkit / '导出发布包.py'), '--batch', args.batch]
    send = [sys.executable, str(toolkit / '导入分发台.py'), '--batch', args.batch]
    if args.only:
        export += ['--only', args.only]
        send += ['--only', args.only]
    else:
        # Never use export --all: it includes unfinished/unreviewed production.
        send += ['--all']
    if args.pkg:
        export += ['--out', args.pkg]
        send += ['--pkg', args.pkg]
    if args.account:
        send += ['--account', args.account]
    if args.apply:
        send += ['--go']
    return export, send


def main():
    parser = argparse.ArgumentParser(description='更新已完成内容的发布包并同步分发台；默认仅预演导入，不写分发库。')
    parser.add_argument('--batch', required=True)
    parser.add_argument('--only', help='只同步这些序号，逗号分隔')
    parser.add_argument('--pkg', help='指定发布包目录')
    parser.add_argument('--account', help='目标账号名称；省略沿用生产导入器配置')
    parser.add_argument('--apply', action='store_true', help='执行同步；重复回执由导入器跳过，禁止隐式另建版本')
    args = parser.parse_args()
    for command in commands(args):
        subprocess.run(command, check=True)


if __name__ == '__main__':
    main()
