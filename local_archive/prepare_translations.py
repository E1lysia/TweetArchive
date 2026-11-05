"""Make stable, deduplicated translation tasks from the local archive (read only)."""
import hashlib
import json
import sqlite3
from pathlib import Path

root = Path(r"D:\gallery-dl")
out = Path(__file__).parent / "translations"
out.mkdir(exist_ok=True)
db = sqlite3.connect((root / "_推文归档/tweets.sqlite").as_uri() + "?mode=ro", uri=True)
tasks = []
seen = set()
for (value,) in db.execute("SELECT document FROM tweets WHERE status='archived' ORDER BY tweet_id DESC"):
    doc = json.loads(value)
    content = doc["content"]
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if not content.strip() or doc.get("translation_zh") or digest in seen:
        continue
    seen.add(digest)
    tasks.append({"key": f"t{len(tasks)+1:04d}", "source_sha256": digest,
                  "account": doc["account"], "content": content})
db.close()
(out / "tasks.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
for start in range(0, len(tasks), 75):
    batch = tasks[start:start+75]
    (out / f"source_{start//75+1:02d}.json").write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"unique_texts":len(tasks), "chars":sum(len(t['content']) for t in tasks)}, ensure_ascii=False))
