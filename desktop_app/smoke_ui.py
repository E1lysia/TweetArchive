"""Exercise application state and its asynchronous job queue using a disposable library."""
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import app as manager
from PIL import Image
from PySide6.QtCore import QPoint, QPointF
from PySide6.QtGui import QWheelEvent

qt = manager.QApplication([])
qt.setStyle('Fusion')
qt.setStyleSheet(manager.STYLE)
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    (root / 'tools').mkdir()
    (root / '_推文归档').mkdir()
    accounts = [dict(key='a', name='测试账号', handle='@tester', folder='tester', url='https://x.com/tester/media')]
    accounts += [dict(key=f'other{i}', name=f'其他人物{i}', handle=f'@other{i}', folder=f'other{i}', url=f'https://x.com/other{i}/media') for i in range(35)]
    (root / 'tools/accounts.json').write_text(json.dumps(accounts), encoding='utf-8')
    Image.new('RGB', (100, 150), '#67d6bd').save(root / 'photo.jpg')
    Image.new('RGB', (150, 100), '#cc6677').save(root / 'photo2.jpg')
    Image.new('RGB', (100, 100), '#6677cc').save(root / 'photo3.jpg')
    db = sqlite3.connect(root / '_推文归档/tweets.sqlite')
    db.execute('CREATE TABLE tweets(account TEXT,tweet_id TEXT,status TEXT,document TEXT)')
    for i in range(60):
        d = dict(account='a', tweet_id=str(100 + i), author='测试', handle='@tester', status='archived', content='日本語原文', translation_zh='中文测试译文', images=['photo.jpg'], videos=[], date_beijing='2026-10-01T00:00:00+08:00', url=f'https://x.com/tester/status/{100+i}')
        if i < 30:
            d['date_beijing'] = '2024-06-01T00:00:00+08:00'
        if i == 59:
            d['images'] = ['photo.jpg', 'photo2.jpg', 'photo3.jpg']
        db.execute('INSERT INTO tweets VALUES(?,?,?,?)', ('a', d['tweet_id'], 'archived', json.dumps(d)))
    db.commit()
    db.close()
    window = manager.Window(root)
    window.show()
    qt.processEvents()
    assert len(window.results) == 60 and window.cards.count() == 48
    assert not hasattr(window, 'layout_choice') and window.tags.isHidden()
    assert window.favorite.parent() == window.reading_tools and window.first.text() == '«'
    assert window.language.count() == 3
    window.layout_cards()
    qt.processEvents()
    controls = [window.sync_button, window.translate_button, *window.view.buttons]
    before_y = [w.mapTo(window.feed_scroll.viewport(), QPoint(0, 0)).y() for w in controls]
    window.feed_scroll.verticalScrollBar().setValue(110)
    qt.processEvents()
    assert window.feed_scroll.verticalScrollBar().value() == 110
    assert [w.mapTo(window.feed_scroll.viewport(), QPoint(0, 0)).y() for w in controls] == [y-110 for y in before_y]
    assert window.cards.verticalScrollBar().maximum() == 0
    window.feed_scroll.verticalScrollBar().setValue(0)
    wheel_event = QWheelEvent(QPointF(20,20), QPointF(20,20), QPoint(), QPoint(0,-120),
                              manager.Qt.MouseButton.NoButton, manager.Qt.KeyboardModifier.NoModifier,
                              manager.Qt.ScrollPhase.NoScrollPhase, False)
    qt.sendEvent(window.cards.viewport(), wheel_event)
    qt.processEvents()
    assert window.feed_scroll.verticalScrollBar().value() > 0
    window.feed_scroll.verticalScrollBar().setValue(0)
    window.splitter.setSizes([200, 600, 700])
    qt.processEvents()
    window.layout_cards()
    qt.processEvents()
    for control in controls:
        pos = control.mapTo(window.feed_scroll.viewport(), QPoint(0,0))
        assert pos.x() >= 0 and pos.x()+control.width() <= window.feed_scroll.viewport().width()
    window.media.setCurrentIndex(0)
    window.update_more_actions()
    assert not window.source_action.isVisible() and window.tags_action.isEnabled()
    window.account_search.setText('@TESTER')
    assert sum(not window.account_box.itemAt(i).widget().isHidden() for i in range(window.account_box.count())) == 1
    window.account_search.setText('不存在的账号')
    assert not window.account_empty.isHidden()
    window.account_search.clear()
    assert window.account_box.count() == 36
    def wheel(delta):
        event = QWheelEvent(QPointF(20, 20), QPointF(20, 20), QPoint(), QPoint(0, delta),
                            manager.Qt.MouseButton.NoButton, manager.Qt.KeyboardModifier.NoModifier,
                            manager.Qt.ScrollPhase.NoScrollPhase, False)
        qt.sendEvent(window.photo, event)
    wheel(-120)
    assert window.media.currentIndex() == 1
    wheel(-120)
    assert window.media.currentIndex() == 2
    wheel(-120)
    assert window.media.currentIndex() == 2
    wheel(120)
    assert window.media.currentIndex() == 1
    wheel(60)
    wheel(60)
    assert window.media.currentIndex() == 0
    window.change_page(1)
    assert window.cards.count() == 12
    window.search.setText('159')
    window.filter()
    assert window.cards.count() == 1
    window.tags.setText('现场 演出')
    window.save_tags()
    window.toggle_favorite()
    window.search.clear()
    window.set_mode('all')
    window.cards.setCurrentRow(1)
    window.cards.setCurrentRow(0)
    assert window.current['favorite'] and window.current['tags'] == '现场 演出'
    window.search.clear()
    window.set_mode('favorites')
    assert len(window.results) == 1
    assert window.current['tags'] == '现场 演出'
    window.language.setCurrentIndex(1)
    assert '中文测试译文' in window.body.toPlainText() and '日本語原文' not in window.body.toPlainText()
    window.language.setCurrentIndex(2)
    assert '日本語原文' in window.body.toPlainText() and '中文测试译文' not in window.body.toPlainText()
    window.library.reload()
    assert len(window.library.query(search='现场 演出')) == 1
    window.queue.enqueue('本地成功测试', sys.executable, ['-c', 'print("中文任务成功")'])
    window.queue.enqueue('本地失败测试', sys.executable, ['-c', 'import sys; print("保留错误日志"); sys.exit(3)'])
    deadline = time.monotonic() + 10
    while (window.queue.current or window.queue.waiting) and time.monotonic() < deadline:
        qt.processEvents()
        time.sleep(.01)
    assert not window.queue.current and not window.queue.waiting, 'Queue failed to finish'
    tasks = window.library.state.execute('SELECT status,log FROM tasks ORDER BY id').fetchall()
    assert tasks[0][0] == '完成' and '中文任务成功' in tasks[0][1], tasks
    assert tasks[1][0] == '失败' and '保留错误日志' in tasks[1][1], tasks
    window.show_tasks()
    qt.processEvents()
    assert window.task_list.count() == 2
    window.task_dialog.close()
    window.set_mode('all')
    window.set_period('2024')
    assert len(window.results) == 30
    assert window.time_counts()['2024-06'] == 30
    window.set_period('2026-10')
    assert len(window.results) == 30
    window.jump_edge(True)
    assert not window.period and window.current['tweet_id'] == '100'
    assert window.sort.currentIndex() == 0 and window.page == 1
    window.jump_edge(False)
    assert window.current['tweet_id'] == '159'
    window.set_period('2026-10')
    window.sort.buttons[1].click()
    assert window.period == '2026-10' and len(window.results) == 30
    window.jump_edge(False)
    assert not window.period and window.current['tweet_id'] == '159'
    assert window.sort.currentIndex() == 1 and window.page == 1
    window.jump_edge(True)
    assert window.current['tweet_id'] == '100' and window.sort.currentIndex() == 1
    window.sort.buttons[0].click()
    window.view.buttons[1].click()
    assert window.cards.viewMode() == manager.QListWidget.ViewMode.ListMode
    window.view.buttons[0].click()
    assert window.cards.viewMode() == manager.QListWidget.ViewMode.IconMode
    window.jump_edge(False)
    assert window.current['tweet_id'] == '159'
    window.go_to_page(100)
    assert window.page == 1 and not window.next.isEnabled() and not window.last.isEnabled()
    window.go_to_page(-1)
    assert window.page == 0 and not window.first.isEnabled()
    window.go_to_page(1)
    window.cards.setCurrentRow(4)
    qt.processEvents()
    window.feed_scroll.verticalScrollBar().setValue(100)
    saved = window.capture_browse()
    window.reload()
    qt.processEvents()
    assert window.page == saved['page'] and window.current['tweet_id'] == saved['selected']
    assert window.feed_scroll.verticalScrollBar().value() == saved['scroll']
    window.account_search.setText('@TESTER')
    saved_sizes = window.splitter.sizes()
    # A previously saved classic selection must migrate to the latest reading interface.
    window.save_session()
    legacy = window.library.preference('browse_v2')
    legacy['layout'] = 'classic'
    window.close()
    from contextlib import closing
    with closing(sqlite3.connect(root / '_推文归档/manager.sqlite')) as state_db:
        with state_db:
            state_db.execute('UPDATE preferences SET value=? WHERE key=?', (json.dumps(legacy), 'browse_v2'))
    qt.processEvents()
    reopened = manager.Window(root)
    reopened.show()
    qt.processEvents()
    qt.processEvents()
    assert reopened.page == saved['page'] and reopened.current['tweet_id'] == saved['selected']
    assert reopened.feed_scroll.verticalScrollBar().value() == saved['scroll']
    assert reopened.account_search.text() == '@TESTER'
    assert not hasattr(reopened, 'layout_choice') and reopened.splitter.sizes() == saved_sizes
    reopened.set_period('2024-06')
    reopened.set_mode('images')
    assert reopened.period == '2024-06' and len(reopened.results) == 30
    new_doc = dict(account='a', tweet_id='999', author='测试', handle='@tester', status='archived',
                   content='新正文', translation_zh='新译文', images=['photo.jpg'], videos=[],
                   post_type='quote', account_name='测试账号',
                   date_beijing='2026-11-03T18:00:00+08:00', url='https://x.com/tester/status/999')
    reposted = {**new_doc, 'tweet_id':'1000', 'post_type':'retweet', 'author':'原作者', 'handle':'@origin'}
    # Simulate the child downloader/archive process committing newly classified records.
    code = ('import sqlite3,json,sys; db=sqlite3.connect(sys.argv[1]); '
            'docs=json.loads(sys.argv[2]); '
            'db.executemany("INSERT INTO tweets VALUES(?,?,?,?)", '
            '[(d["account"],d["tweet_id"],d["status"],json.dumps(d)) for d in docs]); '
            'db.commit(); db.close()')
    reopened.queue.enqueue('模拟补新', sys.executable,
                           ['-c', code, str(root / '_推文归档/tweets.sqlite'), json.dumps([new_doc, reposted])],
                           context=dict(kind='sync', account='a', name='测试账号'))
    deadline = time.monotonic() + 10
    while reopened.queue.current and time.monotonic() < deadline:
        qt.processEvents()
        time.sleep(.01)
    assert not reopened.queue.current
    assert '引用 1' in reopened.notice_text.text() and '转推 1' in reopened.notice_text.text()
    assert reopened.period == '2024-06' and len(reopened.results) == 30
    assert any(d['tweet_id'] == '1000' for d in reopened.library.docs)
    reopened.show_updated_latest()
    assert reopened.current['tweet_id'] == '1000' and not reopened.period
    assert '转推' in reopened.detail_type.text() and '原作者' in reopened.detail_type.text()
    reopened.kind.setTypes(['original'])
    assert len(reopened.results) == 60
    reopened.kind.buttons[2].click()
    assert len(reopened.results) == 61
    reopened.kind.buttons[1].click()
    assert [d['tweet_id'] for d in reopened.results] == ['999']
    reopened.kind.buttons[3].click()
    assert len(reopened.results) == 2
    reopened.kind.buttons[2].click()
    assert [d['tweet_id'] for d in reopened.results] == ['1000']
    reopened.kind.buttons[0].click()
    reopened.close()
    qt.processEvents()
print('UI smoke passed: original/quote/retweet filters and provenance, sync refresh, image wheel, account search, browsing restoration and job queue.')
