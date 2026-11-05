import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from contextlib import closing
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import app as manager

qt=manager.QApplication.instance() or manager.QApplication([])


class ArchiveUiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.root=self.base/'资料库';self.runtime=self.base/'程序';self.runtime.mkdir()
        manager.initialize_library(self.root)
        (self.root/'tools/accounts.json').write_text(json.dumps([dict(key='a',name='示例',folder='作者',handle='@example')]),encoding='utf-8')
        (self.root/'作者').mkdir()
        with closing(sqlite3.connect(self.root/'_推文归档/tweets.sqlite')) as db,db:
            for tid,kind in [('100','original'),('200','quote'),('300','retweet')]:
                doc=dict(tweet_id=tid,status='archived',post_type=kind,author='示例',handle='@example',content='日本語の本文 '*30,
                         translation_zh=None,images=[],videos=[],source_media_count=0,date_beijing='2026-11-04T12:00:00+08:00',url='https://x.com/example/status/'+tid)
                db.execute('INSERT INTO tweets VALUES(?,?,?,?)',('a',tid,'archived',json.dumps(doc)))
        self.w=manager.Window(self.root,program_root=self.runtime)
        self.w.setAttribute(manager.Qt.WidgetAttribute.WA_DontShowOnScreen);self.w.show();qt.processEvents()

    def tearDown(self):
        self.w.close();qt.processEvents();self.temp.cleanup()

    def test_multiselect_restores_and_text_detail_has_no_media_space(self):
        self.w.kind.setTypes(['original','quote']);qt.processEvents()
        self.assertEqual({d['post_type'] for d in self.w.results},{'original','quote'})
        self.assertTrue(self.w.preview.isHidden());self.assertTrue(self.w.media_tools.isHidden())
        self.assertLess(self.w.cards.y(),300)
        self.assertLessEqual(self.w.cards.item(0).sizeHint().height(),286)
        self.assertIn('日本語',self.w.body.toPlainText())
        state=self.w.capture_browse();self.w.kind.setCurrentIndex(3);self.w.restore_scope(state)
        self.assertEqual(self.w.kind.types(),{'original','quote'})
        self.w.restore_scope(dict(kind=2));self.assertEqual(self.w.kind.types(),{'quote'})
        self.w.kind.buttons[2].click();self.assertEqual(self.w.kind.types(),{'quote'})

    def test_pending_body_is_not_claimed_original_or_empty_and_confirmed_empty_is_archived(self):
        pending=dict(self.w.current,status='pending',post_type='original',content='',translation_zh=None,images=[],videos=[])
        item=manager.QListWidgetItem();item.setData(manager.Qt.ItemDataRole.UserRole,pending)
        self.w.selected(item,None)
        self.assertIn('待核对',self.w.detail_type.text());self.assertNotIn('原创',self.w.detail_type.text())
        self.assertIn('取得原文后才能翻译',self.w.body.toPlainText());self.assertNotIn('无需翻译',self.w.body.toPlainText())
        with closing(sqlite3.connect(self.root/'_推文归档/tweets.sqlite')) as db,db:
            doc=dict(pending,status='archived',tweet_id='400',text_state='empty',source_media_count=0)
            db.execute('INSERT INTO tweets VALUES(?,?,?,?)',('a','400','archived',json.dumps(doc)))
        self.w.reload();self.w.set_mode('all')
        self.assertTrue(any(d['tweet_id']=='400' for d in self.w.results))
        self.w.current=next(d for d in self.w.library.docs if d['tweet_id']=='400');self.w.show_text()
        self.assertIn('已确认原推无文字正文，无需翻译',self.w.body.toPlainText())

    def test_translation_and_sync_use_runtime_code_and_selected_data(self):
        self.w.kind.setTypes(['original','quote'])
        with patch.object(self.w.queue,'enqueue') as enqueue:
            self.w.translate()
            args=enqueue.call_args.args
            self.assertEqual(args[1],str(self.runtime/'python/python.exe'))
            argv=args[2]
            self.assertEqual(argv[argv.index('--root')+1],str(self.root))
            self.assertEqual(argv[argv.index('--runtime-root')+1],str(self.runtime))
            self.assertEqual([argv[i+1] for i,t in enumerate(argv) if t=='--translation-type'],['original','quote'])
            self.w.sync()
            sync_args=next(call.args[2] for call in enqueue.call_args_list if call.args[1]=='powershell.exe')
            self.assertIn(str(self.runtime/'tools/update.ps1'),sync_args)
            self.assertEqual(sync_args[sync_args.index('-DataRoot')+1],str(self.root))

    def test_copy_then_empty_then_reopen_preserves_original(self):
        with patch.object(manager.QMessageBox,'information'),patch.object(manager.QMessageBox,'warning') as warning:
            self.w.change_storage('copy',self.base/'迁移目标')
            self.assertFalse(warning.called,warning.call_args)
            self.assertEqual(len(self.w.library.docs),3)
            self.w.change_storage('new',self.base/'教学空库')
            self.assertFalse(warning.called,warning.call_args)
            self.assertFalse(self.w.library.accounts);self.assertFalse(self.w.library.docs)
            self.w.change_storage('open',self.root)
            self.assertEqual(len(self.w.library.docs),3)
            self.assertEqual(manager.resolve_library(self.runtime),self.root)

    def test_busy_migration_does_not_switch_or_create_directory(self):
        self.w.queue.waiting.append(('fixture',))
        self.w.change_storage('new',self.base/'blocked')
        self.assertFalse((self.base/'blocked').exists());self.w.queue.waiting.clear()


if __name__=='__main__':unittest.main()
