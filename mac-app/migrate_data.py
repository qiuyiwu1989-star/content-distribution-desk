"""One-time move to a stable Mac application data location; never overwrite live data."""
import os
import shutil
import sqlite3
from pathlib import Path

project=Path(os.environ['PROJECT_PATH'])
old=project/'data'
new=Path.home()/'Library/Application Support/内容分发台/data'
new.mkdir(parents=True,exist_ok=True)
new.chmod(0o700)
if (new/'desk.sqlite3').exists():
    print('Existing app data retained')
else:
    db=old/'desk.sqlite3'
    if db.exists():
        with sqlite3.connect(db) as source, sqlite3.connect(new/'desk.sqlite3') as destination:
            source.backup(destination)
    for name in ('files','bridge-secret.json'):
        origin=old/name
        if origin.is_dir():shutil.copytree(origin,new/name,dirs_exist_ok=True)
        elif origin.exists():shutil.copy2(origin,new/name)
    print('Existing desk data copied to application support')
