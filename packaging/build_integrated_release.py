"""One current portable distribution with a single consolidated user guide."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import zipfile

WORK=Path(__file__).resolve().parents[1]
RELEASE=WORK/'release'
SOURCE=RELEASE/'TweetArchive-1.1.0-win-x64.zip'
OLD='TweetArchive-1.1.0-win-x64'
NAME='推文资料库-最新整合版'
archive=RELEASE/(NAME+'.zip')
removed={'先读我.txt','功能说明.md','刷新登录态说明.txt','升级到1.1.0.txt',
         '推文资料库操作指南.html','推文资料库操作指南.txt'}
report=json.loads((RELEASE/'1.1.0验证报告.json').read_text(encoding='utf-8'))
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==report['zip_sha256']

with zipfile.ZipFile(SOURCE) as original:
    manifest=json.loads(original.read(OLD+'/MANIFEST.json'))
    payload={entry['path']:original.read(OLD+'/'+entry['path']) for entry in manifest['files'] if entry['path'] not in removed}
    guide=original.read(OLD+'/推文资料库操作指南.html').decode('utf-8')
    guide=guide.replace('本文按分享版界面编写。','最新整合版；程序版本 1.1.0。本包已包含全部更新，无需另外安装补丁。')
    guide=guide.replace('本指南按分享版 1.1.0 的实际界面与功能编写。','本指南按最新整合版（程序 1.1.0）的实际界面与功能编写。')
    guide=guide.replace('<h2 id="section-2">2. 解压与启动</h2>',
        '<h2 id="section-2">2. 解压与启动</h2><p>本整合包包含最新版程序、多选筛选、存储迁移、纯文字与历史正文归档、多翻译引擎，以及固定的 TweetArchive-XLogin 本地扩展。操作说明统一在本页，不需要叠加旧补丁。</p>'
        '<p>已有资料的电脑请解压到新目录，不要用空库的账号文件覆盖原目录。启动后可在“设置与翻译 → 存储与归档 → 打开已有资料库”中选择原完整资料库；登录文件和翻译密钥仍按本程序目录单独配置。只是录教学时，直接使用这份空资料库即可。</p>')
    guide=guide.replace('<h3>第一次打开没有任何内容</h3>',
        '<h3>下载时需要开加速器吗</h3><p>取决于当前网络能否直接访问 X。需要代理时，整个补新过程保持连接，并确保下载程序的流量也经过代理；只装浏览器代理插件可能无法让程序联网。已归档的正文和媒体可以离线浏览，翻译需要连接所选服务。</p><h3>第一次打开没有任何内容</h3>')
    payload['操作指南.html']=guide.encode('utf-8')

class GuideCheck(HTMLParser):
    def __init__(self):super().__init__();self.ids=set();self.links=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if 'id' in attrs:self.ids.add(attrs['id'])
        if tag=='a' and attrs.get('href','').startswith('#'):self.links.append(attrs['href'][1:])
parser=GuideCheck();parser.feed(guide)
assert len(parser.links)==12 and all(link in parser.ids for link in parser.links)
assert '<script' not in guide
assert 'TweetArchive-XLogin/manifest.json' in payload and 'TweetArchive-XLogin/background.js' in payload
assert json.loads(payload['tools/accounts.json'])==[]
forbidden={'cookies.txt','deepl.local.json','translation.local.json','storage.local.json','archive.local.json','tweets.sqlite','manager.sqlite'}
assert not any(Path(name).name in forbidden for name in payload)
assert not any(name.lower().endswith(('.jpg','.jpeg','.mp4','.webm')) for name in payload)
manifest['distribution']='integrated'
manifest['files']=[dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in sorted(payload.items())]
payload['MANIFEST.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')
temporary=archive.with_suffix('.integrated.tmp')
with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as target:
    for name,data in payload.items():target.writestr(NAME+'/'+name,data)
with zipfile.ZipFile(temporary) as checked:
    assert checked.testzip() is None
    assert len(checked.namelist())==len(set(checked.namelist()))
    for entry in manifest['files']:
        assert hashlib.sha256(checked.read(NAME+'/'+entry['path'])).hexdigest()==entry['sha256']
    for entry in json.loads((RELEASE/'TweetArchive-1.1.0-win-x64/MANIFEST.json').read_text(encoding='utf-8'))['files']:
        if entry['path'] not in removed:
            assert hashlib.sha256(payload[entry['path']]).hexdigest()==entry['sha256']
temporary.replace(archive)
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='utf-8')
result=dict(archive=str(archive),version='1.1.0',sha256=digest,files=len(payload),
            single_user_guide=True,removed_redundant_documents=sorted(removed),
            runtime_identical_to_verified_release=True,no_private_data=True,
            root_files=[name for name in payload if '/' not in name])
(RELEASE/'整合版验证报告.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
