import http.cookiejar
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import grab_cookies as refresh


def cookie(**values):
    return dict(domain='.x.com', path='/', secure=True, httpOnly=True,
                name='auth_token', value='test-fixture-token', **values)


class RefreshTests(unittest.TestCase):
    def test_only_x_domains(self):
        cookies = [cookie(), dict(cookie(), domain='.notx.com'),
                   dict(cookie(), domain='.x.com.attacker.example'),
                   dict(cookie(), domain='.twitter.com')]
        self.assertEqual(len(refresh.selected_cookies(cookies)), 2)

    def test_expired_or_missing_auth_rejected(self):
        for cookies in ([], [cookie(expirationDate=1)], [dict(cookie(), name='ct0')]):
            with self.assertRaises(ValueError):
                refresh.selected_cookies(cookies)

    def test_netscape_session_and_http_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'cookies.txt'
            refresh.save_cookies([cookie()], path)
            jar = http.cookiejar.MozillaCookieJar(str(path))
            jar.load(ignore_discard=True)
            loaded = list(jar)
            self.assertEqual(len(loaded), 1)
            self.assertFalse(loaded[0].is_expired())
            self.assertEqual(loaded[0].name, 'auth_token')
            self.assertTrue(loaded[0].has_nonstandard_attr('HTTPOnly'))

    def test_invalid_export_preserves_existing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'cookies.txt'; path.write_text('original')
            for cookies in ([], [dict(cookie(), value='bad\nline')]):
                with self.assertRaises(ValueError): refresh.save_cookies(cookies, path)
                self.assertEqual(path.read_text(), 'original')

    def test_replace_failure_preserves_existing_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'cookies.txt'; path.write_text('original')
            with patch.object(Path, 'replace', side_effect=PermissionError):
                with self.assertRaises(PermissionError): refresh.save_cookies([cookie()], path)
            self.assertEqual(path.read_text(), 'original')
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_extension_has_only_scoped_hosts(self):
        with tempfile.TemporaryDirectory() as directory:
            refresh.make_extension(Path(directory), 12345, 'test-fixture-secret')
            manifest = json.loads((Path(directory)/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['permissions'], ['cookies'])
            self.assertNotIn('<all_urls>', manifest['host_permissions'])
            script = (Path(directory)/'background.js').read_text(encoding='utf-8')
            self.assertIn('http://127.0.0.1:12345/cookies/test-fixture-secret', script)
            self.assertNotIn('getAll({})', script)

    def test_bundled_extension_stays_inactive_until_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)/'TweetArchive-XLogin'
            refresh.make_extension(folder)
            script = (folder/'background.js').read_text(encoding='utf-8')
            self.assertIn('const ENDPOINT = null;', script)
            self.assertIn('if (!ENDPOINT || busy) return;', script)
            manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['background']['service_worker'], 'background.js')

    def test_extension_reset_preserves_fixed_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)/'TweetArchive-XLogin'
            refresh.make_extension(folder, 12345, 'old-fixture-secret')
            refresh.make_extension(folder, 12346, 'new-fixture-secret')
            script = (folder/'background.js').read_text(encoding='utf-8')
            self.assertIn('new-fixture-secret', script)
            self.assertNotIn('old-fixture-secret', script)
            refresh.make_extension(folder)
            self.assertTrue((folder/'manifest.json').is_file())
            self.assertTrue((folder/'background.js').is_file())
            self.assertNotIn('fixture-secret', (folder/'background.js').read_text(encoding='utf-8'))

    def test_loopback_endpoint_validation(self):
        result, done = {}, threading.Event()
        server = refresh.http.server.ThreadingHTTPServer(('127.0.0.1', 0), refresh.make_handler('fixture-secret', result, done))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            def post(path, payload, length=None):
                conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
                headers = {'Content-Type':'application/json'}
                if length is not None: headers['Content-Length'] = str(length)
                conn.request('POST', path, payload, headers)
                response = conn.getresponse(); status = response.status; response.read(); conn.close()
                return status
            self.assertEqual(post('/cookies/wrong', '[]'), 404)
            self.assertEqual(post('/cookies/fixture-secret', '[]'), 422)
            self.assertEqual(post('/cookies/fixture-secret', '', refresh.LIMIT+1), 413)
            self.assertFalse(done.is_set())
            self.assertEqual(post('/cookies/fixture-secret', json.dumps([cookie()])), 200)
            self.assertTrue(done.is_set())
            self.assertEqual(len(result['cookies']), 1)
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()
