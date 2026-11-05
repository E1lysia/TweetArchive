"""Overlay reviewed UI code onto the verified clean integrated runtime."""
import hashlib
import json
from pathlib import Path
import runpy
import zipfile

WORK=Path(__file__).resolve().parents[1]; RELEASE=WORK/'release'
VERSION='1.1.2'; NAME='推文资料库-最新整合版'; archive=RELEASE/(NAME+'.zip')
old_digest=hashlib.sha256(archive.read_bytes()).hexdigest()
with zipfile.ZipFile(archive) as base:
    manifest=json.loads(base.read(NAME+'/MANIFEST.json'))
    assert manifest['version'] in ('1.1.1',VERSION)
    previous=RELEASE/('推文资料库-整合版-'+manifest['version']+'-保留.zip')
    if manifest['version']!=VERSION:
        if previous.exists():assert previous.read_bytes()==archive.read_bytes()
        else:previous.write_bytes(archive.read_bytes())
    payload={entry['path']:base.read(NAME+'/'+entry['path']) for entry in manifest['files']}
updates={}
for name in ['app.py','storage_settings.py','translation_settings.py','settings_dialog.py','version.py']:
    source=(WORK/'desktop_app'/name).read_text(encoding='utf-8').replace(", r'D:\\gallery-dl\\资料库\\vendor'",'')
    updates['资料库/'+name]=source.encode('utf-8')
runpy.run_path(str(WORK/'packaging/build_guide.py'),run_name='__main__',init_globals={'RELEASE_VERSION':VERSION,'GUIDE_ONLY':True})
updates['操作指南.html']=(RELEASE/'推文资料库操作指南.html').read_bytes()
payload.update(updates)
manifest.update(version=VERSION,distribution='integrated')
manifest['files']=[dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in sorted(payload.items())]
payload['MANIFEST.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')
temporary=archive.with_suffix('.settings.tmp')
with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name,data in payload.items():z.writestr(NAME+'/'+name,data)
with zipfile.ZipFile(temporary) as z:
    assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
    for entry in manifest['files']:assert hashlib.sha256(z.read(NAME+'/'+entry['path'])).hexdigest()==entry['sha256']
    assert json.loads(z.read(NAME+'/tools/accounts.json'))==[]
    forbidden={'cookies.txt','tweets.sqlite','manager.sqlite','translation.local.json','deepl.local.json','storage.local.json','archive.local.json'}
    assert not any(Path(name).name in forbidden for name in z.namelist())
temporary.replace(archive)
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='utf-8')
with zipfile.ZipFile(RELEASE/('内部安装-'+VERSION+'-程序文件.zip'),'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name,data in updates.items():z.writestr(name,data)
report=dict(version=VERSION,archive=str(archive),old_sha256=old_digest,sha256=digest,files=len(payload),no_private_data=True,
            single_user_guide=True,compact_account_tools=True,settings_pages=['storage','translation','login'])
(RELEASE/'整合版验证报告.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
