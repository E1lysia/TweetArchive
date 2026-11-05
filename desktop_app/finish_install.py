"""Update app files after validation; the initial database backup is retained."""
import shutil
from pathlib import Path

source = Path(__file__).resolve().parent
root = Path(r'D:\gallery-dl')
destination = root / '资料库'
for name in ('app.py', 'library.py', 'video_posters.py', '使用说明.md'):
    shutil.copy2(source / name, destination / name)
for path in (source / 'launcher/dist').iterdir():
    if path.suffix in ('.exe', '.dll', '.json'):
        shutil.copy2(path, root / path.name)
shutil.copy2(source.parent / 'local_archive/tools/update.ps1', root / 'tools/update.ps1')
shutil.copy2(source / 'launcher/archive.ico', destination / 'archive.ico')
print('Desktop manager and executable launcher installed.')
