"""Build the current clean integrated release from the verified runtime template."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import runpy
import zipfile

WORK=Path(__file__).resolve().parents[1]
RELEASE=WORK/'release'
VERSION=runpy.run_path(str(WORK/'desktop_app/version.py'))['VERSION']
NAME='TweetArchive-'+VERSION+'-win-x64'
ARCHIVE=RELEASE/(NAME+'.zip')


def validate(z):
    assert z.testzip() is None
    names=z.namelist();assert len(names)==len(set(name.casefold() for name in names))
    prefixes={PurePosixPath(name).parts[0] for name in names}
    assert len(prefixes)==1
    prefix=next(iter(prefixes))
    for name in names:
        relative=PurePosixPath(name)
        assert relative.parts[0]==prefix and '..' not in relative.parts and '\\' not in name
    manifest=json.loads(z.read(prefix+'/MANIFEST.json'))
    expected={prefix+'/'+entry['path'] for entry in manifest['files']}|{prefix+'/MANIFEST.json'}
    assert set(names)==expected
    for entry in manifest['files']:
        data=z.read(prefix+'/'+entry['path'])
        assert len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256']
    assert json.loads(z.read(prefix+'/tools/accounts.json'))==[]
    forbidden={'cookies.txt','tweets.sqlite','manager.sqlite','storage.local.json','archive.local.json'}
    media={'.jpg','.jpeg','.mp4','.webm','.mov','.mkv','.gif'}
    for name in names:
        path=PurePosixPath(name);lower=name.casefold()
        assert path.name.casefold() not in forbidden
        assert not lower.endswith(('.local.json','.sqlite','.sqlite3','.db','.log','.pyc'))
        assert not any(part.casefold() in ('_推文归档','_版本备份','__pycache__') for part in path.parts)
        assert path.suffix.casefold() not in media
    for path in ('刷新登录态.cmd','TweetArchive-XLogin/manifest.json','TweetArchive-XLogin/background.js',
                 'python/python.exe','资料库/task_runner.py','操作指南.html'):
        assert prefix+'/'+path in names
    assert any(prefix+'/'+name in names for name in ('TweetArchive.exe','推文资料库.exe'))
    return manifest


def main():
    # Reuse only a previously verified clean runtime, never the personal library.
    base_archive=ARCHIVE if ARCHIVE.exists() else RELEASE/'推文资料库-最新整合版.zip'
    if not base_archive.exists():
        raise SystemExit('需要一个经过验证的干净运行环境模板；请先构建基础便携版。')
    old_digest=hashlib.sha256(base_archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(base_archive) as base:
        old=validate(base)
        prefix=PurePosixPath(base.namelist()[0]).parts[0]
        payload={entry['path']:base.read(prefix+'/'+entry['path']) for entry in old['files']}
    if base_archive==ARCHIVE and old['version']!=VERSION:
        previous=RELEASE/('推文资料库-整合版-'+old['version']+'-保留.zip')
        if previous.exists():assert hashlib.sha256(previous.read_bytes()).hexdigest()==old_digest
        else:previous.write_bytes(base_archive.read_bytes())
    updates={}
    launcher=WORK/'packaging/launcher-dist/TweetArchive.exe'
    assert launcher.is_file() and launcher.stat().st_size>5_000_000, '请先 publish self-contained single-file TweetArchive 启动器'
    for name in list(payload):
        if name in ('推文资料库.exe','推文资料库.cmd','启动资料库.cmd') or name.startswith('推文资料库操作指南.'):
            del payload[name]
    updates['TweetArchive.exe']=launcher.read_bytes()
    updates['TweetArchive.cmd']=(WORK/'packaging/assets/TweetArchive.cmd').read_bytes()
    for name in ('Launcher.csproj','Program.cs','archive.ico'):
        updates['源码/launcher/'+name]=(WORK/'desktop_app/launcher'/name).read_bytes()
    for path in ('TweetArchive-XLogin/manifest.json','_setup/grab_cookies.py'):
        updates[path]=(WORK/'packaging/assets'/path).read_bytes()
    ui=['app.py','adaptive_cards.py','text_presentation.py','library.py','media_viewer.py','settings_dialog.py','storage.py',
        'storage_settings.py','task_runner.py','translation_settings.py','version.py','video_posters.py']
    for name in ui:
        source=(WORK/'desktop_app'/name).read_text(encoding='utf-8-sig').replace(", r'D:\\gallery-dl\\资料库\\vendor'",'')
        compile(source,name,'exec')
        assert 'D:\\gallery-dl' not in source and 'C:\\Users\\Administrator' not in source
        updates['资料库/'+name]=source.encode('utf-8')
    updates['资料库/icons/check.svg']=(WORK/'desktop_app/icons/check.svg').read_bytes()
    for source in (WORK/'local_archive/tools').iterdir():
        if source.suffix in ('.py','.ps1','.html'):
            data=source.read_bytes()
            if source.suffix=='.py':compile(data,str(source),'exec')
            updates['tools/'+source.name]=data
    runpy.run_path(str(WORK/'packaging/build_guide.py'),run_name='__main__',
                   init_globals={'RELEASE_VERSION':VERSION,'GUIDE_ONLY':True})
    guide=(RELEASE/'推文资料库操作指南.html').read_text(encoding='utf-8')
    assert VERSION in guide and '不同账号分别记住组合' not in guide
    class GuideParser(HTMLParser):
        def __init__(self):super().__init__();self.ids=set();self.links=[]
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            if 'id' in attrs:self.ids.add(attrs['id'])
            if tag=='a' and attrs.get('href','').startswith('#'):self.links.append(attrs['href'][1:])
    parser=GuideParser();parser.feed(guide)
    assert len(parser.links)==12 and all(link in parser.ids for link in parser.links)
    updates['操作指南.html']=guide.encode('utf-8')
    updates['先读我.txt']=(f'TweetArchive {VERSION} · Windows x64 便携版\n\n'
        '完整解压后双击 TweetArchive.exe。操作方法见“操作指南.html”。\n'
        '首次使用请添加归档账号，并使用“刷新登录态.cmd”或设置中的“X 登录”配置本人登录。\n'
        '正文待补全页面的“补全推文”按原推 ID 获取历史正文，不下载媒体、不自动翻译。\n'
        '每位使用者自行配置翻译服务。本包不包含个人归档、账号列表、Cookies 或密钥。\n').encode('utf-8-sig')
    payload.update(updates)
    manifest={**{key:value for key,value in old.items() if key!='files'},'version':VERSION,'distribution':'integrated'}
    manifest['files']=[dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in sorted(payload.items())]
    payload['MANIFEST.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')
    temporary=ARCHIVE.with_suffix('.current.tmp')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,data in sorted(payload.items()):z.writestr(NAME+'/'+name,data)
    with zipfile.ZipFile(temporary) as z:
        assert validate(z)['version']==VERSION
        assert NAME+'/TweetArchive.exe' in z.namelist()
        assert NAME+'/推文资料库.exe' not in z.namelist()
        assert z.read(NAME+'/资料库/version.py').decode().strip()==f"VERSION = '{VERSION}'"
    temporary.replace(ARCHIVE)
    digest=hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    ARCHIVE.with_suffix('.zip.sha256').write_text(digest+'  '+ARCHIVE.name+'\n',encoding='utf-8')
    report=dict(version=VERSION,archive=str(ARCHIVE),sha256=digest,old_sha256=old_digest,base_archive=str(base_archive),
                files=len(payload),updated_program_and_guide_files=len(updates),no_private_data=True,single_user_guide=True)
    (RELEASE/'整合版验证报告.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
