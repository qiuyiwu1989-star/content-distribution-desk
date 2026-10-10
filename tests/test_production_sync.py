import argparse
import importlib.util
from pathlib import Path
import unittest
spec = importlib.util.spec_from_file_location('sync', Path(__file__).resolve().parents[1] / 'scripts/sync_production.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ProductionSyncTest(unittest.TestCase):
    def test_finished_only_and_no_implicit_versions(self):
        export, send = module.commands(argparse.Namespace(batch='example', only=None, pkg=None, account=None, apply=False))
        self.assertNotIn('--all', export)
        self.assertNotIn('--go', send)
        self.assertNotIn('--new-version', send)
    def test_explicit_apply_and_selection(self):
        export, send = module.commands(argparse.Namespace(batch='example', only='1,2', pkg='/tmp/package', account='target', apply=True))
        self.assertIn('--go', send)
        self.assertEqual(send[send.index('--only')+1], '1,2')
        self.assertEqual(export[export.index('--out')+1], '/tmp/package')
