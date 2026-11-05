"""Native mixed-card geometry, selection, clipping, and scope regressions."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parent))
import app as manager
from adaptive_cards import lines,font
from PySide6.QtCore import QPoint,QPointF
from PySide6.QtGui import QKeyEvent,QMouseEvent
from PySide6.QtWidgets import QStyleOptionViewItem

qt=manager.QApplication.instance() or manager.QApplication([])


class AdaptiveCardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='mixed cards 中文 ')
        self.root=Path(self.temp.name)
        manager.initialize_library(self.root)
        (self.root/'tools/accounts.json').write_text(json.dumps([dict(key='a',name='示例账号',handle='@tester',folder='作者')]),encoding='utf-8')
        for name,w,h,color in [('portrait',200,400,'#b37b6c'),('wide',400,200,'#527f9a'),
                                ('square',200,200,'#7f996d'),('fourth',300,400,'#8f769e')]:
            image=manager.QImage(w,h,manager.QImage.Format.Format_RGB32)
            image.fill(manager.QColor(color));image.save(str(self.root/(name+'.png')))
        self.documents=[]
        with closing(sqlite3.connect(self.root/'_推文归档/tweets.sqlite')) as db,db:
            for i in range(55):
                doc=dict(tweet_id=str(1000-i),status='archived',post_type='original',author='示例作者',handle='@tester',
                         content='短い原文',translation_zh='谢谢大家！',images=[],videos=[],source_media_count=0,
                         date_beijing='2026-11-05T12:00:00+08:00',url='https://x.com/tester/status/'+str(1000-i))
                if i==1:doc.update(images=['portrait.png'],content='写真',translation_zh='今天的照片。',source_media_count=1)
                if i==2:doc.update(content='原文の長文。'*100,translation_zh='这是一段需要截断的长文字。'*100)
                if i==3:doc.update(images=['portrait.png','wide.png','square.png','fourth.png'],source_media_count=4)
                if i==4:doc.update(post_type='quote',source_tweet_id='995',content='引用した本文',translation_zh='一起听听看吧！')
                if i==5:doc.update(content='引用元の本文',translation_zh='来源推文的中文内容。')
                if i==6:doc.update(post_type='retweet',author='另一位作者',handle='@source')
                if i==7:doc.update(images=['wide.png'],translation_zh=None,source_media_count=1)
                self.documents.append(doc)
                db.execute('INSERT INTO tweets VALUES(?,?,?,?)',('a',doc['tweet_id'],'archived',json.dumps(doc)))
        self.w=manager.Window(self.root,remember=False)
        self.w.setAttribute(manager.Qt.WidgetAttribute.WA_DontShowOnScreen)
        self.w.resize(1800,1050);self.w.show();self.w.splitter.setSizes([205,1000,565])
        self.settle()

    def settle(self):
        deadline=time.monotonic()+.12
        while time.monotonic()<deadline:
            qt.processEvents();time.sleep(.005)
        self.w.layout_cards();qt.processEvents()

    def tearDown(self):
        self.w.pool.waitForDone();qt.processEvents()
        self.w.close();qt.processEvents();self.temp.cleanup()

    def plan(self,row):
        item=self.w.cards.item(row)
        return self.w.adaptive_renderer.plan(item.data(manager.Qt.ItemDataRole.UserRole),item.sizeHint().width(),item.data(manager.Qt.ItemDataRole.UserRole+5) or ())

    def test_short_text_shrinks_and_geometry_stays_stable_after_async_thumbnails(self):
        self.assertTrue(self.w.cards.adaptive)
        self.assertLess(self.w.cards.item(0).sizeHint().height(),180)
        self.assertGreater(self.w.cards.item(1).sizeHint().height(),self.w.cards.item(0).sizeHint().height()+100)
        self.assertTrue(self.plan(0)['media'].isNull())
        self.w.pool.waitForDone();self.settle()
        frames=[self.w.cards.visualItemRect(self.w.cards.item(i)) for i in range(self.w.cards.count())]
        self.assertEqual(len({r.x() for r in frames}),2)
        self.assertEqual([r.y() for r in frames],sorted(r.y() for r in frames))
        for i,rect in enumerate(frames):
            self.assertEqual(rect,self.w.cards.card_frames[i])
            self.assertEqual(self.w.cards.indexAt(rect.center()).row(),i)
            self.assertLessEqual(rect.right(),self.w.cards.viewport().width())
            for previous in frames[:i]:self.assertFalse(rect.intersects(previous))
        self.assertEqual(self.w.cards.verticalScrollBar().maximum(),0)

    def test_only_all_tweets_grid_changes(self):
        for mode in ('images','text','favorites','untranslated','videos','pending'):
            self.w.set_mode(mode);self.settle()
            self.assertFalse(self.w.cards.adaptive,mode)
            self.assertFalse(self.w.cards.card_frames)
            heights={self.w.cards.item(i).sizeHint().height() for i in range(self.w.cards.count())}
            self.assertLessEqual(len(heights),1)
        self.w.set_mode('all');self.w.view.setCurrentIndex(1);self.settle()
        self.assertFalse(self.w.cards.adaptive)
        self.assertEqual(self.w.cards.item(0).sizeHint().height(),169)
        self.w.view.setCurrentIndex(0);self.settle();self.assertTrue(self.w.cards.adaptive)

    def test_combined_thumbnails_keep_each_image_and_its_proportions(self):
        self.w.pool.waitForDone();self.settle()
        item=self.w.cards.item(3)
        self.assertEqual(len(self.plan(3)['cells']),4)
        paths=item.data(manager.Qt.ItemDataRole.UserRole+4)
        pixmaps=item.data(manager.Qt.ItemDataRole.UserRole+3)
        self.assertEqual(set(paths),set(pixmaps))
        self.assertEqual(item.data(manager.Qt.ItemDataRole.UserRole+1).size(),pixmaps[paths[0]].size())
        self.assertAlmostEqual(pixmaps[paths[0]].width()/pixmaps[paths[0]].height(),.5,places=2)
        self.assertAlmostEqual(pixmaps[paths[1]].width()/pixmaps[paths[1]].height(),2,places=2)

    def test_rendered_portrait_is_contained_without_stretching(self):
        self.w.pool.waitForDone();self.settle()
        item=self.w.cards.item(1)
        size=item.sizeHint()
        pixmap=manager.QPixmap(size);pixmap.fill(manager.QColor('#000000'))
        painter=manager.QPainter(pixmap)
        option=QStyleOptionViewItem();option.rect=manager.QRect(0,0,size.width(),size.height())
        self.w.cards.itemDelegate().paint(painter,option,self.w.cards.model().index(1,0))
        painter.end()
        image=pixmap.toImage();color=manager.QColor('#b37b6c').rgb()
        pixels=[(x,y) for y in range(image.height()) for x in range(image.width()) if image.pixel(x,y)==color]
        self.assertTrue(pixels)
        width=max(x for x,y in pixels)-min(x for x,y in pixels)+1
        height=max(y for x,y in pixels)-min(y for x,y in pixels)+1
        self.assertAlmostEqual(width/height,.5,delta=.01)

    def test_cards_cannot_be_dragged_into_a_different_time_order(self):
        before=list(self.w.cards.card_frames)
        point=self.w.cards.visualItemRect(self.w.cards.item(0)).center()
        for kind,where,button,buttons in [
            (manager.QEvent.Type.MouseButtonPress,point,manager.Qt.MouseButton.LeftButton,manager.Qt.MouseButton.LeftButton),
            (manager.QEvent.Type.MouseMove,point+QPoint(60,70),manager.Qt.MouseButton.NoButton,manager.Qt.MouseButton.LeftButton),
            (manager.QEvent.Type.MouseButtonRelease,point+QPoint(60,70),manager.Qt.MouseButton.LeftButton,manager.Qt.MouseButton.NoButton)]:
            qt.sendEvent(self.w.cards.viewport(),QMouseEvent(kind,QPointF(where),QPointF(self.w.cards.viewport().mapToGlobal(where)),button,buttons,manager.Qt.KeyboardModifier.NoModifier))
        self.settle()
        self.assertEqual(self.w.cards.card_frames,before)
        self.assertEqual([self.w.cards.visualItemRect(self.w.cards.item(i)) for i in range(self.w.cards.count())],before)

    def test_video_card_uses_poster_and_duration_without_starting_a_player(self):
        item=self.w.cards.item(7)
        doc=dict(item.data(manager.Qt.ItemDataRole.UserRole),images=[],videos=['offline-fixture.mp4'])
        item.setData(manager.Qt.ItemDataRole.UserRole,doc)
        item.setData(manager.Qt.ItemDataRole.UserRole+3,{})
        item.setData(manager.Qt.ItemDataRole.UserRole+4,[])
        item.setData(manager.Qt.ItemDataRole.UserRole+5,[])
        poster=manager.QPixmap(320,180);poster.fill(manager.QColor('#23567c'))
        item.setData(manager.Qt.ItemDataRole.UserRole+1,poster)
        item.setData(manager.Qt.ItemDataRole.UserRole+2,28000)
        self.w.layout_cards()
        plan=self.plan(7)
        self.assertEqual(len(plan['cells']),1)
        self.assertLessEqual(plan['media'].height(),240)
        canvas=manager.QPixmap(item.sizeHint());canvas.fill(manager.QColor('#000000'))
        painter=manager.QPainter(canvas)
        option=QStyleOptionViewItem();option.rect=manager.QRect(0,0,canvas.width(),canvas.height())
        self.w.cards.itemDelegate().paint(painter,option,self.w.cards.model().index(7,0));painter.end()
        self.assertEqual(canvas.toImage().pixelColor(plan['media'].center()),manager.QColor('#23567c'))
        self.assertTrue(self.w.player.source().isEmpty())

    def test_quote_summary_changes_language_and_source_link_is_clickable(self):
        plan=self.plan(4)
        self.assertFalse(plan['quote'].isNull())
        self.assertIn('中文内容',''.join(plan['quote_lines']))
        self.w.language.setCurrentIndex(2);self.settle()
        self.assertIn('引用元',''.join(self.plan(4)['quote_lines']))
        rect=self.w.cards.visualItemRect(self.w.cards.item(4))
        point=rect.topLeft()+self.plan(4)['quote_link'].center()
        with patch.object(manager.QDesktopServices,'openUrl') as opened:
            for kind,button,buttons in [(manager.QEvent.Type.MouseButtonPress,manager.Qt.MouseButton.LeftButton,manager.Qt.MouseButton.LeftButton),
                                       (manager.QEvent.Type.MouseButtonRelease,manager.Qt.MouseButton.LeftButton,manager.Qt.MouseButton.NoButton)]:
                event=QMouseEvent(kind,QPointF(point),QPointF(self.w.cards.viewport().mapToGlobal(point)),button,buttons,manager.Qt.KeyboardModifier.NoModifier)
                qt.sendEvent(self.w.cards.viewport(),event)
            self.assertEqual(opened.call_args.args[0].toString(),'https://x.com/i/web/status/995')
        self.assertEqual(self.w.current['tweet_id'],'996')

    def test_keyboard_sort_paging_and_filter_keep_result_order(self):
        self.w.cards.setCurrentRow(0)
        event=QKeyEvent(manager.QEvent.Type.KeyPress,manager.Qt.Key.Key_Down,manager.Qt.KeyboardModifier.NoModifier)
        qt.sendEvent(self.w.cards,event)
        self.assertEqual(self.w.cards.currentRow(),1)
        self.assertEqual(self.w.current['tweet_id'],'999')
        self.w.go_to_page(1);self.settle();self.assertEqual(self.w.cards.count(),7)
        self.w.sort.setCurrentIndex(1);self.settle()
        ids=[int(self.w.cards.item(i).data(manager.Qt.ItemDataRole.UserRole)['tweet_id']) for i in range(self.w.cards.count())]
        self.assertEqual(ids,sorted(ids))
        self.w.kind.setTypes(['quote','retweet']);self.settle()
        self.assertEqual(self.w.cards.count(),2)

    def test_resize_to_single_column_and_selection_scroll_restore(self):
        self.w.cards.setCurrentRow(20);self.w.reveal_card(20);self.settle()
        state=self.w.capture_browse()
        self.w.splitter.setSizes([205,390,1100]);self.settle()
        self.assertEqual(len({self.w.cards.visualItemRect(self.w.cards.item(i)).x() for i in range(self.w.cards.count())}),1)
        self.assertEqual(self.w.current['tweet_id'],'980')
        self.w.restore_scope(state);self.settle()
        self.assertEqual(self.w.current['tweet_id'],'980')
        self.assertGreater(self.w.feed_scroll.verticalScrollBar().value(),0)

    def test_text_clamps_quote_and_repost_content_are_measured(self):
        self.assertTrue(self.plan(2)['clipped'])
        self.assertEqual(len(self.plan(2)['body_lines']),6)
        self.assertTrue(self.plan(2)['body_lines'][-1].endswith('…'))
        self.assertIn('示例账号 转推了 另一位作者',self.plan(6)['credit'])
        value,clipped=lines('第一行\n第二行\n第三行',300,2,font(14))
        self.assertEqual(value[0],'第一行');self.assertTrue(clipped)


if __name__=='__main__':unittest.main()
