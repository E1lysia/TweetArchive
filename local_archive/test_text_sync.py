import datetime as dt
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from gallery_dl.extractor.message import Message

spec=importlib.util.spec_from_file_location('text_archive',Path(__file__).parent/'tools/tweet_archive.py')
archive=importlib.util.module_from_spec(spec);spec.loader.exec_module(archive)


class Source:
    def __init__(self, posts):self.posts=posts;self._cursor=None
    def __iter__(self):
        for i,post in enumerate(self.posts):
            self._cursor='1/page-'+str(i//2)
            yield Message.Directory,'',post


class TextSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.account=dict(key='a',name='作者',handle='@example',folder='作者')
        (self.root/'tools').mkdir();(self.root/'tools/accounts.json').write_text(json.dumps([self.account]),encoding='utf-8')
        self.db=archive.database(self.root)
        self.options=dict(sync_text=True,include_replies=False,post_types=['original','quote','retweet','reference'])

    def tearDown(self):self.db.close();self.temp.cleanup()

    def post(self,tid,**extra):
        return dict(tweet_id=str(tid),author=dict(name='example',nick='作者'),content='テスト本文 '+str(tid),count=0,
                    date=dt.datetime(2026,11,4,tzinfo=dt.timezone.utc),**extra)

    def test_text_and_missing_media_kept_separately_and_exported(self):
        posts=[self.post(100),dict(self.post(101),count=2)]
        archive.scan_timeline(self.db,self.root,self.account,Source(posts),self.options)
        self.assertEqual(archive.load_document(self.db,'a','100')['source_media_count'],0)
        self.assertEqual(archive.load_document(self.db,'a','101')['source_media_count'],2)
        counts=archive.export(self.db,self.root,[self.account]);self.assertEqual(counts['archived'],2)
        self.assertEqual(len(list((self.root/'作者/推文').rglob('*.json'))),2)
        self.assertIn('テスト本文', (self.root/'推文归档.html').read_text(encoding='utf-8'))

    def test_capture_types_and_reply_preference_independent(self):
        self.options['post_types']=['original','quote']
        posts=[self.post(100),self.post(101,quoted_id=555),self.post(102,retweet_id=888),self.post(103,reply_id=999)]
        archive.scan_timeline(self.db,self.root,self.account,Source(posts),self.options)
        self.assertIsNotNone(archive.load_document(self.db,'a','100'))
        self.assertIsNotNone(archive.load_document(self.db,'a','101'))
        self.assertIsNone(archive.load_document(self.db,'a','102'))
        self.assertIsNone(archive.load_document(self.db,'a','103'))
        self.options['include_replies']=True
        archive.scan_timeline(self.db,self.root,self.account,Source(posts),self.options)
        self.assertIsNotNone(archive.load_document(self.db,'a','103'))

    def test_replay_deduplicates_preserves_translation_and_history_cursor(self):
        posts=[self.post(i) for i in range(100,105)]
        result=archive.scan_timeline(self.db,self.root,self.account,Source(posts),self.options,limit=3,history=True,fingerprint='fixture')
        self.assertFalse(result['complete']);self.assertTrue(result['cursor'])
        doc=archive.load_document(self.db,'a','100');doc['translation_zh']='保留的译文';archive.save(self.db,'a',doc)
        archive.scan_timeline(self.db,self.root,self.account,Source(posts),self.options,history=True,fingerprint='fixture')
        self.assertEqual(self.db.execute('SELECT count(*) FROM tweets').fetchone()[0],5)
        self.assertEqual(archive.load_document(self.db,'a','100')['translation_zh'],'保留的译文')
        self.assertIsNone(json.loads(self.db.execute('SELECT value FROM sync_state').fetchone()[0])['cursor'])

    def test_history_date_and_old_pinned_record_do_not_hide_new_posts(self):
        posts=[dict(self.post(100),date=dt.datetime(2020,1,1,tzinfo=dt.timezone.utc)),self.post(101)]
        archive.scan_timeline(self.db,self.root,self.account,Source(posts),self.options,since='2026-01-01',history=True)
        self.assertIsNone(archive.load_document(self.db,'a','100'))
        self.assertIsNotNone(archive.load_document(self.db,'a','101'))

    def test_resume_uses_saved_cursor_and_separate_runtime_config(self):
        runtime=self.root/'程序';runtime.mkdir();(runtime/'config.json').write_text('{}')
        source=Source([self.post(i) for i in range(100,105)])
        from gallery_dl import extractor,config
        with patch.object(extractor,'find',return_value=source):
            archive.sync_text(self.db,self.root,runtime,self.account,self.options,limit=2,history=True)
        with patch.object(extractor,'find',return_value=Source([])):
            archive.sync_text(self.db,self.root,runtime,self.account,self.options,limit=2,history=True)
            self.assertEqual(config.get(('extractor','twitter'),'cursor'),'1/page-0')
            self.assertEqual(config.get(('extractor','twitter'),'cookies'),str(runtime/'cookies.txt'))

    def test_cli_translation_multiselect_accepts_text_without_media(self):
        archive.accept(self.db,self.account,self.post(100),create=True)
        archive.accept(self.db,self.account,self.post(101,quoted_id=555),create=True)
        archive.accept(self.db,self.account,self.post(102,retweet_id=888),create=True)
        self.db.commit()
        runtime=self.root/'程序';(runtime/'tools').mkdir(parents=True)
        cmd=[sys.executable,'-X','utf8',str(Path(__file__).parent/'tools/tweet_archive.py'),'--root',str(self.root),'--runtime-root',str(runtime),
             '--translation-preview','--translation-type','original','--translation-type','quote']
        result=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('待译 2 条',result.stdout)


if __name__=='__main__':unittest.main()
