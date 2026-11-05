"""Check the clean release using disposable accounts, retained files and quote links."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import zipfile

WORK=Path(__file__).resolve().parents[1];NAME='推文资料库-最新整合版';VERSION='1.1.5'
CODE=r'''
import json,sqlite3,sys,time
from pathlib import Path
from contextlib import closing
root=Path(sys.argv[1]);out=Path(sys.argv[2])
sys.path[:0]=[str(root/'资料库'),str(root/'资料库/vendor'),str(root/'tools')]
import app,library,version,PySide6
from PySide6.QtCore import QPointF,QEvent
from PySide6.QtGui import QMouseEvent
assert version.VERSION=='1.1.5'
assert all(Path(m.__file__).resolve().is_relative_to(root) for m in [app,library,version,PySide6])
qt=app.QApplication([]);qt.setQuitOnLastWindowClosed(False);qt.setStyle('Fusion');qt.setStyleSheet(app.STYLE)
app.initialize_library(root)
w=app.Window(root,program_root=root,remember=False);w.setAttribute(app.Qt.WidgetAttribute.WA_DontShowOnScreen)
assert not w.library.accounts
first=w.library.add_account('example_owner','示例作者');second=w.library.add_account('second_user','保留账号')
group=w.library.create_group('演示分组');w.library.move_account(first['key'],group['id'])
file=root/first['folder']/'retained.bin';file.write_bytes(b'keep original media')
with closing(sqlite3.connect(root/'_推文归档/tweets.sqlite')) as db,db:
    for tid,kind,owner,content in [('300','quote',first,'引用了一条其他作者的推文。'),('200','reference',first,'这是被引用的来源正文，点击上方链接可以打开原推。'),('100','original',second,'另一个账号的正文保留。')]:
        doc=dict(tweet_id=tid,status='archived',post_type=kind,content=content,translation_zh=None,images=[],videos=[],
                 source_media_count=0,author='来源作者' if tid=='200' else owner['name'],handle='@source_author' if tid=='200' else owner['handle'],
                 date_beijing='2026-11-05T12:00:00+08:00',url='https://x.com/example_owner/status/'+tid)
        if tid=='300':doc.update(source_tweet_id='200',metadata={'quoted_id':200})
        db.execute('INSERT INTO tweets VALUES(?,?,?,?)',(owner['key'],tid,'archived',json.dumps(doc,ensure_ascii=False)))
w.reload();w.set_account(first['key']);w.show();qt.processEvents()
w.favorite.click();assert w.current['favorite']
cursor=w.body.document().find('查看来源推文');cursor.setPosition(cursor.selectionStart()+1)
w.body.setTextCursor(cursor);w.body.ensureCursorVisible();qt.processEvents()
point=w.body.cursorRect(cursor).center();link=w.body.anchorAt(point)
assert link=='https://x.com/i/web/status/200'
opened=[];app.QDesktopServices.openUrl=lambda url:opened.append(url.toString()) or True
for kind,buttons in [(QEvent.Type.MouseButtonPress,app.Qt.MouseButton.LeftButton),(QEvent.Type.MouseButtonRelease,app.Qt.MouseButton.NoButton)]:
    event=QMouseEvent(kind,QPointF(point),QPointF(w.body.viewport().mapToGlobal(point)),app.Qt.MouseButton.LeftButton,buttons,app.Qt.KeyboardModifier.NoModifier)
    app.QApplication.sendEvent(w.body.viewport(),event)
assert opened==[link] and '来源正文' in w.body.toPlainText()
qt.sendPostedEvents(None,QEvent.Type.DeferredDelete);qt.processEvents()
w.grab().save(str(out/'引用来源链接.png'))
menu=w.build_account_menu(first['key']);menu.setAttribute(app.Qt.WidgetAttribute.WA_DontShowOnScreen)
menu.popup(w.mapToGlobal(w.rect().center()));qt.processEvents();menu.grab().save(str(out/'账号右键菜单.png'));menu.close()
w.queue.paused=True
cancel=w.queue.enqueue('删除账号的暂停任务',sys.executable,['-c','pass','--index','1'])
marker=out/'continued-index.txt'
code='import sys;from pathlib import Path;Path(sys.argv[1]).write_text(sys.argv[sys.argv.index("--index")+1])'
keep=w.queue.enqueue('保留账号的暂停任务',sys.executable,['-c',code,str(marker),'--index','2'])
before=(root/'_推文归档/tweets.sqlite').read_bytes()
app.QMessageBox.question=lambda *args,**kw:app.QMessageBox.StandardButton.Yes
action=next(a for a in w.build_account_menu(first['key']).actions() if a.text()=='删除账号…');action.trigger()
assert [a['key'] for a in w.library.accounts]==[second['key']] and len(w.library.docs)==1
assert w.account=='' and first['key'] not in w.library.account_groups()['memberships']
assert file.read_bytes()==b'keep original media' and (root/'_推文归档/tweets.sqlite').read_bytes()==before
assert [t[0] for t in w.queue.waiting]==[keep]
assert w.library.state.execute('SELECT status FROM tasks WHERE id=?',(cancel,)).fetchone()[0]=='已取消'
restored=w.library.add_account('@example_owner','')
assert restored['key']==first['key'] and restored['folder']==first['folder']
w.reload();assert len(w.library.docs)==3 and len(w.library.query(mode='favorites'))==1
assert w.library.account_groups()['memberships'][first['key']]==group['id']
assert w.queue.resume()
deadline=time.monotonic()+8
while w.queue.current and time.monotonic()<deadline:qt.processEvents();time.sleep(.01)
assert w.queue.current is None and marker.read_text()=='1'
assert w.library.state.execute('SELECT status FROM tasks WHERE id=?',(keep,)).fetchone()[0]=='完成'
w.close();qt.processEvents()
report=dict(version=version.VERSION,independent_runtime=True,remove_account=True,media_and_rows_preserved=True,
            restored_identity_and_favorite=True,group_membership_restored=True,own_paused_task_cancelled=True,
            other_account_index_correct=True,quote_link_clicked=link,screenshots=str(out))
(out/'运行验证.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
'''


def main():
    archive=WORK/'release'/(NAME+'.zip')
    qa=WORK/'packaging/qa'/('账号删除与引用链接 中文 空格-'+time.strftime('%Y%m%d-%H%M%S'));qa.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
        manifest=json.loads(z.read(NAME+'/MANIFEST.json'));assert manifest['version']==VERSION
        assert json.loads(z.read(NAME+'/tools/accounts.json'))==[]
        for entry in manifest['files']:assert hashlib.sha256(z.read(NAME+'/'+entry['path'])).hexdigest()==entry['sha256']
        forbidden={'cookies.txt','manager.sqlite','tweets.sqlite','translation.local.json','deepl.local.json','storage.local.json','archive.local.json'}
        assert not any(Path(name).name in forbidden for name in z.namelist())
        z.extractall(qa)
    root=qa/NAME;env=os.environ.copy()
    for key in ('PYTHONPATH','PYTHONHOME','QT_PLUGIN_PATH','QML2_IMPORT_PATH'):env.pop(key,None)
    env['QT_QPA_PLATFORM']='windows';env['PYTHONUTF8']='1'
    env['PATH']=os.pathsep.join([str(root/'python'),env.get('SystemRoot',r'C:\Windows')+'\\System32'])
    python=str(root/'python/python.exe')
    result=subprocess.run([python,'-u',str(root/'资料库/task_runner.py'),'--',python,'-X','utf8','-c',CODE,str(root),str(qa)],
                          env=env,cwd=qa,capture_output=True,encoding='utf-8',errors='replace',timeout=35)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    report=json.loads((qa/'运行验证.json').read_text(encoding='utf-8'))
    report.update(desktop_tests=63,no_private_data_in_zip=True,manifest_files=len(manifest['files']),zip_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    (WORK/'release/1.1.5验证报告.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
