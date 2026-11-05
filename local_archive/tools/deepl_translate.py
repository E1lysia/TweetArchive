"""DeepL text translation for the local tweet archive; Python standard library only."""
import argparse
import concurrent.futures
import datetime as dt
import getpass
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from translation_engine import (TranslationError, TranslationValidationError,
                                TranslationBatchValidationError, validated_xml,
                                ChatClient, load_config, effective_settings, is_local, atomic_json)

DEFAULTS = {
    "enabled": True, "api_key": "", "plan": "auto", "batch_size": 25,
    "workers": 3, "max_characters_per_run": 10000, "timeout_seconds": 30,
    "max_retries": 3,
    "protected_terms": ["青木陽菜", "鈴木みのり", "MyGO!!!!!", "Ave Mujica", "BanG Dream!"],
}
CONFIG_FILE = "deepl.local.json"
RETRYABLE = {429, 500, 502, 503, 504, 529}


DeepLError = TranslationError  # Backward-compatible error name for existing callers.


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def read_settings(root):
    settings = dict(DEFAULTS)
    path = root / "tools" / CONFIG_FILE
    if path.is_file():
        try:
            settings.update(json.loads(path.read_text(encoding="utf-8-sig")))
        except (ValueError, TypeError, OSError):
            raise DeepLError("DeepL 本地配置文件格式不正确，请检查 tools/deepl.local.json。") from None
    settings["api_key"] = os.environ.get("DEEPL_AUTH_KEY", "").strip() or str(settings["api_key"]).strip()
    if settings["plan"] not in ("auto", "free", "pro") or not isinstance(settings["enabled"], bool):
        raise DeepLError("DeepL 配置的 plan 或 enabled 无效。")
    for key, low, high in (("batch_size", 1, 50), ("workers", 1, 5),
                           ("max_characters_per_run", 1, 1000000),
                           ("timeout_seconds", 5, 60), ("max_retries", 0, 5)):
        value = settings[key]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise DeepLError(f"DeepL 配置 {key} 应为 {low}—{high} 之间的整数。")
    terms = settings["protected_terms"]
    if not isinstance(terms, list) or not all(isinstance(t, str) and t.strip() for t in terms):
        raise DeepLError("DeepL 配置 protected_terms 应为非空字符串组成的列表。")
    return settings


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DeepLError("DeepL 请求出现意外重定向，已停止。")


class DeepLClient:
    def __init__(self, settings, opener=None, sleep=time.sleep):
        self.settings = settings
        self.key = settings["api_key"]
        if not self.key:
            raise DeepLError("尚未配置 DeepL API 密钥，请双击「配置DeepL.cmd」。")
        plan = settings["plan"]
        if plan == "auto":
            plan = "free" if self.key.endswith(":fx") else "pro"
        self.base = "https://api-free.deepl.com" if plan == "free" else "https://api.deepl.com"
        self.opener = opener or urllib.request.build_opener(NoRedirect())
        self.sleep = sleep

    def request(self, endpoint, payload=None):
        # Only these two official endpoints receive the key. Never load cookies.
        if endpoint not in ("/v2/translate", "/v2/usage"):
            raise DeepLError("不支持的 DeepL 接口。")
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        for attempt in range(self.settings["max_retries"] + 1):
            req = urllib.request.Request(self.base + endpoint, data=body, headers={
                "Authorization": "DeepL-Auth-Key " + self.key,
                "Content-Type": "application/json", "User-Agent": "LocalTweetArchive/1.0",
            })
            try:
                with self.opener.open(req, timeout=self.settings["timeout_seconds"]) as response:
                    result = json.loads(response.read().decode("utf-8"))
                if not isinstance(result, dict):
                    raise TranslationValidationError('response_shape', "DeepL 返回的数据格式不正确。")
                return result
            except urllib.error.HTTPError as exc:
                status = exc.code
                exc.close()
                if status not in RETRYABLE or attempt == self.settings["max_retries"]:
                    messages = {403: "密钥无效、端点不匹配或缺少接口权限", 456: "账户额度或用量上限已耗尽",
                                400: "请求参数不受支持", 413: "请求过大"}
                    raise DeepLError(f"DeepL HTTP {status}：{messages.get(status, '服务暂时不可用，请稍后重试')}。") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
                if attempt == self.settings["max_retries"]:
                    raise DeepLError("无法连接 DeepL，请检查网络或代理后重试。") from None
            except (ValueError, UnicodeError):
                raise TranslationValidationError('response_json', "DeepL 返回的响应无法解析；未写入该批译文。") from None
            self.sleep(min(2 ** attempt, 16))

    def usage(self):
        result = self.request("/v2/usage")
        remaining = []
        for prefix in ("", "api_key_"):
            used, limit = result.get(prefix + "character_count"), result.get(prefix + "character_limit")
            if isinstance(used, int) and isinstance(limit, int):
                remaining.append(max(0, limit - used))
        if not remaining:
            raise DeepLError("DeepL 用量数据不完整，未发送翻译请求。")
        return min(remaining)

    def translate(self, tasks):
        payload = make_payload(tasks)
        result = self.request("/v2/translate", payload)
        values = result.get("translations")
        if not isinstance(values, list) or len(values) != len(tasks):
            raise TranslationValidationError('response_count', "DeepL 返回的译文数量不匹配；未写入该批译文。")
        outputs, failures = [], []
        for task, value in zip(tasks, values):
            try:
                translated = validated_xml(value['text'], task['keep'])
            except (KeyError, TypeError):
                failures.append((task, TranslationValidationError('response_shape', 'DeepL 响应缺少有效译文。')))
                continue
            except TranslationValidationError as exc:
                failures.append((task, exc))
                continue
            outputs.append((task, translated, value.get("detected_source_language")))
        if failures:
            raise TranslationBatchValidationError(outputs, failures)
        return outputs


