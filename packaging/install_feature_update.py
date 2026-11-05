"""Install the allowlisted code patch with backups; never copy library/config files."""
import datetime
import json
from pathlib import Path
import shutil
import zipfile

WORK=Path(__file__).resolve().parents[1]
ROOT=Path(r'D:\gallery-dl').resolve()
PATCH=WORK/'release/推文资料库-1.1.0-更新补丁.zip'
allowed={
    '资料库/app.py','资料库/library.py','资料库/video_posters.py','资料库/translation_settings.py',
    '资料库/storage.py','资料库/storage_settings.py',
    'tools/tweet_archive.py','tools/deepl_translate.py','tools/translation_engine.py','tools/tweet_archive_view.html',
    'tools/update.ps1','tools/archive_months.py','_setup/gen_sheet.py','先读我.txt','功能说明.md','_setup/grab_cookies.py','刷新登录态.cmd','刷新登录态说明.txt',
    'TweetArchive-XLogin/manifest.json','TweetArchive-XLogin/background.js','升级到1.1.0.txt',
    '推文资料库操作指南.html','推文资料库操作指南.txt',
}
backup=ROOT/'资料库/_版本备份'/('before-1.1.0-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
with zipfile.ZipFile(PATCH) as archive:
    assert set(archive.namelist())==allowed
    assert archive.testzip() is None
    for name in allowed:
        target=(ROOT/name).resolve()
        assert target.is_relative_to(ROOT) and target!=ROOT
    backup.mkdir(parents=True,exist_ok=False)
    for name in sorted(allowed,key=lambda name:name=='资料库/app.py'):
        target=ROOT/name
        if target.is_file():
            previous=backup/name;previous.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,previous)
        target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_suffix(target.suffix+'.update-new')
        temporary.write_bytes(archive.read(name));temporary.replace(target)
        assert target.read_bytes()==archive.read(name)
print(json.dumps(dict(installed=True,version='1.1.0',files=len(allowed),backup=str(backup),
                     no_data_or_credentials_written=True,restart_required=True),ensure_ascii=False))
