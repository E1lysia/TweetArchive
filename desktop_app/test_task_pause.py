"""Queue pause/restart checks using disposable local downloads and process trees.

No request is made to X or a translation provider.  The helper's process IDs
are recorded solely so failed assertions still leave no test downloader alive.
"""
import json
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app as manager

qt = manager.QApplication.instance() or manager.QApplication([])


FIXTURE = r'''
import json, os, sqlite3, subprocess, sys, time
from pathlib import Path
root, mode = Path(sys.argv[1]), sys.argv[2]
with (root / 'fixture-pids.jsonl').open('a', encoding='utf-8') as out:
    out.write(json.dumps(dict(pid=os.getpid(), mode=mode)) + '\n')
if mode == 'download':
    with (root / 'runs.txt').open('a', encoding='utf-8') as out:
        out.write('download\n')
    with sqlite3.connect(root / 'download.sqlite') as db:
        db.execute('CREATE TABLE IF NOT EXISTS posts(id TEXT PRIMARY KEY, content TEXT)')
        db.execute("INSERT OR IGNORE INTO posts VALUES('100', 'retained original')")
    (root / 'retained.bin').write_bytes(b'already downloaded media')
    (root / 'download.ready').write_text('ready', encoding='utf-8')
    print('committed original and media', flush=True)
    while not (root / 'release.download').exists():
        time.sleep(.025)
    print('download complete', flush=True)
elif mode == 'second':
    (root / 'second.done').write_text('done', encoding='utf-8')
    print('second complete', flush=True)
elif mode == 'fail':
    print('synthetic failure', flush=True)
    sys.exit(7)
elif mode == 'partial':
    print('synthetic translation partially complete', flush=True)
    sys.exit(10)
elif mode == 'tree':
    child = subprocess.Popen([sys.executable, __file__, str(root), 'branch'])
    while True:
        time.sleep(.025)
elif mode == 'branch':
    child = subprocess.Popen([sys.executable, __file__, str(root), 'heartbeat'])
    while True:
        time.sleep(.025)
elif mode == 'heartbeat':
    while True:
        with (root / 'heartbeat.txt').open('a', encoding='utf-8') as out:
            out.write('beat\n')
        time.sleep(.025)
else:
    raise ValueError('unknown fixture mode')
'''


