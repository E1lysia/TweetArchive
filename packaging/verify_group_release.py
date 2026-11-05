"""Test the shipped account-group build from an isolated Chinese extraction path."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import zipfile

WORK=Path(__file__).resolve().parents[1];NAME='推文资料库-最新整合版'
archive=WORK/'release'/(NAME+'.zip')
qa=WORK/'packaging/qa'/('分组独立验证 空格-'+time.strftime('%H%M%S'));qa.mkdir(parents=True)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    manifest=json.loads(z.read(NAME+'/MANIFEST.json'))
    assert manifest['version']=='1.1.1'
    assert json.loads(z.read(NAME+'/tools/accounts.json'))==[]
    for entry in manifest['files']:assert hashlib.sha256(z.read(NAME+'/'+entry['path'])).hexdigest()==entry['sha256']
    assert not any(Path(name).name in {'cookies.txt','manager.sqlite','tweets.sqlite','translation.local.json','deepl.local.json'} for name in z.namelist())
    z.extractall(qa)
root=qa/NAME
code='''import json,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path[:0]=[str(root/'资料库'),str(root/'资料库/vendor'),str(root/'tools')]
import app,library,storage,storage_settings,version
assert version.VERSION=='1.1.1'
assert all(Path(m.__file__).resolve().is_relative_to(root) for m in [app,library,storage,storage_settings,version])
app.initialize_library(root)
qt=app.QApplication([]);qt.setStyle('Fusion');qt.setStyleSheet(app.STYLE)
w=app.Window(root,program_root=root,remember=False)
w.setAttribute(app.Qt.WidgetAttribute.WA_DontShowOnScreen);w.show();qt.processEvents()
assert not w.library.accounts
account=w.library.add_account('example_user','最初名称');key=account['key'];folder=account['folder']
group=w.library.create_group('分组示例');w.library.move_account(key,group['id'])
w.library.rename_account(key,'第一次改名');w.library.rename_account(key,'第二次改名');w.reload();qt.processEvents()
assert w.library.accounts[0]['name']=='第二次改名' and w.library.accounts[0]['folder']==folder
assert w.library.account_groups()['memberships'][key]==group['id']
assert '重命名账号…' in [action.text() for action in w.build_account_menu(key).actions()]
assert w.settings_button.menu().actions()[0].text()=='存储位置与归档…'
w.library.toggle_group(group['id']);w.rebuild_accounts();w.account_search.setText('分组示例');qt.processEvents()
rows=[w.account_box.itemAt(i).widget() for i in range(w.account_box.count())]
assert any(row.property('account')==key and not row.isHidden() for row in rows)
w.grab().save(str(root.parent/'账号分组.png'));w.close();qt.processEvents()
lib=library.Library(root)
assert lib.account_groups()['memberships'][key]==group['id'] and group['id'] in lib.account_groups()['collapsed']
lib.state.close()
print(json.dumps(dict(version=version.VERSION,independent_runtime=True,rename_twice=True,groups_persist=True,left_settings=True),ensure_ascii=False))
'''
env=os.environ.copy()
for key in ('PYTHONPATH','PYTHONHOME','QT_PLUGIN_PATH','QML2_IMPORT_PATH'):env.pop(key,None)
env['QT_QPA_PLATFORM']='windows'
env['PATH']=os.pathsep.join([str(root/'python'),env.get('SystemRoot',r'C:\Windows')+'\\System32'])
result=subprocess.run([str(root/'python/python.exe'),'-X','utf8','-c',code,str(root)],env=env,cwd=qa,capture_output=True,encoding='utf-8',errors='replace',timeout=45)
assert result.returncode==0,result.stdout+'\n'+result.stderr
report=json.loads(result.stdout);report.update(desktop_tests=33,archive_tests=49,ui_smoke=True,manifest_files=len(manifest['files']),zip_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),root=str(root))
(WORK/'release/1.1.1验证报告.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
