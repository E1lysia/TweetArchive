"""Update the single integrated archive, preserving the tested runtime and clean data."""
import hashlib
import json
from pathlib import Path
import runpy
import zipfile

WORK=Path(__file__).resolve().parents[1];RELEASE=WORK/'release'
archive=RELEASE/'推文资料库-最新整合版.zip';NAME='推文资料库-最新整合版'
old_digest=hashlib.sha256(archive.read_bytes()).hexdigest()
previous=RELEASE/'推文资料库-整合版-1.1.0-保留.zip'
with zipfile.ZipFile(archive) as base:
    manifest=json.loads(base.read(NAME+'/MANIFEST.json'))
    if manifest['version']=='1.1.0' and not previous.exists():previous.write_bytes(archive.read_bytes())
    payload={entry['path']:base.read(NAME+'/'+entry['path']) for entry in manifest['files']}
updates={}
for name in ['app.py','library.py','video_posters.py','translation_settings.py','storage.py','storage_settings.py','version.py']:
    text=(WORK/'desktop_app'/name).read_text(encoding='utf-8').replace(", r'D:\\gallery-dl\\资料库\\vendor'",'')
    updates['资料库/'+name]=text.encode('utf-8')
updates['tools/tweet_archive.py']=(WORK/'local_archive/tools/tweet_archive.py').read_bytes()
runpy.run_path(str(WORK/'packaging/build_guide.py'),run_name='__main__',init_globals={'RELEASE_VERSION':'1.1.1','GUIDE_ONLY':True})
guide=(RELEASE/'推文资料库操作指南.html').read_text(encoding='utf-8')
guide=guide.replace('本文按分享版界面编写。','最新整合版；本包包含账号分组、右键改名及此前全部更新，无需叠加旧补丁。')
guide=guide.replace('<h2 id="section-2">2. 解压与启动</h2>',
    '<h2 id="section-2">2. 解压与启动</h2><p>完整解压到新目录。已有资料可通过左下角“设置 → 存储位置与归档 → 打开已有资料库”接入；不要用分享包中的空账号文件覆盖原资料。操作说明统一在本页。</p>')
guide=guide.replace('<h3>第一次打开没有任何内容</h3>',
    '<h3>下载时需要开加速器吗</h3><p>取决于当前网络能否直接访问 X。需要代理时，确保下载程序的流量也经过代理；仅浏览器代理插件可能无法让程序联网。已保存内容可以离线阅读，翻译需要连接所选服务。</p><h3>第一次打开没有任何内容</h3>')
updates['操作指南.html']=guide.encode('utf-8')
payload.update(updates)
manifest.update(version='1.1.1',distribution='integrated')
manifest['files']=[dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in sorted(payload.items())]
payload['MANIFEST.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')
temporary=archive.with_suffix('.groups.tmp')
with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name,data in payload.items():z.writestr(NAME+'/'+name,data)
forbidden={'cookies.txt','tweets.sqlite','manager.sqlite','translation.local.json','deepl.local.json','storage.local.json','archive.local.json'}
with zipfile.ZipFile(temporary) as z:
    assert z.testzip() is None
    assert len(z.namelist())==len(set(z.namelist()))
    for entry in manifest['files']:assert hashlib.sha256(z.read(NAME+'/'+entry['path'])).hexdigest()==entry['sha256']
    assert json.loads(z.read(NAME+'/tools/accounts.json'))==[]
    assert not any(Path(name).name in forbidden for name in z.namelist())
temporary.replace(archive)
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='utf-8')
patch_path=RELEASE/'内部安装-1.1.1-程序文件.zip'
with zipfile.ZipFile(patch_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name,data in updates.items():z.writestr(name,data)
result=dict(version='1.1.1',archive=str(archive),old_sha256=old_digest,sha256=digest,files=len(payload),
            no_private_data=True,single_user_guide=True,account_groups=True,rename_accounts=True,auto_update_implemented=False)
(RELEASE/'整合版验证报告.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
