"""Back up the current app and install the switchable reading/classic layouts."""
import datetime
import shutil
from pathlib import Path

source = Path(__file__).resolve().parent
root = Path(r'D:\gallery-dl')
backup = root / '_推文归档/backups' / ('reading-layout-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
for name in ('app.py', '使用说明.md'):
    shutil.copy2(root / '资料库' / name, backup / name)
    temp = root / '资料库' / (name + '.new')
    shutil.copy2(source / name, temp)
    temp.replace(root / '资料库' / name)
print('Updated. Backup: ' + str(backup))
