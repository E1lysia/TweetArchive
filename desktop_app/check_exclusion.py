"""Recheck only classification fields for the files in the reported screenshot."""
from pathlib import Path
from gallery_dl import config, extractor
from gallery_dl.extractor.message import Message
import json

root = Path(r'D:\gallery-dl')
config.clear()
config.load([str(root / 'config.json')], strict=True)
for key, value in {'cookies':str(root / 'cookies.txt'), 'quoted':False, 'retweets':False, 'videos':True}.items():
    config.set(('extractor','twitter'), key, value)
config.set(('cache',), 'file', str(root / '_推文归档/gallery-cache.sqlite'))
for tid in ('2116855504727425235', '2117464284792000823', '2117525193770090971'):
    found = False
    try:
        for message in extractor.find(f'https://x.com/aoki__hina/status/{tid}'):
            if message[0] == Message.Directory:
                m = message[2]
                if str(m['tweet_id']) == tid:
                    print(json.dumps(dict(id=tid, author=(m.get('author') or {}).get('name'),
                                          retweet_id=m.get('retweet_id'), quote_id=m.get('quote_id'), quoted_id=m.get('quoted_id')), ensure_ascii=False), flush=True)
                    found = True
                    break
        if not found:
            print(tid + ': classification not available', flush=True)
    except Exception as exc:
        print(tid + ': ' + type(exc).__name__, flush=True)
