import json
import hashlib
import sqlite3
import sys
from collections import Counter
from pathlib import Path

root = Path(sys.argv[1])
db = sqlite3.connect((root / "_推文归档/tweets.sqlite").as_uri() + "?mode=ro", uri=True)
totals = {}
problems = []
for account, status, document in db.execute("SELECT account,status,document FROM tweets"):
    doc = json.loads(document)
    stats = totals.setdefault(account, Counter())
    stats[status] += 1
    if status == "archived":
        stats["images"] += len(doc["images"])
        stats["videos"] += len(doc.get("videos", []))
        for path in doc["images"] + doc.get("videos", []):
            if not (root / path).is_file():
                problems.append(path)
        kind = doc.get('post_type')
        stats[kind or 'unclassified'] += 1
        metadata = doc.get('metadata') or {}
        if kind == 'original' and any(metadata.get(k) for k in ('retweet_id','quote_id','quoted_id')):
            problems.append(doc['tweet_id'] + ': 转推或引用不应标成原创')
        if kind not in ('original','quote','retweet','reference'):
            problems.append(doc['tweet_id'] + ': 缺少类型')
        if doc.get("translation_zh"):
            stats["translated"] += 1
            digest = hashlib.sha256(doc["content"].encode("utf-8")).hexdigest()
            if doc.get("translation_info", {}).get("source_sha256") != digest:
                problems.append(doc["tweet_id"] + ": 译文与原文不匹配")
        elif doc["content"].strip():
            problems.append(doc["tweet_id"] + ": 缺少译文")
        else:
            stats["no_text"] += 1
db.close()
for folder in [a['folder'] for a in json.loads((root / 'tools/accounts.json').read_text(encoding='utf-8-sig'))]:
    documents = list((root / folder / "推文").rglob("*.json"))
    for path in documents:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc["status"] != "archived" or not path.with_suffix(".md").is_file():
            problems.append(str(path))
print(json.dumps({"accounts": totals, "problems": problems}, ensure_ascii=False, indent=2))
sys.exit(bool(problems))
