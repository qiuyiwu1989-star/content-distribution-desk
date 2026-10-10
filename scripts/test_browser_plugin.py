#!/usr/bin/env python3
"""Run the Channels extension's deterministic logic and release regression suite."""
import argparse,subprocess,sys,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--node',default=shutil.which('node'));args=parser.parse_args()
 if not args.node:parser.error('Provide --node /absolute/path/to/node')
 tests=sorted((ROOT/'tests').glob('test_channels*.cjs'))+sorted((ROOT/'extensions/channels-assistant/tests').glob('*.cjs'))
 for path in tests:
  result=subprocess.run([args.node,str(path)],cwd=ROOT,capture_output=True,text=True)
  print(('PASS ' if result.returncode==0 else 'FAIL ')+str(path.relative_to(ROOT)),flush=True)
  if result.returncode:print(result.stdout+result.stderr);return result.returncode
 for path in sorted((ROOT/'extensions/channels-assistant').glob('*.js')):
  result=subprocess.run([args.node,'--check',str(path)],cwd=ROOT)
  if result.returncode:return result.returncode
 result=subprocess.run([sys.executable,'-m','unittest','tests.test_browser_plugin_releases','tests.test_channel_observations'],cwd=ROOT)
 if result.returncode:return result.returncode
 print(f'PASS {len(tests)} Node groups, JavaScript syntax, 9 Python tests. Platform UI was not exercised.')
 return 0
if __name__=='__main__':raise SystemExit(main())
