"""Retry only the unsaved portion of the initial 10,000-character migration batch."""
import importlib.util
import re
from pathlib import Path

root = Path(r'D:\gallery-dl')
def module(name, file):
    spec = importlib.util.spec_from_file_location(name, root / 'tools' / file)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value
archive = module('archive_retry', 'tweet_archive.py')
deepl = module('deepl_retry', 'deepl_translate.py')
db = archive.database(root)
shared = {'quote','retweet','reference'}
try:
    docs = [__import__('json').loads(row['document']) for row in db.execute('SELECT document FROM tweets WHERE status=\'archived\' ORDER BY tweet_id DESC')]
    groups = {}
    for doc in docs:
        if doc.get('post_type') not in shared or not doc['content'].strip():
            continue
        info = doc.get('translation_info') or {}
        plain = re.sub(r'https?://[^\s]+|#[\w]+|(?<![\w@])@[A-Za-z0-9_]+', '', doc['content'])
        if info.get('cache_reused') or info.get('translator') == '原样保留' or not any(c.isalpha() for c in plain):
            continue
        groups.setdefault(deepl.digest(doc['content']), doc)
    budget = deepl.read_settings(root)['max_characters_per_run']
    selected, characters = [], 0
    for digest, doc in groups.items():
        if characters + len(doc['content']) <= budget:
            selected.append((digest, doc))
            characters += len(doc['content'])
    failed = {digest for digest, doc in selected if not doc.get('translation_zh')}
    pending = [digest for digest, doc in groups.items() if not doc.get('translation_zh')]
    assert len(selected) == 89, 'Initial migration batch differs; no request sent'
    assert failed == set(pending[:len(failed)]), 'Pending order differs; no request sent'
    print(f'Retrying {len(failed)} unsaved texts from the original bounded batch.', flush=True)
    if failed:
        deepl.translate_archive(db, root, limit=len(failed), post_types=shared)
    accounts = __import__('json').loads((root / 'tools/accounts.json').read_text(encoding='utf-8-sig'))
    archive.export(db, root, accounts)
finally:
    db.close()