def masked(text, terms):
    pattern = r"https?://[^\s]+|#[\w]+|(?<![\w@])@[A-Za-z0-9_]+"
    if terms:
        pattern += "|" + "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    parts, keep, position = [], [], 0
    for match in re.finditer(pattern, text):
        parts.extend((html.escape(text[position:match.start()]), "<keep>", html.escape(match[0]), "</keep>"))
        keep.append(match[0])
        position = match.end()
    parts.append(html.escape(text[position:]))
    return "<tweet>" + "".join(parts) + "</tweet>", keep


def make_payload(tasks):
    return {"text": [t["xml"] for t in tasks], "target_lang": "ZH-HANS",
            "tag_handling": "xml", "outline_detection": False,
            "ignore_tags": ["keep"], "preserve_formatting": True,
            "split_sentences": "nonewlines"}


def batches(tasks, size):
    current = []
    for task in tasks:
        candidate = current + [task]
        length = len(json.dumps(make_payload(candidate), ensure_ascii=False).encode("utf-8"))
        if current and (len(candidate) > size or length > 120000):
            yield current
            current = []
        if len(json.dumps(make_payload([task]), ensure_ascii=False).encode("utf-8")) > 120000:
            raise DeepLError("有单条正文超过 DeepL 请求大小限制，暂未翻译。")
        current.append(task)
    if current:
        yield current


def store_translation(db, refs, source_hash, translated, info):
    count = 0
    with db:
        for account, tid in refs:
            row = db.execute("SELECT document FROM tweets WHERE account=? AND tweet_id=?", (account, tid)).fetchone()
            if not row:
                continue
            doc = json.loads(row[0])
            if doc["status"] != "archived" or doc.get("translation_zh") or digest(doc["content"]) != source_hash:
                continue
            doc["translation_zh"] = translated
            doc["translation_info"] = {**info, "language": "zh-CN", "source_sha256": source_hash,
                                       "translated_at": now()}
            db.execute("UPDATE tweets SET document=? WHERE account=? AND tweet_id=?",
                       (json.dumps(doc, ensure_ascii=False, indent=2), account, tid))
            count += 1
    return count


def task_label(task):
    # Log identifiers only; never echo source text or a provider response.
    return '、'.join(f'{account}/{tid}' for account, tid in task['refs'])


def translate_resilient(client, tasks, retries, sleep=None):
    """Retry invalid items independently and retain valid results in their batch."""
    outputs, failures = [], []
    fatal = None
    sleep = sleep or time.sleep

    def attempt(batch):
        nonlocal fatal
        try:
            outputs.extend(client.translate(batch))
            return []
        except TranslationBatchValidationError as exc:
            outputs.extend(exc.outputs)
            return exc.failures
        except TranslationValidationError as exc:
            return [(task, exc) for task in batch]
        except TranslationError as exc:
            fatal = exc
            return []

    pending = attempt(tasks)
    for task, error in pending:
        attempts = 1
        for retry in range(retries):
            if fatal:
                break
            print(f'  校验重试 {retry + 1}/{retries}：{task_label(task)}；原因：{error}', flush=True)
            sleep(min(2 ** retry, 4))
            remaining = attempt([{**task, '_validation_retry': True}])
            attempts += 1
            if fatal:
                break
            if not remaining:
                error = None
                break
            error = remaining[0][1]
        if error is not None:
            failures.append(dict(refs=task['refs'], code=error.code, reason=str(error), attempts=attempts))
            print(f'  已跳过：{task_label(task)}；原因：{error}；仍保留待翻译。', flush=True)
    return outputs, failures, fatal


