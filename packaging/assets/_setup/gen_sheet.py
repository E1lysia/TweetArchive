"""Build a single contact sheet of all downloaded images, grouped by year.

用法: gen_sheet.py [目录] [@handle] [显示名]
默认: 当前工作目录
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
HANDLE = sys.argv[2] if len(sys.argv) > 2 else ""
NAME = sys.argv[3] if len(sys.argv) > 3 else ROOT.name
OUT = ROOT / "_缩略图总览.jpg"

COLS, CELL, GAP, MARGIN = 30, 90, 4, 24
HEADER, LABEL_H = 74, 46
BG = (255, 255, 255)
LABEL_BG = (242, 243, 245)
TEXT = (32, 36, 44)

files = sorted(
    (p for p in ROOT.rglob("*.jpg") if "视频GIF" not in p.parts and not p.name.startswith("_")),
    key=lambda p: p.name,
)
print("images:", len(files))
if not files:
    print("no images found"); sys.exit(0)

years = {}
for p in files:
    years.setdefault(p.name[:4], []).append(p)

rows = []
for year in sorted(years):
    items = years[year]
    rows.append(("label", year, len(items)))
    for i in range(0, len(items), COLS):
        rows.append(("imgs", items[i : i + COLS]))

W = MARGIN * 2 + COLS * CELL + (COLS - 1) * GAP
H = HEADER + sum(LABEL_H if r[0] == "label" else CELL + GAP for r in rows) + MARGIN
print("canvas:", W, "x", H)

canvas = Image.new("RGB", (W, H), BG)
draw = ImageDraw.Draw(canvas)
fonts = [Path(__import__("os").environ.get("WINDIR", r"C:\Windows")) / "Fonts" / name for name in ("msyh.ttc", "segoeui.ttf", "arial.ttf")]
font_path = next((p for p in fonts if p.exists()), None)
font_big = ImageFont.truetype(str(font_path), 30) if font_path else ImageFont.load_default()
font_small = ImageFont.truetype(str(font_path), 22) if font_path else ImageFont.load_default()

first, last = files[0].name[:10], files[-1].name[:10]
draw.text(
    (MARGIN, 18),
    f"{NAME} {HANDLE}   {len(files)} 张原图   {first} ~ {last}",
    font=font_big,
    fill=TEXT,
)

y = HEADER
for row in rows:
    if row[0] == "label":
        draw.rectangle([0, y, W, y + LABEL_H], fill=LABEL_BG)
        draw.text((MARGIN, y + 9), f"{row[1]} 年   {row[2]} 张", font=font_small, fill=TEXT)
        y += LABEL_H
        continue

    for i, path in enumerate(row[1]):
        x = MARGIN + i * (CELL + GAP)
        try:
            with Image.open(path) as img:
                img = ImageOps.exif_transpose(img)
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                img.thumbnail((CELL, CELL), Image.LANCZOS)
                canvas.paste(img, (x + (CELL - img.width) // 2, y + (CELL - img.height) // 2))
        except Exception as exc:  # noqa: BLE001
            print("skip", path.name, exc)
    y += CELL + GAP

    if len(row[1]) < COLS:
        pass

canvas = canvas.crop((0, 0, W, min(y + MARGIN, H)))
canvas.save(OUT, "JPEG", quality=85, optimize=True, progressive=True)
print("saved:", OUT, canvas.size, round(OUT.stat().st_size / 1024 / 1024, 2), "MB")
