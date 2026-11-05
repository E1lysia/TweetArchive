import importlib.util
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

spec = importlib.util.spec_from_file_location('library', Path(__file__).with_name('library.py'))
library = importlib.util.module_from_spec(spec)
spec.loader.exec_module(library)


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'tools').mkdir()
        (self.root / '_推文归档').mkdir()
        self.accounts = [dict(key='a', name='测试', handle='@tester', folder='tester', url='https://x.com/tester/media')]
        (self.root / 'tools/accounts.json').write_text(json.dumps(self.accounts), encoding='utf-8')
        (self.root / 'photo.jpg').write_bytes(b'fixture')
        (self.root / 'video.mp4').write_bytes(b'fixture')
        with sqlite3.connect(self.root / '_推文归档/tweets.sqlite') as db:
            db.execute('CREATE TABLE tweets(account TEXT,tweet_id TEXT,status TEXT,document TEXT)')
            for tid, status, images, videos in [('100', 'archived', ['photo.jpg'], []), ('200', 'archived', [], ['video.mp4']), ('300', 'excluded', [], ['video.mp4']), ('400', 'pending', [], ['video.mp4'])]:
                doc = dict(tweet_id=tid, status=status, content='日本語テスト', translation_zh='中文译文' if tid == '100' else None, images=images, videos=videos, date_beijing='2026-10-01T00:00:00+08:00')
                doc['post_type'] = 'retweet' if tid == '200' else 'original'
                db.execute('INSERT INTO tweets VALUES(?,?,?,?)', ('a', tid, status, json.dumps(doc)))
        db.close()
        self.lib = library.Library(self.root)

    def tearDown(self):
        self.lib.state.close()
        self.temp.cleanup()

    def test_filters_exclude_unverified_and_retweets(self):
        self.assertEqual([d['tweet_id'] for d in self.lib.query()], ['200', '100'])
        self.assertEqual([d['tweet_id'] for d in self.lib.query(mode='videos')], ['200'])
        self.assertEqual([d['tweet_id'] for d in self.lib.query(mode='images')], ['100'])
        self.assertEqual([d['tweet_id'] for d in self.lib.query(mode='pending')], ['400'])
        self.assertEqual([d['tweet_id'] for d in self.lib.query(mode='untranslated')], ['200'])

    def test_archive_counts_include_excluded_without_showing_them(self):
        self.assertEqual(self.lib.archive_counts('a'), {'archived':2, 'excluded':1, 'pending':1})
        self.assertEqual(self.lib.archive_counts('unknown'), {'archived':0, 'excluded':0, 'pending':0})
        self.assertEqual(len(self.lib.query(account='a')), 2)

    def test_post_types_filter_and_counts_are_separate_from_owner(self):
        self.assertEqual([d['tweet_id'] for d in self.lib.query(post_type='original')], ['100'])
        self.assertEqual([d['tweet_id'] for d in self.lib.query(post_type='retweet')], ['200'])
        self.assertEqual(self.lib.content_counts('a'), dict(original=1, retweet=1, quote=0, reference=0))
        self.assertEqual(len(self.lib.query(post_types={'original','retweet'})),2)
        self.assertEqual(len(self.lib.query(post_types={'original','quote'})),1)

    def test_text_post_and_unavailable_media_are_not_confused(self):
        with closing(sqlite3.connect(self.root/'_推文归档/tweets.sqlite')) as db, db:
            for tid,count in [('500',0),('600',3)]:
                doc=dict(tweet_id=tid,status='archived',content='纯文字与媒体缺失',images=[],videos=[],source_media_count=count)
                db.execute('INSERT INTO tweets VALUES(?,?,?,?)',('a',tid,'archived',json.dumps(doc)))
        self.lib.reload()
        self.assertEqual([d['tweet_id'] for d in self.lib.query(mode='text')],['500'])
        self.assertEqual(next(d for d in self.lib.docs if d['tweet_id']=='600')['media_state'],'missing')
        self.assertEqual(len(self.lib.query()),4)

    def test_search_translation_original_date_and_account(self):
        self.assertEqual(len(self.lib.query(search='中文译文')), 1)
        self.assertEqual(len(self.lib.query(search='日本語')), 2)
        self.assertFalse(self.lib.query(month='2026-09'))
        self.assertFalse(self.lib.query(account='unknown'))
        self.assertEqual(self.lib.query(oldest=True)[0]['tweet_id'], '100')
        self.assertEqual(len(self.lib.query(month='2026')), 2)

    def test_preferences_roundtrip_and_invalid_json_fallback(self):
        state = {'page': 3, 'period': '2024-06', 'selected': '200'}
        self.lib.set_preference('browse', state)
        self.assertEqual(self.lib.preference('browse'), state)
        with self.lib.state:
            self.lib.state.execute("UPDATE preferences SET value='invalid' WHERE key='browse'")
        self.assertEqual(self.lib.preference('browse', {}), {})

    def test_favorites_and_tags_survive_restart(self):
        self.lib.annotate(self.lib.query()[0], favorite=True, tags='现场 演出')
        self.lib.reload()
        self.assertEqual(len(self.lib.query(mode='favorites')), 1)
        self.assertEqual(len(self.lib.query(search='现场 演出')), 1)
        self.assertEqual(len(self.lib.query(search='无此标签')), 0)

    def test_paths_cannot_escape_library(self):
        self.assertIsNone(self.lib.safe_path('../outside.mp4'))
        self.assertIsNone(self.lib.safe_path(self.root.parent))
        self.assertEqual(self.lib.safe_path('video.mp4'), self.root / 'video.mp4')

    def test_account_add_validation_duplicate_and_backup(self):
        for handle in ('../escape', 'https://x.com/a', 'name with space'):
            with self.assertRaises(ValueError):
                self.lib.add_account(handle, '')
        with self.assertRaises(ValueError):
            self.lib.add_account('@TESTER', '')
        added = self.lib.add_account('@new_author', '新账号')
        self.assertTrue((self.root / added['folder']).is_dir())
        self.assertEqual(json.loads((self.root / 'tools/accounts.before-manager.json').read_text(encoding='utf-8')), self.accounts)
        self.lib.reload()
        self.assertEqual(len(self.lib.accounts), 2)

    def test_new_handle_does_not_reuse_existing_account_key_or_directory(self):
        (self.root / 'a').mkdir()
        account = self.lib.add_account('a', '新账号')
        self.assertNotEqual(account['key'], 'a')
        self.assertNotEqual(account['folder'], 'a')


if __name__ == '__main__':
    unittest.main()
