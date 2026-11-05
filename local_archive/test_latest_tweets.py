"""Offline incremental boundary, media replay and failure/resume regressions."""
import datetime as dt
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from gallery_dl.extractor.message import Message

spec=importlib.util.spec_from_file_location('latest_fixture',Path(__file__).parent/'tools/latest_tweets.py')
latest=importlib.util.module_from_spec(spec);spec.loader.exec_module(latest)
UTC=dt.timezone.utc
NOW=dt.datetime(2026,11,5,12,tzinfo=UTC)


def snowflake(date):
    return str((int(date.timestamp()*1000)-1288834974657)<<22)


def post(date=NOW,**extra):
    return dict(tweet_id=snowflake(date),date=date,author=dict(name='tester',nick='示例'),
                count=0,content='测试正文',**extra)


class Source:
    def __init__(self,posts):self.posts=posts;self._cursor=None
    def __iter__(self):
        for i,p in enumerate(self.posts):
            self._cursor='1/page-'+str(i//20)
            yield Message.Directory,'',p
            for n,ext in enumerate(p.get('files',[]),1):
                yield Message.Url,'http://127.0.0.1/fixture',dict(p,num=n,extension=ext)


class LatestTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='增量 中文 ');self.root=Path(self.temp.name)
        self.runtime=self.root/'程序';self.runtime.mkdir();(self.runtime/'config.json').write_text('{}')
        (self.runtime/'cookies.txt').write_text('# Netscape HTTP Cookie File\n',encoding='utf-8')
        self.account=dict(key='a',name='示例账号',handle='@tester',folder='示例账号')
        self.options=dict(sync_text=True,include_replies=False,post_types=['original','quote','retweet','reference'])
        self.db=latest.archive.database(self.root)

    def tearDown(self):self.db.close();self.temp.cleanup()

    def state(self):
        return json.loads(self.db.execute('SELECT value FROM sync_state WHERE scope=?',(latest.SCOPE,)).fetchone()[0])

    def run_sync(self,posts,**kwargs):
        kwargs.setdefault('downloader',lambda *a:None);kwargs.setdefault('refresh',lambda *a:None)
        with patch.object(latest.archive,'export'):
            return latest.sync_account(self.db,self.root,self.runtime,self.account,self.options,[self.account],
                                       source_factory=lambda _:Source(posts),**kwargs)

    def anchor(self):
        latest.archive.accept(self.db,self.account,post(NOW-dt.timedelta(days=5)),create=True)

    def test_more_than_500_events_automatically_continue_on_same_source(self):
        self.anchor();calls=[]
        posts=[post(NOW-dt.timedelta(minutes=i)) for i in range(1103)]
        state=self.run_sync(posts,downloader=lambda msgs,*args:calls.append((len([m for m in msgs if m[0]==Message.Directory]),args[-1])))
        self.assertEqual(self.db.execute('SELECT count(*) FROM tweets').fetchone()[0],1104)
        self.assertEqual(calls,[(500,False),(500,True),(500,False),(500,True),(103,False),(103,True)])
        self.assertFalse(state['in_progress']);self.assertEqual(state['watermark'],NOW.timestamp())

    def test_download_failure_does_not_advance_boundary_after_new_metadata_saved(self):
        self.anchor();before=latest.start_state(self.db,self.account,self.options).copy()
        def fail(*args):raise RuntimeError('fixture media failure')
        with self.assertRaises(RuntimeError):self.run_sync([post()],downloader=fail)
        self.assertEqual(self.state(),before)
        self.assertEqual(latest.local_latest(self.db,self.account),NOW.timestamp())
        self.assertEqual(latest.start_state(self.db,self.account,self.options)['lower'],before['lower'])
        result=self.run_sync([post()]);self.assertFalse(result['in_progress'])

    def test_resume_preserves_last_successful_batch_cursor_and_original_lower(self):
        self.anchor();calls=0
        def download(*args):
            nonlocal calls
            calls+=1
            if calls==3:raise RuntimeError('second batch')
        with self.assertRaises(RuntimeError):self.run_sync([post(NOW-dt.timedelta(minutes=i)) for i in range(45)],batch_size=21,downloader=download)
        saved=self.state();self.assertEqual(saved['cursor'],'1/page-1');self.assertTrue(saved['in_progress'])
        self.assertEqual(saved['watermark'],(NOW-dt.timedelta(days=5)).timestamp())
        with patch.object(latest.archive,'export'):
            def factory(_):
                from gallery_dl import config
                self.assertEqual(config.get(('extractor','twitter'),'cursor'),saved['cursor'])
                return Source([post(NOW-dt.timedelta(minutes=i)) for i in range(20,45)])
            latest.sync_account(self.db,self.root,self.runtime,self.account,self.options,[self.account],
                                source_factory=factory,downloader=lambda *a:None,refresh=lambda *a:None)
        self.assertFalse(self.state()['in_progress'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM tweets').fetchone()[0],46)

    def test_old_retweet_source_and_quote_source_use_current_event_time(self):
        self.anchor()
        parent=post(NOW,quoted_id=snowflake(NOW-dt.timedelta(days=365)))
        reference=post(NOW-dt.timedelta(days=365),quote_id=parent['tweet_id'])
        retweet=post(NOW-dt.timedelta(seconds=1),retweet_id=snowflake(NOW-dt.timedelta(days=400)),
                     date_original=NOW-dt.timedelta(days=400))
        state=self.run_sync([parent,reference,retweet])
        self.assertEqual(self.db.execute('SELECT count(*) FROM tweets').fetchone()[0],4)
        self.assertEqual(state['watermark'],NOW.timestamp())
        self.assertEqual(latest.archive.load_document(self.db,'a',reference['tweet_id'])['post_type'],'reference')

    def test_old_pinned_event_does_not_stop_scan_but_16_old_events_do(self):
        self.anchor()
        old=[post(NOW-dt.timedelta(days=50,minutes=i)) for i in range(18)]
        self.run_sync([old[0],post(),*old[1:],post(NOW+dt.timedelta(minutes=1))])
        self.assertIsNotNone(latest.archive.load_document(self.db,'a',snowflake(NOW)))
        self.assertIsNone(latest.archive.load_document(self.db,'a',snowflake(NOW+dt.timedelta(minutes=1))))
        self.assertEqual(self.db.execute('SELECT count(*) FROM tweets').fetchone()[0],2)

    def test_options_filter_and_change_invalidates_in_progress_cursor(self):
        self.anchor();state=latest.start_state(self.db,self.account,self.options)
        state['cursor']='1/old';latest.put_state(self.db,self.account,state)
        self.options.update(include_replies=True,post_types=['original','quote'])
        self.assertIsNone(latest.start_state(self.db,self.account,self.options)['cursor'])
        self.run_sync([post(reply_id=888),post(NOW-dt.timedelta(seconds=1),retweet_id=999)])
        self.assertIsNotNone(latest.archive.load_document(self.db,'a',snowflake(NOW)))
        self.assertIsNone(latest.archive.load_document(self.db,'a',snowflake(NOW-dt.timedelta(seconds=1))))

    def test_disabled_text_keeps_media_but_does_not_archive_text_only(self):
        self.anchor();self.options['sync_text']=False
        self.run_sync([post(),dict(post(NOW-dt.timedelta(seconds=1)),count=1)])
        self.assertIsNone(latest.archive.load_document(self.db,'a',snowflake(NOW)))
        self.assertIsNotNone(latest.archive.load_document(self.db,'a',snowflake(NOW-dt.timedelta(seconds=1))))

    def test_empty_or_api_failure_keeps_frozen_checkpoint(self):
        self.anchor();before=latest.start_state(self.db,self.account,self.options).copy()
        with self.assertRaises(RuntimeError):self.run_sync([])
        self.assertEqual(self.state(),before)
        class Broken(Source):
            def __iter__(self):
                yield Message.Directory,'',post()
                raise ConnectionError('fixture')
        with patch.object(latest.archive,'export'),self.assertRaises(ConnectionError):
            latest.sync_account(self.db,self.root,self.runtime,self.account,self.options,[self.account],source_factory=lambda _:Broken([]))
        self.assertEqual(self.state(),before)

    def test_new_account_bootstrap_continues_until_accessible_timeline_ends(self):
        state=self.run_sync([post(NOW-dt.timedelta(minutes=i)) for i in range(24)],batch_size=21)
        self.assertTrue(state['bootstrap']);self.assertFalse(state['in_progress'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM tweets').fetchone()[0],24)

    def test_completed_checkpoint_is_not_replaced_by_later_partial_rows(self):
        self.anchor();state=self.run_sync([post()])
        latest.archive.accept(self.db,self.account,post(NOW+dt.timedelta(days=20)),create=True)
        new=latest.start_state(self.db,self.account,self.options)
        self.assertEqual(new['lower'],state['watermark']-latest.OVERLAP)

    def test_real_download_jobs_replay_urls_without_twitter_login_and_deduplicate(self):
        from gallery_dl.extractor.twitter import TwitterExtractor
        requests=[]
        # Reproduce the actual old global override rather than an empty config.
        wrong=self.root/'错误旧目录'
        (self.runtime/'config.json').write_text(json.dumps({'base-directory':str(wrong),'directory':['wrong']}),encoding='utf-8')
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path);data=b'offline fixture bytes'
                self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            def log_message(self,*a):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        metadata=dict(post(),count=2)
        messages=[(Message.Directory,'',metadata)]
        for n,ext in enumerate(('jpg','mp4'),1):
            messages.append((Message.Url,f'http://127.0.0.1:{server.server_port}/{n}.{ext}',dict(metadata,num=n,extension=ext)))
        try:
            with patch.object(TwitterExtractor,'login',side_effect=AssertionError('second login forbidden')):
                for _ in range(2):
                    for video in (False,True):latest.download(messages,self.root,self.runtime,self.account,self.options,video)
            self.assertEqual(len(requests),2)
            folder=self.root/self.account['folder'];self.assertEqual(len(list(folder.rglob('*.jpg'))),1)
            self.assertEqual(len(list(folder.rglob('*.mp4'))),1)
            self.assertTrue((folder/'archive.sqlite').is_file());self.assertTrue((folder/'archive_video.sqlite').is_file())
            self.assertFalse(wrong.exists())
            # A stale archive row is not proof that its file is still present.
            next(folder.glob('*.jpg')).unlink()
            latest.download(messages,self.root,self.runtime,self.account,self.options,False)
            self.assertEqual(len(requests),3);self.assertEqual(len(list(folder.glob('*.jpg'))),1)
        finally:
            server.shutdown();server.server_close();worker.join(timeout=3)

    def test_option_change_after_failure_keeps_completed_boundary(self):
        self.anchor();before=latest.start_state(self.db,self.account,self.options)
        latest.archive.accept(self.db,self.account,post(NOW+dt.timedelta(days=20)),create=True)
        self.options['include_replies']=True
        self.assertEqual(latest.start_state(self.db,self.account,self.options)['lower'],before['lower'])

    def test_local_indexing_failure_does_not_advance_checkpoint(self):
        self.anchor();before=latest.start_state(self.db,self.account,self.options)
        def fail(*args):raise OSError('fixture indexing failure')
        with self.assertRaises(OSError):self.run_sync([post()],refresh=fail)
        self.assertEqual(self.state(),before)

    def test_missing_cursor_cannot_silently_complete_a_capped_batch(self):
        self.anchor();before=latest.start_state(self.db,self.account,self.options)
        class NoCursor(Source):
            def __iter__(self):
                for p in self.posts:yield Message.Directory,'',p
        with patch.object(latest.archive,'export'),self.assertRaises(latest.LatestError):
            latest.sync_account(self.db,self.root,self.runtime,self.account,self.options,[self.account],
                                source_factory=lambda _:NoCursor([post(NOW-dt.timedelta(minutes=i)) for i in range(6)]),
                                downloader=lambda *a:None,refresh=lambda *a:None,batch_size=3)
        self.assertEqual(self.state(),before)

    def test_expired_saved_cursor_retries_head_once_without_changing_lower_bound(self):
        from gallery_dl import config
        self.anchor();state=latest.start_state(self.db,self.account,self.options)
        state['cursor']='1/expired';latest.put_state(self.db,self.account,state)
        seen=[]
        def factory(_):
            cursor=config.get(('extractor','twitter'),'cursor');seen.append(cursor)
            return Source([] if cursor=='1/expired' else [post()])
        with patch.object(latest.archive,'export'):
            result=latest.sync_account(self.db,self.root,self.runtime,self.account,self.options,[self.account],
                                       source_factory=factory,downloader=lambda *a:None,refresh=lambda *a:None)
        self.assertEqual(seen,['1/expired',True]);self.assertEqual(result['lower'],state['lower'])
        self.assertFalse(result['in_progress'])

    def test_live_twitter_lazy_fallbacks_are_frozen_before_copying(self):
        from gallery_dl.extractor.twitter import TwitterExtractor
        # Use the real extractor's generator, the structure omitted by the old fixture.
        extractor=object.__new__(TwitterExtractor);extractor._size_fallback=('large','medium','small')
        metadata=dict(post(),num=1,extension='jpg',_fallback=extractor._image_fallback('https://media.example/size='))
        original=(Message.Url,'https://media.example/size=orig',metadata)
        cloned=latest.snapshot_message(original)
        self.assertEqual(cloned[2]['_fallback'],('https://media.example/size=large','https://media.example/size=medium','https://media.example/size=small'))
        metadata['author']['nick']='changed after yield'
        self.assertEqual(cloned[2]['author']['nick'],'示例')
        self.assertEqual(latest.snapshot_message(cloned),cloned)

    def test_batch_and_real_download_retry_keep_lazy_fallback_urls(self):
        from gallery_dl.extractor.twitter import TwitterExtractor
        requests=[]
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                if self.path.startswith('/missing'):
                    self.send_response(404);self.end_headers();return
                data=b'fallback fixture'
                self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            def log_message(self,*a):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{server.server_port}'
        def messages():
            yield Message.Directory,'',dict(post(),count=1)
            yield Message.Url,base+'/missing.jpg',dict(post(),count=1,num=1,extension='jpg',_fallback=(base+'/working.jpg' for _ in range(1)))
        try:
            state=dict(high=0,lower=0,cursor=None)
            batch=next(latest.batches(messages(),self.account,self.options,state))
            self.assertIsInstance(batch['messages'][1][2]['_fallback'],tuple)
            with patch.object(TwitterExtractor,'login',side_effect=AssertionError('second login forbidden')):
                latest.download(batch['messages'],self.root,self.runtime,self.account,self.options,False)
                latest.download(batch['messages'],self.root,self.runtime,self.account,self.options,False)
            self.assertEqual(requests,['/missing.jpg','/working.jpg'])
            image=next((self.root/self.account['folder']).glob('*.jpg'))
            self.assertEqual(image.read_bytes(),b'fallback fixture')
        finally:
            server.shutdown();server.server_close();worker.join(timeout=3)

    def test_programming_failure_log_has_locations_without_exception_values(self):
        try:raise TypeError('private-auth-token-value')
        except TypeError as exc:message=latest.failure_message(exc)
        self.assertIn('程序处理时间线数据出错',message);self.assertIn('TypeError',message)
        self.assertIn('test_latest_tweets.py:',message);self.assertNotIn('private-auth-token-value',message)

    def test_recovery_links_known_tweets_only_preserves_sources_and_is_idempotent(self):
        latest.archive.accept(self.db,self.account,dict(post(),count=2),create=True)
        source=self.runtime/'downloads';source.mkdir()
        first=source/f'2026-11-05_{snowflake(NOW)}_01.jpg';first.write_bytes(b'original photo')
        video=source/f'2026-11-05_{snowflake(NOW)}_02.mp4';video.write_bytes(b'original video')
        unknown=source/f'2026-11-05_{snowflake(NOW+dt.timedelta(days=1))}_01.jpg';unknown.write_bytes(b'not assigned to account')
        (source/f'2026-11-05_{snowflake(NOW)}_03.jpg.part').write_bytes(b'incomplete')
        count=latest.recover_downloads(self.db,self.root,self.runtime,[self.account])
        self.assertEqual(count,2);self.assertTrue(first.exists());self.assertTrue(video.exists());self.assertTrue(unknown.exists())
        doc=latest.archive.load_document(self.db,'a',snowflake(NOW))
        self.assertEqual(len(doc['images']),1);self.assertEqual(len(doc['videos']),1)
        self.assertEqual((self.root/doc['images'][0]).read_bytes(),b'original photo')
        self.assertEqual((self.root/doc['videos'][0]).read_bytes(),b'original video')
        self.assertEqual(latest.recover_downloads(self.db,self.root,self.runtime,[self.account]),0)

    def test_monthly_existing_media_skips_network_without_archive_hit(self):
        folder=self.root/self.account['folder']/'2026/11';folder.mkdir(parents=True)
        file=folder/f'2026-11-05_{snowflake(NOW)}_01.jpg';file.write_bytes(b'existing monthly photo')
        metadata=dict(post(),count=1,num=1,extension='jpg')
        messages=[(Message.Directory,'',metadata),(Message.Url,'http://127.0.0.1:1/unreachable',metadata)]
        latest.download(messages,self.root,self.runtime,self.account,self.options,False)
        self.assertEqual(file.read_bytes(),b'existing monthly photo')
        self.assertEqual(len(list((self.root/self.account['folder']).rglob('*.jpg'))),1)

    def test_offline_repair_backs_up_database_and_does_not_require_cookies(self):
        import subprocess,sys
        (self.root/'tools').mkdir();(self.root/'tools/accounts.json').write_text(json.dumps([self.account]),encoding='utf-8')
        latest.archive.accept(self.db,self.account,dict(post(),count=1),create=True)
        source=self.runtime/'downloads';source.mkdir()
        (source/f'2026-11-05_{snowflake(NOW)}_01.jpg').write_bytes(b'recovered without network')
        (self.runtime/'cookies.txt').unlink()
        result=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).parent/'tools/latest_tweets.py'),
                               '--root',str(self.root),'--runtime-root',str(self.runtime),'--repair-local-media'],capture_output=True,encoding='utf-8',timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('补回 1 个文件',result.stdout)
        self.assertEqual(len(list((self.root/'_推文归档/维护备份').glob('*.sqlite'))),1)


if __name__=='__main__':unittest.main()
