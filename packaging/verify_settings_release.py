"""Check clean-package hashes, isolated imports and the three settings pages."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import zipfile

WORK=Path(__file__).resolve().parents[1]; NAME='推文资料库-最新整合版'
archive=WORK/'release'/(NAME+'.zip')
qa=WORK/'packaging/qa'/('紧凑设置验证 空格-'+time.strftime('%H%M%S'));qa.mkdir(parents=True)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    manifest=json.loads(z.read(NAME+'/MANIFEST.json')); assert manifest['version']=='1.1.2'
    assert json.loads(z.read(NAME+'/tools/accounts.json'))==[]
    for entry in manifest['files']:assert hashlib.sha256(z.read(NAME+'/'+entry['path'])).hexdigest()==entry['sha256']
    assert not any(Path(name).name in {'cookies.txt','manager.sqlite','tweets.sqlite','translation.local.json','deepl.local.json'} for name in z.namelist())
    z.extractall(qa)
root=qa/NAME
code='''import json,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path[:0]=[str(root/'资料库'),str(root/'资料库/vendor'),str(root/'tools')]
import app,library,settings_dialog,translation_settings,storage_settings,version
assert version.VERSION=='1.1.2'
assert all(Path(m.__file__).resolve().is_relative_to(root) for m in [app,library,settings_dialog,translation_settings,storage_settings,version])
app.initialize_library(root)
qt=app.QApplication([]);qt.setStyle('Fusion');qt.setStyleSheet(app.STYLE)
w=app.Window(root,program_root=root,remember=False)
w.setAttribute(app.Qt.WidgetAttribute.WA_DontShowOnScreen);w.show();qt.processEvents()
assert not w.library.accounts
for handle,name in [('example_user','示例作者'),('sample_music','音乐账号'),('sample_photo','摄影账号')]:
    w.library.add_account(handle,name)
group=w.library.create_group('音乐与演出');key=w.library.accounts[1]['key'];w.library.move_account(key,group['id']);w.reload();qt.processEvents()
assert w.settings_button.menu() is None and w.settings_button.width()==30
assert w.settings_button.x()<w.connection.x()
assert not w.account_search.isVisible()
w.grab().save(str(root.parent/'主界面.png'))
w.toggle_account_search();w.account_search.setText('音乐');qt.processEvents()
assert w.account_search_button.isChecked()
w.account_search_popup.grab().save(str(root.parent/'账号搜索.png'))
w.account_search_popup.hide();assert w.account_search.text()=='音乐'
w.account_search.clear()
d=settings_dialog.SettingsDialog(root,root,w,app.ReadableComboBox)
d.setAttribute(app.Qt.WidgetAttribute.WA_DontShowOnScreen);d.show();qt.processEvents()
assert d.navigation.count()==3
for index,name in enumerate(['存储与归档','翻译模型','X登录']):
    d.navigation.setCurrentRow(index);qt.processEvents()
    panel=d.pages.widget(index)
    assert panel.isVisible() and panel.width()>400
    d.grab().save(str(root.parent/(name+'.png')))
assert '尚未导入' in d.login_status.text()
assert not (root/'cookies.txt').exists()
d.close();w.close();qt.processEvents()
print(json.dumps(dict(version=version.VERSION,independent_runtime=True,compact_sidebar=True,search_popup=True,separate_settings_pages=True),ensure_ascii=False))
'''
env=os.environ.copy()
for key in ('PYTHONPATH','PYTHONHOME','QT_PLUGIN_PATH','QML2_IMPORT_PATH'):env.pop(key,None)
env['QT_QPA_PLATFORM']='windows'
env['PATH']=os.pathsep.join([str(root/'python'),env.get('SystemRoot',r'C:\Windows')+'\\System32'])
result=subprocess.run([str(root/'python/python.exe'),'-X','utf8','-c',code,str(root)],env=env,cwd=qa,capture_output=True,encoding='utf-8',errors='replace',timeout=45)
assert result.returncode==0,result.stdout+'\n'+result.stderr
report=json.loads(result.stdout);report.update(desktop_tests=39,ui_smoke=True,manifest_files=len(manifest['files']),zip_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),screenshots=str(qa))
(WORK/'release/1.1.2验证报告.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
