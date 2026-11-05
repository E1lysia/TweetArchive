"""Back up the existing archive, install translation support, and import it."""
import datetime as dt
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

source = Path(__file__).resolve().parent
root = Path(r"D:\gallery-dl")
bundle = source / "translations/translations.zh-CN.json"
if not bundle.is_file() or not (root / "_推文归档/tweets.sqlite").is_file():
    raise SystemExit("缺少译文文件或归档数据库")
backup = root / "_推文归档/backups" / ("before-translation-" + dt.datetime.now(
    dt.timezone(dt.timedelta(hours=8))).strftime("%Y%m%d-%H%M%S"))
backup.mkdir(parents=True, exist_ok=False)
db_path = root / "_推文归档/tweets.sqlite"
with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as old_db:
    before = {tid: json.loads(value) for tid, value in old_db.execute("SELECT account || ':' || tweet_id, document FROM tweets")}
    with sqlite3.connect(backup / "tweets.sqlite") as backup_db:
        old_db.backup(backup_db)
for relative in ("tools/tweet_archive.py", "tools/tweet_archive_view.html", "推文归档手册.md", "推文归档.html"):
    original = root / relative
    if original.is_file():
        destination = backup / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)
for relative in ("tools/tweet_archive.py", "tools/tweet_archive_view.html", "推文归档手册.md"):
    shutil.copy2(source / relative, root / relative)
bundle_target = root / "_推文归档/translations.zh-CN.json"
if bundle_target.exists():
    shutil.copy2(bundle_target, backup / bundle_target.name)
shutil.copy2(bundle, bundle_target)
subprocess.run([sys.executable, "-B", str(root / "tools/tweet_archive.py"),
                "--root", str(root), "--import-translations", str(bundle_target)], check=True)
counts = {"translated": 0, "no_text": 0, "missing": 0}
with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as db:
    for tid, value in db.execute("SELECT account || ':' || tweet_id, document FROM tweets"):
        doc = json.loads(value)
        old = before[tid]
        for key in old:
            if key not in ("translation_zh", "translation_info") and old[key] != doc.get(key):
                raise AssertionError(f"原有字段发生变化：{tid} {key}")
        if doc["status"] != "archived":
            if doc.get("translation_zh"):
                raise AssertionError("排除的推文不应导入翻译")
            continue
        if not doc["content"].strip():
            counts["no_text"] += 1
        elif doc.get("translation_zh"):
            counts["translated"] += 1
            if hashlib.sha256(doc["content"].encode()).hexdigest() != doc["translation_info"]["source_sha256"]:
                raise AssertionError("译文关联校验失败")
        else:
            counts["missing"] += 1
if counts["missing"]:
    raise AssertionError("仍有正文缺少译文")
print(json.dumps({"counts": counts, "backup": str(backup)}, ensure_ascii=False, indent=2))
