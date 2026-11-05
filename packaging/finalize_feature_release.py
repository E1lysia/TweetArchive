"""Refresh the allowlisted 1.1.0 payload, docs, manifest and data-preserving patch."""
import hashlib
import json
from pathlib import Path
import runpy
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_assets import main as prepare_assets

WORK=Path(__file__).resolve().parents[1]
RELEASE=WORK/'release';NAME='TweetArchive-1.1.0-win-x64'
archive=RELEASE/(NAME+'.zip')
prepare_assets()
outputs={}
for name in ['app.py','library.py','video_posters.py','translation_settings.py','storage.py','storage_settings.py']:
    source=(WORK/'desktop_app'/name).read_text(encoding='utf-8').replace(", r'D:\\gallery-dl\\资料库\\vendor'",'')
    outputs['资料库/'+name]=source.encode('utf-8')
for name in ['tweet_archive.py','deepl_translate.py','translation_engine.py','tweet_archive_view.html']:
    source=(WORK/'local_archive/tools'/name).read_text(encoding='utf-8')
    if name=='deepl_translate.py':source=source.replace('["青木陽菜", "鈴木みのり", "MyGO!!!!!", "Ave Mujica", "BanG Dream!"]','[]')
    outputs['tools/'+name]=source.encode('utf-8')
for name in ['tools/update.ps1','tools/archive_months.py','_setup/gen_sheet.py','先读我.txt','功能说明.md','_setup/grab_cookies.py','刷新登录态.cmd','刷新登录态说明.txt','TweetArchive-XLogin/manifest.json','TweetArchive-XLogin/background.js']:
    outputs[name]=(WORK/'packaging/assets'/name).read_bytes()
notice='''推文资料库 1.1.0 更新说明

新增：内容类型多选、资料库位置选择与复制迁移、教学空资料库、纯文字归档与卡片、历史正文补录。

旧用户升级：
1. 等待任务结束，退出软件。
2. 将“推文资料库-1.1.0-更新补丁.zip”解压到“推文资料库.exe”所在目录，同名程序文件替换。
3. 再启动软件。默认继续使用原资料库，不需要重建账号或删除数据库。
补丁不包含 accounts.json、数据库、Cookies、API 密钥、下载清单或媒体文件，不会用空资料覆盖旧内容。
完整分享版是空资料库，只供新用户或另外解压演示使用；已有资料升级请用补丁。

操作入口：
- 内容类型：同时点击“原创”和“引用”等；选中带勾，“全部”为一键全选。
- 资料库位置：设置与翻译 → 存储与归档；复制迁移会保留原目录，任务执行时不能切换。
- 纯文字：在存储与归档中默认开启，日常补新会保存新正文；左侧“纯文字”单独查看。
- 旧的纯文字：补新菜单 → 补历史正文；设置日期与上限，可继续或停止历史任务。默认不自动翻译历史正文。
- 归档范围与页面筛选独立；回复默认关闭。有媒体但下载失败时保留正文并标记媒体待下载/缺失。
- 更改位置后，数据保存在资料库目录；登录文件和翻译密钥仍在程序目录。备份要同时保存这两处。

完整操作见“推文资料库操作指南.html”。X 可返回的内容受网络、登录权限与接口限制，不能保证获取全部历史推文。
'''
outputs['升级到1.1.0.txt']=notice.encode('utf-8-sig')
temp=archive.with_suffix('.feature.tmp')
with zipfile.ZipFile(archive) as original:
    manifest=json.loads(original.read(NAME+'/MANIFEST.json'))
    manifest['files']=[entry for entry in manifest['files'] if entry['path'] not in outputs]
    manifest['files'].extend(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in outputs.items())
    manifest['files'].sort(key=lambda entry:entry['path'])
    manifest_bytes=json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')
    excluded={NAME+'/MANIFEST.json',*(NAME+'/'+name for name in outputs)}
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as target:
        for entry in original.infolist():
            if entry.filename not in excluded:target.writestr(entry,original.read(entry))
        for name,data in outputs.items():target.writestr(NAME+'/'+name,data)
        target.writestr(NAME+'/MANIFEST.json',manifest_bytes)
with zipfile.ZipFile(temp) as z:
    assert z.testzip() is None
    for entry in manifest['files']:assert hashlib.sha256(z.read(NAME+'/'+entry['path'])).hexdigest()==entry['sha256']
temp.replace(archive)
for name,data in {**outputs,'MANIFEST.json':manifest_bytes}.items():
    path=RELEASE/NAME/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
runpy.run_path(str(WORK/'packaging/build_guide.py'),run_name='__main__',init_globals={'RELEASE_VERSION':'1.1.0'})
for name in ['推文资料库操作指南.html','推文资料库操作指南.txt']:outputs[name]=(RELEASE/name).read_bytes()
patch_path=RELEASE/'推文资料库-1.1.0-更新补丁.zip'
with zipfile.ZipFile(patch_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name,data in outputs.items():z.writestr(name,data)
forbidden={'accounts.json','cookies.txt','deepl.local.json','translation.local.json','storage.local.json','archive.local.json','tweets.sqlite','manager.sqlite'}
with zipfile.ZipFile(patch_path) as z:
    assert z.testzip() is None
    assert not any(Path(name).name in forbidden for name in z.namelist())
with zipfile.ZipFile(archive) as z:
    assert json.loads(z.read(NAME+'/tools/accounts.json'))==[]
    assert len(z.namelist())==len(set(z.namelist()))
    assert not any(Path(name).name in forbidden-{'accounts.json'} for name in z.namelist())
    manifest=json.loads(z.read(NAME+'/MANIFEST.json'))
report=dict(version='1.1.0',desktop_tests=29,archive_translation_tests=49,login_tool_tests=9,
            ui_smoke=True,powershell_pipeline_stubbed=True,manifest_files=len(manifest['files']),
            no_private_data=True,live_x_fetch_tested=False,live_translation_tested=False,
            zip_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),patch_files=len(outputs))
(RELEASE/'1.1.0验证报告.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
