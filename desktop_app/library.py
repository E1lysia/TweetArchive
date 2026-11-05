"""Local archive queries and independent user annotations."""
import json
import re
import sqlite3
import http.cookiejar
import uuid
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit


def source_tweet_url(doc):
    """Resolve a source ID to a canonical X post link, including older records."""
    metadata=doc.get('metadata') or {}
    if not isinstance(metadata,dict):metadata={}
    ids=[metadata.get('quoted_id'),doc.get('source_tweet_id')] if doc.get('post_type')=='quote' else [doc.get('source_tweet_id'),metadata.get('retweet_id')]
    for value in ids:
        if re.fullmatch(r'[1-9][0-9]*',str(value or '')):
            return 'https://x.com/i/web/status/'+str(value)
    try:
        url=urlsplit(str(doc.get('source_url') or ''))
        if url.scheme!='https' or url.hostname not in ('x.com','twitter.com','www.x.com','www.twitter.com') or url.username or url.password:return ''
        match=re.fullmatch(r'/(?:i/web|[A-Za-z0-9_]{1,15})/status/([1-9][0-9]*)/?',url.path)
        return 'https://x.com/i/web/status/'+match[1] if match else ''
    except ValueError:return ''


def initialize_library(root):
    root=Path(root).resolve()
    (root/'tools').mkdir(parents=True,exist_ok=True)
    (root/'_推文归档').mkdir(exist_ok=True)
    accounts=root/'tools/accounts.json'
    if not accounts.exists():
        accounts.write_text('[]\n',encoding='utf-8')
    with closing(sqlite3.connect(root/'_推文归档/tweets.sqlite')) as db:
        with db:
            db.execute('CREATE TABLE IF NOT EXISTS tweets(account TEXT NOT NULL,tweet_id TEXT NOT NULL,status TEXT NOT NULL,document TEXT NOT NULL,PRIMARY KEY(account,tweet_id))')


def import_login_file(root,source):
    jar=http.cookiejar.MozillaCookieJar(str(source))
    try:
        jar.load(ignore_discard=True,ignore_expires=True)
    except (OSError,http.cookiejar.LoadError,ValueError):
        raise ValueError('无法读取登录文件，请选择 Netscape 格式的 cookies.txt。') from None
    selected=[cookie for cookie in jar if cookie.domain.lstrip('.').lower() in ('x.com','twitter.com') or
              cookie.domain.lower().endswith(('.x.com','.twitter.com'))]
    if not any(c.name=='auth_token' and c.value and not c.is_expired() for c in selected):
        raise ValueError('文件中没有有效的 X 登录信息，请导出本人已登录账号的 cookies 后重试。')
    target=Path(root)/'cookies.txt'
    temporary=target.with_suffix('.tmp')
    cleaned=http.cookiejar.MozillaCookieJar(str(temporary))
    for cookie in selected:
        if not cookie.is_expired(): cleaned.set_cookie(cookie)
    cleaned.save(ignore_discard=True,ignore_expires=False)
    temporary.replace(target)
    return len(cleaned)


