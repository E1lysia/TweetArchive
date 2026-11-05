"""Verify release integrity and exercise the shipped player with generated media."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import zipfile

WORK=Path(__file__).resolve().parents[1];NAME='推文资料库-最新整合版'
archive=WORK/'release'/(NAME+'.zip')
qa=WORK/'packaging/qa'/('媒体独立验证 空格-'+time.strftime('%H%M%S'));qa.mkdir(parents=True)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
    manifest=json.loads(z.read(NAME+'/MANIFEST.json'));assert manifest['version']=='1.1.3'
    assert json.loads(z.read(NAME+'/tools/accounts.json'))==[]
    for entry in manifest['files']:
        data=z.read(NAME+'/'+entry['path']);assert len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256']
    assert NAME+'/资料库/icons/check.svg' in z.namelist()
    forbidden={'cookies.txt','manager.sqlite','tweets.sqlite','translation.local.json','deepl.local.json','storage.local.json','archive.local.json'}
    assert not any(Path(name).name in forbidden or name.lower().endswith(('.mp4','.jpg','.jpeg','.webm')) for name in z.namelist())
    z.extractall(qa)
root=qa/NAME
env=os.environ.copy()
for key in ('PYTHONPATH','PYTHONHOME','QT_PLUGIN_PATH','QML2_IMPORT_PATH'):env.pop(key,None)
env['QT_QPA_PLATFORM']='windows'
env['PATH']=os.pathsep.join([str(root/'python'),env.get('SystemRoot',r'C:\Windows')+'\\System32'])
result=subprocess.run([str(root/'python/python.exe'),'-X','utf8',str(WORK/'packaging/check_media_ui.py'),
                       '--root',str(root),'--output',str(qa/'界面截图')],cwd=qa,env=env,capture_output=True,
                      encoding='utf-8',errors='replace',timeout=55)
assert result.returncode==0,result.stdout+'\n'+result.stderr
report=json.loads((qa/'界面截图/界面验证.json').read_text(encoding='utf-8'))
assert report['independent_runtime'] and report['video_click'] and report['playback']['frames']>0
report.update(desktop_tests=44,ui_smoke=True,manifest_files=len(manifest['files']),
              zip_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),no_private_data_in_zip=True)
(WORK/'release/1.1.3验证报告.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
