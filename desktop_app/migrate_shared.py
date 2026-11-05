"""Back up original data, then reopen old excluded media with the new classifier."""
import datetime
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

source = Path(__file__).resolve().parent.parent
root = Path(r'D:\gallery-dl')
backup = root / '_推文归档/backups' / ('shared-posts-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
with closing(sqlite3.connect((root / '_推文归档/tweets.sqlite').as_uri() + '?mode=ro', uri=True)) as old:
    with closing(sqlite3.connect(backup / 'tweets.sqlite')) as new:
        old.backup(new)
for name in ('tweet_archive.py', 'tweet_archive_view.html', 'update.ps1'):
    shutil.copy2(root / 'tools' / name, backup / name)
    if name != 'update.ps1':
        temp = root / 'tools' / (name + '.new')
        shutil.copy2(source / 'local_archive/tools' / name, temp)
        temp.replace(root / 'tools' / name)
print('Backup: ' + str(backup), flush=True)
