"""Data-library location and copy-first migration; credentials stay with the app."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from contextlib import closing

TYPES = ('original', 'quote', 'retweet', 'reference')


def atomic_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def validate_library(root):
    root = Path(root).resolve()
    if (root/'.tweetarchive-copying').exists():
        raise ValueError('这个目录的迁移尚未完成，请选择完整资料库或新的空目录。')
    accounts = json.loads((root/'tools/accounts.json').read_text(encoding='utf-8-sig'))
    if not isinstance(accounts, list):
        raise ValueError('账号文件格式不正确。')
    for account in accounts:
        if not isinstance(account,dict) or not all(isinstance(account.get(key),str) and account[key] for key in ('folder','key','handle','name')):
            raise ValueError('账号文件缺少有效的目录或作者信息。')
        folder = (root/account['folder']).resolve()
        if folder == root or not folder.is_relative_to(root):
            raise ValueError('账号目录超出资料库范围。')
    database = root/'_推文归档/tweets.sqlite'
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)) as db:
        columns = {r[1] for r in db.execute('PRAGMA table_info(tweets)')}
        if not {'account','tweet_id','status','document'} <= columns:
            raise ValueError('所选目录不是完整的推文资料库。')
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('数据库检查未通过。')
    return root


def resolve_library(program_root):
    program_root = Path(program_root).resolve()
    pointer = program_root/'tools/storage.local.json'
    if not pointer.exists():
        return program_root
    try:
        value = json.loads(pointer.read_text(encoding='utf-8'))
        root = Path(value['data_root'])
        if not root.is_absolute():
            root = program_root/root
        return validate_library(root)
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        raise ValueError('当前资料库无法打开，可能是磁盘未连接。请重新连接磁盘，或在启动提示中选择完整资料库。') from exc


def select_library(program_root, root):
    root = validate_library(root)
    atomic_json(Path(program_root)/'tools/storage.local.json', dict(version=1, data_root=str(root)))


def archive_options(root):
    defaults = dict(sync_text=True, include_replies=False, post_types=list(TYPES))
    path = Path(root)/'tools/archive.local.json'
    if path.exists():
        value = json.loads(path.read_text(encoding='utf-8'))
        defaults.update({k:v for k,v in value.items() if k in defaults})
    defaults['post_types'] = [t for t in defaults['post_types'] if t in TYPES]
    if not defaults['post_types']:
        defaults['post_types'] = list(TYPES)
    return defaults


def save_archive_options(root, options):
    atomic_json(Path(root)/'tools/archive.local.json', options)


def empty_destination(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if target == source or target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError('新位置不能与当前资料库相同，也不能是它的上级或下级目录。')
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError('请选择空目录；已有资料库请使用“打开已有资料库”。')
    return target


def copy_library(source, target, progress=lambda *args: None):
    source = validate_library(source)
    target = empty_destination(source, target)
    accounts = json.loads((source/'tools/accounts.json').read_text(encoding='utf-8-sig'))
    roots = [source/'_推文归档', source/'tools/accounts.json', source/'tools/archive.local.json']
    reserved = {'python','tools','资料库','_setup','TweetArchive-XLogin','_推文归档'}
    for account in accounts:
        folder=source/account['folder']
        if folder.is_symlink():raise ValueError('账号目录为链接，请使用普通文件夹后再迁移。')
        relative = folder.resolve().relative_to(source)
        if relative.parts[0].casefold() in {name.casefold() for name in reserved}:
            raise ValueError('账号媒体目录与程序目录冲突，无法自动迁移。')
        roots.append(folder)
    files = {}
    for folder in roots:
        candidates = folder.rglob('*') if folder.is_dir() else [folder]
        for path in candidates:
            if not path.is_file(): continue
            if path.name == 'manager.lock' or path.name.endswith(('-wal','-shm','-journal','.tmp')): continue
            if not path.resolve().is_relative_to(source):
                raise ValueError('资料库包含指向外部的链接，无法自动迁移。')
            files[path.relative_to(source)] = path
    parent = target
    while not parent.exists(): parent = parent.parent
    if shutil.disk_usage(parent).free < sum(p.stat().st_size for p in files.values()) + 16*1024*1024:
        raise ValueError('目标磁盘空间不足。')
    target.mkdir(parents=True, exist_ok=True)
    marker = target/'.tweetarchive-copying'; marker.write_text('Incomplete copy; source preserved.', encoding='ascii')
    for index, (relative, path) in enumerate(files.items(), 1):
        destination = target/relative; destination.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == '.sqlite':
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as src, closing(sqlite3.connect(destination)) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('复制后的数据库校验失败。')
        else:
            before = hashlib.sha256()
            with path.open('rb') as src, destination.open('wb') as dst:
                while block := src.read(1024*1024):
                    before.update(block); dst.write(block)
                    progress(index-1, len(files), relative.as_posix())
            after = hashlib.sha256()
            with destination.open('rb') as copied:
                while block := copied.read(1024*1024): after.update(block)
            if before.digest() != after.digest(): raise ValueError('复制后的文件校验失败。')
        progress(index, len(files), relative.as_posix())
    marker.unlink()
    validate_library(target)
    return target
