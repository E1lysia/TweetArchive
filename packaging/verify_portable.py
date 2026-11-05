"""Verify the shipped ZIP from a fresh extracted path, independently of D: runtime."""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import zipfile
from pathlib import Path

WORK=Path(__file__).resolve().parents[1]
NAME='TweetArchive-1.1.0-win-x64'
ARCHIVE=WORK/'release'/(NAME+'.zip')
QA=WORK/'packaging/qa'/('解压验证 空格-'+time.strftime('%H%M%S'))
QA.mkdir(parents=True,exist_ok=False)
report={}
with zipfile.ZipFile(ARCHIVE) as archive:
    assert archive.testzip() is None
    names=archive.namelist()
    forbidden={'cookies.txt','deepl.local.json','translation.local.json','tweets.sqlite','manager.sqlite','启动错误.log'}
    assert not [n for n in names if Path(n).name in forbidden]
    assert not any(n.lower().endswith(('.jpg','.mp4','.webm','.jpeg')) for n in names)
    archive.extractall(QA)
ROOT=QA/NAME
manifest=json.loads((ROOT/'MANIFEST.json').read_text(encoding='utf-8'))
for entry in manifest['files']:
    assert hashlib.sha256((ROOT/entry['path']).read_bytes()).hexdigest()==entry['sha256'],entry['path']
report['manifest_files']=len(manifest['files'])
report['no_private_data']=True
env=os.environ.copy()
for key in ('PYTHONPATH','PYTHONHOME','QT_PLUGIN_PATH','QML2_IMPORT_PATH'):
    env.pop(key,None)
env['DOTNET_ROOT']=str(QA/'no-dotnet')
env['DOTNET_MULTILEVEL_LOOKUP']='0'
env['QT_QPA_PLATFORM']='offscreen'
env['PATH']=os.pathsep.join([str(ROOT/'python'),env.get('SystemRoot',r'C:\Windows')+'\\System32'])
def run(args,timeout=30):
    p=subprocess.run(args,cwd=QA,env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=timeout)
    if p.returncode:
        raise RuntimeError(str(args[:2])+' failed: '+p.stdout[-1000:]+p.stderr[-1000:])
    return p.stdout

report['gallery_dl']=run([str(ROOT/'python/python.exe'),'-X','utf8','-m','gallery_dl','--config-ignore','--version']).strip()
code='''
import sys,json
from pathlib import Path
root=Path(sys.argv[1])
sys.path[:0]=[str(root/'资料库'),str(root/'资料库/vendor'),str(root/'tools')]
import app,PySide6,shiboken6,requests,PIL,gallery_dl,translation_engine
app.initialize_library(root)
qt=app.QApplication([]); qt.setStyle('Fusion'); qt.setStyleSheet(app.STYLE)
w=app.Window(root,remember=False)
w.setAttribute(app.Qt.WidgetAttribute.WA_DontShowOnScreen)
w.show(); qt.processEvents(); w.layout_cards(); qt.processEvents()
assert not w.results and not w.library.accounts
assert 'text' in w.nav
w.kind.setTypes(['original','quote'])
assert w.kind.types()=={'original','quote'}
assert w.capture_browse()['types']==['original','quote']
storage=app.StorageSettings(root,w); storage.reject()
assert '还没有归档账号' in w.empty.text()
assert len(translation_engine.PROVIDERS)==5
d=app.TranslationSettings(root,w,app.ReadableComboBox)
d.engine.setCurrentIndex(d.engine.findData('deepseek'))
assert not d.key.text() and d.model.text()=='deepseek-flash'
d.reject()
w.grab().save(str(root.parent/'empty-library.png'))
modules=[app,PySide6,shiboken6,requests,PIL,gallery_dl,translation_engine]
assert all(Path(m.__file__).resolve().is_relative_to(root) for m in modules)
print(json.dumps(dict(qt=PySide6.__version__,first_run=True,engines=5)))
w.close(); qt.quit()
'''
report['gui']=json.loads(run([str(ROOT/'python/python.exe'),'-X','utf8','-c',code,str(ROOT)]))
report['root']=str(ROOT)
report['launcher_bytes']=(ROOT/'推文资料库.exe').stat().st_size
# Playback is exercised only in the QA extraction; this fixture is NEVER put in the ZIP.
fixture=next(Path(r'D:\gallery-dl\青木阳菜\视频GIF').rglob('*.mp4'))
shutil.copy2(fixture,ROOT/'fixture.mp4')
(ROOT/'tools/accounts.json').write_text(json.dumps([dict(key='demo',name='演示',handle='@demo',folder='demo')]),encoding='utf-8')
doc=dict(account='demo',tweet_id='1',author='演示',handle='@demo',status='archived',content='视频验证',translation_zh=None,images=[],videos=['fixture.mp4'],post_type='original',date_beijing='2026-11-03T12:00:00+08:00',url='https://x.com/demo/status/1')
with sqlite3.connect(ROOT/'_推文归档/tweets.sqlite') as db:
    db.execute('INSERT INTO tweets VALUES(?,?,?,?)',('demo','1','archived',json.dumps(doc)))
run([str(ROOT/'python/python.exe'),'-X','utf8',str(ROOT/'资料库/app.py'),'--root',str(ROOT),'--video-smoke',str(QA/'video.json')])
video=json.loads((QA/'video.json').read_text(encoding='utf-8'))
assert video['has_video'] and video['duration']>0 and video['position']>0 and not video['error'],video
report['video']={k:video[k] for k in ('has_video','duration','position','error')}
output=WORK/'release/1.1.0独立解压验证.json'
output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
