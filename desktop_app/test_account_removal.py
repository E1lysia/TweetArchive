import json
import sys
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import app as manager
import test_archive_ui as fixtures


class AccountRemovalTests(unittest.TestCase):
    setUp=fixtures.ArchiveUiTests.setUp
    tearDown=fixtures.ArchiveUiTests.tearDown

    def remove_ui(self):
        action=next(a for a in self.w.build_account_menu('a').actions() if a.text()=='删除账号…')
        with patch.object(manager.QMessageBox,'question',return_value=manager.QMessageBox.StandardButton.Yes):action.trigger()

    def test_remove_hides_account_preserves_data_and_readding_restores_identity(self):
        original=dict(self.w.library.accounts[0]);media=self.root/original['folder']/'keep.bin';media.write_bytes(b'keep media')
        before=(self.root/'_推文归档/tweets.sqlite').read_bytes()
        doc=self.w.library.docs[0];self.w.library.annotate(doc,favorite=True,tags='保留标签')
        group=self.w.library.create_group('保留分组');self.w.library.move_account('a',group['id'])
        self.w.library.add_account('second','另一账号');self.w.reload();self.w.set_account('a')
        self.remove_ui()
        self.assertEqual(self.w.account,'');self.assertEqual(self.w.library.docs,[])
        self.assertEqual([a['handle'] for a in self.w.library.accounts],['@second'])
        self.assertEqual(self.w.library.archive_counts()['archived'],0)
        self.assertNotIn('a',self.w.library.account_groups()['memberships'])
        self.assertEqual(media.read_bytes(),b'keep media');self.assertEqual((self.root/'_推文归档/tweets.sqlite').read_bytes(),before)
        self.assertEqual(self.w.library.state.execute('SELECT count(*) FROM notes WHERE account=?',('a',)).fetchone()[0],1)
        restored=self.w.library.add_account('@example','')
        self.assertEqual((restored['key'],restored['folder']),(original['key'],original['folder']))
        self.w.reload();self.assertEqual(len(self.w.library.docs),3)
        self.assertEqual(self.w.library.query(mode='favorites')[0]['tags'],'保留标签')
        self.assertEqual(self.w.library.account_groups()['memberships']['a'],group['id'])

    def test_cancel_confirmation_keeps_account(self):
        with patch.object(manager.QMessageBox,'question',return_value=manager.QMessageBox.StandardButton.No):
            self.w.remove_archive_account('a')
        self.assertEqual(len(self.w.library.accounts),1);self.assertEqual(len(self.w.library.docs),3)

    def test_delete_failure_keeps_configuration_and_group_membership(self):
        group=self.w.library.create_group('分组');self.w.library.move_account('a',group['id'])
        before=(self.root/'tools/accounts.json').read_bytes()
        with patch.object(Path,'replace',side_effect=OSError('fixture write failure')):
            with self.assertRaises(OSError):self.w.library.remove_account('a')
        self.assertEqual((self.root/'tools/accounts.json').read_bytes(),before)
        self.assertEqual(self.w.library.account_groups()['memberships']['a'],group['id'])
        self.assertFalse(self.w.library.preference('removed_accounts_v1',{}))

    def test_running_task_requires_pause_before_removal(self):
        self.w.queue.current=(99,'fixture',sys.executable,[],{})
        try:
            with patch.object(manager.QMessageBox,'information') as info,patch.object(manager.QMessageBox,'question') as question:
                self.w.remove_archive_account('a');info.assert_called_once();question.assert_not_called()
            self.assertEqual(len(self.w.library.accounts),1)
        finally:self.w.queue.current=None

    def test_removal_cancels_own_paused_tasks_and_reindexes_other_account(self):
        other=self.w.library.add_account('second','第二个');self.w.reload()
        self.w.queue.paused=True
        first=self.w.queue.enqueue('被删除账号',sys.executable,['-c','pass','--index','1'])
        output=self.root/'ran-index.txt'
        code='import sys;from pathlib import Path;Path(sys.argv[1]).write_text(sys.argv[sys.argv.index("--index")+1])'
        second=self.w.queue.enqueue('保留账号',sys.executable,['-c',code,str(output),'--index','2'])
        # Simulate a 1.1.4 saved translation task without a stable account key.
        plan=self.w.library.preference('task_queue_v1');plan['tasks'][1]['context']={}
        self.w.library.set_preference('task_queue_v1',plan);self.w.queue.restore()
        self.assertEqual(self.w.queue.waiting[1][4]['account'],other['key'])
        self.remove_ui()
        self.assertEqual([t[0] for t in self.w.queue.waiting],[second])
        self.assertEqual(self.w.library.state.execute('SELECT status FROM tasks WHERE id=?',(first,)).fetchone()[0],'已取消')
        self.assertTrue(self.w.queue.resume())
        deadline=time.monotonic()+8
        while self.w.queue.current and time.monotonic()<deadline:fixtures.qt.processEvents();time.sleep(.01)
        self.assertIsNone(self.w.queue.current);self.assertEqual(output.read_text(),'1')
        self.assertEqual(self.w.library.state.execute('SELECT status FROM tasks WHERE id=?',(second,)).fetchone()[0],'完成')

    def test_unrelated_handle_does_not_reuse_retained_rows(self):
        self.w.library.remove_account('a')
        other=self.w.library.add_account('a','不同账号');self.w.library.reload()
        self.assertNotEqual(other['key'],'a');self.assertEqual(self.w.library.docs,[])

    def test_unresolvable_index_does_not_run_against_another_account(self):
        output=self.root/'should-not-exist.txt'
        code='from pathlib import Path;Path('+repr(str(output))+').write_text("unexpected")'
        tid=self.w.queue.enqueue('旧账号编号',sys.executable,['-c',code,'--index','99'])
        fixtures.qt.processEvents()
        self.assertFalse(output.exists())
        self.assertEqual(self.w.library.state.execute('SELECT status FROM tasks WHERE id=?',(tid,)).fetchone()[0],'失败')


if __name__=='__main__':unittest.main()
