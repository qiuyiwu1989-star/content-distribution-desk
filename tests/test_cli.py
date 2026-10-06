import contextlib
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path

from werkzeug.serving import make_server

from desk_cli import DeskClient, main
from server import create_app


class CLITests(unittest.TestCase):
    def test_local_only_and_draft_workflow(self):
        with self.assertRaises(ValueError):
            DeskClient('https://example.com')
        with tempfile.TemporaryDirectory() as temp:
            app = create_app(temp)
            server = make_server('127.0.0.1', 0, app)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = 'http://127.0.0.1:' + str(server.server_port)
                client = DeskClient(base)
                account = client.request('/api/accounts', 'POST', {'platform': 'zhihu', 'name': 'CLI 测试号'})['id']
                body_file = Path(temp) / 'body.md'
                body_file.write_text('CLI 测试正文', encoding='utf-8')
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(['--base', base, 'create-package', '--title', 'CLI 测试', '--body-file', str(body_file)]), 0)
                package = json.loads(output.getvalue())['id']
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(['--base', base, 'distribute', package, '--target', account + ':article']), 0)
                task = json.loads(output.getvalue())['created'][0]
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(['--base', base, 'preflight', task]), 0)
                self.assertTrue(json.loads(output.getvalue())['ok'])
                state = client.request('/api/state')
                self.assertEqual(next(x for x in state['tasks'] if x['id'] == task)['status'], 'draft')
                self.assertFalse(state['runs'])
            finally:
                server.shutdown()
                thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
