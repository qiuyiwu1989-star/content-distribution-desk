import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from server import create_app
from skill_center import SkillCatalog


class SkillCenterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.skill = root / 'source'
        (self.skill / 'references').mkdir(parents=True)
        (self.skill / 'SKILL.md').write_text('---\nname: sample\ndescription: 真实技能\n---\n# 原始版本\n')
        (self.skill / 'references/evidence.md').write_text('原始经验')
        registry = root / 'sources.json'
        registry.write_text(json.dumps({'skills': [{'id': 'sample', 'label': '样例', 'path': str(self.skill)}]}))
        with patch('skill_center.SkillCatalog', return_value=SkillCatalog(registry)):
            self.client = create_app(root / 'data').test_client()
        token = re.search(r'name="desk-token" content="([^"]+)"', self.client.get('/').get_data(as_text=True)).group(1)
        self.headers = {'X-Desk-Token': token}
        self.pid = self.client.post('/api/packages', json={'title': '观点内容', 'body': '原声文字'}, headers=self.headers).json['id']
        self.payload = dict(skill_id='sample', skill_revision=self.client.get('/api/skills/sample').json['revision'], package_ids=[self.pid], instruction='制作候选样稿', idempotency_key='one-request')

    def post(self):
        return self.client.post('/api/skill-requests', json=self.payload, headers=self.headers)

    def test_updates_are_live_and_existing_jobs_keep_snapshot(self):
        saved = self.post().json
        before = self.client.get('/api/state').json
        (self.skill / 'references/evidence.md').write_text('新增的经验与修正')
        new = self.client.get('/api/skills/sample').json
        self.assertNotEqual(new['revision'], self.payload['skill_revision'])
        self.assertEqual(new['supporting_texts']['references/evidence.md'], '新增的经验与修正')
        snapshot = self.client.get('/api/skill-requests/' + saved['id']).json
        self.assertEqual(snapshot['context']['skill']['supporting_texts']['references/evidence.md'], '原始经验')
        self.assertEqual(self.post().json['id'], saved['id'])
        self.payload['idempotency_key'] = 'another-request'
        self.assertEqual(self.post().status_code, 409)
        after = self.client.get('/api/state').json
        for field in ['packages', 'assets', 'tasks']:
            self.assertEqual(before[field], after[field])

    def test_authorized_queue_and_claim_result_lifecycle(self):
        self.assertEqual(self.client.post('/api/skill-requests', json=self.payload).status_code, 403)
        saved = self.post().json
        route = '/api/skill-requests/' + saved['id'] + '/transition'
        running = self.client.post(route, json={'status': 'running', 'worker': 'agent-1'}, headers=self.headers)
        self.assertEqual(running.json['status'], 'running')
        self.assertEqual(self.client.post(route, json={'status': 'running', 'worker': 'agent-2'}, headers=self.headers).status_code, 409)
        self.assertEqual(self.client.post(route, json={'status': 'completed', 'worker': 'agent-2', 'summary': '完成'}, headers=self.headers).status_code, 409)
        done = self.client.post(route, json={'status': 'completed', 'worker': 'agent-1', 'summary': '输出方案，待用户选择'}, headers=self.headers)
        self.assertEqual(done.json['result']['summary'], '输出方案，待用户选择')

    def test_missing_source_does_not_silently_use_old_skill(self):
        (self.skill / 'SKILL.md').unlink()
        self.assertFalse(self.client.get('/api/skills').json['skills'][0]['available'])
        self.assertEqual(self.client.get('/api/skills/sample').status_code, 503)
        self.assertEqual(self.post().status_code, 503)


if __name__ == '__main__':
    unittest.main()
