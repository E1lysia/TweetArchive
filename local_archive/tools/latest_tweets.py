"""Incremental account events: one timeline stream shared by text and media."""
import argparse
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import logging
from pathlib import Path
import subprocess
import sys
import traceback
import re
import shutil
import uuid
import sqlite3
from contextlib import closing


def sibling(name):
    spec = importlib.util.spec_from_file_location('latest_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


archive = sibling('tweet_archive')
SCOPE = 'latest_v1'
OVERLAP = 72 * 3600
BATCH_SIZE = 500
OLD_RUN = 16
VIDEO = {'mp4', 'gif', 'm4v', 'webm', 'mov'}
MEDIA_NAME = re.compile(r'^\d{4}-\d{2}-\d{2}_(\d{15,22})_(\d+)[^.]*\.(jpg|jpeg|png|webp|mp4|gif|m4v|webm|mov)$',re.I)


class LatestError(RuntimeError):
    """Only locally authored diagnostics are safe to include in the task log."""


def snapshot_message(message):
    """Freeze Twitter metadata, including its finite lazy image-size fallbacks.

    gallery-dl's _image_fallback yields local URL strings, without making requests.
    Materialize it once so both metadata copying and retry replay remain safe.
    """
    metadata = dict(message[2])
    if '_fallback' in metadata:
        metadata['_fallback'] = tuple(metadata['_fallback'] or ())
    return message[0], message[1], copy.deepcopy(metadata)


def failure_message(exc):
    if isinstance(exc, LatestError):
        return str(exc)
    frames = traceback.extract_tb(exc.__traceback__)
    # File/function locations only: exception values/locals may contain credentials.
    location = ' → '.join(f'{Path(f.filename).name}:{f.lineno}' for f in frames[-3:])
    if isinstance(exc, (TypeError, AttributeError, KeyError)):
        reason = '程序处理时间线数据出错，请保留任务日志反馈'
    elif isinstance(exc, (OSError, subprocess.SubprocessError)):
        reason = '网络连接、文件读写或归档步骤出错，请检查详细任务日志'
    else:
        reason = '抓取未完成，请检查登录状态、网络和归档设置'
    return f'{reason}（{type(exc).__name__}）' + (f'；位置：{location}' if location else '')


def timestamp(value):
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value)
    if not isinstance(value, dt.datetime):
        raise ValueError('推文时间缺失，未推进补充检查点。')
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.timestamp()


def event_time(metadata):
    # Quote source inclusion follows its parent, even if the source is years old.
    if metadata.get('quote_id') and not metadata.get('retweet_id'):
        return ((int(metadata['quote_id']) >> 22) + 1288834974657) / 1000
    # retweets=True retains the retweet event ID/date, unlike retweets="original".
    return timestamp(metadata.get('date'))


def local_latest(db, account):
    high = 0
    for row in db.execute('SELECT document FROM tweets WHERE account=?', (account['key'],)):
        doc = json.loads(row[0])
        if doc.get('status') != 'archived' or doc.get('post_type') not in ('original', 'quote', 'retweet'):
            continue
        try:
            high = max(high, timestamp(doc.get('date_beijing')))
        except (TypeError, ValueError):
            pass
    return high


def put_state(db, account, state):
    with db:
        db.execute('INSERT OR REPLACE INTO sync_state VALUES(?,?,?)',
                   (account['key'], SCOPE, archive.encode(state)))


def start_state(db, account, options):
    db.execute('CREATE TABLE IF NOT EXISTS sync_state(account TEXT, scope TEXT, value TEXT, PRIMARY KEY(account,scope))')
    row = db.execute('SELECT value FROM sync_state WHERE account=? AND scope=?', (account['key'], SCOPE)).fetchone()
    previous = json.loads(row[0]) if row else {}
    fingerprint = hashlib.sha256(archive.encode(dict(handle=account['handle'].lower(), options=options)).encode()).hexdigest()
    if previous.get('fingerprint') == fingerprint and previous.get('in_progress'):
        return previous
    # A partial run may already have newer rows: the completed watermark wins.
    high = previous['watermark'] if 'watermark' in previous else local_latest(db, account)
    state = dict(fingerprint=fingerprint, watermark=high, lower=max(0, high - OVERLAP),
                 high=high, cursor=None, in_progress=True, bootstrap=not high)
    put_state(db, account, state)  # Freeze before any request or accepted metadata.
    return state


