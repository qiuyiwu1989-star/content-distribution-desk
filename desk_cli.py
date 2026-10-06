#!/usr/bin/env python3
"""Local agent-facing CLI. Deliberately excludes dispatch, retry and publication."""
import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class DeskClient:
    def __init__(self, base='http://127.0.0.1:4318'):
        parsed = urllib.parse.urlparse(base)
        if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost'} or parsed.username or parsed.password or parsed.path not in {'', '/'}:
            raise ValueError('CLI 只能连接本机 HTTP 分发台')
        self.base = base.rstrip('/')
        self.token = None

    def request(self, path, method='GET', payload=None):
        headers = {'Accept': 'application/json'}
        data = None
        if method != 'GET':
            if self.token is None:
                with urllib.request.urlopen(self.base + '/', timeout=5) as response:
                    page = response.read().decode('utf-8')
                match = re.search(r'<meta name="desk-token" content="([^"]+)"', page)
                if not match:
                    raise ValueError('无法读取本机会话令牌')
                self.token = match.group(1)
            headers['X-Desk-Token'] = self.token
            headers['Content-Type'] = 'application/json'
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                detail = json.load(exc)
            except (ValueError, UnicodeError):
                detail = {}
            raise ValueError(f'HTTP {exc.code}: {detail.get("error", exc.reason)}') from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description='内容分发台本机 CLI；提交发布仍需在应用里确认')
    parser.add_argument('--base', default='http://127.0.0.1:4318')
    commands = parser.add_subparsers(dest='command', required=True)
    listing = commands.add_parser('list', help='列出本机记录')
    listing.add_argument('kind', choices=['packages', 'tasks', 'accounts', 'runs', 'site-imports'])
    imported = commands.add_parser('import-site', help='导入网站批准的 JSON 快照')
    imported.add_argument('file', type=Path)
    package = commands.add_parser('create-package', help='新建本地成品包')
    package.add_argument('--title', required=True)
    package.add_argument('--body-file', type=Path)
    package.add_argument('--notes', default='')
    distribute = commands.add_parser('distribute', help='为成品包建立渠道草稿任务')
    distribute.add_argument('package_id')
    distribute.add_argument('--target', action='append', required=True, metavar='ACCOUNT_ID:FORMAT')
    check = commands.add_parser('preflight', help='发布前检查；不提交执行')
    check.add_argument('task_id')
    args = parser.parse_args(argv)
    try:
        client = DeskClient(args.base)
        if args.command == 'list':
            result = client.request('/api/site-imports' if args.kind == 'site-imports' else '/api/state')
            result = result['items'] if args.kind == 'site-imports' else result[args.kind]
        elif args.command == 'import-site':
            if args.file.stat().st_size > 1024 * 1024:
                raise ValueError('快照文件超过 1 MB')
            result = client.request('/api/site-import', 'POST', json.loads(args.file.read_text(encoding='utf-8')))
        elif args.command == 'create-package':
            body = args.body_file.read_text(encoding='utf-8') if args.body_file else ''
            result = client.request('/api/packages', 'POST', {'title': args.title, 'body': body, 'notes': args.notes})
        elif args.command == 'distribute':
            targets = []
            for item in args.target:
                account_id, sep, fmt = item.partition(':')
                if not sep or not account_id or fmt not in {'article', 'gallery', 'video'}:
                    raise ValueError('--target 格式应为 ACCOUNT_ID:article|gallery|video')
                targets.append({'account_id': account_id, 'format': fmt})
            result = client.request('/api/packages/' + urllib.parse.quote(args.package_id, safe='') + '/distribute', 'POST', {'targets': targets})
        else:
            result = client.request('/api/tasks/' + urllib.parse.quote(args.task_id, safe='') + '/preflight')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, urllib.error.URLError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
