"""Add the portable login helper without ever scanning personal data directories."""
import hashlib
import json
from pathlib import Path
import runpy
import sys
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_assets import main as prepare_assets

WORK=Path(__file__).resolve().parents[1]
RELEASE=WORK/'release'
NAME='TweetArchive-1.0.0-win-x64'
archive=RELEASE/(NAME+'.zip')
old_digest=hashlib.sha256(archive.read_bytes()).hexdigest()
prepare_assets()
patch_paths=['_setup/grab_cookies.py','刷新登录态.cmd','刷新登录态说明.txt',
             'TweetArchive-XLogin/manifest.json','TweetArchive-XLogin/background.js']
paths=[*patch_paths,
       '先读我.txt','功能说明.md','tools/update.ps1']
outputs={name:(WORK/'packaging/assets'/name).read_bytes() for name in paths}
temp=archive.with_suffix('.login.tmp')
with zipfile.ZipFile(archive) as original:
    manifest=json.loads(original.read(NAME+'/MANIFEST.json'))
    manifest['files']=[entry for entry in manifest['files'] if entry['path'] not in outputs]
    manifest['files'].extend(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in outputs.items())
    manifest['files'].sort(key=lambda entry:entry['path'])
    manifest_bytes=json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')
    excluded={NAME+'/MANIFEST.json',*(NAME+'/'+name for name in outputs)}
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as target:
        for entry in original.infolist():
            if entry.filename not in excluded: target.writestr(entry,original.read(entry))
        for name,data in outputs.items(): target.writestr(NAME+'/'+name,data)
        target.writestr(NAME+'/MANIFEST.json',manifest_bytes)
with zipfile.ZipFile(temp) as checked:
    assert checked.testzip() is None
    for entry in manifest['files']:
        assert hashlib.sha256(checked.read(NAME+'/'+entry['path'])).hexdigest()==entry['sha256']
    assert json.loads(checked.read(NAME+'/tools/accounts.json'))==[]
    forbidden={'cookies.txt','deepl.local.json','translation.local.json','tweets.sqlite','manager.sqlite'}
    assert not any(Path(name).name in forbidden for name in checked.namelist())
temp.replace(archive)
for name,data in {**outputs,'MANIFEST.json':manifest_bytes}.items():
    target=RELEASE/NAME/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
# Render and incorporate updated instructions using the same verified ZIP base.
runpy.run_path(str(WORK/'packaging/build_guide.py'),run_name='__main__')
patch=RELEASE/'登录态刷新补丁.zip'
with zipfile.ZipFile(patch,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name in patch_paths: z.writestr(name,outputs[name])
with zipfile.ZipFile(patch) as z:
    assert z.testzip() is None and set(z.namelist())==set(patch_paths)
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
report_path=RELEASE/'验证报告.json'
report=json.loads(report_path.read_text(encoding='utf-8'))
report.update(zip_sha256=digest,login_refresh_included=True,login_refresh_tests=9,
              login_extension_bundled=True,
              login_refresh_live_browser_tested=False,manifest_files=len(manifest['files']))
report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(old_sha256=old_digest,new_sha256=digest,patch=str(patch),private_data_included=False),ensure_ascii=False))