def configure(root, runtime, options, cursor=None):
    from gallery_dl import config
    config.clear()
    config.load([str(runtime / 'config.json')], strict=True)
    values = {'cookies': str(runtime / 'cookies.txt'), 'retweets': True, 'quoted': True,
              'text-tweets': True, 'replies': bool(options['include_replies']), 'cards': False,
              'pinned': False, 'videos': True, 'ratelimit': 'abort', 'cursor': cursor or True,
              'strategy': 'with_replies' if options['include_replies'] else 'tweets',
              'expand': False, 'unique': True}
    for key, value in values.items():
        config.set(('extractor', 'twitter'), key, value)
        config.setg(key, value)  # Top-level CLI-style settings take precedence in gallery-dl.
    config.set(('cache',), 'file', str(root / '_推文归档/gallery-cache.sqlite'))
    config.set(('extractor',), 'retries', 3)
    config.set(('extractor',), 'timeout', 30)
    return config


def batches(source, account, options, state, batch_size=BATCH_SIZE):
    """Saved cursors replay a page on resume; each yielded batch ends at a post."""
    from gallery_dl.extractor.message import Message
    messages, count, total, old = [], 0, 0, 0
    high, cursor, selected = state['high'], state.get('cursor'), False
    for message in source:
        if message[0] == Message.Directory:
            metadata = message[2]
            primary = not metadata.get('quote_id') or bool(metadata.get('retweet_id'))
            if primary and count >= batch_size:
                yield dict(messages=messages, count=count, high=high, cursor=cursor, complete=False)
                messages, count = [], 0
            when = event_time(metadata)
            if primary:
                total += 1
                count += 1
                high = max(high, when)
                old = old + 1 if when < state['lower'] else 0
                if old >= OLD_RUN:
                    break
            kind = archive.post_type(account, metadata)
            selected = (when >= state['lower'] and kind in options['post_types'] and
                        (options['include_replies'] or not metadata.get('reply_id')) and
                        (options['sync_text'] or int(metadata.get('count') or 0) > 0))
        elif message[0] != Message.Url:
            raise LatestError('时间线消息类型异常，检查点保持不变。')
        if selected:
            messages.append(snapshot_message(message))
        cursor = getattr(source, '_cursor', None)
    if getattr(source, 'status', 0):
        raise LatestError('时间线返回异常，检查点保持不变。')
    if not total:
        raise LatestError('接口未返回账号推文，请检查登录或账号可见性。')
    yield dict(messages=messages, count=count, high=high, cursor=cursor, complete=True)


def download(messages, root, runtime, account, options, video):
    from gallery_dl import extractor, job
    from gallery_dl.extractor.message import Message
    urls = [m for m in messages if m[0] == Message.Url and (m[2].get('extension', '').lower() in VIDEO) == video]
    if not urls:
        return
    config = configure(root, runtime, options)
    folder = (root / account['folder']).resolve()
    if not folder.is_relative_to(root.resolve()) or folder == root.resolve():
        raise ValueError('账号目录必须位于资料库内。')
    output = folder / '视频GIF' if video else folder
    # Keep the legacy archive identities; completed downloads remain deduplicated.
    for key, value in {'base-directory': str(output), 'directory': [],
                       'filename': '{date:%Y-%m-%d}_{tweet_id}_{num:02}.{extension}',
                       'archive': str(folder / ('archive_video.sqlite' if video else 'archive.sqlite')),
                       'archive-event': ['file', 'skip'], 'skip': True, 'postprocessors': [],
                       'image-filter': None, 'post-filter': None, 'range': None, 'image-range': None,
                       'async':False,'download':True}.items():
        config.set(('extractor', 'twitter'), key, value)
        config.setg(key, value)
    config.set(('extractor',), 'postprocess', False)
    config.set(('extractor',), 'sleep-extractor', None)
    config.set(('downloader',), 'rate', '8M' if video else None)
    source = extractor.find(f"https://x.com/{account['handle'].lstrip('@')}/timeline")
    if source is None:
        raise LatestError('无法识别账号地址。')
    allowed = {id(m) for m in urls}
    replay = [snapshot_message(m) for m in messages if m[0] == Message.Directory or id(m) in allowed]
    # Replaying captured URLs bypasses a second timeline/API/login scan.
    source.items = lambda: iter(copy.deepcopy(replay))
    class LocalFileJob(job.DownloadJob):
        def initialize(self, kwdict=None):
            super().initialize(kwdict)
            if self.archive is not None:
                original_check=self.archive.check
                # An old archive hit alone cannot prove the file still exists locally.
                self.archive.check=lambda data:media_key(data) in local_files and original_check(data)
    local_files=media_files(folder)
    # Already archived monthly files must not be downloaded again into the flat folder.
    replay[:]=[m for m in replay if m[0]==Message.Directory or media_key(m[2]) not in local_files]
    task = LocalFileJob(source)
    task.run()
    if task.status:
        raise LatestError('媒体未下载完成，检查点保持不变，下次重试本批。')
    indexed=media_files(folder)
    if any(media_key(m[2]) not in indexed for m in urls):
        raise LatestError('媒体任务结束但账号目录仍缺少文件，未推进检查点；请重试补充。')


