"""把下载目录里散落的文件按 年/月 归档。可重复运行。

用法: archive_months.py [目录]
默认: 当前工作目录
"""

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
PATTERN = re.compile(r"^(\d{4})-(\d{2})-\d{2}.*\.(jpg|jpeg|png|mp4|gif|webm|m4v)$", re.I)


def organize(base: Path) -> int:
    if not base.exists():
        return 0
    moved = 0
    for path in [p for p in base.iterdir() if p.is_file()]:
        match = PATTERN.match(path.name)
        if not match:
            continue
        target_dir = base / match.group(1) / match.group(2)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / path.name
        if target.exists():
            target = target_dir / f"{path.stem}_dup{path.suffix}"
        shutil.move(str(path), str(target))
        moved += 1
    return moved


if __name__ == "__main__":
    total = organize(ROOT) + organize(ROOT / "视频GIF")
    print(f"[archive] {ROOT.name}: moved {total} file(s) into year/month folders")
