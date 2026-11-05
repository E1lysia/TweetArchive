"""Install the browsing update without changing downloader, accounts or archive documents."""
import datetime
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

source = Path(__file__).resolve().parent
root = Path(r'D:\gallery-dl')
destination = root / '资料库'
backup = root / '_推文归档/backups' / ('desktop-ui-v2-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
for name in ('app.py', 'library.py', 'video_posters.py', '使用说明.md'):
    shutil.copy2(destination / name, backup / name)
    shutil.copy2(source / name, destination / name)
state = root / '_推文归档/manager.sqlite'
if state.exists():
    with closing(sqlite3.connect(state.as_uri() + '?mode=ro', uri=True)) as old:
        with closing(sqlite3.connect(backup / 'manager.sqlite')) as new:
            old.backup(new)
print('Updated. Backup: ' + str(backup))
