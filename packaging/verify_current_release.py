"""Run the integrated package's own Python and Qt against disposable fixtures."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_current_release import validate, NAME, VERSION, ARCHIVE, WORK

ADDITIONAL=r'''
import translation_engine as engine,deepl_translate as translator,adaptive_cards
assert all(Path(m.__file__).resolve().is_relative_to(root) for m in (engine,translator,adaptive_cards))
images=[]
for i,(width,height) in enumerate(((200,400),(400,200),(200,200),(300,400))):
    relative=first['folder']+'/布局示例-'+str(i)+'.png'
    image=app.QImage(width,height,app.QImage.Format.Format_RGB32);image.fill(app.QColor(80+i*30,130,140))
    assert image.save(str(root/relative));images.append(relative)
with closing(sqlite3.connect(root/'_推文归档/tweets.sqlite')) as db,db:
    for i in range(64):
        doc=dict(tweet_id=str(10000-i),status='archived',post_type='quote' if i==4 else 'original',
                 author=first['name'],handle=first['handle'],content='日本語の本文 '+str(i),translation_zh='谢谢大家！',
                 images=[],videos=[],source_media_count=0,date_beijing='2026-11-05T12:00:00+08:00')
        if i==1:doc.update(images=images[:1],source_media_count=1)
        if i==2:doc.update(content='長文。'*100,translation_zh='需要截断的长文字。'*100)
        if i==3:doc.update(images=images,source_media_count=4)
        if i==4:doc.update(source_tweet_id='200',metadata={'quoted_id':200})
        db.execute('INSERT INTO tweets VALUES(?,?,?,?)',(first['key'],doc['tweet_id'],'archived',json.dumps(doc)))
w.reload();w.set_account(first['key']);w.resize(1920,1080);w.splitter.setSizes([210,1150,550])
deadline=time.monotonic()+.15
while time.monotonic()<deadline:qt.processEvents();time.sleep(.005)
w.pool.waitForDone();qt.processEvents();w.layout_cards();qt.processEvents()
assert w.cards.adaptive and w.cards.count()==48
assert w.cards.item(0).sizeHint().height()<w.cards.item(1).sizeHint().height()
assert len({rect.x() for rect in w.cards.card_frames})==2
rects=[w.cards.visualItemRect(w.cards.item(i)) for i in range(w.cards.count())]
assert [rect.y() for rect in rects]==sorted(rect.y() for rect in rects)
assert all(w.cards.indexAt(rect.center()).row()==i for i,rect in enumerate(rects))
assert all(not a.intersects(b) for i,a in enumerate(rects) for b in rects[:i])
assert w.cards.verticalScrollBar().maximum()==0
assert len(w.cards.item(3).data(app.Qt.ItemDataRole.UserRole+3))==4
assert list(w.nav)[:3]==['all','favorites','images']
w.feed_scroll.verticalScrollBar().setValue(350);qt.processEvents();assert w.back_to_top.isVisible()
qt.sendPostedEvents(None,QEvent.Type.DeferredDelete);qt.processEvents()
w.grab().save(str(out/'自适应卡片与返回顶部.png'))
w.back_to_top.click();assert w.feed_scroll.verticalScrollBar().value()==0 and w.back_to_top.isHidden()
w.scope_states['all|'+second['key']]=dict(view=0,sort=0,types=['retweet'])
w.view.setCurrentIndex(1);w.sort.setCurrentIndex(1);w.kind.setTypes(['original','quote'])
display=w.capture_display();w.set_account(second['key']);qt.processEvents()
assert w.capture_display()==display
w.set_account(first['key']);qt.processEvents();assert w.capture_display()==display
w.remember=True;w.save_session()
assert w.library.preference('browse_v2')['display']==display
partial=out/'partial fixture/tweet_archive.py';partial.parent.mkdir()
partial.write_text('import sys;print("offline fixture: partial translation");sys.exit(10)',encoding='utf-8')
task=w.queue.enqueue('部分完成状态验证',sys.executable,['-u',str(partial)])
deadline=time.monotonic()+8
while w.queue.current and time.monotonic()<deadline:qt.processEvents();time.sleep(.01)
assert w.queue.current is None and w.queue.last_finished['partial']
assert w.library.state.execute('SELECT status FROM tasks WHERE id=?',(task,)).fetchone()[0]=='部分完成'
w.close();qt.processEvents()
w=app.Window(root,program_root=root);w.setAttribute(app.Qt.WidgetAttribute.WA_DontShowOnScreen);w.show();qt.processEvents()
assert w.capture_display()==display
w.set_account(second['key']);assert w.capture_display()==display

# Model calls are replaced locally; no credentials or external service are used.
config=engine.load_config(root);config.update(engine='custom',workers=1,max_characters_per_run=1000)
config['profiles']['custom'].update(base_url='http://localhost:1/v1',model='offline-fixture',api_key='')
engine.save_config(root,config)
translation_db=sqlite3.connect(':memory:')
translation_db.execute('CREATE TABLE tweets(account TEXT,tweet_id TEXT,status TEXT,document TEXT)')
for tid,source in [('3','失敗 #Live'),('2','成功 @tester https://example.invalid/?a=1&b=2'),('1','失敗 #Live')]:
    doc=dict(status='archived',content=source,translation_zh=None,metadata={'lang':'ja'})
    translation_db.execute('INSERT INTO tweets VALUES(?,?,?,?)',('fixture',tid,'archived',json.dumps(doc)))
original_request=engine.ChatClient.request
request_state=dict(calls=0,fixed=False)
def fake_request(self,payload):
    request_state['calls']+=1
    value=json.loads(payload['messages'][1]['content'])['text']
    if '失敗' in value and not request_state['fixed']:value='丢失了保护编号的错误译文'
    else:value=value.replace('失敗','恢复译文').replace('成功','成功译文')
    return dict(choices=[dict(finish_reason='stop',message=dict(content=json.dumps({'translation':value},ensure_ascii=False)))])
engine.ChatClient.request=fake_request
try:
    translated=translator.translate_archive(translation_db,root)
    assert translated['status']=='partial' and translated['failed']==2 and translated['translated']==1
    assert request_state['calls']==4 and Path(translated['failure_report']).is_file()
    saved=json.loads(translation_db.execute("SELECT document FROM tweets WHERE tweet_id='2'").fetchone()[0])
    assert '@tester https://example.invalid/?a=1&b=2' in saved['translation_zh']
    assert saved['translation_info']['format']=='placeholders-json-v1'
    request_state['fixed']=True
    translated=translator.translate_archive(translation_db,root)
    assert translated['status']=='complete' and translated['pending']==0 and request_state['calls']==5
finally:
    engine.ChatClient.request=original_request;translation_db.close()
'''


def main():
    digest=hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    qa=WORK/'packaging/qa'/(VERSION+' 独立解压 中文 空格 '+time.strftime('%Y%m%d-%H%M%S'))
    qa.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(ARCHIVE) as z:
        manifest=validate(z);assert manifest['version']==VERSION
        for entry in z.infolist():
            assert (qa/entry.filename).resolve().is_relative_to(qa.resolve())
        z.extractall(qa)
    root=qa/NAME
    old=runpy.run_path(str(WORK/'packaging/verify_account_release.py'))['CODE']
    code=old.replace("assert version.VERSION=='1.1.5'",f"assert version.VERSION=='{VERSION}'")
    assert code.count('w.close();qt.processEvents()')==1
    code=code.replace('w.close();qt.processEvents()',ADDITIONAL+'\nw.close();qt.processEvents()')
    env=os.environ.copy()
    for key in ('PYTHONPATH','PYTHONHOME','QT_PLUGIN_PATH','QML2_IMPORT_PATH'):env.pop(key,None)
    env['QT_QPA_PLATFORM']='windows';env['PYTHONUTF8']='1'
    env['PATH']=os.pathsep.join([str(root/'python'),env.get('SystemRoot',r'C:\Windows')+'\\System32'])
    python=str(root/'python/python.exe')
    result=subprocess.run([python,'-u',str(root/'资料库/task_runner.py'),'--',python,'-X','utf8','-c',code,str(root),str(qa)],
                          cwd=qa,env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=55)
    (qa/'验证输出.txt').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    report=json.loads((qa/'运行验证.json').read_text(encoding='utf-8'))
    assert digest==hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    report.update(zip_sha256=digest,manifest_files=len(manifest['files']),no_private_data_in_zip=True,
                  adaptive_mixed_cards=True,multiple_image_previews=True,back_to_top=True,
                  shared_display_settings=True,restart_preferences=True,placeholder_translation=True,
                  validation_retry_and_skip=True,partial_task_status=True,external_requests=0)
    (WORK/'release'/(VERSION+'验证报告.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