@unittest.skipUnless(os.name == 'nt', 'Windows downloader process protection')
class TaskPauseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tweet pause 空格 ')
        self.base = Path(self.temp.name)
        self.root = self.base / '资料库'
        self.runtime = self.base / '程序'
        self.runtime.mkdir()
        manager.initialize_library(self.root)
        self.library = manager.Library(self.root)
        self.script = self.base / 'local_download_fixture.py'
        self.script.write_text(FIXTURE, encoding='utf-8')
        self.queues = []
        self.results = []
        self.queue = self.new_queue()

    def new_queue(self):
        queue = manager.TaskQueue(self.library, program_root=self.runtime)
        queue.completed.connect(lambda q=queue: self.results.append(dict(q.last_finished or {})))
        self.queues.append(queue)
        return queue

    def wait_for(self, condition, description, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            qt.processEvents()
            if condition():
                return
            time.sleep(.01)
        self.fail(description + '\nTasks: ' + repr(self.task_rows()))

    def pump_for(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            qt.processEvents()
            time.sleep(.01)

    def enqueue(self, mode, queue=None):
        queue = queue or self.queue
        queue.enqueue('本地测试 ' + mode, sys.executable,
                      ['-u', str(self.script), str(self.root), mode])
        return self.library.state.execute('SELECT max(id) FROM tasks').fetchone()[0]

    def task_rows(self):
        try:
            return self.library.state.execute('SELECT id,title,status FROM tasks ORDER BY id').fetchall()
        except sqlite3.ProgrammingError:
            return [('database already closed',)]

    def status(self, task_id):
        return self.library.state.execute('SELECT status FROM tasks WHERE id=?', (task_id,)).fetchone()[0]

    def pause_and_wait(self, queue=None):
        queue = queue or self.queue
        self.assertTrue(queue.pause())
        self.wait_for(lambda: queue.paused and not queue.stopping and queue.current is None,
                      'Pause did not finish stopping the task tree')
        self.assertEqual(queue.process.state(), manager.QProcess.ProcessState.NotRunning)

    def tearDown(self):
        # Settle queues first, then kill only PIDs written by our own fixture.
        # The latter also catches a faulty runner that leaves descendants alive.
        try:
            for queue in reversed(self.queues):
                queue.paused = True
                if queue.process.state() != manager.QProcess.ProcessState.NotRunning:
                    queue.process.kill()
                    queue.process.waitForFinished(5000)
            qt.processEvents()
            path = self.root / 'fixture-pids.jsonl'
            if path.exists():
                pids = [json.loads(line)['pid'] for line in path.read_text(encoding='utf-8').splitlines()]
                for pid in reversed(pids):
                    subprocess.run(['taskkill.exe', '/PID', str(pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            for queue in self.queues:
                queue.deleteLater()
            qt.processEvents()
        finally:
            self.library.state.close()
            self.temp.cleanup()

    def test_partial_translation_status_and_following_job_continues(self):
        self.script = self.base / 'tweet_archive.py'
        self.script.write_text(FIXTURE, encoding='utf-8')
        first = self.enqueue('partial')
        second = self.enqueue('second')
        self.wait_for(lambda: not self.queue.current and not self.queue.waiting, 'Partial task blocked following job')
        self.assertEqual(self.status(first), '部分完成')
        self.assertEqual(self.status(second), '完成')
        self.assertTrue(self.results[0]['partial'])
        self.assertFalse(self.results[0]['success'])

    def test_unrelated_exit_ten_is_a_failure(self):
        task_id = self.enqueue('partial')
        self.wait_for(lambda: not self.queue.current, 'Fixture did not finish')
        self.assertEqual(self.status(task_id), '失败')
        self.assertFalse(self.results[0]['partial'])

    def test_pause_preserves_saved_content_and_next_job_waits_until_resume(self):
        first = self.enqueue('download')
        second = self.enqueue('second')
        self.wait_for(lambda: (self.root / 'download.ready').exists(), 'Download fixture did not commit')
        self.pause_and_wait()
        self.assertEqual(self.status(first), '已暂停')
        self.assertEqual(self.queue.waiting[0][0], first)
        self.assertEqual([item[0] for item in self.queue.waiting], [first, second])
        self.assertEqual((self.root / 'retained.bin').read_bytes(), b'already downloaded media')
        with closing(sqlite3.connect(self.root / 'download.sqlite')) as db:
            self.assertEqual(db.execute('SELECT id,content FROM posts').fetchall(), [('100', 'retained original')])
        self.pump_for(.2)
        self.assertFalse((self.root / 'second.done').exists())
        self.assertTrue(self.queue.last_finished.get('paused'))
        (self.root / 'release.download').touch()
        self.assertTrue(self.queue.resume())
        self.wait_for(lambda: not self.queue.current and not self.queue.waiting, 'Resumed jobs did not finish')
        self.assertTrue((self.root / 'second.done').exists())
        self.assertEqual(self.status(first), '完成')
        self.assertEqual(self.status(second), '完成')
        self.assertEqual((self.root / 'runs.txt').read_text().splitlines(), ['download', 'download'])
        with closing(sqlite3.connect(self.root / 'download.sqlite')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM posts').fetchone()[0], 1)

    def test_pause_stops_grandchild_heartbeat(self):
        self.enqueue('tree')
        heartbeat = self.root / 'heartbeat.txt'
        self.wait_for(lambda: heartbeat.exists() and heartbeat.stat().st_size >= 20,
                      'Grandchild never started')
        self.pause_and_wait()
        # The QProcess finished signal can precede kernel cleanup of descendants.
        self.pump_for(.25)
        size = heartbeat.stat().st_size
        self.pump_for(.4)
        self.assertEqual(heartbeat.stat().st_size, size, 'A downloader descendant kept running after pause')
        modes = {json.loads(line)['mode'] for line in (self.root / 'fixture-pids.jsonl').read_text().splitlines()}
        self.assertTrue({'tree', 'branch', 'heartbeat'}.issubset(modes))

    def test_paused_queue_restores_after_reopen_without_auto_start(self):
        first = self.enqueue('download')
        second = self.enqueue('second')
        self.wait_for(lambda: (self.root / 'download.ready').exists(), 'Download fixture did not start')
        self.pause_and_wait()
        self.assertTrue(self.library.preference('task_queue_v1', {}))
        old = self.queue
        old.completed.disconnect()
        # Closing and reopening SQLite models a new app instance. The original
        # queue remains idle and is never resumed or allowed to write again.
        self.library.state.close()
        self.library = manager.Library(self.root)
        self.queue = self.new_queue()
        self.assertTrue(self.queue.paused)
        self.assertIsNone(self.queue.current)
        self.assertEqual([item[0] for item in self.queue.waiting], [first, second])
        self.pump_for(.3)
        self.assertEqual((self.root / 'runs.txt').read_text().splitlines(), ['download'])
        self.assertFalse((self.root / 'second.done').exists())
        (self.root / 'release.download').touch()
        self.assertTrue(self.queue.resume())
        self.wait_for(lambda: not self.queue.current and not self.queue.waiting, 'Restored jobs did not finish')
        self.assertEqual([row[2] for row in self.task_rows()], ['完成', '完成'])

    def test_pause_immediately_before_started_keeps_task_resumable(self):
        task_id = self.enqueue('second')
        # No Qt event pumping occurred after enqueue: the started notification
        # has not reached TaskQueue even when Windows created the wrapper fast.
        self.pause_and_wait()
        self.assertEqual(self.status(task_id), '已暂停')
        self.assertEqual([item[0] for item in self.queue.waiting], [task_id])
        self.assertTrue(self.queue.resume())
        self.wait_for(lambda: not self.queue.current and not self.queue.waiting, 'Early-paused task did not resume')
        self.assertEqual(self.status(task_id), '完成')
        self.assertTrue((self.root / 'second.done').exists())

    def test_success_failure_and_following_task_still_complete_normally(self):
        failing = self.enqueue('fail')
        following = self.enqueue('second')
        self.wait_for(lambda: not self.queue.current and not self.queue.waiting, 'Normal queue did not finish')
        self.assertEqual(self.status(failing), '失败')
        self.assertEqual(self.status(following), '完成')
        results = {row['id']: row for row in self.results}
        self.assertFalse(results[failing]['success'])
        self.assertTrue(results[following]['success'])
        self.assertFalse(results[failing].get('paused', False))
        self.assertTrue((self.root / 'second.done').exists())


@unittest.skipUnless(os.name == 'nt', 'Windows downloader process protection')
class TaskPauseWindowTests(unittest.TestCase):
    new_queue = TaskPauseTests.new_queue
    wait_for = TaskPauseTests.wait_for
    pump_for = TaskPauseTests.pump_for
    enqueue = TaskPauseTests.enqueue
    task_rows = TaskPauseTests.task_rows
    status = TaskPauseTests.status
    pause_and_wait = TaskPauseTests.pause_and_wait

    def setUp(self):
        TaskPauseTests.setUp(self)
        # Replace the unused setup queue with the real window's queue; this
        # ensures normal Window startup and shutdown run against the database.
        self.queue.deleteLater()
        self.queues.clear()
        self.library.state.close()
        self.windows = []
        self.open_window()

    def open_window(self):
        self.w = manager.Window(self.root, program_root=self.runtime)
        self.w.setAttribute(manager.Qt.WidgetAttribute.WA_DontShowOnScreen)
        self.w.show()
        self.windows.append(self.w)
        self.queue = self.w.queue
        self.library = self.w.library
        self.queues.append(self.queue)
        qt.processEvents()
        return self.w

    def tearDown(self):
        # Exercise the production close path even after an assertion failure,
        # then retain the queue suite's descendant cleanup as a final fallback.
        try:
            with patch.object(manager.QMessageBox, 'question', return_value=manager.QMessageBox.StandardButton.Yes):
                for window in reversed(self.windows):
                    if not window.closed:
                        window.close()
                        self.wait_for(lambda w=window: w.closed, 'Test window could not shut down')
        finally:
            TaskPauseTests.tearDown(self)

    def test_close_yes_waits_for_task_stop_then_saves_pending_queue(self):
        first = self.enqueue('download')
        second = self.enqueue('second')
        self.wait_for(lambda: (self.root / 'download.ready').exists(), 'Download did not start')
        with patch.object(manager.QMessageBox, 'question', return_value=manager.QMessageBox.StandardButton.Yes) as question:
            self.assertFalse(self.w.close(), 'Active download should close only after asynchronous stop')
            self.assertTrue(self.w._close_when_paused)
            self.assertFalse(self.w.closed)
            self.wait_for(lambda: self.w.closed, 'Pause-and-exit did not close the main window')
            question.assert_called_once()
        self.assertEqual(self.queue.process.state(), manager.QProcess.ProcessState.NotRunning)
        self.assertFalse(self.queue.stopping)
        self.assertTrue(self.queue.paused)
        self.assertFalse((self.root / 'second.done').exists())
        self.assertTrue((self.root / 'retained.bin').exists())
        with closing(sqlite3.connect(self.root / '_推文归档/manager.sqlite')) as db:
            self.assertEqual(db.execute('SELECT id,status FROM tasks ORDER BY id').fetchall(),
                             [(first, '已暂停'), (second, '已暂停')])
            saved = json.loads(db.execute("SELECT value FROM preferences WHERE key='task_queue_v1'").fetchone()[0])
        self.assertEqual([plan['id'] for plan in saved['tasks']], [first, second])

    def test_close_no_leaves_active_download_running(self):
        self.enqueue('download')
        self.wait_for(lambda: (self.root / 'download.ready').exists(), 'Download did not start')
        with patch.object(manager.QMessageBox, 'question', return_value=manager.QMessageBox.StandardButton.No) as question:
            self.assertFalse(self.w.close())
            question.assert_called_once()
        self.pump_for(.2)
        self.assertFalse(self.w.closed)
        self.assertFalse(self.w._close_when_paused)
        self.assertFalse(self.queue.paused)
        self.assertIsNotNone(self.queue.current)
        self.assertEqual(self.queue.process.state(), manager.QProcess.ProcessState.Running)
        (self.root / 'release.download').touch()
        self.wait_for(lambda: not self.queue.current and not self.queue.waiting, 'Uninterrupted download did not finish')

    def test_already_paused_window_closes_and_reopens_without_prompt_or_auto_download(self):
        first = self.enqueue('download')
        second = self.enqueue('second')
        self.wait_for(lambda: (self.root / 'download.ready').exists(), 'Download did not start')
        self.w.toggle_tasks_pause()
        self.wait_for(lambda: self.queue.paused and not self.queue.stopping and not self.queue.current,
                      'Window pause control did not stop the task')
        self.assertEqual(self.w.pause_tasks_button.text(), '继续')
        with patch.object(manager.QMessageBox, 'question') as question:
            self.assertTrue(self.w.close())
            self.assertTrue(self.w.closed)
            question.assert_not_called()
        self.open_window()
        self.assertTrue(self.queue.paused)
        self.assertIsNone(self.queue.current)
        self.assertEqual([task[0] for task in self.queue.waiting], [first, second])
        self.assertEqual(self.w.pause_tasks_button.text(), '继续')
        self.assertTrue(self.w.pause_tasks_button.isEnabled())
        self.pump_for(.3)
        self.assertFalse((self.root / 'second.done').exists())
        self.assertEqual((self.root / 'runs.txt').read_text().splitlines(), ['download'])
        (self.root / 'release.download').touch()
        self.w.toggle_tasks_pause()
        self.wait_for(lambda: not self.queue.current and not self.queue.waiting, 'Window resume control did not finish jobs')
        self.assertTrue((self.root / 'second.done').exists())

    def test_window_recovers_persisted_running_and_waiting_plans_after_crash(self):
        first = self.enqueue('download')
        second = self.enqueue('second')
        self.wait_for(lambda: (self.root / 'download.ready').exists(), 'Download did not start')
        self.pause_and_wait()
        self.assertTrue(self.w.close())
        # Simulate the on-disk state left by a crash, after stopping our actual
        # fixture tree safely. A fresh Window must not mark these rows as lost.
        with closing(sqlite3.connect(self.root / '_推文归档/manager.sqlite')) as db, db:
            saved = json.loads(db.execute("SELECT value FROM preferences WHERE key='task_queue_v1'").fetchone()[0])
            saved['paused'] = False
            db.execute("UPDATE preferences SET value=? WHERE key='task_queue_v1'", (json.dumps(saved),))
            db.execute("UPDATE tasks SET status='进行中' WHERE id=?", (first,))
            db.execute("UPDATE tasks SET status='等待中' WHERE id=?", (second,))
        self.open_window()
        self.assertTrue(self.queue.paused)
        self.assertIsNone(self.queue.current)
        self.assertEqual([task[0] for task in self.queue.waiting], [first, second])
        self.assertEqual(self.status(first), '已暂停')
        self.assertEqual(self.status(second), '已暂停')
        self.pump_for(.3)
        self.assertFalse((self.root / 'second.done').exists())
        self.assertEqual((self.root / 'runs.txt').read_text().splitlines(), ['download'])


if __name__ == '__main__':
    unittest.main()
