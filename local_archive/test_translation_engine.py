import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).parent/'tools'))
import translation_engine as engine
import deepl_translate as deepl
from test_deepl import Opener,settings


def llm_settings(**changes):
    return dict(engine='deepseek',name='DeepSeek',model='deepseek-flash',api_key='fake-llm-key',
                endpoint='https://api.deepseek.com/v1/chat/completions',max_characters_per_run=10000,
                timeout_seconds=60,max_retries=1,**changes)


def response(text,reason='stop'):
    return dict(choices=[dict(finish_reason=reason,message=dict(content=text))])


def translation_reply(transform=lambda text: text):
    def reply(request):
        text = json.loads(json.loads(request.data)['messages'][1]['content'])['text']
        return response(json.dumps({'translation':transform(text)},ensure_ascii=False))
    return reply


class EngineTests(unittest.TestCase):
    def test_translation_preserves_protected_parts_and_request_schema(self):
        source='こんにちは 青木陽菜 #Live @tester https://example.com'
        xml,keep=deepl.masked(source,['青木陽菜'])
        op=Opener([translation_reply(lambda text:text.replace('こんにちは','你好'))])
        value=engine.ChatClient(llm_settings(),opener=op).translate([dict(source=source,xml=xml,keep=keep)])[0][1]
        self.assertEqual(value,source.replace('こんにちは','你好'))
        req=op.requests[0]
        self.assertEqual(req.headers['Authorization'],'Bearer fake-llm-key')
        self.assertNotIn('Cookie',req.headers)
        payload=json.loads(req.data)
        self.assertEqual(payload['model'],'deepseek-flash')
        self.assertEqual(payload['thinking'],{'type':'disabled'})
        self.assertFalse(payload['stream'])
        sent = payload['messages'][1]['content']
        for protected in keep:
            self.assertNotIn(protected, sent)
        self.assertNotIn('<keep>', sent)

    def test_rejects_truncation_bad_format_or_missing_placeholders(self):
        task=dict(source='hi #Live',xml='<tweet>hi <keep>#Live</keep></tweet>',keep=['#Live'])
        bad=[response('<tweet>你好</tweet>'),response('<tweet>你好<keep>#Live</keep></tweet>','length'),
             response('解释一下'),response('<tweet><script>text</script><keep>#Live</keep></tweet>'),
             response('<tweet><keep x="1">#Live</keep></tweet>')]
        for value in bad:
            with self.assertRaises(engine.TranslationError):
                engine.ChatClient(llm_settings(),opener=Opener([value])).translate([task])

    def test_retry_and_redacted_errors(self):
        error=lambda code: urllib.error.HTTPError('https://example.com',code,'fake-llm-key',{},io.BytesIO(b'secret'))
        op=Opener([error(429),translation_reply(lambda text:'你好')]); sleep=mock.Mock()
        engine.ChatClient(llm_settings(),opener=op,sleep=sleep).translate([dict(xml='<tweet>hello</tweet>',keep=[])])
        self.assertEqual(len(op.requests),2); sleep.assert_called_once_with(1)
        for code in (400,401,402,403,404):
            with self.assertRaises(engine.TranslationError) as exc:
                engine.ChatClient(llm_settings(),opener=Opener([error(code)])).request({})
            self.assertNotIn('fake-llm-key',str(exc.exception)); self.assertNotIn('secret',str(exc.exception))
        with self.assertRaises(engine.TranslationError):
            engine.NoRedirect().redirect_request(None,None,302,'',{},'https://other.example')

    def test_url_validation_and_normalization(self):
        self.assertEqual(engine.endpoint('https://example.com/v1/'),'https://example.com/v1/chat/completions')
        self.assertEqual(engine.endpoint('http://localhost:11434/v1/chat/completions'),'http://localhost:11434/v1/chat/completions')
        for url in ('http://example.com/v1','https://user:secret@example.com','https://example.com?key=secret','file:///tmp'):
            with self.assertRaises(engine.TranslationError): engine.endpoint(url)

    def test_legacy_fallback_and_credentials_are_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'tools').mkdir()
            legacy=settings(); engine.atomic_json(root/'tools/deepl.local.json',legacy)
            config=engine.load_config(root)
            self.assertEqual(config['engine'],'deepl')
            self.assertEqual(engine.effective_settings(root,config,legacy)['api_key'],legacy['api_key'])
            config['engine']='deepseek'
            self.assertEqual(engine.effective_settings(root,config,legacy)['api_key'],'')
            config['profiles']['deepseek']['api_key']='separate-fake-key'
            engine.save_config(root,config)
            self.assertNotIn(legacy['api_key'],(root/'tools'/engine.CONFIG_FILE).read_text())
            self.assertEqual(engine.read_json(root/'tools/deepl.local.json'),legacy)
            self.assertEqual(engine.load_config(root)['profiles']['deepseek']['api_key'],'separate-fake-key')

    def test_archive_engine_route_provenance_budget_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'tools').mkdir(); (root/'image.jpg').write_bytes(b'fixture')
            config=engine.load_config(root); config.update(engine='deepseek',workers=1,enabled=False,max_characters_per_run=5)
            config['profiles']['deepseek']['api_key']='fake-key'; engine.save_config(root,config)
            db=sqlite3.connect(':memory:')
            try:
                db.execute('CREATE TABLE tweets(account TEXT,tweet_id TEXT,status TEXT,document TEXT)')
                for tid,translated in [('1','已有译文'),('2',None),('3',None)]:
                    doc=dict(status='archived',tweet_id=tid,content='こんにちは' if tid!='2' else 'こんばんは',translation_zh=translated,images=['image.jpg'],videos=[])
                    db.execute('INSERT INTO tweets VALUES(?,?,?,?)',('a',tid,'archived',json.dumps(doc)))
                opener=Opener([translation_reply(lambda text:'你好')])
                with mock.patch.object(engine.urllib.request,'build_opener',return_value=opener),mock.patch.dict(deepl.os.environ,{'DEEPL_AUTH_KEY':''}):
                    self.assertEqual(deepl.translate_archive(db,root)['status'],'missing_key')
                    result=deepl.translate_archive(db,root,force=True)
                self.assertEqual(result['translated'],1); self.assertEqual(result['pending'],1)
                docs={tid:json.loads(raw) for tid,raw in db.execute('SELECT tweet_id,document FROM tweets')}
                self.assertEqual(docs['1']['translation_zh'],'已有译文')
                info=docs['3']['translation_info']
                self.assertEqual(info['engine'],'deepseek'); self.assertEqual(info['model'],'deepseek-flash')
                self.assertEqual(len(opener.requests),1)
            finally: db.close()

    def test_embedded_cli_loads_provider_and_preserves_archive_without_a_key(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'tools').mkdir()
            engine.atomic_json(root/'tools/accounts.json',[dict(key='a',folder='account',name='测试',handle='@tester')])
            config=engine.load_config(root); config['engine']='deepseek'; engine.save_config(root,config)
            result=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).parent/'tools/tweet_archive.py'),
                                   '--root',str(root),'--translate-only'],capture_output=True,encoding='utf-8',timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('没有需要调用翻译引擎',result.stdout)
            self.assertTrue((root/'推文归档.html').is_file())


if __name__=='__main__': unittest.main()
