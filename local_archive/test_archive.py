import datetime as dt
import importlib.util
import hashlib
import json
import tempfile
import subprocess
import sys
import unittest
from unittest import mock
from pathlib import Path

spec = importlib.util.spec_from_file_location("archive", Path(__file__).parent / "tools/tweet_archive.py")
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.account = {"key": "test", "folder": "测试账号", "name": "测试", "handle": "@tester"}
        self.tid = "2105455273142001910"
        self.image = self.root / "测试账号/2026/10" / f"2026-10-01_{self.tid}_01.jpg"
        self.image.parent.mkdir(parents=True)
        self.image.write_bytes(b"fixture")
        self.db = archive.database(self.root)
        archive.seed(self.db, self.root, self.account, archive.images_for(self.root, self.account))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def metadata(self, **extra):
        return {"tweet_id": int(self.tid), "author": {"name": "tester", "nick": "测试"},
                "content": "日本語原文\n<script>alert(1)</script>",
                "date": dt.datetime(2026, 10, 1, 16, 30), **extra}

    def test_archive_links_timezone_dedup_and_script_safety(self):
        archive.accept(self.db, self.account, self.metadata())
        archive.seed(self.db, self.root, self.account, archive.images_for(self.root, self.account))
        self.assertEqual(self.db.execute("SELECT count(*) FROM tweets").fetchone()[0], 1)
        result = archive.export(self.db, self.root, [self.account])
        self.assertEqual(result, {"archived": 1, "pending": 0})
        doc = json.loads(next((self.root / "测试账号/推文").rglob("*.json")).read_text(encoding="utf-8"))
        self.assertTrue(doc["date_beijing"].startswith("2026-10-02T00:30"))
        self.assertEqual(doc["images"], [self.image.relative_to(self.root).as_posix()])
        self.assertNotIn("<script>", (self.root / "_推文归档/data.js").read_text(encoding="utf-8"))

    def test_retweets_quotes_and_sources_are_classified_without_claiming_original(self):
        for flags, kind in (({'retweet_id':1}, 'retweet'), ({'quote_id':1}, 'reference'),
                            ({'quoted_id':1}, 'quote'), ({'author':{'name':'someone_else'}}, 'reference')):
            archive.accept(self.db, self.account, self.metadata(**flags))
            result = archive.export(self.db, self.root, [self.account])
            self.assertEqual(result, {"archived": 1, "pending": 0})
            self.assertTrue(self.image.is_file())
            doc = archive.load_document(self.db, 'test', self.tid)
            self.assertEqual(doc['post_type'], kind)
            self.assertEqual(doc['content'], self.metadata()['content'])

    def test_legacy_excluded_records_are_reopened_for_reclassification(self):
        doc = archive.load_document(self.db, 'test', self.tid)
        doc.update(status='excluded', metadata=None, exclusion_reason='转推或引用推文')
        archive.save(self.db, 'test', doc)
        archive.seed(self.db, self.root, self.account, archive.images_for(self.root, self.account))
        migrated = archive.load_document(self.db, 'test', self.tid)
        self.assertEqual(migrated['status'], 'pending')
        archive.accept(self.db, self.account, self.metadata(quoted_id=123))
        self.assertEqual(archive.load_document(self.db, 'test', self.tid)['post_type'], 'quote')

    def test_retweet_retains_archive_owner_and_original_author(self):
        archive.accept(self.db, self.account, self.metadata(retweet_id=123, author={'name':'origin','nick':'原作者'}))
        doc = archive.load_document(self.db, 'test', self.tid)
        self.assertEqual(doc['account_handle'], '@tester')
        self.assertEqual(doc['handle'], '@origin')
        self.assertEqual(doc['author'], '原作者')
        self.assertEqual(doc['source_tweet_id'], '123')
        self.assertIn('/tester/status/', doc['url'])

    def test_pending_has_no_fabricated_document(self):
        self.assertEqual(archive.export(self.db, self.root, [self.account])["pending"], 1)
        self.assertFalse((self.root / "测试账号/推文").exists())

    def test_explicit_empty_body_archives_normally_but_missing_body_stays_pending(self):
        metadata=self.metadata();metadata.pop('content')
        self.assertFalse(archive.accept(self.db,self.account,metadata))
        self.assertEqual(archive.load_document(self.db,'test',self.tid)['status'],'pending')
        metadata['content']=''
        self.assertTrue(archive.accept(self.db,self.account,metadata))
        doc=archive.load_document(self.db,'test',self.tid)
        self.assertEqual(doc['status'],'archived');self.assertEqual(doc['text_state'],'empty')
        self.assertEqual(archive.export(self.db,self.root,[self.account])['archived'],1)

    def test_video_only_exports_original_translation_and_relative_links(self):
        video = self.root / '测试账号/视频GIF/2026/10' / f'2026-10-01_{self.tid}_01.mp4'
        video.parent.mkdir(parents=True)
        video.write_bytes(b'video fixture')
        archive.seed(self.db, self.root, self.account, {}, archive.videos_for(self.root, self.account))
        archive.accept(self.db, self.account, self.metadata())
        doc = archive.load_document(self.db, 'test', self.tid)
        doc['translation_zh'] = '中文视频原文'
        archive.save(self.db, 'test', doc)
        self.assertEqual(archive.export(self.db, self.root, [self.account]), {'archived': 1, 'pending': 0})
        exported = next((self.root / '测试账号/推文').rglob('*.md')).read_text(encoding='utf-8')
        self.assertIn('播放视频 1', exported)
        self.assertIn('中文视频原文', exported)
        archive.seed(self.db, self.root, self.account, {}, archive.videos_for(self.root, self.account))
        self.assertEqual(archive.load_document(self.db, 'test', self.tid)['translation_zh'], '中文视频原文')

    def test_video_scan_ignores_unrelated_files_and_keeps_quote_type(self):
        folder = self.root / '测试账号/视频GIF'
        folder.mkdir()
        (folder / f'2026-10-01_{self.tid}_01.mp4').write_bytes(b'fixture')
        (folder / 'unrelated.mp4').write_bytes(b'fixture')
        videos = archive.videos_for(self.root, self.account)
        self.assertEqual(list(videos), [self.tid])
        archive.seed(self.db, self.root, self.account, {}, videos)
        archive.accept(self.db, self.account, self.metadata(quoted_id=123))
        self.assertEqual(archive.export(self.db, self.root, [self.account])['archived'], 1)
        self.assertEqual(archive.load_document(self.db, 'test', self.tid)['post_type'], 'quote')

    def test_content_update_clears_stale_translation(self):
        archive.accept(self.db, self.account, self.metadata())
        doc = archive.load_document(self.db, "test", self.tid)
        doc["translation_zh"] = "旧译文"
        doc["translation_info"] = {"translator": "test"}
        archive.save(self.db, "test", doc)
        archive.accept(self.db, self.account, self.metadata(content="新原文"))
        self.assertIsNone(archive.load_document(self.db, "test", self.tid)["translation_zh"])
        self.assertNotIn("translation_info", archive.load_document(self.db, "test", self.tid))

    def bundle(self, text=None, translation="中文译文\n<script>保留为纯文本</script>"):
        source = text if text is not None else self.metadata()["content"]
        path = self.root / "translations.json"
        path.write_text(json.dumps({"version": 1, "language": "zh-CN", "translations": [
            {"source_text": source, "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
             "translation_zh": translation}]}), encoding="utf-8")
        return path

    def test_import_translation_export_and_repeat(self):
        archive.accept(self.db, self.account, self.metadata())
        self.assertEqual(archive.import_translations(self.db, self.bundle()), 1)
        self.assertEqual(archive.import_translations(self.db, self.bundle()), 0)
        archive.export(self.db, self.root, [self.account])
        doc = archive.load_document(self.db, "test", self.tid)
        self.assertTrue(doc["translation_zh"].startswith("中文译文"))
        self.assertEqual(doc["content"], self.metadata()["content"])
        md = next((self.root / "测试账号/推文").rglob("*.md")).read_text(encoding="utf-8")
        self.assertIn(doc["translation_zh"], md)
        self.assertNotIn("<script>保留为纯文本", (self.root / "推文归档.html").read_text(encoding="utf-8"))

    def test_wrong_source_translation_is_not_imported(self):
        archive.accept(self.db, self.account, self.metadata())
        self.assertEqual(archive.import_translations(self.db, self.bundle(text="其他原文")), 0)
        self.assertIsNone(archive.load_document(self.db, "test", self.tid)["translation_zh"])

    def test_corrupt_translation_bundle_rejected(self):
        archive.accept(self.db, self.account, self.metadata())
        path = self.bundle()
        bundle = json.loads(path.read_text(encoding="utf-8"))
        bundle["translations"][0]["source_sha256"] = "incorrect"
        path.write_text(json.dumps(bundle), encoding="utf-8")
        self.assertRaises(ValueError, archive.import_translations, self.db, path)
        self.assertIsNone(archive.load_document(self.db, "test", self.tid)["translation_zh"])

    def test_missing_images_and_video_directory_ignored(self):
        self.image.unlink()
        video_image = self.root / "测试账号/视频GIF" / self.image.name
        video_image.parent.mkdir()
        video_image.write_bytes(b"fixture")
        self.assertFalse(archive.images_for(self.root, self.account))
        self.assertEqual(archive.export(self.db, self.root, [self.account]), {"archived": 0, "pending": 0})

    def test_folder_must_stay_under_root(self):
        self.assertRaises(ValueError, archive.images_for, self.root, {**self.account, "folder": ".."})

    def test_incremental_uses_single_tweet_then_skips_completed(self):
        from gallery_dl.extractor.message import Message
        (self.root / "config.json").write_text("{}", encoding="utf-8")
        with mock.patch("gallery_dl.extractor.find", return_value=[(Message.Directory, "", self.metadata())]) as find:
            archive.sync(self.db, self.root, self.account, archive.images_for(self.root, self.account))
            self.assertIn("/status/" + self.tid, find.call_args[0][0])
        with mock.patch("gallery_dl.extractor.find", side_effect=AssertionError("不应联网")):
            archive.sync(self.db, self.root, self.account, archive.images_for(self.root, self.account))

    def test_large_repost_batch_uses_timeline_and_keeps_original_author(self):
        from gallery_dl.extractor.message import Message
        (self.root / 'config.json').write_text('{}', encoding='utf-8')
        media = {str(int(self.tid) + i):[self.image.relative_to(self.root).as_posix()] for i in range(21)}
        archive.seed(self.db, self.root, self.account, media)
        messages = [(Message.Directory, '', self.metadata(tweet_id=int(tid), retweet_id=123,
                    author={'name':'origin', 'nick':'原作者'})) for tid in media]
        with mock.patch('gallery_dl.extractor.find', return_value=messages) as find:
            archive.sync(self.db, self.root, self.account, media)
            self.assertTrue(find.call_args[0][0].endswith('/timeline'))
        self.assertTrue(all(archive.load_document(self.db, 'test', tid)['post_type']=='retweet' for tid in media))

    def test_unavailable_tweet_retains_pending(self):
        (self.root / "config.json").write_text("{}", encoding="utf-8")
        with mock.patch("gallery_dl.extractor.find", return_value=[]):
            self.assertRaises(RuntimeError, archive.sync, self.db, self.root,
                              self.account, archive.images_for(self.root, self.account))
        self.assertEqual(archive.load_document(self.db, "test", self.tid)["status"], "pending")

    def test_portable_python_cli_loads_sibling_translation_module(self):
        archive.accept(self.db, self.account, self.metadata())
        (self.root / "tools").mkdir()
        (self.root / "tools/accounts.json").write_text(json.dumps([self.account]), encoding="utf-8")
        result = subprocess.run([sys.executable, "-B", str(Path(archive.__file__)), "--root", str(self.root),
                                 "--translate-only"], capture_output=True, text=True, encoding="utf-8",
                                env={**__import__('os').environ, "PYTHONIOENCODING": "utf-8", "DEEPL_AUTH_KEY": ""})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("尚未启用或未填密钥", result.stdout)


if __name__ == "__main__":
    unittest.main()
