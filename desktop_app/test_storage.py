import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from contextlib import closing

spec=importlib.util.spec_from_file_location('storage',Path(__file__).with_name('storage.py'))
storage=importlib.util.module_from_spec(spec);spec.loader.exec_module(storage)
spec=importlib.util.spec_from_file_location('library',Path(__file__).with_name('library.py'))
library=importlib.util.module_from_spec(spec);spec.loader.exec_module(library)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.source=self.base/'原始库 空格';library.initialize_library(self.source)
        storage.atomic_json(self.source/'tools/accounts.json',[dict(key='test',folder='作者',handle='@example',name='测试')])
        (self.source/'作者/2026').mkdir(parents=True);(self.source/'作者/2026/photo.jpg').write_bytes(b'fixture')
        (self.source/'cookies.txt').write_text('private-fixture')
        (self.source/'tools/translation.local.json').write_text('private-fixture')
        self.target=self.base/'新位置'
        with closing(sqlite3.connect(self.source/'_推文归档/tweets.sqlite')) as db, db:
            doc=dict(tweet_id='1',status='archived',content='原文',translation_zh='译文',images=['作者/2026/photo.jpg'],videos=[])
            db.execute('INSERT INTO tweets VALUES(?,?,?,?)',('test','1','archived',json.dumps(doc)))
        lib=library.Library(self.source);lib.annotate(lib.docs[0],favorite=True,tags='保留');lib.state.close()

    def tearDown(self):self.temp.cleanup()

    def test_copy_keeps_source_notes_media_and_excludes_credentials(self):
        original=library.Library(self.source)
        group=original.create_group('作者分组');original.move_account('test',group['id']);original.state.close()
        storage.copy_library(self.source,self.target)
        lib=library.Library(self.target)
        try:
            self.assertEqual(lib.docs[0]['translation_zh'],'译文')
            self.assertTrue(lib.docs[0]['favorite']);self.assertEqual(lib.docs[0]['tags'],'保留')
            self.assertEqual(lib.account_groups()['memberships']['test'],group['id'])
        finally:lib.state.close()
        self.assertEqual((self.target/'作者/2026/photo.jpg').read_bytes(),b'fixture')
        self.assertTrue((self.source/'作者/2026/photo.jpg').is_file())
        self.assertFalse((self.target/'cookies.txt').exists())
        self.assertFalse((self.target/'tools/translation.local.json').exists())

    def test_pointer_changes_only_after_valid_target_and_offline_not_reinitialized(self):
        with self.assertRaises((OSError,ValueError)):storage.select_library(self.source,self.target)
        self.assertFalse((self.source/'tools/storage.local.json').exists())
        storage.copy_library(self.source,self.target);storage.select_library(self.source,self.target)
        self.assertEqual(storage.resolve_library(self.source),self.target.resolve())
        storage.atomic_json(self.source/'tools/storage.local.json',dict(data_root=str(self.base/'离线磁盘')))
        with self.assertRaises(ValueError):storage.resolve_library(self.source)
        self.assertFalse((self.base/'离线磁盘').exists())

    def test_reject_nested_nonempty_and_incomplete_library(self):
        for target in [self.source,self.source/'nested',self.base]:
            with self.assertRaises(ValueError):storage.empty_destination(self.source,target)
        self.target.mkdir();(self.target/'owned.txt').write_text('preserve')
        with self.assertRaises(ValueError):storage.copy_library(self.source,self.target)
        self.assertEqual((self.target/'owned.txt').read_text(),'preserve')
        (self.source/'.tweetarchive-copying').touch()
        with self.assertRaises(ValueError):storage.validate_library(self.source)

    def test_failure_retains_source_and_does_not_select_partial_target(self):
        def fail(*args):raise OSError('fixture interruption')
        with self.assertRaises(OSError):storage.copy_library(self.source,self.target,fail)
        self.assertTrue((self.target/'.tweetarchive-copying').exists())
        self.assertEqual(storage.resolve_library(self.source),self.source.resolve())
        self.assertTrue((self.source/'作者/2026/photo.jpg').exists())
        with self.assertRaises(ValueError):storage.validate_library(self.target)

    def test_sqlite_backup_includes_uncheckpointed_wal(self):
        path=self.source/'作者/archive.sqlite'
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('PRAGMA journal_mode=WAL');db.execute('CREATE TABLE downloaded(id TEXT)')
            db.execute("INSERT INTO downloaded VALUES('preserved')");db.commit()
            storage.copy_library(self.source,self.target)
        with closing(sqlite3.connect(self.target/'作者/archive.sqlite')) as db:
            self.assertEqual(db.execute('SELECT id FROM downloaded').fetchone()[0],'preserved')

    def test_new_empty_library_does_not_copy_old_accounts(self):
        storage.empty_destination(self.source,self.target);library.initialize_library(self.target)
        storage.select_library(self.source,self.target)
        self.assertEqual(json.loads((self.target/'tools/accounts.json').read_text()),[])
        self.assertEqual(len(json.loads((self.source/'tools/accounts.json').read_text())),1)


if __name__=='__main__':unittest.main()
