"""Verify the shipped 1.1.4 runtime and its durable pause/exit behavior.

Only generated QA fixtures are changed. The runtime check never accesses X,
translation services, the installed application, or a personal archive.
"""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import time
import uuid
import zipfile


WORK = Path(__file__).resolve().parents[1]
NAME = '推文资料库-最新整合版'
VERSION = '1.1.4'


RUNTIME_CHECK = r"""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

root=Path(sys.argv[1]).resolve()
output=Path(sys.argv[2]).resolve()
sys.path[:0]=[str(root/'资料库'),str(root/'资料库/vendor'),str(root/'tools')]
import app, library, task_runner, translation_engine, version
import PySide6
from PySide6 import QtCore

assert version.VERSION=='1.1.4', version.VERSION
modules=[app,library,task_runner,translation_engine,version,PySide6,QtCore]
assert all(Path(module.__file__).resolve().is_relative_to(root) for module in modules)
assert Path(sys.executable).resolve().is_relative_to(root)

qt=app.QApplication([])
qt.setQuitOnLastWindowClosed(False)
qt.setStyle('Fusion')
qt.setStyleSheet(app.STYLE)
app.QMessageBox.question=lambda *a,**kw:app.QMessageBox.StandardButton.Yes

# Keep QA windows hidden while using the real Windows Qt platform and fonts.
OriginalDialog=app.QDialog
class HiddenDialog(OriginalDialog):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.setAttribute(app.Qt.WidgetAttribute.WA_DontShowOnScreen)
app.QDialog=HiddenDialog

def wait_for(predicate, message, seconds=8):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        qt.processEvents()
        if predicate():return
        time.sleep(.015)
    raise AssertionError(message)

def pump(seconds=.25):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        qt.processEvents()
        time.sleep(.01)

fixture=output/'本地任务资料'
fixture.mkdir()
script=output/'本地断点任务.py'
script.write_text('''import sqlite3,sys,time
from pathlib import Path
folder=Path(sys.argv[1]);name=sys.argv[2]
with sqlite3.connect(folder/'checkpoint.sqlite') as db:
    db.execute('CREATE TABLE IF NOT EXISTS saved(name TEXT PRIMARY KEY,value TEXT)')
    db.execute('INSERT OR IGNORE INTO saved VALUES (?,?)',(name,'already-saved'))
    db.commit()
(folder/(name+'.started')).write_text('started',encoding='utf-8')
if name in ('first','exit'):
    while not (folder/(name+'.continue')).exists():time.sleep(.03)
(folder/(name+'.done')).write_text('complete',encoding='utf-8')
print(name+' finished',flush=True)
''',encoding='utf-8')

windows=[]
def new_window():
    window=app.Window(root,program_root=root,remember=False)
    windows.append(window)
    window.setAttribute(app.Qt.WidgetAttribute.WA_DontShowOnScreen)
    window.show()
    qt.processEvents()
    return window

def task_status(window,tid):
    row=window.library.state.execute('SELECT status FROM tasks WHERE id=?',(tid,)).fetchone()
    assert row is not None
    return row[0]

kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
kernel.OpenProcess.restype=wintypes.HANDLE
kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
kernel.WaitForSingleObject.restype=wintypes.DWORD
kernel.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT]
kernel.TerminateProcess.restype=wintypes.BOOL
kernel.CloseHandle.argtypes=[wintypes.HANDLE]
kernel.CloseHandle.restype=wintypes.BOOL
wrapper=None
controller=None
handles=[]
report=dict(version=version.VERSION,independent_runtime=True)
try:
    app.initialize_library(root)
    w=new_window()
    assert not w.library.accounts and not w.queue.current and not w.queue.waiting
    ids=[w.queue.enqueue('本地补新断点验证',sys.executable,[str(script),str(fixture),'first']),
         w.queue.enqueue('后续任务顺序验证',sys.executable,[str(script),str(fixture),'second'])]
    wait_for(lambda:(fixture/'first.started').exists(),'First task did not save its checkpoint')
    assert not (fixture/'second.started').exists()
    assert w.queue.pause()
    wait_for(lambda:w.queue.paused and not w.queue.current and not w.queue.stopping,
             'Pause did not stop the active process')
    assert [task[0] for task in w.queue.waiting]==ids
    assert [task_status(w,tid) for tid in ids]==['已暂停','已暂停']
    assert not (fixture/'first.done').exists() and not (fixture/'second.started').exists()
    with sqlite3.connect(fixture/'checkpoint.sqlite') as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT name,value FROM saved').fetchall()==[('first','already-saved')]
    plans=w.library.preference('task_queue_v1')['tasks']
    assert [task['id'] for task in plans]==ids
    w.show_tasks()
    qt.processEvents()
    assert w.task_resume_button.isEnabled() and not w.task_pause_button.isEnabled()
    screenshot=output/'任务已暂停.png'
    assert w.task_dialog.grab().save(str(screenshot))
    assert w.close()
    wait_for(lambda:w.closed,'Paused window could not close')
    report.update(pause_stops_active=True,pending_order_preserved=True,
                  checkpoint_preserved=True,close_when_paused=True,paused_screenshot=str(screenshot))

    w=new_window()
    assert w.queue.paused and [task[0] for task in w.queue.waiting]==ids
    pump()
    assert not w.queue.current and not (fixture/'second.started').exists()
    (fixture/'first.continue').write_text('resume',encoding='utf-8')
    assert w.queue.resume()
    wait_for(lambda:not w.queue.current and not w.queue.waiting,'Resumed tasks did not finish')
    assert [task_status(w,tid) for tid in ids]==['完成','完成']
    assert (fixture/'first.done').exists() and (fixture/'second.done').exists()
    assert w.library.state.execute('SELECT id FROM tasks ORDER BY id').fetchall()==[(tid,) for tid in ids]
    with sqlite3.connect(fixture/'checkpoint.sqlite') as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT count(*) FROM saved').fetchone()[0]==2
    report.update(reopen_without_auto_start=True,resume_same_task_ids=True,queued_tasks_finish=True)

    exit_id=w.queue.enqueue('运行中退出验证',sys.executable,[str(script),str(fixture),'exit'])
    wait_for(lambda:(fixture/'exit.started').exists(),'Exit task did not start')
    w.close()  # The patched confirmation explicitly selects Pause and exit.
    wait_for(lambda:w.closed,'Closing an active download did not finish')
    assert not (fixture/'exit.done').exists()
    w=new_window()
    assert w.queue.paused and [task[0] for task in w.queue.waiting]==[exit_id]
    pump()
    assert w.queue.current is None and not (fixture/'exit.done').exists()
    (fixture/'exit.continue').write_text('resume',encoding='utf-8')
    assert w.queue.resume()
    wait_for(lambda:not w.queue.current and not w.queue.waiting,'Exit task could not resume')
    assert task_status(w,exit_id)=='完成' and (fixture/'exit.done').exists()
    assert w.close()
    wait_for(lambda:w.closed,'Final window did not close')
    report['close_during_download_and_resume']=True

    # Test actual inherited grandchildren, not only the QProcess wrapper.
    heartbeat=fixture/'grandchild.heartbeat'
    # Use newlines directly for the loop to avoid shell quoting entirely.
    grandchild_code='import os,time\nfrom pathlib import Path\np=Path('+repr(str(fixture))+')\n(p/"grandchild.pid").write_text(str(os.getpid()))\nwhile True:\n (p/"grandchild.heartbeat").write_text(str(time.time_ns()))\n time.sleep(.03)\n'
    child_code=('import os,subprocess,sys,time; from pathlib import Path; '
        'p=Path('+repr(str(fixture))+'); (p/"child.pid").write_text(str(os.getpid())); '
        'subprocess.Popen([sys.executable,"-c",'+repr(grandchild_code)+']); time.sleep(120)')
    wrapper=subprocess.Popen([sys.executable,'-u',str(root/'资料库/task_runner.py'),'--',
                              sys.executable,'-c',child_code],stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    wait_for(lambda:heartbeat.exists() and (fixture/'grandchild.pid').exists(),
             'Descendant heartbeat did not start')
    for name in ('child.pid','grandchild.pid'):
        pid=int((fixture/name).read_text())
        handle=kernel.OpenProcess(0x100001,False,pid) # SYNCHRONIZE | PROCESS_TERMINATE
        assert handle,ctypes.get_last_error()
        handles.append(handle)
    assert all(kernel.WaitForSingleObject(handle,0)==258 for handle in handles)
    previous=heartbeat.read_text()
    wait_for(lambda:heartbeat.read_text()!=previous,'Heartbeat was not advancing')
    wrapper.kill()
    wrapper.wait(timeout=5)
    wait_for(lambda:all(kernel.WaitForSingleObject(handle,0)==0 for handle in handles),
             'A downloader descendant survived wrapper termination')
    stopped=heartbeat.read_text()
    pump(.2)
    assert heartbeat.read_text()==stopped
    report.update(descendant_tree_terminated=True,heartbeat_stopped=True)

    # A GUI crash must not leave the wrapper running and downloading invisibly.
    parent_case=fixture/'父进程退出'
    parent_case.mkdir()
    parent_heartbeat=parent_case/'heartbeat'
    grandchild_code=('import os,time\nfrom pathlib import Path\np=Path('+repr(str(parent_case))+')\n'
        '(p/"grandchild.pid").write_text(str(os.getpid()))\nwhile True:\n '
        '(p/"heartbeat").write_text(str(time.time_ns()))\n time.sleep(.03)\n')
    child_code=('import os,subprocess,sys,time; from pathlib import Path; '
        'p=Path('+repr(str(parent_case))+'); (p/"child.pid").write_text(str(os.getpid())); '
        'subprocess.Popen([sys.executable,"-c",'+repr(grandchild_code)+']); time.sleep(120)')
    arguments=[sys.executable,'-u',str(root/'资料库/task_runner.py'),'--',
               sys.executable,'-c',child_code]
    controller_code=('import subprocess,time; from pathlib import Path; '
        'process=subprocess.Popen('+repr(arguments)+'); '
        'Path('+repr(str(parent_case/'wrapper.pid'))+').write_text(str(process.pid)); time.sleep(120)')
    controller=subprocess.Popen([sys.executable,'-c',controller_code],stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    wait_for(lambda:parent_heartbeat.exists() and (parent_case/'wrapper.pid').exists(),
             'Parent-death fixture did not start')
    parent_handles=[]
    for name in ('wrapper.pid','child.pid','grandchild.pid'):
        handle=kernel.OpenProcess(0x100001,False,int((parent_case/name).read_text()))
        assert handle,ctypes.get_last_error()
        handles.append(handle)
        parent_handles.append(handle)
    assert all(kernel.WaitForSingleObject(handle,0)==258 for handle in parent_handles)
    previous=parent_heartbeat.read_text()
    wait_for(lambda:parent_heartbeat.read_text()!=previous,'Parent-case heartbeat was not advancing')
    controller.kill()  # Only the simulated GUI/controller is terminated here.
    controller.wait(timeout=5)
    wait_for(lambda:all(kernel.WaitForSingleObject(handle,0)==0 for handle in parent_handles),
             'Parent death left a wrapper or downloader running')
    stopped=parent_heartbeat.read_text()
    pump(.2)
    assert parent_heartbeat.read_text()==stopped
    report.update(parent_death_terminates_tree=True,parent_death_heartbeat_stopped=True)
finally:
    if controller is not None and controller.poll() is None:
        controller.kill()
        controller.wait(timeout=5)
    if wrapper is not None and wrapper.poll() is None:
        wrapper.kill()
        wrapper.wait(timeout=5)
    # Handles refer only to the exact synthetic processes opened above; cleanup
    # cannot accidentally target a newly reused PID or any user's process.
    for handle in handles:
        if kernel.WaitForSingleObject(handle,0)==258:
            kernel.TerminateProcess(handle,125)
            kernel.WaitForSingleObject(handle,1000)
        kernel.CloseHandle(handle)
    for window in windows:
        if window.closed:continue
        window.queue.pause()
        wait_for(lambda:not window.queue.current and not window.queue.stopping,
                 'QA task did not stop during cleanup')
        window.close()
        wait_for(lambda:window.closed,'QA window did not close during cleanup')
    qt.processEvents()

report['synthetic_helpers_cleaned_up']=True
(output/'运行验证.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
"""


