"""Ensure the desktop migration preserved every preexisting original and translation."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

root = Path(r'D:\gallery-dl')
backups = sorted((root / '_推文归档/backups').glob('desktop-*/tweets.sqlite'))
before = backups[0]
with closing(sqlite3.connect(before.as_uri() + '?mode=ro', uri=True)) as db:
    old = {(a, i): json.loads(d) for a, i, d in db.execute('SELECT account,tweet_id,document FROM tweets')}
with closing(sqlite3.connect((root / '_推文归档/tweets.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
    new = {(a, i): json.loads(d) for a, i, d in db.execute('SELECT account,tweet_id,document FROM tweets')}
checked = 0
for key, doc in old.items():
    assert key in new, ('Missing old record', key)
    for field in ('status', 'content', 'translation_zh', 'translation_info', 'date_beijing', 'images'):
        assert doc.get(field) == new[key].get(field), (key, field)
    checked += 1
print(f'Migration verified: {checked} existing records unchanged; {len(new) - len(old)} video records added.')
