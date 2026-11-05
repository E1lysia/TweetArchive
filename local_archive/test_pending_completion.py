"""Known-ID completion must reach old posts and preserve interrupted progress."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from gallery_dl import exception
from gallery_dl.extractor.message import Message

spec = importlib.util.spec_from_file_location('pending_archive', Path(__file__).parent / 'tools/tweet_archive.py')
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


class PendingCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir()
        (self.runtime / 'config.json').write_text('{}', encoding='utf-8')
        self.account = dict(key='a', handle='@tester', name='测试', folder='media')
        self.db = archive.database(self.root)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def seed(self, count=1):
        ids = [str(1500000000000000000 + i) for i in range(count)]
        archive.seed(self.db, self.root, self.account, {tid: [f'media/{tid}.jpg'] for tid in ids})
        return ids

    def metadata(self, tid, **extra):
        return dict(tweet_id=int(tid), content='古い本文', author=dict(name='tester', nick='测试'), **extra)

    def run_completion(self, find):
        with mock.patch('gallery_dl.extractor.find', side_effect=find), contextlib.redirect_stdout(io.StringIO()):
            return archive.complete_pending(self.db, self.root, self.runtime, self.account)

    def test_more_than_twenty_old_posts_use_individual_urls_and_skip_completed_on_retry(self):
        ids = self.seed(25)
        requested = []
        def find(url):
            requested.append(url)
            tid = url.rsplit('/', 1)[1]
            # URL messages can contain lazy fallbacks; no download job may run.
            metadata = self.metadata(tid)
            metadata['_fallback'] = (x for x in ['https://example.invalid/fallback'])
            return iter([(Message.Directory, '', metadata), (Message.Url, 'https://example.invalid/image', metadata)])
        result = self.run_completion(find)
        self.assertEqual(result['completed'], 25)
        self.assertEqual(result['remaining'], 0)
        self.assertEqual({url.rsplit('/', 1)[1] for url in requested}, set(ids))
        self.assertTrue(all('/tester/status/' in url for url in requested))
        self.assertEqual(archive.load_document(self.db, 'a', ids[0])['images'], [f'media/{ids[0]}.jpg'])
        self.assertEqual(self.run_completion(lambda url: self.fail('must not refetch'))['attempted'], 0)

    def test_explicit_empty_is_archived_missing_body_remains_pending_and_unrelated_post_is_ignored(self):
        empty, missing = self.seed(2)
        def find(url):
            tid = url.rsplit('/', 1)[1]
            metadata = self.metadata(tid)
            if tid == empty: metadata['content'] = ''
            else: metadata.pop('content')
            return iter([(Message.Directory, '', self.metadata('1800000000000000000')),
                         (Message.Directory, '', metadata)])
        result = self.run_completion(find)
        self.assertEqual((result['completed'], result['remaining']), (1, 1))
        self.assertEqual(archive.load_document(self.db, 'a', empty)['text_state'], 'empty')
        self.assertEqual(archive.load_document(self.db, 'a', missing)['status'], 'pending')
        self.assertIn('completion_error', archive.load_document(self.db, 'a', missing))
        self.assertIsNone(archive.load_document(self.db, 'a', '1800000000000000000'))

    def test_unavailable_continues_then_retry_clears_error_and_keeps_other_accounts_unchanged(self):
        old, unavailable = self.seed(2)
        other = dict(self.account, key='other')
        archive.seed(self.db, self.root, other, {old: ['other.jpg']})
        def find(url):
            if url.endswith(unavailable): raise exception.NotFoundError('secret must not be logged')
            return iter([(Message.Directory, '', self.metadata(old, quoted_id=123))])
        result = self.run_completion(find)
        self.assertEqual((result['completed'], result['remaining']), (1, 1))
        self.assertEqual(archive.load_document(self.db, 'a', old)['post_type'], 'quote')
        result = self.run_completion(lambda url: iter([(Message.Directory, '', self.metadata(unavailable))]))
        self.assertEqual(result['remaining'], 0)
        self.assertNotIn('completion_error', archive.load_document(self.db, 'a', unavailable))
        self.assertEqual(archive.load_document(self.db, 'other', old)['status'], 'pending')

    def test_rate_limit_stops_without_reclassifying_unknown_posts(self):
        self.seed(3)
        requests = []
        def find(url):
            requests.append(url)
            raise exception.AbortExtraction('Rate limit exceeded')
        result = self.run_completion(find)
        self.assertTrue(result['stopped'])
        self.assertEqual(len(requests), 1)
        self.assertEqual(result['remaining'], 3)

    def test_cli_does_not_scan_timeline_seed_media_or_translate_and_reports_partial(self):
        self.seed()
        (self.root / 'tools').mkdir()
        (self.root / 'tools/accounts.json').write_text(json.dumps([self.account]), encoding='utf-8')
        (self.runtime / 'cookies.txt').write_text('fixture', encoding='utf-8')
        self.db.close()
        args = ['tweet_archive.py', '--root', str(self.root), '--runtime-root', str(self.runtime), '--complete-pending']
        with mock.patch('sys.argv', args), mock.patch.object(archive, 'complete_pending', return_value=dict(remaining=1, stopped=False)) as complete, \
             mock.patch.object(archive, 'sync_text', side_effect=AssertionError('timeline')), \
             mock.patch.object(archive, 'images_for', side_effect=AssertionError('media scan')), \
             mock.patch('importlib.util.spec_from_file_location', side_effect=AssertionError('translation')), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(archive.main(), 10)
            complete.assert_called_once()
        self.db = archive.database(self.root)


if __name__ == '__main__':
    unittest.main()
