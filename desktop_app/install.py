"""Install app and compatible video-aware archive scripts, with a rollback copy."""
import datetime
import json
import shutil
import sqlite3
import sys
from pathlib import Path

source = Path(__file__).resolve().parent
root = Path(sys.argv[1] if len(sys.argv) > 1 else r'D:\gallery-dl')
backup = root / '_推文归档/backups' / ('desktop-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
database = root / '_推文归档/tweets.sqlite'
with sqlite3.connect(database) as original, sqlite3.connect(backup / 'tweets.sqlite') as target:
    original.backup(target)
for name in ('tweet_archive.py', 'deepl_translate.py', 'tweet_archive_view.html', 'update.ps1'):
    shutil.copy2(root / 'tools' / name, backup / name)
    shutil.copy2(source.parent / 'local_archive/tools' / name, root / 'tools' / name)
destination = root / '资料库'
destination.mkdir(exist_ok=True)
for name in ('app.py', 'library.py', 'video_posters.py', '使用说明.md'):
    shutil.copy2(source / name, destination / name)
(root / '推文资料库.cmd').write_text('@echo off\nstart "" "%~dp0python\\pythonw.exe" "%~dp0资料库\\app.py" --root "%~dp0."\n', encoding='gbk')
print(json.dumps(dict(installed=str(destination), backup=str(backup)), ensure_ascii=False))
