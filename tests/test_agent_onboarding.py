import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from flask import Flask, abort
from agent_onboarding import install
from skill_center import SkillCatalog


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        rows = []
        for sid in ['platform-onboarding', 'editing', 'review']:
            path = self.root / sid
            path.mkdir()
            (path / 'SKILL.md').write_text('# ' + sid)
            rows.append(dict(id=sid, label=sid, path=str(path)))
        (self.root / 'editing/SKILL.md').write_text('[review](../review/SKILL.md)')
        (self.root / 'review/SKILL.md').write_text('[editing](../editing/SKILL.md)')
        registry = self.root / 'registry.json'
        registry.write_text(json.dumps(dict(skills=rows)))
        app = Flask(__name__)
        install(app, SkillCatalog(registry), lambda msg, code=400: abort(code, description=msg))
        self.client = app.test_client()

    def test_bootstrap_contains_current_policy_and_resources(self):
        data = self.client.get('/api/agent/bootstrap').json
        self.assertTrue(data['read_only'])
        self.assertEqual(len(data['resources']), 6)
        self.assertEqual(data['policy']['content'], '# platform-onboarding')

    def test_dependencies_cycle_and_honest_readiness(self):
        data = self.client.get('/api/agent/preflight?skills=editing').json
        self.assertEqual({x['id'] for x in data['skills']}, {'editing', 'review'})
        self.assertEqual(data['resource_status'], 'ready')
        self.assertIsNone(data['execution_ready'])
        self.assertEqual(data['media_review'], 'not_performed')

    def test_empty_and_unknown_not_ready(self):
        for query in ['', '?skills=unknown']:
            self.assertEqual(self.client.get('/api/agent/preflight' + query).json['resource_status'], 'needs_attention')

    def test_missing_dependency_not_ready(self):
        (self.root / 'review/SKILL.md').unlink()
        data = self.client.get('/api/agent/preflight?skills=editing').json
        self.assertEqual(data['unavailable'], ['review'])
        self.assertEqual(data['resource_status'], 'needs_attention')

    def test_policy_changes_are_live(self):
        before = self.client.get('/api/agent/bootstrap').json['policy']['revision']
        (self.root / 'platform-onboarding/SKILL.md').write_text('changed')
        self.assertNotEqual(before, self.client.get('/api/agent/bootstrap').json['policy']['revision'])

    def test_missing_policy_is_failure(self):
        (self.root / 'platform-onboarding/SKILL.md').unlink()
        self.assertEqual(self.client.get('/api/agent/bootstrap').status_code, 503)

    def test_reject_path_and_long_request(self):
        for ids in ['../review', ','.join(['review'] * 33)]:
            self.assertEqual(self.client.get('/api/agent/preflight', query_string={'skills': ids}).status_code, 400)

    def test_gets_do_not_change_files(self):
        def snapshot():
            return {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        before = snapshot()
        self.client.get('/api/agent/bootstrap')
        self.client.get('/api/agent/preflight?skills=editing')
        self.assertEqual(before, snapshot())


class MCPOnboardingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'mcp'))
        import desk_mcp
        cls.bridge = desk_mcp

    def test_handshake_instructions_and_tools(self):
        value = self.bridge.respond({'method': 'initialize', 'params': {}})
        self.assertIn('desk_agent_bootstrap', value['instructions'])
        names = [x['name'] for x in self.bridge.TOOLS]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn('desk_agent_preflight', names)

    def test_scoped_preflight_route(self):
        with patch.object(self.bridge, 'DeskClient') as client:
            self.bridge.call('desk_agent_preflight', {'skill_ids': ['course-video-editing']})
            client.return_value.request.assert_called_once_with('/api/agent/preflight?skills=course-video-editing')

    def test_bad_preflight_rejected_before_request(self):
        with patch.object(self.bridge, 'DeskClient') as client:
            for ids in [None, 'editing', ['../escape'], [1]]:
                with self.assertRaises(ValueError):
                    self.bridge.call('desk_agent_preflight', {'skill_ids': ids})
            client.assert_not_called()

    def test_case_kind_rejected(self):
        with self.assertRaises(ValueError):
            self.bridge.call('desk_find_cases', {'kind': 'other'})

    def test_cover_uses_current_skill_and_filtered_catalog(self):
        with patch.object(self.bridge, 'DeskClient') as client:
            client.return_value.request.side_effect = [
                {'templates': []}, {'content': 'current', 'revision': 'revision', 'source_path': 'canonical'}]
            value = self.bridge.call('desk_cover_templates', {})
            self.assertEqual(value['skill_text'], 'current')
            self.assertEqual(value['skill_revision'], 'revision')
            self.assertEqual(client.return_value.request.call_args_list[0].args[0], '/api/cover-design/catalog')


if __name__ == '__main__':
    unittest.main()