def media_key(data):
    extension=str(data.get('extension','')).lower()
    if extension in ('jpeg','jpe','jfif','jif','jfi'):extension='jpg'
    return str(data.get('tweet_id')),int(data.get('num') or 0),extension


def media_files(folder):
    """Index valid account media by tweet, media number and extension, ignoring .part."""
    folder=folder.resolve();result={}
    if not folder.is_dir():return result
    for path in folder.rglob('*'):
        if not path.is_file() or not path.resolve().is_relative_to(folder):continue
        relative=path.relative_to(folder)
        if '推文' in relative.parts:continue
        match=MEDIA_NAME.fullmatch(path.name)
        if match and path.stat().st_size:
            key=media_key(dict(tweet_id=match[1],num=match[2],extension=match[3]))
            result.setdefault(key,path)
    return result


def recover_downloads(db,root,runtime,accounts):
    """Copy only media with known tweet ownership; preserve the original downloads."""
    sources={}
    for base in dict.fromkeys(((runtime/'downloads').resolve(),(root/'downloads').resolve())):
        for key,path in media_files(base).items():sources.setdefault(key,path)
    copied=0
    for account in accounts:
        folder=(root/account['folder']).resolve()
        if not folder.is_relative_to(root.resolve()) or folder==root.resolve():raise LatestError('账号目录必须位于资料库内。')
        owned={str(tid) for tid, in db.execute('SELECT tweet_id FROM tweets WHERE account=?',(account['key'],))}
        indexed=media_files(folder)
        for key,source in sources.items():
            if key[0] not in owned or key in indexed:continue
            year,month=source.name[:4],source.name[5:7]
            destination=(folder/'视频GIF' if key[2] in VIDEO else folder)/year/month/source.name
            if not destination.resolve().is_relative_to(folder):raise LatestError('媒体恢复目标超出账号目录。')
            destination.parent.mkdir(parents=True,exist_ok=True)
            temporary=destination.with_name(destination.name+'.recovering-'+uuid.uuid4().hex)
            try:
                before=source.stat()
                shutil.copy2(source,temporary)
                after=source.stat()
                if before.st_size!=after.st_size or before.st_mtime_ns!=after.st_mtime_ns or temporary.stat().st_size!=after.st_size:
                    raise LatestError('源媒体文件仍在变化，未更新其索引；请等当前下载结束后重试。')
                with source.open('rb') as stream:source_hash=hashlib.file_digest(stream,'sha256').digest()
                with temporary.open('rb') as stream:copy_hash=hashlib.file_digest(stream,'sha256').digest()
                if source_hash!=copy_hash:raise LatestError('媒体复制校验未通过，源文件保留。')
                if destination.exists():
                    if destination.stat().st_size!=temporary.stat().st_size:raise LatestError('恢复目标已有不同文件，原文件保留。')
                else:temporary.rename(destination)
            finally:
                if temporary.exists():temporary.unlink()
            indexed[key]=destination;copied+=1
        archive.seed(db,root,account,archive.images_for(root,account),archive.videos_for(root,account))
    print(f'本地媒体核对：从旧 downloads 目录补回 {copied} 个文件；源文件保留。',flush=True)
    return copied


def repair_local_media(db,root,runtime,selected,accounts):
    state_path=root/'_推文归档/manager.sqlite'
    if state_path.is_file():
        with closing(sqlite3.connect(state_path.as_uri()+'?mode=ro',uri=True,timeout=15)) as state:
            if state.execute("SELECT 1 FROM tasks WHERE status='进行中' LIMIT 1").fetchone():
                raise LatestError('请先等待当前任务完成或在软件中暂停，再进行离线媒体修复。')
    backup=root/'_推文归档/维护备份'/('media-index-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.sqlite')
    if not backup.resolve().is_relative_to(root.resolve()):raise LatestError('备份目录必须位于资料库内。')
    backup.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(backup)) as target:db.backup(target)
    copied=recover_downloads(db,root,runtime,selected)
    archive.export(db,root,accounts)
    print(f'离线媒体修复完成：补回 {copied} 个文件，已重建索引；原数据库已备份。重启软件后查看。',flush=True)
    return copied


def refresh_files(db, root, runtime, account):
    folder = (root / account['folder']).resolve()
    if not folder.is_relative_to(root.resolve()) or folder == root.resolve():
        raise ValueError('账号目录必须位于资料库内。')
    folder.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(runtime / 'tools/archive_months.py'), str(folder)], check=True)
    archive.seed(db, root, account, archive.images_for(root, account), archive.videos_for(root, account))


