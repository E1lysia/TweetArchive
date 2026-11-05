"""Install clearer selectors and grouped paging controls."""
import datetime
import shutil
from pathlib import Path

source = Path(__file__).resolve().parent
root = Path(r'D:\gallery-dl')
destination = root / '资料库'
backup = root / '_推文归档/backups' / ('desktop-ui-v3-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
for name in ('app.py', '使用说明.md'):
    shutil.copy2(destination / name, backup / name)
    shutil.copy2(source / name, destination / name)
print('Updated. Backup: ' + str(backup))
