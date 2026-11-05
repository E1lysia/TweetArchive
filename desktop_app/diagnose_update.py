import json
import sqlite3
from pathlib import Path
from contextlib import closing

root = Path(r'D:\gallery-dl')
with closing(sqlite3.connect((root / '_推文归档/tweets.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
    for tid in ('2116855504727425235', '2117464284792000823', '2117525193770090971'):
        row = db.execute('SELECT account,status,document FROM tweets WHERE tweet_id=?', (tid,)).fetchone()
        if row:
            doc = json.loads(row[2])
            print(json.dumps(dict(id=tid, account=row[0], status=row[1], date=doc.get('date_beijing'), images=len(doc.get('images', [])), translated=bool(doc.get('translation_zh')), reason=doc.get('exclusion_reason')), ensure_ascii=False))
        else:
            print(tid + ': not indexed')
with closing(sqlite3.connect((root / '_推文归档/manager.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
    for tid, title, status, created, log in db.execute('SELECT id,title,status,created,log FROM tasks ORDER BY id DESC LIMIT 8'):
        print(json.dumps(dict(task=tid, title=title, status=status, created=created, tail=log[-3800:]), ensure_ascii=False))
