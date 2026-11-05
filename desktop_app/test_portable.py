import http.cookiejar
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from library import initialize_library,import_login_file


class PortableTests(unittest.TestCase):
    def test_first_start_initializes_empty_library_and_keeps_existing_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'带 空格的资料库'
            initialize_library(root)
            self.assertEqual(json.loads((root/'tools/accounts.json').read_text()),[])
            with closing(sqlite3.connect(root/'_推文归档/tweets.sqlite')) as db:
                with db: db.execute('INSERT INTO tweets VALUES(?,?,?,?)',('a','1','archived','{}'))
            (root/'tools/accounts.json').write_text('[{"key":"a"}]')
            initialize_library(root)
            self.assertEqual(json.loads((root/'tools/accounts.json').read_text()),[{'key':'a'}])
            with closing(sqlite3.connect(root/'_推文归档/tweets.sqlite')) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM tweets').fetchone()[0],1)

    def test_import_only_copies_x_cookies_and_rejects_bad_or_expired_login(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'input.txt'
            source.write_text('# Netscape HTTP Cookie File\n.x.com\tTRUE\t/\tTRUE\t2147483647\tauth_token\tfixture-token\n.example.com\tTRUE\t/\tTRUE\t2147483647\tsecret\tother-site\n',encoding='utf-8')
            self.assertEqual(import_login_file(root,source),1)
            data=(root/'cookies.txt').read_text()
            self.assertIn('auth_token',data); self.assertNotIn('other-site',data)
            source.write_text('# Netscape HTTP Cookie File\n.x.com\tTRUE\t/\tTRUE\t1\tauth_token\texpired\n')
            with self.assertRaises(ValueError): import_login_file(root,source)
            self.assertEqual((root/'cookies.txt').read_text(),data)
            source.write_text('not a cookies file')
            with self.assertRaises(ValueError): import_login_file(root,source)


if __name__=='__main__': unittest.main()
