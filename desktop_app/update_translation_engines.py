"""Install provider support without changing saved credentials or archive records."""
import datetime
import hashlib
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

source=Path(__file__).resolve().parent
root=Path(r'D:\gallery-dl')
backup=root/'_推文归档/backups'/('translation-engines-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
files={
    '资料库/app.py':source/'app.py',
    '资料库/translation_settings.py':source/'translation_settings.py',
    '资料库/使用说明.md':source/'使用说明.md',
    'tools/translation_engine.py':source.parent/'local_archive/tools/translation_engine.py',
    'tools/deepl_translate.py':source.parent/'local_archive/tools/deepl_translate.py',
    'tools/tweet_archive.py':source.parent/'local_archive/tools/tweet_archive.py',
}
for value in files.values():
    if not value.is_file(): raise SystemExit('Missing prepared source file.')
def snapshot():
    with closing(sqlite3.connect((root/'_推文归档/tweets.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
        return hashlib.sha256(repr(db.execute('SELECT account,tweet_id,status,document FROM tweets ORDER BY account,tweet_id').fetchall()).encode()).hexdigest()
before=snapshot()
keypath=root/'tools/deepl.local.json'
keyhash=hashlib.sha256(keypath.read_bytes()).digest() if keypath.exists() else None
backup.mkdir(parents=True)
for relative,prepared in files.items():
    target=root/relative
    if target.exists():
        saved=backup/relative; saved.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(target,saved)
    temp=target.with_name(target.name+'.new')
    shutil.copy2(prepared,temp); temp.replace(target)
assert before==snapshot(),'Archive changed during installation; check backup.'
assert keyhash==(hashlib.sha256(keypath.read_bytes()).digest() if keypath.exists() else None),'DeepL configuration changed.'
print('Installed translation engines; archive and DeepL credentials unchanged.')
