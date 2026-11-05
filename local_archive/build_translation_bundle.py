"""Assemble reviewed translations; retain original URLs and hashtags."""
import json
import re
from pathlib import Path

folder = Path(__file__).parent / "translations"
tasks = json.loads((folder / "tasks.json").read_text(encoding="utf-8"))
translated = {}
for path in sorted(folder.glob("zh_*.json")):
    values = json.loads(path.read_text(encoding="utf-8"))
    if translated.keys() & values.keys():
        raise ValueError("译文键重复")
    translated.update(values)
if set(translated) != {item["key"] for item in tasks}:
    raise ValueError("译文不完整")
items = []
for task in tasks:
    source = task["content"]
    result = translated[task["key"]].strip()
    urls = re.findall(r"https?://[^\s]+", source)
    missing_urls = list(dict.fromkeys(url for url in urls if url not in result))
    if missing_urls:
        result += "\n\n" + "\n".join(missing_urls)
    tags = re.findall(r"#[\w]+", source)
    missing_tags = list(dict.fromkeys(tag for tag in tags if tag not in result))
    if missing_tags:
        result += "\n\n" + " ".join(missing_tags)
    items.append({"source_sha256": task["source_sha256"], "source_text": source,
                  "translation_zh": result})
bundle = {"version": 1, "language": "zh-CN", "translator": "Codex", "translations": items}
(folder / "translations.zh-CN.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"已生成 {len(items)} 份按原文校验的中文译文；重复原文共用译文，原始链接和话题标签均已保留。")
