"""Install UI-only files with a complete backup before the first replacement."""
import datetime
import json
from pathlib import Path
import shutil
import zipfile

WORK=Path(__file__).resolve().parents[1]; ROOT=Path(r'D:\gallery-dl').resolve()
patch=WORK/'release/内部安装-1.1.3-程序文件.zip'
allowed={'资料库/'+name for name in ['app.py','storage_settings.py','translation_settings.py','settings_dialog.py','media_viewer.py','version.py']}
allowed.update({'操作指南.html','资料库/icons/check.svg'})
backup=ROOT/'资料库/_版本备份'/('before-1.1.3-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
with zipfile.ZipFile(patch) as z:
    assert set(z.namelist())==allowed and z.testzip() is None
    assert backup.resolve().is_relative_to(ROOT)
    for name in allowed:assert (ROOT/name).resolve().is_relative_to(ROOT)
    backup.mkdir(parents=True,exist_ok=False)
    for name in allowed:
        target=ROOT/name
        if target.is_file():
            previous=backup/name;previous.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,previous)
    for name in sorted(allowed,key=lambda name:name=='资料库/app.py'):
        target=ROOT/name;target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_suffix(target.suffix+'.update-new')
        temporary.write_bytes(z.read(name));temporary.replace(target)
        assert target.read_bytes()==z.read(name)
print(json.dumps(dict(version='1.1.3',backup=str(backup),program_files=len(allowed),data_and_credentials_preserved=True,restart_required=True),ensure_ascii=False))
