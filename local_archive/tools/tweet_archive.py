"""Archive and classify tweets associated with existing gallery-dl media."""
import argparse
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

IMAGE = re.compile(r"^\d{4}-\d{2}-\d{2}_(\d{15,22})_\d+.*\.(?:jpe?g|png|webp)$", re.I)
VIDEO = re.compile(r"^\d{4}-\d{2}-\d{2}_(\d{15,22})_\d+.*\.(?:mp4|gif|webm|m4v|mov)$", re.I)
CST = dt.timezone(dt.timedelta(hours=8))
TYPE_LABELS = {'original':'原创', 'quote':'引用', 'retweet':'转推', 'reference':'关联来源'}


def post_type(account, metadata):
    if metadata.get('retweet_id'):
        return 'retweet'
    if metadata.get('quote_id'):
        return 'reference'
    if metadata.get('quoted_id'):
        return 'quote'
    author = (metadata.get('author') or {}).get('name', '')
    if author.lower() == account['handle'].lstrip('@').lower():
        return 'original'
    # A standalone fetch of old external media cannot prove a repost event.
    return 'reference'


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def write_text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(value, encoding="utf-8")
    temp.replace(path)


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def database(root):
    folder = root / "_推文归档"
    folder.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(folder / "tweets.sqlite")
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS tweets (
        account TEXT NOT NULL, tweet_id TEXT NOT NULL, status TEXT NOT NULL,
        document TEXT NOT NULL, PRIMARY KEY(account, tweet_id))""")
    return db


def load_document(db, account, tid):
    row = db.execute("SELECT document FROM tweets WHERE account=? AND tweet_id=?",
                     (account, tid)).fetchone()
    return json.loads(row[0]) if row else None


def save(db, account, doc):
    with db:
        db.execute("INSERT OR REPLACE INTO tweets VALUES (?, ?, ?, ?)",
                   (account, doc["tweet_id"], doc["status"], encode(doc)))


def images_for(root, account):
    folder = (root / account["folder"]).resolve()
    if not folder.is_relative_to(root.resolve()) or folder == root.resolve():
        raise ValueError("账号图片目录必须在 gallery-dl 目录内")
    images = {}
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or any(part in ("推文", "视频GIF") for part in path.relative_to(folder).parts):
            continue
        match = IMAGE.fullmatch(path.name)
        if match:
            images.setdefault(match[1], []).append(path.relative_to(root).as_posix())
    return images


def videos_for(root, account):
    folder = (root / account["folder"]).resolve()
    if not folder.is_relative_to(root.resolve()) or folder == root.resolve():
        raise ValueError("账号视频目录必须在 gallery-dl 目录内")
    videos = {}
    for path in sorted((folder / "视频GIF").rglob("*")):
        if path.is_file() and (match := VIDEO.fullmatch(path.name)):
            videos.setdefault(match[1], []).append(path.relative_to(root).as_posix())
    return videos


def seed(db, root, account, images, videos=None):
    videos = videos or {}
    for tid in dict.fromkeys([*images, *videos]):
        doc = load_document(db, account["key"], tid)
        if doc is None:
            date = dt.datetime.fromtimestamp(((int(tid) >> 22) + 1288834974657) / 1000,
                                             dt.timezone.utc).astimezone(CST)
            doc = {"tweet_id": tid, "status": "pending", "content": "",
                   "translation_zh": None, "date_beijing": date.isoformat(),
                   "url": f"https://x.com/{account['handle'].lstrip('@')}/status/{tid}",
                   "account": account["key"], "handle": account["handle"],
                   "author": account["name"], "first_archived_at": stamp()}
        doc["images"] = images.get(tid, [])
        doc["videos"] = videos.get(tid, doc.get("videos", []))
        if doc['status'] == 'excluded' and doc.get('classification_version') != 2:
            doc.update(status='pending', previous_exclusion_reason=doc.get('exclusion_reason'))
            doc.pop('exclusion_reason', None)
        if doc['status'] == 'archived' and not doc.get('post_type'):
            doc.update(post_type=post_type(account, doc.get('metadata') or {}), classification_version=2)
        doc.update(account_name=account['name'], account_handle=account['handle'])
        save(db, account["key"], doc)


def accept(db, account, metadata, create=False):
    # An explicit empty body is confirmed; an absent/null field is still unknown.
    if not isinstance(metadata.get('content'),str):return False
    tid = str(metadata["tweet_id"])
    doc = load_document(db, account["key"], tid)
    if doc is None:
        if not create:return False
        date=dt.datetime.fromtimestamp(((int(tid)>>22)+1288834974657)/1000,dt.timezone.utc).astimezone(CST)
        doc=dict(tweet_id=tid,status='pending',content='',translation_zh=None,images=[],videos=[],
                 account=account['key'],first_archived_at=stamp(),date_beijing=date.isoformat())
    author = metadata.get('author') or {}
    name = author.get('name') or account['handle'].lstrip('@')
    kind = post_type(account, metadata)
    content = metadata['content']
    if content != doc.get('content'):
        if doc.get('translation_zh'):
            doc['previous_translation_zh']=doc['translation_zh']
        doc['translation_zh'] = None
        doc.pop('translation_info', None)
    date = metadata.get('date')
    if isinstance(date, dt.datetime):
        if date.tzinfo is None:
            date = date.replace(tzinfo=dt.timezone.utc)
        doc['date_beijing'] = date.astimezone(CST).isoformat()
    source_id = metadata.get('retweet_id') or metadata.get('quoted_id')
    if kind == 'reference':
        source_id = tid
    doc.update(status='archived', content=content, author=author.get('nick') or name,
               handle='@' + name, post_type=kind, classification_version=2,
               account_name=account['name'], account_handle=account['handle'],
               url=f'https://x.com/{name}/status/{tid}',
               source_tweet_id=str(source_id) if source_id else None,
               source_url=f'https://x.com/i/web/status/{source_id}' if source_id else None,
               parent_tweet_id=str(metadata['quote_id']) if metadata.get('quote_id') else None,
               metadata=json.loads(encode(metadata)))
    if kind == 'retweet':
        doc['url'] = f"https://x.com/{account['handle'].lstrip('@')}/status/{tid}"
    doc.pop('exclusion_reason', None)
    if metadata.get('count') is not None:
        doc['source_media_count']=int(metadata['count'])
    doc["last_checked_at"] = stamp()
    doc['text_state']='present' if content.strip() else 'empty'
    save(db, account["key"], doc)
    return True


def sync(db, root, account, images, limit=0, runtime_root=None):
    pending = {tid for tid in images
               if load_document(db, account["key"], tid)["status"] == "pending"}
    if not pending:
        print("  对应推文均已核对，无需联网。", flush=True)
        return
    from gallery_dl import config, extractor
    from gallery_dl.extractor.message import Message
    config.clear()
    runtime_root=runtime_root or root
    config.load([str(runtime_root / "config.json")], strict=True)
    for key, value in {"cookies": str(runtime_root / "cookies.txt"), "retweets": True,
                       "quoted": True, "text-tweets": False, "videos": True,
                       "cards": False, "pinned": False}.items():
        config.set(("extractor", "twitter"), key, value)
    config.set(("cache",), "file", str(root / "_推文归档" / "gallery-cache.sqlite"))
    config.set(("extractor",), "retries", 3)
    config.set(("extractor",), "timeout", 30)
    handle = account['handle'].lstrip('@')
    # Small daily updates use tweet URLs directly; the first bulk import uses
    # the media timeline to avoid one HTTP request for every historical post.
    if len(pending) <= 20:
        urls = [f"https://x.com/{handle}/status/{tid}" for tid in sorted(pending, key=int, reverse=True)]
        scanned = matched = 0
        for url in urls:
            source = extractor.find(url)
            if source is None:
                raise RuntimeError("gallery-dl 无法识别推文地址")
            try:
                for message in source:
                    if message[0] == Message.Directory:
                        scanned += 1
                        metadata = copy.deepcopy(message[2])
                        if str(metadata["tweet_id"]) in pending and accept(db, account, metadata):
                            matched += 1
                            print(f"  已核对 {matched}/{len(pending)} 条待补全推文", flush=True)
            except Exception as exc:
                print(f"  单条推文暂无法读取（{type(exc).__name__}），保留待补全状态。", flush=True)
            if limit and matched >= limit:
                break
        print(f"  本次补全 {matched} 条；仍无法读取的记录保留为待补全。", flush=True)
        if not scanned:
            raise RuntimeError("未取得任何待补全推文，请检查登录态、网络或推文可见性")
        return
    # The media endpoint omits native repost events. Match the downloader's
    # timeline source so a batch of newly downloaded reposts can be resolved.
    url = f"https://x.com/{handle}/timeline"
    source = extractor.find(url)
    if source is None:
        raise RuntimeError("gallery-dl 无法识别账号地址")
    visited = set()
    scanned = matched = 0
    for message in source:
        if message[0] != Message.Directory:
            continue
        scanned += 1
        metadata = copy.deepcopy(message[2])
        tid = str(metadata["tweet_id"])
        if tid in pending and tid not in visited:
            visited.add(tid)
            accept(db, account, metadata)
            matched += 1
            if matched <= 5 or matched % 25 == 0 or matched == len(pending):
                print(f"  已核对 {matched}/{len(pending)} 条待补全推文", flush=True)
        if (limit and matched >= limit) or len(visited) == len(pending):
            break
    if not scanned:
        raise RuntimeError("没有取得任何推文；请检查登录态、网络或账号可见性")
    print(f"  本次扫描 {scanned} 条，匹配 {matched} 条。未匹配记录保留为待补全。", flush=True)


def complete_pending(db, root, runtime_root, account):
    """Resolve known missing posts by ID, independently of any timeline cutoff."""
    rows = db.execute("SELECT tweet_id FROM tweets WHERE account=? AND status='pending'",
                      (account['key'],)).fetchall()
    pending = {row[0] for row in rows}
    result = dict(total=len(pending), attempted=0, completed=0, remaining=len(pending), stopped=False)
    if not pending:
        print('没有正文待补全记录，无需联网。', flush=True)
        return result
    from gallery_dl import config, extractor
    from gallery_dl.extractor.message import Message
    config.clear()
    config.load([str(runtime_root / 'config.json')], strict=True)
    for key, value in {'cookies': str(runtime_root / 'cookies.txt'), 'retweets': True,
                       'quoted': True, 'text-tweets': True, 'replies': True, 'videos': True,
                       'cards': False, 'pinned': False, 'ratelimit': 'abort', 'cursor': True}.items():
        config.set(('extractor', 'twitter'), key, value)
    config.set(('cache',), 'file', str(root / '_推文归档/gallery-cache.sqlite'))
    config.set(('extractor',), 'retries', 3)
    config.set(('extractor',), 'timeout', 30)
    print(f'按原推 ID 补全 {len(pending)} 条；不受时间范围限制，不下载媒体、不调用翻译。暂停后再次运行会跳过已完成记录。', flush=True)
    for tid in sorted(pending, key=int, reverse=True):
        # A quote response can also resolve another pending post in this account.
        if load_document(db, account['key'], tid)['status'] != 'pending':
            continue
        result['attempted'] += 1
        reason = '接口未返回这条推文的完整正文；可能不可见、已删除或暂时无法读取'
        stop = False
        try:
            source = extractor.find(f'https://x.com/{account["handle"].lstrip("@")}/status/{tid}')
            if source is None:
                raise ValueError('unsupported post URL')
            for message in source:
                if message[0] != Message.Directory:
                    continue
                metadata = dict(message[2])
                # Image fallback generators are not serializable and are irrelevant
                # when fetching text only. URL messages never start downloads.
                metadata.pop('_fallback', None)
                candidate = str(metadata.get('tweet_id', ''))
                existing = load_document(db, account['key'], candidate) if candidate in pending else None
                if existing and existing['status'] == 'pending' and accept(db, account, metadata):
                    doc = load_document(db, account['key'], candidate)
                    doc.pop('completion_error', None)
                    save(db, account['key'], doc)
                    result['completed'] += 1
        except Exception as exc:
            name = type(exc).__name__
            status = getattr(exc, 'status', 0)
            stop = name in ('AuthenticationError', 'AuthRequired', 'AbortExtraction') or status in (401, 429)
            if name == 'NotFoundError' or status == 404:
                reason = '原推无法找到或当前登录账号不可见；不代表原推没有正文'
            elif stop:
                reason = '登录态失效、需要登录或接口限流；本次停止，请检查登录或稍后重试'
            elif name == 'AuthorizationError' or status == 403:
                reason = '当前登录账号没有读取权限，请确认原推可见性'
            else:
                reason = f'读取失败（{name}）；请检查网络或稍后重试'
        doc = load_document(db, account['key'], tid)
        if doc['status'] == 'pending':
            doc['completion_error'] = dict(reason=reason, checked_at=stamp())
            save(db, account['key'], doc)
            print(f'  {tid}：保留待补全。{reason}', flush=True)
        print(f'  已请求 {result["attempted"]}/{result["total"]} 条，已补全 {result["completed"]} 条。', flush=True)
        if stop:
            result['stopped'] = True
            break
    result['remaining'] = db.execute("SELECT count(*) FROM tweets WHERE account=? AND status='pending'",
                                     (account['key'],)).fetchone()[0]
    print(f'正文补全结果：成功 {result["completed"]} 条，仍待补全 {result["remaining"]} 条。已有媒体、收藏和译文保留。', flush=True)
    return result


def capture_options(root):
    options=dict(sync_text=True,include_replies=False,post_types=list(TYPE_LABELS))
    path=root/'tools/archive.local.json'
    if path.exists():
        value=json.loads(path.read_text(encoding='utf-8'))
        options.update({key:value[key] for key in options if key in value})
    if not isinstance(options['post_types'],list) or not set(options['post_types']) or not set(options['post_types'])<=set(TYPE_LABELS):
        raise ValueError('归档类型设置无效，请在存储与归档中重新保存。')
    return options


def scan_timeline(db, root, account, source, options, limit=500, since='', history=False, fingerprint=''):
    """Commit posts before the continuation cursor; replay is safe after interruption."""
    from gallery_dl.extractor.message import Message
    db.execute('CREATE TABLE IF NOT EXISTS sync_state(account TEXT, scope TEXT, value TEXT, PRIMARY KEY(account,scope))')
    scanned=saved=created=known_run=0
    completed=True
    cursor=None
    seen=set()
    boundary=dt.date.fromisoformat(since) if since else None
    for message in source:
        if message[0]!=Message.Directory:continue
        metadata=copy.deepcopy(message[2]);tid=str(metadata['tweet_id'])
        if tid in seen:continue
        seen.add(tid);scanned+=1
        existing=load_document(db,account['key'],tid)
        known_run=known_run+1 if existing and existing['status']=='archived' else 0
        date=metadata.get('date')
        within=not boundary or not isinstance(date,dt.datetime) or date.date()>=boundary
        kind=post_type(account,metadata)
        if within and kind in options['post_types'] and (options['include_replies'] or not metadata.get('reply_id')):
            if accept(db,account,metadata,create=True):
                saved+=1;created+=existing is None
        cursor=getattr(source,'_cursor',None)
        if scanned%25==0:
            print(f'  正文已扫描 {scanned} 条，已保存 {saved} 条，其中新增 {created} 条。',flush=True)
            if history and cursor:
                with db:db.execute('INSERT OR REPLACE INTO sync_state VALUES(?,?,?)',(account['key'],'history',encode(dict(fingerprint=fingerprint,cursor=cursor))))
        # A run of old records handles pinned/reordered entries without stopping at the first old ID.
        if scanned>=limit or (not history and known_run>=64):
            completed=False;break
    if history:
        with db:db.execute('INSERT OR REPLACE INTO sync_state VALUES(?,?,?)',(account['key'],'history',encode(dict(fingerprint=fingerprint,cursor=cursor if not completed else None,complete=completed))))
    print(f'正文归档：扫描 {scanned} 条，保存 {saved} 条，新增 {created} 条。',flush=True)
    if not completed and history:
        print('达到本次扫描上限；再次运行“补历史正文”可继续。' if cursor else '达到上限但接口尚未提供游标；下次请增大扫描上限以覆盖更早内容。',flush=True)
    if not scanned:print('本次接口没有返回推文；已有归档保留。请检查账号可见性与任务日志。',flush=True)
    return dict(scanned=scanned,saved=saved,created=created,complete=completed,cursor=cursor)


def sync_text(db, root, runtime_root, account, options, limit=500, since='', history=False, restart=False):
    from gallery_dl import config,extractor
    config.clear();config.load([str(runtime_root/'config.json')],strict=True)
    values={'cookies':str(runtime_root/'cookies.txt'),'retweets':True,'quoted':True,'text-tweets':True,
            'replies':bool(options['include_replies']),'cards':False,'pinned':False,'videos':True}
    for key,value in values.items():config.set(('extractor','twitter'),key,value)
    config.set(('cache',),'file',str(root/'_推文归档/gallery-cache.sqlite'))
    config.set(('extractor',),'retries',3);config.set(('extractor',),'timeout',30)
    config.set(('extractor','twitter'),'ratelimit','abort')
    fingerprint=hashlib.sha256(encode(dict(since=since,options=options)).encode()).hexdigest()
    if history and not restart:
        db.execute('CREATE TABLE IF NOT EXISTS sync_state(account TEXT, scope TEXT, value TEXT, PRIMARY KEY(account,scope))')
        row=db.execute('SELECT value FROM sync_state WHERE account=? AND scope=?',(account['key'],'history')).fetchone()
        state=json.loads(row[0]) if row else {}
        if state.get('fingerprint')==fingerprint and state.get('cursor'):
            config.set(('extractor','twitter'),'cursor',state['cursor'])
            print('继续上次历史正文扫描（当前页可能重放，已归档记录不会重复创建）。',flush=True)
    config.set(('extractor','twitter'),'strategy','with_replies' if options['include_replies'] else 'tweets')
    source=extractor.find(f"https://x.com/{account['handle'].lstrip('@')}/timeline")
    if source is None:raise ValueError('无法识别账号地址。')
    return scan_timeline(db,root,account,source,options,limit,since,history,fingerprint)


def import_translations(db, path):
    """Import Chinese translations only when their source text still matches."""
    bundle = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if bundle.get("version") != 1 or bundle.get("language") != "zh-CN":
        raise ValueError("译文文件格式或目标语言不正确")
    entries = {}
    for item in bundle["translations"]:
        content = item["source_text"]
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        translation = item["translation_zh"]
        if digest != item["source_sha256"] or not isinstance(translation, str) or not translation.strip():
            raise ValueError("译文文件包含原文校验失败或空译文")
        if digest in entries and entries[digest]["translation_zh"] != translation:
            raise ValueError("同一原文存在冲突译文")
        entries[digest] = item
    updated = 0
    # Validate the whole bundle first; updates then commit in one transaction.
    with db:
        for row in db.execute("SELECT account, document FROM tweets WHERE status='archived'").fetchall():
            doc = json.loads(row["document"])
            digest = hashlib.sha256(doc["content"].encode("utf-8")).hexdigest()
            item = entries.get(digest)
            if not item or not doc["content"].strip():
                continue
            if doc.get("translation_zh") == item["translation_zh"]:
                continue
            doc["translation_zh"] = item["translation_zh"]
            doc["translation_info"] = {"language": "zh-CN", "translator": "Codex",
                                       "source_sha256": digest, "translated_at": stamp()}
            db.execute("UPDATE tweets SET document=? WHERE account=? AND tweet_id=?",
                       (encode(doc), row["account"], doc["tweet_id"]))
            updated += 1
    print(f"中文译文已更新 {updated} 条；原文未变且译文相同的记录自动跳过。")
    return updated


def export(db, root, accounts):
    visible = []
    known_accounts = {a["key"]: a for a in accounts}
    for row in db.execute("SELECT account, document FROM tweets ORDER BY length(tweet_id) DESC, tweet_id DESC"):
        account = known_accounts.get(row["account"])
        if account is None:
            continue
        doc = json.loads(row["document"])
        doc.update(account_name=account['name'],account_handle=account['handle'])
        if doc["status"] == "excluded":
            continue
        doc["images"] = [p for p in doc.get("images",[]) if (root / p).is_file()]
        doc["videos"] = [p for p in doc.get("videos", []) if (root / p).is_file()]
        if doc['status']!='archived' and not doc["images"] and not doc["videos"] and not (doc.get('content') or '').strip():
            continue
        # Pending records appear in the viewer, but do not become tweet documents.
        if doc["status"] == "archived":
            date = dt.datetime.fromisoformat(doc["date_beijing"])
            folder = root / account["folder"] / "推文" / f"{date:%Y}" / f"{date:%m}"
            write_text(folder / f"{doc['tweet_id']}.json", encode(doc) + "\n")
            lines = [f"# {doc['author']} {doc['handle']}", "", doc["date_beijing"], "",
                     f"类型：{TYPE_LABELS.get(doc.get('post_type'), '待核对')} · 归档账号：{account['name']}", "",
                     f"[查看原推]({doc['url']})", "", "## 原文", "", doc["content"], "",
                     "## 中文翻译", "", doc.get("translation_zh") or
                     ("原推无文字正文，无需翻译" if not doc["content"].strip() else "待翻译"),
                     "", "## 本地图片", ""]
            for i, image in enumerate(doc["images"], 1):
                relative = Path(os.path.relpath(root / image, folder)).as_posix()
                lines += [f"![图片 {i}]({quote(relative, safe='/')})", ""]
            if doc["videos"]:
                lines += ["## 本地视频", ""]
                for i, video in enumerate(doc["videos"], 1):
                    relative = Path(os.path.relpath(root / video, folder)).as_posix()
                    lines += [f"[播放视频 {i}]({quote(relative, safe='/')})", ""]
            write_text(folder / f"{doc['tweet_id']}.md", "\n".join(lines))
        visible.append({key: doc.get(key) for key in (
            "tweet_id", "status", "content", "translation_zh", "date_beijing",
            "url", "account", "handle", "author", "images", "videos", "post_type",
            "account_name", "account_handle", "source_url", "source_tweet_id", "parent_tweet_id", "source_media_count")})
    data = json.dumps(visible, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    write_text(root / "_推文归档" / "data.js", "window.TWEET_ARCHIVE = " + data + ";\n")
    template = Path(__file__).with_name("tweet_archive_view.html").read_text(encoding="utf-8")
    template = template.replace('<script src="_推文归档/data.js"></script>',
                                "<script>window.TWEET_ARCHIVE = " + data + ";</script>")
    write_text(root / "推文归档.html", template)
    counts = {state: sum(d["status"] == state for d in visible) for state in ("archived", "pending")}
    excluded = db.execute("SELECT count(*) FROM tweets WHERE status='excluded'").fetchone()[0]
    kinds = {kind:sum(d.get('post_type') == kind for d in visible if d['status']=='archived') for kind in TYPE_LABELS}
    print(f"归档原文 {counts['archived']} 条；正文待补全 {counts['pending']} 条；原创 {kinds['original']}、引用 {kinds['quote']}、转推 {kinds['retweet']}、关联来源 {kinds['reference']} 条。")
    return counts


def main():
    parser = argparse.ArgumentParser(description="归档已有媒体对应的原创、引用和转推，并按本地配置补充 DeepL 中文译文。")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--runtime-root',type=Path,help='程序及登录/翻译凭据位置，与资料库目录分开')
    parser.add_argument('--history',action='store_true',help='补历史正文，不下载媒体')
    parser.add_argument('--complete-pending',action='store_true',help='按 ID 补全已有待补全推文，不扫描时间线、不下载媒体、不翻译')
    parser.add_argument('--sync-text-only',action='store_true',help='只同步账号正文，不扫描本地媒体')
    parser.add_argument('--media-only',action='store_true',help='仅核对本地媒体对应正文，不重复扫描账号文字时间线')
    parser.add_argument('--scan-limit',type=int,default=500)
    parser.add_argument('--since',default='',help='历史正文最早日期 YYYY-MM-DD')
    parser.add_argument('--restart-history',action='store_true')
    parser.add_argument("--index", type=int, default=0, help="账号编号，0=全部")
    parser.add_argument("--offline", action="store_true", help="仅扫描已有图片并重建离线浏览页")
    parser.add_argument("--import-translations", type=Path, help="导入经原文校验的中文译文并重建归档，不联网")
    parser.add_argument("--translate-only", action="store_true", help="只补译已有正文，不访问 X、不下载媒体")
    parser.add_argument("--no-translate", action="store_true", help="本次跳过自动翻译")
    parser.add_argument("--translation-preview", action="store_true", help="预览待译数量和字符数，不联网")
    parser.add_argument("--translation-limit", type=int, default=0, help="本次最多处理多少段不同原文，0=不另行限制")
    parser.add_argument('--translation-type', action='append',choices=['all','original','quote','retweet','reference','shared'], help='可重复指定，仅补译所选类型的合集')
    parser.add_argument("--limit", type=int, default=0, help="每个账号最多核对几条已有图片推文，0=全部")
    args = parser.parse_args()
    root = args.root.resolve()
    runtime_root=(args.runtime_root or root).resolve()
    options=capture_options(root)
    if args.since:
        try:dt.date.fromisoformat(args.since)
        except ValueError:parser.error('起始日期必须为 YYYY-MM-DD')
    if not 1<=args.scan_limit<=10000:parser.error('扫描上限必须介于 1 到 10000')
    if (args.history or args.sync_text_only) and (args.offline or args.translate_only or args.media_only):parser.error('正文同步与离线/媒体模式不能混用')
    if args.complete_pending and (args.history or args.sync_text_only or args.media_only or args.offline or args.translate_only or args.translation_preview or args.import_translations):
        parser.error('--complete-pending 不能与其他抓取、离线或翻译模式混用')
    accounts = json.loads((root / "tools" / "accounts.json").read_text(encoding="utf-8-sig"))
    if not 0 <= args.index <= len(accounts) or args.limit < 0 or args.translation_limit < 0:
        parser.error("账号编号或 limit 无效")
    if args.offline and args.translate_only:
        parser.error("--offline 与 --translate-only 不能同时使用")
    if args.translate_only and args.no_translate:
        parser.error("--translate-only 与 --no-translate 不能同时使用")
    selected = accounts if not args.index else [accounts[args.index - 1]]
    local_only = args.offline or args.import_translations is not None or args.translate_only or args.translation_preview
    if not local_only and not (runtime_root / "cookies.txt").is_file():
        parser.error("找不到 cookies.txt，请先刷新登录态")
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    failed = False
    translation_partial = False
    completion_partial = False
    db = database(root)
    try:
        for account in selected:
            print(f"\n{account['name']} {account['handle']}", flush=True)
            if args.complete_pending:
                try:
                    completed = complete_pending(db, root, runtime_root, account)
                    completion_partial |= bool(completed['remaining'] or completed['stopped'])
                    if completed['stopped']:break
                except KeyboardInterrupt:
                    print('正文补全已停止；已完成的记录保留，下次会跳过。', flush=True)
                    failed = True
                    break
                except Exception as exc:
                    print(f'正文补全未完成（{type(exc).__name__}）；已有结果保留，请检查登录和网络。', flush=True)
                    failed = True
                continue
            if not local_only and not args.media_only and (options['sync_text'] or args.history):
                try:sync_text(db,root,runtime_root,account,options,args.scan_limit,args.since,args.history,args.restart_history)
                except KeyboardInterrupt:
                    print('已停止，已保存的正文保留；历史任务可重新运行。',flush=True);failed=True;break
                except Exception as exc:
                    print(f'账号正文抓取未完成（{type(exc).__name__}），已保存内容保留；请检查网络、登录态与归档设置。',flush=True);failed=True
            if args.history or args.sync_text_only:continue
            images = images_for(root, account)
            videos = videos_for(root, account)
            media = dict(images)
            for tid, paths in videos.items():
                media.setdefault(tid, paths)
            print(f"本地图片 {sum(map(len, images.values()))} 张、视频 {sum(map(len, videos.values()))} 个，对应 {len(media)} 条推文。", flush=True)
            seed(db, root, account, images, videos)
            if media and not local_only:
                try:
                    sync(db, root, account, media, args.limit,runtime_root)
                except KeyboardInterrupt:
                    print("已中止，保留已保存结果。")
                    failed = True
                    break
                except Exception as exc:
                    # Do not echo request objects, cookies, or account credentials.
                    print(f"抓取未完成（{type(exc).__name__}），已保存的原文保留；请检查登录态和网络。", flush=True)
                    failed = True
        if args.import_translations:
            import_translations(db, args.import_translations)
        if not args.complete_pending and (args.translate_only or args.translation_preview or
                (not args.offline and not args.import_translations and not args.no_translate)):
            # Embedded Python uses ._pth isolation and omits the script folder
            # from sys.path. Load the sibling adapter by its explicit path.
            spec = importlib.util.spec_from_file_location(
                "local_tweet_deepl", Path(__file__).with_name("deepl_translate.py"))
            deepl_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(deepl_module)
            DeepLError, translate_archive = deepl_module.DeepLError, deepl_module.translate_archive
            try:
                translation_result = translate_archive(db, root, {a["key"] for a in selected},
                                  dry_run=args.translation_preview, limit=args.translation_limit, force=args.translate_only,
                                  post_types=None if not args.translation_type or 'all' in args.translation_type else
                                  set().union(*({'quote','retweet','reference'} if t=='shared' else {t} for t in args.translation_type)),config_root=runtime_root)
                translation_partial = translation_result['status'] == 'partial'
            except DeepLError as exc:
                print(f"中文翻译未完成：{exc}", flush=True)
                failed = True
            except KeyboardInterrupt:
                print("翻译已中止，已保存的译文保留。", flush=True)
                failed = True
        export(db, root, accounts)
    finally:
        db.close()
    return 1 if failed else 10 if translation_partial or completion_partial else 0


if __name__ == "__main__":
    sys.exit(main())
