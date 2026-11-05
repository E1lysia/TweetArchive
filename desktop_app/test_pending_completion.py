"""The pending page queues ID completion in the correct stable account scope."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import app as manager

qt = manager.QApplication.instance() or manager.QApplication([])


class PendingCompletionUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        manager.initialize_library(self.root)
        accounts = [dict(key=k, handle='@'+k, name=k, folder=k) for k in ('a', 'b')]
        (self.root / 'tools/accounts.json').write_text(json.dumps(accounts), encoding='utf-8')
        for account in accounts:
            (self.root / account['key']).mkdir()
            (self.root / account['key'] / 'old.jpg').write_bytes(b'fixture')
        with closing(sqlite3.connect(self.root / '_推文归档/tweets.sqlite')) as db, db:
            for key in ('a', 'b'):
                doc = dict(tweet_id='1500000000000000000', status='pending', content='', author=key,
                           images=[key+'/old.jpg'], videos=[], date_beijing='2020-01-01T12:00:00+08:00')
                db.execute('INSERT INTO tweets VALUES(?,?,?,?)', (key, doc['tweet_id'], 'pending', json.dumps(doc)))
        self.w = manager.Window(self.root, program_root=self.root)

    def tearDown(self):
        self.w.close()
        qt.processEvents()
        self.temp.cleanup()

    def test_brand_navigation_and_pending_page_are_distinct_from_recent_sync(self):
        self.assertIn('TweetArchive', self.w.windowTitle())
        self.assertIn('TweetArchive', self.w.topbar_brand.text())
        self.assertIn('视频库', self.w.nav['videos'].text())
        self.w.kind.setTypes(['quote'])
        self.w.set_account('a')
        self.w.set_mode('pending')
        self.assertEqual(len(self.w.results), 1)
        self.assertFalse(self.w.kind.isEnabled())
        self.assertTrue(self.w.sync_button.isHidden())
        self.assertFalse(self.w.complete_pending_button.isHidden())
        self.w.set_mode('all')
        self.assertTrue(self.w.complete_pending_button.isHidden())
        self.assertFalse(self.w.sync_button.isHidden())
        self.assertEqual(self.w.kind.types(), {'quote'})

    def test_button_targets_account_not_search_filter_or_recent_scan(self):
        self.w.set_account('b')
        self.w.set_mode('pending')
        self.w.search.setText('no matches')
        self.w.filter()
        self.assertEqual(self.w.results, [])
        self.assertTrue(self.w.complete_pending_button.isEnabled())
        with mock.patch.object(self.w.queue, 'enqueue') as enqueue, mock.patch.object(self.w, 'show_tasks'):
            self.w.complete_pending_button.click()
        self.assertEqual(enqueue.call_count, 1)
        args = enqueue.call_args.args[2]
        self.assertIn('--complete-pending', args)
        self.assertIn('--no-translate', args)
        self.assertEqual(args[args.index('--index')+1], '2')
        self.assertEqual(enqueue.call_args.kwargs['context']['account'], 'b')
        self.w.set_account('')
        with mock.patch.object(self.w.queue, 'enqueue') as enqueue, mock.patch.object(self.w, 'show_tasks'):
            self.w.complete_pending_tweets()
        self.assertEqual(enqueue.call_count, 2)

    def test_partial_completion_has_its_own_result_and_readable_failure_reason(self):
        self.w.set_account('a')
        self.w.set_mode('pending')
        with self.w.library.state:
            task_id = self.w.library.state.execute("INSERT INTO tasks(title,status,log) VALUES('补全推文','部分完成','')").lastrowid
        self.w.queue.last_finished = dict(id=task_id, partial=True, success=False,
            context=dict(kind='sync', account='a', name='a', complete_pending=True, before=dict(pending=1)))
        self.w.task_completed()
        self.assertIn('部分完成', self.w.notice_text.text())
        self.assertIn('仍待补全 1 条', self.w.notice_text.text())
        self.w.current['completion_error'] = dict(reason='当前登录账号没有读取权限')
        self.w.show_text()
        self.assertIn('当前登录账号没有读取权限', self.w.body.toPlainText())


if __name__ == '__main__':
    unittest.main()