def translate_archive(db, root, account_keys=None, dry_run=False, limit=0, client_factory=DeepLClient, post_types=None, force=False, config_root=None):
    groups, cache = {}, {}
    documents = [(a, t, json.loads(v)) for a, t, v in db.execute("SELECT account,tweet_id,document FROM tweets WHERE status='archived' ORDER BY tweet_id DESC")]
    for account, tid, doc in documents:
        if doc.get("translation_zh") and doc.get("translation_info", {}).get("source_sha256") == digest(doc["content"]):
            cache[digest(doc["content"])] = (doc["translation_zh"], doc["translation_info"])
    for account, tid, doc in documents:
        if account_keys is not None and account not in account_keys:
            continue
        if post_types is not None and doc.get('post_type', 'original') not in post_types:
            continue
        if doc.get("translation_zh") or not doc["content"].strip():
            continue
        # Text is archived independently of whether local media exists.
        text = doc["content"]
        task = groups.setdefault(digest(text), {"source": text, "refs": [], "lang": (doc.get("metadata") or {}).get("lang", "")})
        task["refs"].append((account, tid))
    if limit:
        groups = dict(list(groups.items())[:limit])
    total = sum(len(t["refs"]) for t in groups.values())
    if not total:
        print("中文译文已齐全：没有需要调用翻译引擎的正文。", flush=True)
        return {"status": "complete", "translated": 0, "pending": 0}
    config_root = config_root or root
    settings = effective_settings(config_root, load_config(config_root), read_settings(config_root))
    name = settings['name']
    if dry_run:
        print(f"待译 {total} 条，去重后 {len(groups)} 段，共 {sum(len(t['source']) for t in groups.values())} 字符；仅预览，未联网。")
        return {"status": "preview", "translated": 0, "pending": total}
    local_count = 0
    tasks = []
    for source_hash, task in groups.items():
        task["hash"] = source_hash
        task["xml"], task["keep"] = masked(task["source"], settings["protected_terms"])
        plain = re.sub(r"https?://[^\s]+|#[\w]+|(?<![\w@])@[A-Za-z0-9_]+", "", task["source"])
        if source_hash in cache:
            value, info = cache[source_hash]
            local_count += store_translation(db, task["refs"], source_hash, value, {**info, "cache_reused": True})
        elif str(task["lang"]).lower().startswith("zh") or not any(c.isalpha() for c in plain):
            local_count += store_translation(db, task["refs"], source_hash, task["source"], {"translator": "原样保留"})
        else:
            tasks.append(task)
    if not tasks:
        print(f"已在本地补齐 {local_count} 条，无需调用翻译服务。", flush=True)
        return {"status": "complete", "translated": local_count, "pending": 0}
    local_endpoint = is_local(settings.get('endpoint',''))
    if (not settings["enabled"] and not force) or (not settings["api_key"] and not local_endpoint):
        print(f"{name} 尚未启用或未填密钥，请打开软件“设置与翻译”。原文已保留，可稍后补译。", flush=True)
        return {"status": "missing_key", "translated": local_count, "pending": total - local_count}
    client = ChatClient(settings) if settings['engine']!='deepl' and client_factory is DeepLClient else client_factory(settings)
    remaining = client.usage()
    budget = min(remaining, settings["max_characters_per_run"])
    selected, characters = [], 0
    for task in tasks:
        if characters + len(task["source"]) <= budget:
            selected.append(task)
            characters += len(task["source"])
    if not selected:
        raise DeepLError(f"{name} 剩余额度或本次字符上限不足，未发送翻译请求。")
    # Validate every payload before sending the first translation request.
    work = iter(list(batches(selected, settings["batch_size"])))
    translated = local_count
    first_error = None
    failures = []
    retries = min(2, settings['max_retries'])
    report_path = root / '_推文归档/翻译记录' / (dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8] + '.json')

    def save_failure_report():
        if not failures:
            return
        atomic_json(report_path, dict(engine=settings['engine'], model=settings.get('model'),
                                      updated_at=now(), translated=translated, pending=total-translated,
                                      failures=failures))

    print(f"{name}：计划翻译 {len(selected)} 段、约 {characters} 字符，最多 {settings['workers']} 批并发。", flush=True)
    print(f'格式或保护内容校验失败时，单条最多重试 {retries} 次；仍失败则跳过并继续。重试可能产生额外 API 费用。', flush=True)
    if settings['engine']!='deepl':
        print('模型：'+settings['model']+'；字符上限只限制原文长度，实际费用由服务商按 token 计费。',flush=True)
        print('翻译格式：编号占位符 + JSON；链接、用户名、话题和指定人名由本机原样还原。',flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=settings["workers"]) as pool:
        pending = {}

        def submit():
            batch = next(work, None)
            if batch is not None:
                pending[pool.submit(translate_resilient, client, batch, retries)] = batch

        for _ in range(settings["workers"]):
            submit()
        while pending:
            done, _ = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                pending.pop(future)
                try:
                    outputs, invalid, fatal = future.result()
                    failures.extend(invalid)
                    first_error = first_error or fatal
                    for task, value, lang in outputs:
                        info = dict(translator=name, engine=settings['engine'], detected_source_language=lang)
                        if settings['engine']!='deepl':
                            info['model']=settings['model']
                            info['format']='placeholders-json-v1'
                        translated += store_translation(db, task["refs"], task["hash"], value, info)
                    print(f"  已保存 {translated}/{total} 条中文译文。", flush=True)
                    save_failure_report()
                except DeepLError as exc:
                    first_error = first_error or exc
                if first_error is None:
                    submit()
    failed_count = sum(len(f['refs']) for f in failures)
    if failures:
        print(f'校验失败汇总：{failed_count} 条（去重后 {len(failures)} 段）；已跳过，其余有效译文已保存。', flush=True)
        for failure in failures:
            print(f"  {task_label(failure)}：{failure['reason']}（尝试 {failure['attempts']} 次）", flush=True)
        print(f'失败明细已保存：{report_path}', flush=True)
    if first_error:
        raise first_error
    pending_count = total - translated
    selected_hashes = {task['hash'] for task in selected}
    unselected_count = sum(len(task['refs']) for task in tasks if task['hash'] not in selected_hashes)
    outcome = '部分完成' if failures else '完成'
    print(f"中文翻译{outcome}：本次保存 {translated} 条，校验失败 {failed_count} 条，待译 {pending_count} 条。", flush=True)
    if unselected_count:
        print(f"因本次字符上限尚未处理 {unselected_count} 条，可再次点击“补译中文”继续。", flush=True)
    if failures:
        print('校验失败的条目可再次点击“补译中文”或切换模型重试；已保存译文不会重复调用。', flush=True)
    return {"status": "partial" if failures else "complete" if not pending_count else "limited",
            "translated": translated, "pending": pending_count, "failed": failed_count,
            "unselected": unselected_count, "failure_report": str(report_path) if failures else None}


