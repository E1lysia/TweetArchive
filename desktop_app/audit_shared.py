"""Verify retained originals and report classification/translation coverage."""
import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

root = Path(r'D:\gallery-dl')
before = sorted((root / '_推文归档/backups').glob('shared-posts-*/tweets.sqlite'))[0]
with closing(sqlite3.connect(before.as_uri() + '?mode=ro', uri=True)) as db:
    old = {(a,t):json.loads(v) for a,t,v in db.execute('SELECT account,tweet_id,document FROM tweets')}
with closing(sqlite3.connect((root / '_推文归档/tweets.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
    new = {(a,t):json.loads(v) for a,t,v in db.execute('SELECT account,tweet_id,document FROM tweets')}
preserved = 0
for key, doc in old.items():
    if doc['status'] == 'archived':
        for field in ('content','translation_zh','translation_info','images','videos','author','handle','date_beijing'):
            assert doc.get(field) == new[key].get(field), (key,field)
        preserved += 1
types = Counter()
pending = defaultdict(lambda:dict(records=0, characters=0))
for doc in new.values():
    if doc['status'] != 'archived':
        continue
    kind = doc.get('post_type')
    assert kind in ('original','quote','retweet','reference')
    metadata = doc.get('metadata') or {}
    if kind == 'original':
        assert not any(metadata.get(k) for k in ('retweet_id','quote_id','quoted_id'))
    for path in doc.get('images',[]) + doc.get('videos',[]):
        assert (root / path).is_file(), path
    types[kind] += 1
    if not doc.get('translation_zh') and doc['content'].strip():
        pending[kind]['records'] += 1
        pending[kind]['characters'] += len(doc['content'])
print(json.dumps(dict(preserved_originals=preserved, types=types, untranslated=pending), ensure_ascii=False, indent=2))
