"""Offline regression tests: retry, isolate bad items, and preserve valid commits."""
import contextlib
import io
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent / 'tools'))
import deepl_translate as deepl
import translation_engine as engine
from test_deepl import Opener, settings
from test_translation_engine import llm_settings, response, translation_reply


def task(tid='1', source='こんにちは #Live'):
    xml, keep = deepl.masked(source, [])
    return dict(source=source, xml=xml, keep=keep, refs=[('a', tid)], hash=deepl.digest(source))


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.log = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.log)
        self.redirect.__enter__()
        self.sleep = mock.patch.object(deepl.time, 'sleep', return_value=None)
        self.sleep.start()

    def tearDown(self):
        self.sleep.stop()
        self.redirect.__exit__(None, None, None)

    def test_invalid_then_valid_retries_for_every_chat_provider(self):
        for provider in ('deepseek', 'qwen', 'kimi', 'custom'):
            config = llm_settings()
            config['engine'] = provider
            op = Opener([response('{"translation":"你好"}'), translation_reply(lambda text:text.replace('こんにちは','你好'))])
            outputs, failures, fatal = deepl.translate_resilient(engine.ChatClient(config, opener=op), [task()], 2)
            self.assertIsNone(fatal)
            self.assertFalse(failures)
            self.assertEqual(outputs[0][1], '你好 #Live')
            self.assertEqual(len(op.requests), 2)
            retry = json.loads(op.requests[1].data)
            self.assertIn('上一次结果未通过校验', retry['messages'][0]['content'])
            self.assertEqual(retry['messages'][1]['content'], json.loads(op.requests[0].data)['messages'][1]['content'])

    def test_persistent_validation_failure_is_bounded_and_redacted(self):
        raw = '{"translation":"private-response fake-llm-key"}'
        op = Opener([response(raw)] * 3)
        outputs, failures, fatal = deepl.translate_resilient(engine.ChatClient(llm_settings(), opener=op), [task()], 2)
        self.assertFalse(outputs)
        self.assertIsNone(fatal)
        self.assertEqual(len(op.requests), 3)
        self.assertEqual(failures[0]['attempts'], 3)
        self.assertEqual(failures[0]['code'], 'placeholder_changed')
        self.assertIn('a/1', self.log.getvalue())
        for secret in ('private-response', 'fake-llm-key'):
            self.assertNotIn(secret, self.log.getvalue() + json.dumps(failures))

    def test_deepl_batch_preserves_valid_item_without_retranslating_it(self):
        good, bad = task('1'), task('2', 'こんばんは #Night')
        op = Opener([
            dict(translations=[dict(text='<tweet>你好 <keep>#Live</keep></tweet>'), dict(text='<tweet>坏译文</tweet>')]),
            dict(translations=[dict(text='<tweet>晚上好 <keep>#Night</keep></tweet>')])])
        outputs, failures, fatal = deepl.translate_resilient(deepl.DeepLClient(settings(), opener=op), [good, bad], 2)
        self.assertEqual([value for _, value, _ in outputs], ['你好 #Live', '晚上好 #Night'])
        self.assertFalse(failures)
        self.assertIsNone(fatal)
        self.assertEqual(json.loads(op.requests[1].data)['text'], [bad['xml']])

    def test_service_failure_during_retry_keeps_other_valid_outputs(self):
        good, bad = task('1'), task('2')
        class Client:
            calls = 0
            def translate(self, batch):
                self.calls += 1
                if self.calls == 1:
                    raise engine.TranslationBatchValidationError([(good, '已验证译文', None)],
                        [(bad, engine.TranslationValidationError('invalid_xml', 'XML 错误。'))])
                raise engine.TranslationError('HTTP 401：密钥无效。')
        client = Client()
        outputs, failures, fatal = deepl.translate_resilient(client, [good, bad], 2)
        self.assertEqual(outputs[0][1], '已验证译文')
        self.assertEqual(client.calls, 2)
        self.assertIsNotNone(fatal)
        self.assertEqual(failures[0]['attempts'], 2)

    def test_distinct_validation_reasons_and_strict_protection(self):
        cases = [
            ('<tweet>hi &</tweet>', [], 'invalid_xml'),
            ('<tweet x="1">hi</tweet>', [], 'xml_structure'),
            ('<tweet><keep><b>#Live</b></keep></tweet>', ['#Live'], 'xml_structure'),
            ('<tweet/>', [], 'empty_translation'),
            ('<tweet>#Live</tweet>', ['#Live'], 'protected_text_changed'),
            ('<!DOCTYPE tweet><tweet>hi</tweet>', [], 'xml_declaration'),
            (None, [], 'response_shape')]
        for value, keep, code in cases:
            with self.assertRaises(engine.TranslationValidationError) as raised:
                engine.validated_xml(value, keep)
            self.assertEqual(raised.exception.code, code)
        op = Opener([response('<tweet>partial</tweet>', 'length')])
        with self.assertRaises(engine.TranslationBatchValidationError) as raised:
            engine.ChatClient(llm_settings(), opener=op).translate([task()])
        self.assertEqual(raised.exception.failures[0][1].code, 'truncated')

    def test_invalid_json_response_is_retried_without_logging_it(self):
        op = Opener([[], translation_reply(lambda text:text.replace('こんにちは','你好'))])
        outputs, failures, fatal = deepl.translate_resilient(engine.ChatClient(llm_settings(), opener=op), [task()], 2)
        self.assertEqual(outputs[0][1], '你好 #Live')
        self.assertFalse(failures)
        self.assertIsNone(fatal)

    def test_archive_continues_reports_duplicate_refs_and_only_retries_pending(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = engine.load_config(root)
            config.update(engine='deepseek', workers=1, max_characters_per_run=1000)
            config['profiles']['deepseek']['api_key'] = 'fake-llm-key'
            engine.save_config(root, config)
            db = sqlite3.connect(':memory:')
            self.addCleanup(db.close)
            db.execute('CREATE TABLE tweets(account TEXT,tweet_id TEXT,status TEXT,document TEXT)')
            for tid, source, translated in [('9', '既存', '已有译文'), ('3', '失敗 #Live', None),
                                             ('2', '成功', None), ('1', '失敗 #Live', None)]:
                doc = dict(status='archived', content=source, translation_zh=translated, metadata={'lang':'ja'})
                db.execute('INSERT INTO tweets VALUES(?,?,?,?)', ('a',tid,'archived',json.dumps(doc)))
            op = Opener([response('{"translation":"private-response"}')] * 3 + [response('{"translation":"成功译文"}')])
            with mock.patch.object(engine.urllib.request, 'build_opener', return_value=op):
                result = deepl.translate_archive(db, root)
            self.assertEqual(result['status'], 'partial')
            self.assertEqual((result['translated'], result['failed'], result['pending']), (1, 2, 2))
            self.assertEqual(result['unselected'], 0)
            report = Path(result['failure_report']).read_text(encoding='utf-8')
            entry = json.loads(report)['failures'][0]
            self.assertEqual(entry['refs'], [['a','3'], ['a','1']])
            self.assertEqual(entry['attempts'], 3)
            self.assertNotIn('fake-llm-key', report)
            self.assertNotIn('private-response', report)
            self.assertNotIn('因本次字符上限尚未处理', self.log.getvalue())
            docs = {tid: json.loads(raw) for tid, raw in db.execute('SELECT tweet_id,document FROM tweets')}
            self.assertEqual(docs['9']['translation_zh'], '已有译文')
            self.assertEqual(docs['2']['translation_zh'], '成功译文')
            self.assertIsNone(docs['1']['translation_zh'])
            op = Opener([translation_reply(lambda text:text.replace('失敗','恢复译文'))])
            with mock.patch.object(engine.urllib.request, 'build_opener', return_value=op):
                result = deepl.translate_archive(db, root)
            self.assertEqual((result['translated'], result['pending']), (2, 0))
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(len(op.requests), 1)

    def test_disabled_retries_do_not_send_extra_requests(self):
        op = Opener([response('bad xml')])
        _, failures, _ = deepl.translate_resilient(engine.ChatClient(llm_settings(), opener=op), [task()], 0)
        self.assertEqual(len(op.requests), 1)
        self.assertEqual(failures[0]['attempts'], 1)

    def test_cli_partial_exit_and_export_with_concurrent_local_provider(self):
        from test_archive import archive
        calls, state = [], {'fixed': False}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                text = json.loads(payload['messages'][1]['content'])['text']
                calls.append(text)
                value = '损坏译文' if '失敗' in text and not state['fixed'] else text.replace('原文', '译文').replace('失敗', '恢复')
                body = json.dumps(response(json.dumps({'translation':value}))).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                account = dict(key='a', folder='测试账号', handle='@tester', name='测试')
                engine.atomic_json(root/'tools/accounts.json', [account])
                config = engine.load_config(root)
                config.update(engine='custom', workers=3, max_retries=0)
                config['profiles']['custom'].update(base_url=f'http://127.0.0.1:{server.server_port}/v1', model='offline-fixture')
                engine.save_config(root, config)
                db = archive.database(root)
                for index in range(8):
                    tid = str(2100000000000000000 + index)
                    archive.seed(db, root, account, {tid:[]})
                    doc = archive.load_document(db, 'a', tid)
                    doc.update(status='archived', content=('失敗' if index in (6, 7) else f'原文 {index}')+' #Live',
                               metadata={'lang':'ja'}, post_type='original')
                    archive.save(db, 'a', doc)
                db.close()
                args = [sys.executable, '-X', 'utf8', str(Path(archive.__file__)), '--root', str(root), '--translate-only']
                env = {**os.environ, 'NO_PROXY':'127.0.0.1,localhost', 'no_proxy':'127.0.0.1,localhost'}
                first = subprocess.run(args, capture_output=True, encoding='utf-8', timeout=15, env=env)
                self.assertEqual(first.returncode, 10, first.stdout + first.stderr)
                self.assertIn('校验失败 2 条', first.stdout)
                self.assertIn('本次保存 6 条', first.stdout)
                self.assertTrue((root/'推文归档.html').is_file())
                self.assertEqual(len(calls), 7)
                state['fixed'] = True
                second = subprocess.run(args, capture_output=True, encoding='utf-8', timeout=15, env=env)
                self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
                self.assertIn('本次保存 2 条', second.stdout)
                self.assertEqual(len(calls), 8)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)


if __name__ == '__main__':
    unittest.main()
