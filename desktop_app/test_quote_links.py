import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import app as manager
from library import source_tweet_url
import test_archive_ui as fixtures
from PySide6.QtTest import QTest


class QuoteSourceTests(unittest.TestCase):
    setUp=fixtures.ArchiveUiTests.setUp
    tearDown=fixtures.ArchiveUiTests.tearDown

    def test_clicking_inline_source_opens_original_post_and_keeps_local_body(self):
        self.w.current.update(post_type='quote',source_tweet_id='987654321',quote_summary='原作者：来源正文 <文字>')
        self.w.show_text();fixtures.qt.processEvents()
        cursor=self.w.body.document().find('查看来源推文');cursor.setPosition(cursor.selectionStart()+1)
        self.w.body.setTextCursor(cursor);self.w.body.ensureCursorVisible();fixtures.qt.processEvents()
        point=self.w.body.cursorRect(cursor).center()
        self.assertEqual(self.w.body.anchorAt(point),'https://x.com/i/web/status/987654321')
        with patch.object(manager.QDesktopServices,'openUrl',return_value=True) as opened:
            QTest.mouseClick(self.w.body.viewport(),manager.Qt.MouseButton.LeftButton,pos=point)
            self.assertEqual(opened.call_args.args[0].toString(),'https://x.com/i/web/status/987654321')
        self.assertIn('来源正文 <文字>',self.w.body.toPlainText());self.assertTrue(self.w.body.source().isEmpty())

    def test_quote_without_local_summary_still_has_source_link(self):
        self.w.current.update(post_type='quote',metadata={'quoted_id':123456},source_tweet_id=None)
        self.w.current.pop('quote_summary',None);self.w.show_text()
        self.assertIn('查看来源推文',self.w.body.toPlainText())
        self.assertIn('https://x.com/i/web/status/123456',self.w.body.toHtml())

    def test_legacy_links_normalize_and_invalid_links_are_not_opened(self):
        self.assertEqual(source_tweet_url({'source_url':'https://twitter.com/someone/status/1234?s=20'}),'https://x.com/i/web/status/1234')
        for bad in ['file:///C:/private.txt','javascript:alert(1)','https://x.com.evil.example/a/status/1234']:
            self.assertEqual(source_tweet_url({'source_url':bad}),'')
        self.w.current.update(post_type='quote',source_tweet_id='888');self.w.show_text()
        with patch.object(manager.QDesktopServices,'openUrl') as opened:
            self.w.body.anchorClicked.emit(manager.QUrl('file:///C:/private.txt'));opened.assert_not_called()
        self.w.current.update(source_tweet_id=None,metadata={});self.w.show_text()
        self.assertIn('来源链接暂缺',self.w.body.toPlainText())


if __name__=='__main__':unittest.main()
