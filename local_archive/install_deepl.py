"""Install prepared DeepL integration after backing up the existing local files."""
import datetime as dt
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

source = Path(__file__).resolve().parent
root = Path(r"D:\gallery-dl")
target_db = root / "_推文归档/tweets.sqlite"
backup = root / "_推文归档/backups" / ("before-deepl-" + dt.datetime.now(
    dt.timezone(dt.timedelta(hours=8))).strftime("%Y%m%d-%H%M%S"))
files = ["tools/deepl_translate.py", "tools/deepl.local.example.json", "tools/tweet_archive.py",
         "tools/update.ps1", "推文归档.cmd", "配置DeepL.cmd", "测试DeepL.cmd", "补译中文.cmd",
         "DeepL使用说明.md", "推文归档手册.md"]
for relative in files:
    if not (source / relative).is_file():
        raise SystemExit("安装源不完整：" + relative)
backup.mkdir(parents=True, exist_ok=False)
with sqlite3.connect(target_db.as_uri() + "?mode=ro", uri=True) as db:
    snapshot = dict(db.execute("SELECT account || ':' || tweet_id, document FROM tweets"))
    with sqlite3.connect(backup / "tweets.sqlite") as backup_db:
        db.backup(backup_db)
for relative in files:
    target = root / relative
    if target.is_file():
        saved = backup / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, saved)
    shutil.copy2(source / relative, target)
config = root / "tools/deepl.local.json"
if not config.exists():
    shutil.copy2(source / "tools/deepl.local.example.json", config)
subprocess.run([sys.executable, "-B", str(root / "tools/tweet_archive.py"),
                "--root", str(root), "--translate-only"], check=True)
with sqlite3.connect(target_db.as_uri() + "?mode=ro", uri=True) as db:
    after = dict(db.execute("SELECT account || ':' || tweet_id, document FROM tweets"))
if snapshot != after:
    raise AssertionError("安装期间已有推文记录发生变化，请核对备份。")
print(json.dumps({"installed_files": len(files), "existing_records_preserved": len(snapshot),
                  "backup": str(backup), "api_key_required": True}, ensure_ascii=False, indent=2))