def configure(root):
    print("申请 API 密钥：https://www.deepl.com/your-account/keys")
    print("在此窗口粘贴密钥，输入内容不会显示；不要发送到聊天。")
    key = getpass.getpass("DeepL API 密钥（留空取消）：").strip()
    if not key:
        print("已取消。")
        return
    settings = read_settings(root)
    settings.update(api_key=key, enabled=True, plan="auto")
    remaining = DeepLClient(settings).usage()
    path = root / "tools" / CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    print(f"密钥校验成功，已保存至本地。当前剩余额度约 {remaining} 字符。")
    print("现在可双击「补译中文.cmd」或照常使用「补新.cmd」。")


def main():
    parser = argparse.ArgumentParser(description="本地 DeepL API 密钥配置与连接检查（不发送推文）。")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--configure", action="store_true")
    parser.add_argument("--sample", action="store_true", help="翻译三段固定日语样例并显示耗时，不修改推文库")
    args = parser.parse_args()
    try:
        if args.configure:
            configure(args.root.resolve())
        else:
            settings = read_settings(args.root.resolve())
            client = DeepLClient(settings)
            remaining = client.usage()
            print(f"DeepL 连接成功，剩余额度约 {remaining} 字符；未发送翻译请求。")
            if args.sample:
                samples = ["今日はいい天気ですね。", "ライブに来てくれて、ありがとうございました！", "新しい写真を投稿しました。 #MyGO"]
                if sum(map(len, samples)) > min(remaining, settings["max_characters_per_run"]):
                    raise DeepLError("样例测试所需字符额度不足。")
                tasks = []
                for text in samples:
                    xml, keep = masked(text, settings["protected_terms"])
                    tasks.append({"source": text, "xml": xml, "keep": keep})
                start = time.perf_counter()
                for task, value, _ in client.translate(tasks):
                    print(f"原文：{task['source']}\n译文：{value}\n")
                print(f"三段样例合计耗时 {time.perf_counter() - start:.2f} 秒；未改动推文库。")
    except (DeepLError, KeyboardInterrupt) as exc:
        print(str(exc) if isinstance(exc, DeepLError) else "已取消。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