class Library:
    def __init__(self, root):
        self.root = Path(root).resolve()
        folder = self.root / '_推文归档'
        folder.mkdir(exist_ok=True)
        self.state = sqlite3.connect(folder / 'manager.sqlite', timeout=15)
        self.state.execute('CREATE TABLE IF NOT EXISTS notes (account TEXT, id TEXT, favorite INTEGER DEFAULT 0, tags TEXT DEFAULT \'\', PRIMARY KEY(account,id))')
        self.state.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, title TEXT, status TEXT, log TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)')
        self.state.execute('CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        self.state.commit()
        self.reload()

    def preference(self, key, default=None):
        row = self.state.execute('SELECT value FROM preferences WHERE key=?', (key,)).fetchone()
        try:
            return json.loads(row[0]) if row else default
        except (ValueError, TypeError):
            return default

    def set_preference(self, key, value):
        with self.state:
            self.state.execute('INSERT OR REPLACE INTO preferences VALUES (?,?)',
                               (key, json.dumps(value, ensure_ascii=False)))

    def safe_path(self, relative):
        path = (self.root / relative).resolve()
        return path if path.is_relative_to(self.root) and path != self.root else None

    def archive_counts(self, account=''):
        counts = dict(archived=0, pending=0, excluded=0)
        path = self.root / '_推文归档/tweets.sqlite'
        if not path.exists():
            return counts
        keys=[a['key'] for a in self.accounts if not account or a['key']==account]
        if not keys:return counts
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=15)) as db:
            sql = 'SELECT status,count(*) FROM tweets'
            parameters = ()
            sql += ' WHERE account IN ('+','.join('?' for _ in keys)+')'
            parameters=keys
            counts.update(db.execute(sql + ' GROUP BY status', parameters).fetchall())
        return counts

    def reload(self):
        self.accounts = json.loads((self.root / 'tools/accounts.json').read_text(encoding='utf-8-sig'))
        notes = {(a, i): (bool(f), t) for a, i, f, t in self.state.execute('SELECT * FROM notes')}
        self.docs = []
        owners={account['key']:account for account in self.accounts}
        database = self.root / '_推文归档/tweets.sqlite'
        if not database.exists():
            return
        with closing(sqlite3.connect(f'{database.as_uri()}?mode=ro', uri=True, timeout=15)) as db:
            rows = db.execute("SELECT account,document FROM tweets WHERE status IN ('archived','pending')")
            for account, raw in rows:
                owner=owners.get(account)
                if owner is None:continue
                doc = json.loads(raw)
                doc['account'] = account
                doc['account_name']=owner['name'];doc['account_handle']=owner['handle']
                for field in ('images', 'videos'):
                    doc[field] = [p for p in doc.get(field, []) if (safe := self.safe_path(p)) and safe.is_file()]
                if doc['status']!='archived' and not doc['images'] and not doc['videos'] and not (doc.get('content') or '').strip():
                    continue
                expected=doc.get('source_media_count')
                if expected is None and (doc.get('metadata') or {}).get('count') is not None:
                    expected=doc['metadata']['count']
                doc['media_state']='local' if doc['images'] or doc['videos'] else ('text' if expected == 0 else 'missing' if expected else 'unknown')
                doc['favorite'], doc['tags'] = notes.get((account, doc['tweet_id']), (False, ''))
                self.docs.append(doc)
        sources={(d['account'],d['tweet_id']):d for d in self.docs}
        for doc in self.docs:
            source=sources.get((doc['account'],doc.get('source_tweet_id')))
            if doc.get('post_type')=='quote' and source and source is not doc:
                doc['quote_summary']=(source.get('author') or source.get('handle') or '')+'：'+(source.get('translation_zh') or source.get('content') or '')
        self.docs.sort(key=lambda d: int(d['tweet_id']), reverse=True)

    def query(self, account='', mode='all', search='', month='', oldest=False, post_type='', post_types=None):
        words = search.casefold().split()
        result = []
        for d in self.docs:
            types=post_types if post_types is not None else ({post_type} if post_type else None)
            if mode != 'pending' and types is not None and d.get('post_type', 'original') not in types:
                continue
            if account and d['account'] != account:
                continue
            if mode == 'images' and not d['images'] or mode == 'videos' and not d['videos']:
                continue
            if mode == 'text' and d['media_state'] != 'text':
                continue
            if mode == 'favorites' and not d['favorite']:
                continue
            if mode == 'untranslated' and (d['status'] != 'archived' or not d.get('content', '').strip() or d.get('translation_zh')):
                continue
            if mode == 'pending' and d['status'] != 'pending':
                continue
            if mode != 'pending' and d['status'] != 'archived':
                continue
            if month and not (d.get('date_beijing') or '').startswith(month):
                continue
            haystack = ' '.join(str(d.get(k) or '') for k in ('author', 'handle', 'account_name', 'account_handle', 'content', 'translation_zh', 'tags', 'tweet_id')).casefold()
            if all(w in haystack for w in words):
                result.append(d)
        return list(reversed(result)) if oldest else result

    def content_counts(self, account=''):
        counts = dict(original=0, quote=0, retweet=0, reference=0)
        for doc in self.docs:
            if doc['status'] == 'archived' and (not account or doc['account'] == account):
                kind = doc.get('post_type', 'original')
                counts[kind] = counts.get(kind, 0) + 1
        return counts

    def annotate(self, doc, favorite=None, tags=None):
        favorite = doc['favorite'] if favorite is None else bool(favorite)
        tags = doc['tags'] if tags is None else tags.strip()
        with self.state:
            self.state.execute('INSERT OR REPLACE INTO notes VALUES (?,?,?,?)', (doc['account'], doc['tweet_id'], int(favorite), tags))
        doc.update(favorite=favorite, tags=tags)

    def add_account(self, handle, name):
        handle = handle.strip().lstrip('@')
        if not re.fullmatch(r'[A-Za-z0-9_]{1,15}', handle):
            raise ValueError('请输入有效的 X 用户名，例如 aoki__hina')
        # Re-read to avoid overwriting changes made outside the app.
        path = self.root / 'tools/accounts.json'
        accounts = json.loads(path.read_text(encoding='utf-8-sig'))
        if any(a['handle'].lower() == ('@' + handle).lower() for a in accounts):
            raise ValueError('这个账号已经在资料库中')
        removed=self.preference('removed_accounts_v1',{})
        entry=removed.get(handle.lower()) if isinstance(removed,dict) else None
        if isinstance(entry,dict):
            saved=entry.get('account')
            if (isinstance(saved,dict) and all(isinstance(saved.get(k),str) and saved[k] for k in ('key','name','handle','folder'))
                and saved['handle'].lstrip('@').casefold()==handle.casefold()
                and saved['key'] not in {a['key'] for a in accounts} and self.safe_path(saved['folder'])):
                account=dict(saved);account['name']=name.strip() or account['name']
                self.safe_path(account['folder']).mkdir(parents=True,exist_ok=True)
                temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(accounts+[account],ensure_ascii=False,indent=2),encoding='utf-8')
                temporary.replace(path);self.accounts=accounts+[account]
                grouping=self.account_groups();group=entry.get('group')
                if group in {g['id'] for g in grouping['groups']}:
                    grouping['memberships'][account['key']]=group;self.save_account_groups(grouping)
                self.reload();return account
        key = handle.lower()
        existing_keys = {a['key'] for a in accounts}
        with closing(sqlite3.connect((self.root/'_推文归档/tweets.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
            existing_keys.update(row[0] for row in db.execute('SELECT DISTINCT account FROM tweets'))
        while key in existing_keys:
            key = 'x_' + key
        folder = handle
        while (self.root / folder).exists():
            folder = 'X_' + folder
        account = dict(key=key, name=name.strip() or handle, handle='@' + handle,
                       folder=folder, url=f'https://x.com/{handle}/media')
        backup = path.with_name('accounts.before-manager.json')
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(accounts + [account], ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(path)
        (self.root / folder).mkdir(exist_ok=True)
        self.accounts = accounts + [account]
        return account

    def remove_account(self, key):
        """Remove an account from active browsing while retaining its local data."""
        path=self.root/'tools/accounts.json';original=path.read_bytes()
        accounts=json.loads(original.decode('utf-8-sig'))
        account=next((a for a in accounts if a['key']==key),None)
        if account is None:raise ValueError('账号已不存在，请刷新资料库。')
        removed=self.preference('removed_accounts_v1',{})
        if not isinstance(removed,dict):removed={}
        grouping=self.account_groups()
        removed[account['handle'].lstrip('@').casefold()]=dict(account=account,group=grouping['memberships'].pop(key,None))
        remaining=[a for a in accounts if a['key']!=key]
        temporary=path.with_suffix('.remove.tmp')
        temporary.write_text(json.dumps(remaining,ensure_ascii=False,indent=2),encoding='utf-8')
        replaced=False
        try:
            with self.state:
                for name,value in [('removed_accounts_v1',removed),('account_groups_v1',grouping)]:
                    self.state.execute('INSERT OR REPLACE INTO preferences VALUES (?,?)',(name,json.dumps(value,ensure_ascii=False)))
                temporary.replace(path);replaced=True
        except (OSError,sqlite3.Error):
            if replaced:
                temporary.write_bytes(original);temporary.replace(path)
            raise
        self.reload();return account

    @staticmethod
    def display_name(value):
        value=value.strip()
        if not value or len(value)>80 or any(ord(c)<32 for c in value):
            raise ValueError('名称不能为空，最多 80 个字符，不能包含换行。')
        return value

    def rename_account(self, key, name):
        name=self.display_name(name)
        path=self.root/'tools/accounts.json'
        accounts=json.loads(path.read_text(encoding='utf-8-sig'))
        account=next((a for a in accounts if a['key']==key),None)
        if account is None:raise ValueError('账号已不存在，请刷新资料库。')
        account['name']=name
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(accounts,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(path)
        self.accounts=accounts
        return account

    def account_groups(self):
        value=self.preference('account_groups_v1',{})
        if not isinstance(value,dict):value={}
        groups=[];ids=set()
        for group in value.get('groups',[]):
            if isinstance(group,dict) and isinstance(group.get('id'),str) and isinstance(group.get('name'),str) and group['id'] not in ids:
                groups.append(dict(id=group['id'],name=group['name']));ids.add(group['id'])
        members=value.get('memberships',{})
        if not isinstance(members,dict):members={}
        known={a['key'] for a in self.accounts}
        collapsed=value.get('collapsed',[])
        return dict(groups=groups,memberships={k:v for k,v in members.items() if k in known and v in ids},
                    collapsed=[key for key in collapsed if key in ids])

    def save_account_groups(self, value):
        self.set_preference('account_groups_v1',value)

    def create_group(self, name):
        name=self.display_name(name);value=self.account_groups()
        if any(g['name'].casefold()==name.casefold() for g in value['groups']):raise ValueError('已经存在同名分组。')
        group=dict(id=uuid.uuid4().hex,name=name);value['groups'].append(group)
        self.save_account_groups(value);return group

    def rename_group(self, group_id, name):
        name=self.display_name(name);value=self.account_groups()
        group=next((g for g in value['groups'] if g['id']==group_id),None)
        if group is None:raise ValueError('分组已不存在。')
        if any(g['id']!=group_id and g['name'].casefold()==name.casefold() for g in value['groups']):raise ValueError('已经存在同名分组。')
        group['name']=name;self.save_account_groups(value)

    def move_account(self, key, group_id=None):
        value=self.account_groups()
        if key not in {a['key'] for a in self.accounts}:raise ValueError('账号已不存在。')
        if group_id is not None and group_id not in {g['id'] for g in value['groups']}:raise ValueError('分组已不存在。')
        if group_id is None:value['memberships'].pop(key,None)
        else:value['memberships'][key]=group_id
        self.save_account_groups(value)

    def dissolve_group(self, group_id):
        value=self.account_groups()
        value['groups']=[g for g in value['groups'] if g['id']!=group_id]
        value['memberships']={key:group for key,group in value['memberships'].items() if group!=group_id}
        value['collapsed']=[key for key in value['collapsed'] if key!=group_id]
        self.save_account_groups(value)

    def toggle_group(self, group_id):
        value=self.account_groups()
        if group_id not in {g['id'] for g in value['groups']}:return
        if group_id in value['collapsed']:value['collapsed'].remove(group_id)
        else:value['collapsed'].append(group_id)
        self.save_account_groups(value)