def verify_release():
    archive = WORK / 'release' / (NAME + '.zip')
    qa = WORK / 'packaging' / 'qa' / (
        '暂停独立验证 中文 空格-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    qa.mkdir(parents=True)
    forbidden = {
        'cookies.txt', 'manager.sqlite', 'tweets.sqlite', 'translation.local.json',
        'deepl.local.json', 'storage.local.json', 'archive.local.json',
    }
    media_suffixes = ('.jpg', '.jpeg', '.mp4', '.webm', '.mkv', '.mov', '.mp3', '.wav')
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        assert len(names) == len(set(names)), 'Duplicate ZIP entries'
        assert package.testzip() is None, 'ZIP checksum failure'
        for name in names:
            path = PurePosixPath(name)
            assert not path.is_absolute() and '..' not in path.parts
            assert path.parts[0] == NAME and '\\' not in name
            assert path.name.lower() not in forbidden
            assert not name.lower().endswith(media_suffixes), 'Personal media in package'
        manifest = json.loads(package.read(NAME + '/MANIFEST.json'))
        assert manifest['version'] == VERSION
        assert json.loads(package.read(NAME + '/tools/accounts.json')) == []
        listed = set()
        for entry in manifest['files']:
            full = NAME + '/' + entry['path']
            assert full not in listed
            listed.add(full)
            data = package.read(full)
            assert len(data) == entry['bytes'], full
            assert hashlib.sha256(data).hexdigest() == entry['sha256'], full
        actual = {name for name in names if not name.endswith('/')}
        assert actual == listed | {NAME + '/MANIFEST.json'}, 'Manifest is incomplete'
        assert NAME + '/资料库/task_runner.py' in actual
        package.extractall(qa)

    root = qa / NAME
    env = os.environ.copy()
    for key in ('PYTHONPATH', 'PYTHONHOME', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH',
                'QML_IMPORT_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH'):
        env.pop(key, None)
    env['QT_QPA_PLATFORM'] = 'windows'
    env['PYTHONUTF8'] = '1'
    env['PATH'] = os.pathsep.join([
        str(root / 'python'), env.get('SystemRoot', r'C:\Windows') + '\\System32',
    ])
    python = str(root / 'python' / 'python.exe')
    # Guard the whole QA process too. A timeout kills this wrapper, which cleans
    # every synthetic controller even if an assertion/Qt startup hangs.
    result = subprocess.run(
        [python, '-u', str(root / '资料库' / 'task_runner.py'), '--',
         python, '-X', 'utf8', '-c', RUNTIME_CHECK, str(root), str(qa)],
        env=env, cwd=qa, capture_output=True, encoding='utf-8', errors='replace', timeout=55,
    )
    (qa / '运行输出.log').write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
    assert result.returncode == 0, result.stdout + '\n' + result.stderr
    report = json.loads((qa / '运行验证.json').read_text(encoding='utf-8'))
    report.update(
        desktop_tests=53, ui_smoke=True, prior_checks_source='reported by release builder',
        manifest_files=len(manifest['files']), no_private_data_in_zip=True,
        zip_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), root=str(root),
    )
    target = WORK / 'release' / (VERSION + '验证报告.json')
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return report


if __name__ == '__main__':
    verify_release()
