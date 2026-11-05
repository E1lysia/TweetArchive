"""Shared display settings, legacy migration, and the middle-pane top shortcut."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest

sys.path.insert(0,str(Path(__file__).parent))
import app as manager

qt=manager.QApplication.instance() or manager.QApplication([])


class BrowsePreferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='browse preferences 中文 ')
        self.root=Path(self.temp.name)
        manager.initialize_library(self.root)
        accounts=[dict(key=key,name='账号'+key,handle='@'+key+'test',folder=key) for key in ('a','b')]
        (self.root/'tools/accounts.json').write_text(json.dumps(accounts),encoding='utf-8')
        with closing(sqlite3.connect(self.root/'_推文归档/tweets.sqlite')) as db,db:
            for key,base in [('a',20000),('b',10000)]:
                for i in range(64):
                    doc=dict(tweet_id=str(base+i),status='archived',post_type=['original','quote','retweet'][i%3],
                             author='作者'+key,handle='@'+key+'test',content=('原文'+key+' 日本語。')*100,
                             translation_zh=('译文'+key+'。')*30,images=[],videos=[],source_media_count=0,
                             date_beijing='2026-11-05T12:00:00+08:00',url=f'https://x.com/{key}test/status/{base+i}')
                    db.execute('INSERT INTO tweets VALUES(?,?,?,?)',(key,doc['tweet_id'],'archived',json.dumps(doc)))
        self.w=None
        self.open(dict(active=dict(mode='all',account='a'),scopes={}))

    def open(self,session=None):
        if self.w:self.w.close();qt.processEvents()
        if session is not None:
            library=manager.Library(self.root);library.set_preference('browse_v2',session);library.state.close()
        self.w=manager.Window(self.root)
        self.w.setAttribute(manager.Qt.WidgetAttribute.WA_DontShowOnScreen)
        self.w.show();self.settle()

    def settle(self):
        deadline=time.monotonic()+.12
        while time.monotonic()<deadline:qt.processEvents();time.sleep(.005)
        self.w.layout_cards();qt.processEvents()

    def tearDown(self):
        self.w.close();qt.processEvents();self.temp.cleanup()

    def test_favorites_is_directly_below_all_tweets(self):
        self.assertEqual(list(self.w.nav)[:3],['all','favorites','images'])
        self.assertGreater(self.w.nav['favorites'].y(),self.w.nav['all'].y())
        self.assertLess(self.w.nav['favorites'].y(),self.w.nav['images'].y())
        self.assertFalse(self.w.nav['favorites'].icon().isNull())

    def test_switching_accounts_and_library_views_keeps_current_display(self):
        self.w.scope_states['all|b']=dict(view=0,sort=0,types=['retweet'],page=1,scroll=400)
        self.w.view.setCurrentIndex(1);self.w.sort.setCurrentIndex(1);self.w.kind.setTypes(['original','quote'])
        expected=self.w.capture_display()
        self.w.set_account('b');self.settle()
        self.assertEqual(self.w.capture_display(),expected)
        self.assertEqual(self.w.page,0)
        self.assertEqual({doc['post_type'] for doc in self.w.results},{'original','quote'})
        ids=[int(doc['tweet_id']) for doc in self.w.results];self.assertEqual(ids,sorted(ids))
        self.w.kind.setTypes(['retweet']);self.w.sort.setCurrentIndex(0);self.w.view.setCurrentIndex(0)
        expected=self.w.capture_display()
        for mode,account in [('all','a'),('favorites','a'),('all','b'),('text','a')]:
            self.w.set_mode(mode);self.w.set_account(account);self.settle()
            self.assertEqual(self.w.capture_display(),expected)

    def test_legacy_active_account_settings_migrate_once(self):
        session=dict(active=dict(mode='all',account='a'),scopes={
            'all|a':dict(view=1,sort=1,types=['original','quote']),
            'all|b':dict(view=0,sort=0,kind=3)})
        self.open(session)
        expected=dict(view=1,sort=1,types=['original','quote'])
        self.assertEqual(self.w.capture_display(),expected)
        self.w.set_account('b');self.settle();self.assertEqual(self.w.capture_display(),expected)
        self.w.save_session()
        self.assertEqual(self.w.library.preference('browse_v2')['display'],expected)
        self.open();self.assertEqual(self.w.capture_display(),expected)

    def test_shared_settings_override_stale_active_scope_after_restart(self):
        common=dict(view=1,sort=1,types=['quote'])
        self.open(dict(active=dict(mode='all',account='b'),display=common,
                       scopes={'all|b':dict(view=0,sort=0,types=['retweet'],page=1,scroll=500)}))
        self.assertEqual(self.w.capture_display(),common)
        self.assertEqual(self.w.page,0)
        self.assertTrue(all(doc['post_type']=='quote' for doc in self.w.results))
        self.w.view.setCurrentIndex(0);self.w.kind.setTypes(['original','retweet'])
        expected=self.w.capture_display();self.open()
        self.assertEqual(self.w.capture_display(),expected)

    def test_search_dates_and_reading_position_stay_per_account(self):
        self.w.search.setText('译文a');self.w.set_period('2026-11');self.w.go_to_page(1)
        self.w.cards.setCurrentRow(4);self.w.reveal_card(4);self.settle()
        selected=self.w.current['tweet_id']
        self.w.set_account('b');self.settle()
        self.w.search.setText('译文b');self.w.set_period('2026');self.settle()
        self.w.set_account('a');self.settle()
        self.assertEqual(self.w.search.text(),'译文a')
        self.assertEqual(self.w.period,'2026-11')
        self.assertEqual(self.w.page,1)
        self.assertEqual(self.w.current['tweet_id'],selected)
        self.assertGreater(self.w.feed_scroll.verticalScrollBar().value(),0)
        self.w.set_account('b');self.settle()
        self.assertEqual(self.w.search.text(),'译文b');self.assertEqual(self.w.period,'2026')

    def test_top_button_floats_and_only_scrolls_middle_of_current_page(self):
        self.assertTrue(self.w.back_to_top.isHidden())
        self.w.go_to_page(1);self.settle()
        bar=self.w.feed_scroll.verticalScrollBar();bar.setValue(300);self.settle()
        self.assertTrue(self.w.back_to_top.isVisible())
        viewport=self.w.feed_scroll.viewport()
        button=self.w.back_to_top
        self.assertIs(button.parentWidget(),viewport)
        self.assertLess(button.geometry().right(),viewport.width())
        self.assertLess(button.geometry().bottom(),viewport.height())
        self.w.body.verticalScrollBar().setValue(80)
        detail_scroll=self.w.body.verticalScrollBar().value()
        selected=self.w.current['tweet_id'];display=self.w.capture_display()
        self.w.resize(1450,850);self.settle()
        self.assertLess(button.geometry().right(),viewport.width())
        self.assertLess(button.geometry().bottom(),viewport.height())
        button.click();self.settle()
        self.assertEqual(bar.value(),0)
        self.assertTrue(button.isHidden())
        self.assertEqual(self.w.page,1)
        self.assertEqual(self.w.current['tweet_id'],selected)
        self.assertEqual(self.w.capture_display(),display)
        self.assertEqual(self.w.body.verticalScrollBar().value(),detail_scroll)

    def test_view_only_change_keeps_account_page_and_reveals_selected_post(self):
        self.w.go_to_page(1);self.w.cards.setCurrentRow(4);self.w.reveal_card(4);self.settle()
        selected=self.w.current['tweet_id']
        self.w.set_account('b');self.w.view.setCurrentIndex(1);self.settle()
        self.w.set_account('a');self.settle()
        self.assertEqual(self.w.view.currentIndex(),1)
        self.assertEqual(self.w.page,1)
        self.assertEqual(self.w.current['tweet_id'],selected)
        rect=self.w.cards.visualItemRect(self.w.cards.currentItem())
        center=self.w.cards.y()+rect.center().y()-self.w.feed_scroll.verticalScrollBar().value()
        self.assertGreaterEqual(center,0)
        self.assertLessEqual(center,self.w.feed_scroll.viewport().height())

    def test_empty_results_hide_top_button(self):
        self.w.feed_scroll.verticalScrollBar().setValue(300);self.settle()
        self.assertTrue(self.w.back_to_top.isVisible())
        self.w.search.setText('no matching local fixture');self.w.filter();self.settle()
        self.assertFalse(self.w.results)
        self.assertTrue(self.w.back_to_top.isHidden())


if __name__=='__main__':unittest.main()
