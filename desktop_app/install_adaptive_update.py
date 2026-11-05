"""Install the reviewed desktop and incremental pipeline files, without a ZIP."""
import datetime
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil

WORK=Path(__file__).resolve().parents[1]
ROOT=Path(r'D:\gallery-dl').resolve()
VERSION=runpy.run_path(str(WORK/'desktop_app/version.py'))['VERSION']
parser=argparse.ArgumentParser()
parser.add_argument('--include-launcher',action='store_true',help='同时安装预先构建的 TweetArchive 启动器')
args=parser.parse_args()
files={
    '资料库/adaptive_cards.py':WORK/'desktop_app/adaptive_cards.py',
    '资料库/app.py':WORK/'desktop_app/app.py',
    '资料库/library.py':WORK/'desktop_app/library.py',
    '资料库/media_viewer.py':WORK/'desktop_app/media_viewer.py',
    '资料库/version.py':WORK/'desktop_app/version.py',
    '资料库/text_presentation.py':WORK/'desktop_app/text_presentation.py',
    'tools/latest_tweets.py':WORK/'local_archive/tools/latest_tweets.py',
    'tools/tweet_archive.py':WORK/'local_archive/tools/tweet_archive.py',
    'tools/update.ps1':WORK/'local_archive/tools/update.ps1',
    'tools/tweet_archive_view.html':WORK/'local_archive/tools/tweet_archive_view.html',
}
if args.include_launcher:
    launcher=WORK/'desktop_app/launcher/bin/Release/net8.0/win-x64'
    for name in ('TweetArchive.exe','TweetArchive.dll','TweetArchive.deps.json','TweetArchive.runtimeconfig.json'):
        files[name]=launcher/name
    files['TweetArchive.cmd']=WORK/'packaging/assets/TweetArchive.cmd'
    files['TweetArchive-XLogin/manifest.json']=WORK/'packaging/assets/TweetArchive-XLogin/manifest.json'
    files['_setup/grab_cookies.py']=WORK/'packaging/assets/_setup/grab_cookies.py'
for name,source in files.items():
    assert (ROOT/name).resolve().is_relative_to(ROOT) and source.is_file()
    if source.suffix=='.py':compile(source.read_text(encoding='utf-8-sig'),str(source),'exec')
protected=[ROOT/'cookies.txt',ROOT/'tools/translation.local.json',ROOT/'tools/deepl.local.json',
           ROOT/'tools/accounts.json',ROOT/'storage.local.json',ROOT/'tools/storage.local.json']
hashes={path:hashlib.sha256(path.read_bytes()).digest() for path in protected if path.is_file()}
backup=ROOT/'资料库/_版本备份'/(f'before-{VERSION}-desktop-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
assert backup.resolve().is_relative_to(ROOT)
backup.mkdir(parents=True,exist_ok=False)
existed={name:(ROOT/name).is_file() for name in files}
for name in files:
    if existed[name]:
        saved=backup/name;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,saved)
installed=[]
try:
    for name,source in files.items():
        target=ROOT/name;temp=target.with_name(target.name+'.update-new')
        shutil.copy2(source,temp);temp.replace(target);installed.append(name)
        assert target.read_bytes()==source.read_bytes()
except Exception:
    for name in reversed(installed):
        target=ROOT/name
        if existed[name]:shutil.copy2(backup/name,target)
        else:target.unlink()
    raise
assert all(hashlib.sha256(path.read_bytes()).digest()==value for path,value in hashes.items())
print(json.dumps(dict(version=VERSION,backup=str(backup),program_files=len(files),
                      credentials_and_accounts_unchanged=True,restart_required=True,release_created=False),ensure_ascii=False))
