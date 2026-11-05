"""Reading-only text flow, full-width quote blocks and UTF-16 wrap checks."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).parent))
from text_presentation import readable_text
from adaptive_cards import lines,font
import test_archive_ui as fixtures


class TextFlowTests(unittest.TestCase):
    def test_soft_wraps_join_without_touching_structural_paragraphs(self):
        self.assertEqual(readable_text('田\n邊提供乐曲的青\n木阳菜\n\n#BLUEENCOUNT\nhttps://example.com'),
                         '田邊提供乐曲的青木阳菜\n\n#BLUEENCOUNT\nhttps://example.com')
        self.assertEqual(readable_text('Hello\nworld\n\n• item one\n• item two'),'Hello world\n\n• item one\n• item two')

    def test_retweet_prefix_is_display_only(self):
        original='RT @BLUEN_official: 【📢通知】\n田\n邊提供乐曲'
        self.assertEqual(readable_text(original,'retweet'),'【📢通知】 田邊提供乐曲')
        self.assertTrue(original.startswith('RT @'))
        self.assertTrue(readable_text(original).startswith('RT @'))

    def test_utf16_wrap_preserves_every_character_after_multiple_emoji(self):
        original='📢通知田邊提供乐曲的青木阳菜✨🎉BLUEENCOUNT欢迎收听！'*5
        wrapped,clipped=lines(original,135,100,font(14))
        self.assertFalse(clipped);self.assertEqual(''.join(wrapped),original)
        wrapped,clipped=lines(original,135,3,font(14))
        self.assertTrue(clipped);self.assertTrue(wrapped[-1].endswith('…'))


class QuoteLayoutTests(unittest.TestCase):
    setUp=fixtures.ArchiveUiTests.setUp
    tearDown=fixtures.ArchiveUiTests.tearDown

    def test_quote_body_has_no_indent_and_fills_document_width(self):
        self.w.current.update(post_type='quote',source_tweet_id='123456',quote_summary='来源作者：'+('更多正文内容'*60))
        self.w.show_text();fixtures.qt.processEvents()
        html=self.w.body.toHtml();self.assertNotIn('margin-left:40px',html)
        block=self.w.body.document().begin();source=None
        while block.isValid():
            if '来源作者' in block.text():source=block;break
            block=block.next()
        self.assertIsNotNone(source)
        self.assertEqual(source.blockFormat().leftMargin(),0)
        self.assertEqual(source.blockFormat().rightMargin(),0)
        self.assertGreater(source.layout().lineAt(0).naturalTextWidth(),self.w.body.viewport().width()*.8)
        self.assertIn('https://x.com/i/web/status/123456',html)


if __name__=='__main__':unittest.main()