def timeline_batches(db, root, runtime, account, options, state, source_factory, batch_size):
    """Expired continuation cursors retry once from the head, preserving the lower bound."""
    resumed = state.get('cursor')
    for attempt in range(2):
        yielded = False
        configure(root, runtime, options, state.get('cursor'))
        source = source_factory(f"https://x.com/{account['handle'].lstrip('@')}/timeline")
        if source is None:
            raise LatestError('无法识别账号地址。')
        try:
            for batch in batches(source, account, options, state, batch_size):
                yielded = True
                yield batch
            return
        except Exception:
            if attempt or not resumed or yielded:
                raise
            state['cursor'] = None
            put_state(db, account, state)
            print('上次游标暂不可用，改从最新页重读；原时间边界保留，已下载媒体自动跳过。', flush=True)


def sync_account(db, root, runtime, account, options, all_accounts, source_factory=None,
                 downloader=download, refresh=refresh_files, batch_size=BATCH_SIZE):
    from gallery_dl import extractor
    from gallery_dl.extractor.message import Message
    state = start_state(db, account, options)
    boundary = dt.datetime.fromtimestamp(state['lower'], dt.timezone.utc).astimezone(archive.CST)
    print(f"\n{account['name']} {account['handle']}", flush=True)
    print('首次导入：抓取接口可访问的时间线；每批 500 条，自动继续，可随时暂停。' if state['bootstrap'] else
          f'增量补充：回溯至 {boundary:%Y-%m-%d %H:%M} 北京时间（含三天重叠）；每批 500 条，自动继续。', flush=True)
    recover_downloads(db,root,runtime,[account])
    total = 0
    for batch in timeline_batches(db, root, runtime, account, options, state, source_factory or extractor.find, batch_size):
        for message in batch['messages']:
            if message[0] == Message.Directory:
                if not archive.accept(db, account, message[2], create=True):
                    raise LatestError('正文元数据未完整取得，仍保留待核对状态，未推进检查点。')
        downloader(batch['messages'], root, runtime, account, options, False)
        downloader(batch['messages'], root, runtime, account, options, True)
        refresh(db, root, runtime, account)
        archive.export(db, root, all_accounts)
        if not batch['complete'] and (not batch['cursor'] or batch['cursor'] == state.get('cursor')):
            raise LatestError('接口未提供可前进的游标，原时间边界保留。')
        # Commit progress only after both media jobs and indexing succeeded.
        state.update(high=batch['high'], cursor=batch['cursor'], in_progress=not batch['complete'])
        if batch['complete']:
            state.update(watermark=batch['high'], cursor=None)
        put_state(db, account, state)
        total += batch['count']
        print(f"已检查 {total} 条账号事件，正文与媒体已保存；" + ('本次补充完成。' if batch['complete'] else '继续下一批。'), flush=True)
        configure(root, runtime, options, state.get('cursor'))
    return state


def main():
    parser = argparse.ArgumentParser(description='增量补充最新推文、图片和视频')
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--index', type=int, default=0)
    parser.add_argument('--repair-local-media',action='store_true',help='离线补回误存 downloads 的媒体并重建索引，不抓取、不翻译')
    args = parser.parse_args()
    root, runtime = args.root.resolve(), args.runtime_root.resolve()
    accounts = json.loads((root / 'tools/accounts.json').read_text(encoding='utf-8-sig'))
    if not 0 <= args.index <= len(accounts):
        parser.error('账号编号超出范围。')
    if not args.repair_local_media and not (runtime / 'cookies.txt').is_file():
        parser.error('请先在设置 → X 登录导入登录信息。')
    selected = accounts if not args.index else [accounts[args.index - 1]]
    logging.basicConfig(level=logging.WARNING, format='%(name)s: %(message)s')
    failed, partial = False, False
    db = archive.database(root)
    try:
        if args.repair_local_media:
            repair_local_media(db,root,runtime,selected,accounts)
            return 0
        options = archive.capture_options(root)
        for account in selected:
            try:
                sync_account(db, root, runtime, account, options, accounts)
            except Exception as exc:
                # Do not echo HTTP request objects, signed URLs, or authentication.
                print('补充未完成：' + failure_message(exc) + '。已保存结果保留，再次补充会重试未完成区间。', flush=True)
                failed = True
        try:
            result = sibling('deepl_translate').translate_archive(db, root, {a['key'] for a in selected}, config_root=runtime)
            partial = result['status'] == 'partial'
        except Exception as exc:
            print(f'中文补译未完成（{type(exc).__name__}）；原文和媒体保留，可单独重试补译。', flush=True)
            failed = True
        archive.export(db, root, accounts)
    except KeyboardInterrupt:
        print('已停止；已有内容保留，下次补充会重试未完成区间。', flush=True)
        failed = True
    finally:
        db.close()
    return 1 if failed else 10 if partial else 0


if __name__ == '__main__':
    sys.exit(main())
