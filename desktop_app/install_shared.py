"""Install classified shared-post archive support."""
import datetime
import shutil
from pathlib import Path

source = Path(__file__).resolve().parent
root = Path(r'D:\gallery-dl')
backup = root / '_推文归档/backups' / ('desktop-shared-ui-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
for name in ('app.py', 'library.py', '使用说明.md'):
    shutil.copy2(root / '资料库' / name, backup / name)
    temp = root / '资料库' / (name + '.new')
    shutil.copy2(source / name, temp)
    temp.replace(root / '资料库' / name)
for name in ('tweet_archive.py', 'deepl_translate.py', 'tweet_archive_view.html', 'update.ps1'):
    shutil.copy2(root / 'tools' / name, backup / name)
    temp = root / 'tools' / (name + '.new')
    shutil.copy2(source.parent / 'local_archive/tools' / name, temp)
    temp.replace(root / 'tools' / name)
print('Installed. Backup: ' + str(backup))
