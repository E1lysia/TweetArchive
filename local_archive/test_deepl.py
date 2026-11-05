import copy
import hashlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent / "tools"))
import deepl_translate as deepl


class Response(io.BytesIO):
    def __init__(self, value):
        super().__init__(json.dumps(value).encode())


class Opener:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        item = next(self.replies)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            item = item(request)
        return Response(item)


def settings(**changes):
    return {**copy.deepcopy(deepl.DEFAULTS), "api_key": "fake-local-test-key:fx", **changes}


class ClientTests(unittest.TestCase):
    def test_official_endpoint_header_and_usage(self):
        op = Opener([{"character_count": 30, "character_limit": 100,
                      "api_key_character_count": 5, "api_key_character_limit": 25}])
        client = deepl.DeepLClient(settings(), opener=op)
        self.assertEqual(client.usage(), 20)
        request = op.requests[0]
        self.assertEqual(request.full_url, "https://api-free.deepl.com/v2/usage")
        self.assertIsNone(request.data)
        self.assertNotIn("Cookie", request.headers)
        self.assertEqual(deepl.DeepLClient(settings(api_key="fake-pro-key")).base, "https://api.deepl.com")

    def test_rate_limit_retry_and_no_secret_in_error(self):
        err = urllib.error.HTTPError("https://api-free.deepl.com", 429, "fake-local-test-key:fx", {}, None)
        op = Opener([err, {"character_count": 0, "character_limit": 10}])
        sleep = mock.Mock()
        client = deepl.DeepLClient(settings(), opener=op, sleep=sleep)
        self.assertEqual(client.usage(), 10)
        sleep.assert_called_once_with(1)
        self.assertEqual(len(op.requests), 2)

    def test_auth_and_quota_errors_do_not_retry(self):
        for code in (403, 456):
            err = urllib.error.HTTPError("https://api-free.deepl.com", code, "secret-should-not-print", {}, None)
            op, sleep = Opener([err]), mock.Mock()
            with self.assertRaises(deepl.DeepLError) as raised:
                deepl.DeepLClient(settings(), opener=op, sleep=sleep).usage()
            self.assertNotIn("secret-should-not-print", str(raised.exception))
            sleep.assert_not_called()

    def test_network_error_bounded_retries(self):
        op = Opener([urllib.error.URLError("secret") for _ in range(3)])
        with self.assertRaises(deepl.DeepLError):
            deepl.DeepLClient(settings(max_retries=2), opener=op, sleep=lambda _: None).usage()
        self.assertEqual(len(op.requests), 3)

    def test_xml_preserves_links_tags_terms_and_escapes(self):
        source = '青木陽菜 <3 & こんにちは #MyGO @tester https://example.com/?a=1&b=2'
        xml, keep = deepl.masked(source, ["青木陽菜"])
        task = {"xml": xml, "keep": keep}
        op = Opener([{"translations": [{"text": xml.replace("こんにちは", "你好"), "detected_source_language": "JA"}]}])
        value = deepl.DeepLClient(settings(), opener=op).translate([task])[0][1]
        self.assertEqual(value, source.replace("こんにちは", "你好"))
        payload = json.loads(op.requests[0].data)
        self.assertEqual(payload["target_lang"], "ZH-HANS")
        self.assertEqual(payload["ignore_tags"], ["keep"])

    def test_damaged_or_incomplete_translation_is_rejected(self):
        task = {"xml": "<tweet>hello<keep>#tag</keep></tweet>", "keep": ["#tag"]}
        for response in ({"translations": []}, {"translations": [{"text": "<tweet>你好</tweet>"}]},
                         {"translations": [{"text": "not xml"}]}):
            with self.assertRaises(deepl.DeepLError):
                deepl.DeepLClient(settings(), opener=Opener([response])).translate([task])

    def test_missing_quota_and_redirect_rejected(self):
        with self.assertRaises(deepl.DeepLError):
            deepl.DeepLClient(settings(), opener=Opener([{}])).usage()
        with self.assertRaises(deepl.DeepLError):
            deepl.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example")

    def test_batch_count_and_payload_limits(self):
        task = {"xml": "<tweet>こんにちは</tweet>"}
        self.assertEqual([len(b) for b in deepl.batches([task] * 51, 25)], [25, 25, 1])
        with self.assertRaises(deepl.DeepLError):
            list(deepl.batches([{"xml": "あ" * 50000}], 25))


class FakeClient:
    def __init__(self, budget=10000, fail_after=None):
        self.calls, self.budget, self.fail_after = [], budget, fail_after

    def usage(self):
        return self.budget

    def translate(self, tasks):
        self.calls.append(tasks)
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise deepl.DeepLError("DeepL HTTP 456：额度不足。")
        return [(task, "中文：" + task["source"], "JA") for task in tasks]


class ArchiveTranslationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "tools").mkdir()
        self.path = self.root / "tools" / deepl.CONFIG_FILE
        self.path.write_text(json.dumps(settings(workers=1, batch_size=1)), encoding="utf-8")
        (self.root / "image.jpg").write_bytes(b"fixture")
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE tweets (account TEXT, tweet_id TEXT, status TEXT, document TEXT)")
        self.env = mock.patch.dict(deepl.os.environ, {"DEEPL_AUTH_KEY": ""})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.db.close()
        self.temp.cleanup()

    def add(self, tid, text="こんにちは", account="a", status="archived", translated=None, images=None):
        doc = {"tweet_id": tid, "status": status, "content": text, "translation_zh": translated,
               "images": images if images is not None else ["image.jpg"], "metadata": {"lang": "ja"}}
        if translated:
            doc["translation_info"] = {"translator": "Codex", "source_sha256": deepl.digest(text)}
        self.db.execute("INSERT INTO tweets VALUES(?,?,?,?)", (account, tid, status, json.dumps(doc)))
        self.db.commit()

    def get(self, tid):
        return json.loads(self.db.execute("SELECT document FROM tweets WHERE tweet_id=?", (tid,)).fetchone()[0])

    def run_translate(self, client=None, **kwargs):
        return deepl.translate_archive(self.db, self.root, client_factory=lambda _: client or FakeClient(), **kwargs)

    def test_no_pending_needs_no_key_and_no_network(self):
        self.add("1", translated="已有译文")
        with mock.patch.object(deepl, "read_settings", side_effect=AssertionError("不应读取密钥")):
            self.assertEqual(self.run_translate()["pending"], 0)
        self.assertEqual(self.get("1")["translation_zh"], "已有译文")

    def test_duplicate_content_is_translated_once(self):
        self.add("1")
        self.add("2")
        client = FakeClient()
        self.assertEqual(self.run_translate(client)["translated"], 2)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(len(client.calls[0]), 1)
        self.assertEqual(self.get("1")["translation_info"]["translator"], "DeepL")

    def test_existing_translation_reused_without_network(self):
        self.add("1", translated="你好")
        self.add("2")
        client = FakeClient()
        self.assertEqual(self.run_translate(client)["translated"], 1)
        self.assertEqual(self.get("2")["translation_zh"], "你好")
        self.assertFalse(client.calls)

    def test_excluded_empty_and_missing_images_skipped(self):
        self.add("1", status="excluded")
        self.add("2", text="")
        self.add("3", images=["missing.jpg"])
        self.assertEqual(self.run_translate()["pending"], 0)

    def test_scope_and_character_budget(self):
        self.add("1", text="こんにちは")
        self.add("2", text="おはようございます")
        self.add("3", text="別アカウント", account="b")
        result = self.run_translate(FakeClient(budget=5), account_keys={"a"})
        self.assertEqual(result["translated"], 1)
        self.assertEqual(result["pending"], 1)
        self.assertIsNone(self.get("3")["translation_zh"])

    def test_missing_key_preserves_pending(self):
        self.add("1")
        self.path.write_text(json.dumps(settings(api_key="")), encoding="utf-8")
        self.assertEqual(self.run_translate()["status"], "missing_key")
        self.assertIsNone(self.get("1")["translation_zh"])

    def test_selected_post_type_leaves_other_types_untranslated(self):
        self.add('1', text='オリジナル')
        self.add('2', text='引用した文章')
        doc = self.get('2')
        doc['post_type'] = 'quote'
        with self.db:
            self.db.execute('UPDATE tweets SET document=? WHERE tweet_id=?', (json.dumps(doc), '2'))
        self.assertEqual(self.run_translate(post_types={'quote'})['translated'], 1)
        self.assertIsNone(self.get('1')['translation_zh'])
        self.assertIsNotNone(self.get('2')['translation_zh'])

    def test_successful_batch_survives_later_failure(self):
        self.add("1", text="こんにちは")
        self.add("2", text="おはようございます")
        with self.assertRaises(deepl.DeepLError):
            self.run_translate(FakeClient(fail_after=1))
        self.assertEqual(sum(bool(self.get(t)["translation_zh"]) for t in ("1", "2")), 1)
        self.assertEqual(self.run_translate()["translated"], 1)

    def test_changed_source_and_existing_translation_never_overwritten(self):
        self.add("1", translated="原译文")
        self.assertEqual(deepl.store_translation(self.db, [("a", "1")], deepl.digest("こんにちは"), "新译文", {}), 0)
        self.add("2")
        self.assertEqual(deepl.store_translation(self.db, [("a", "2")], deepl.digest("旧内容"), "错配", {}), 0)

    def test_preview_does_not_write_or_call_api(self):
        self.add("1")
        client = FakeClient()
        self.assertEqual(self.run_translate(client, dry_run=True)["status"], "preview")
        self.assertFalse(client.calls)
        self.assertIsNone(self.get("1")["translation_zh"])

    def test_symbols_and_hashtags_need_no_api(self):
        self.add("1", text="🐥 #MyGO https://example.com")
        self.path.write_text(json.dumps(settings(api_key="")), encoding="utf-8")
        self.assertEqual(self.run_translate()["translated"], 1)
        self.assertEqual(self.get("1")["translation_info"]["translator"], "原样保留")


if __name__ == "__main__":
    unittest.main()
