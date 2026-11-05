"""Build a clean portable release from an explicit file allowlist."""
import hashlib
import json
import shutil
import struct
import zipfile
from pathlib import Path

WORK=Path(__file__).resolve().parents[1]
LOCAL=Path(r'D:\gallery-dl')
OUTPUT=WORK/'release'
VERSION='1.1.0'
NAME='TweetArchive-'+VERSION+'-win-x64'
DEST=OUTPUT/NAME


def copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,target)


def tree(source,target):
    for p in source.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pdb'):
            copy(p,target/p.relative_to(source))


def imports(path):
    """Read normal/delay DLL imports to retain the required Qt runtime closure."""
    data=path.read_bytes()
    if data[:2]!=b'MZ': return []
    pe=struct.unpack_from('<I',data,0x3c)[0]
    count=struct.unpack_from('<H',data,pe+6)[0]
    opt_size=struct.unpack_from('<H',data,pe+20)[0]
    opt=pe+24
    is64=struct.unpack_from('<H',data,opt)[0]==0x20b
    directories=opt+(112 if is64 else 96)
    sections=[]
    for n in range(count):
        at=opt+opt_size+n*40
        virtual_size,virtual_addr,raw_size,raw_offset=struct.unpack_from('<IIII',data,at+8)
        sections.append((virtual_addr,max(virtual_size,raw_size),raw_offset))
    def offset(rva):
        for va,size,raw in sections:
            if va<=rva<va+size: return raw+rva-va
        return rva
    result=[]
    for directory,stride,name_field in ((1,20,12),(13,32,4)):
        rva=struct.unpack_from('<I',data,directories+directory*8)[0]
        if not rva: continue
        at=offset(rva)
        while at+stride<=len(data) and any(data[at:at+stride]):
            name=struct.unpack_from('<I',data,at+name_field)[0]
            pos=offset(name)
            end=data.find(b'\0',pos)
            if end>pos: result.append(data[pos:end].decode('ascii').lower())
            at+=stride
    return result


def main():
    if DEST.exists():
        raise SystemExit('Release folder already exists; choose a new version instead of overwriting it.')
    DEST.mkdir(parents=True)
    for name in ('app.py','library.py','video_posters.py','translation_settings.py','storage.py','storage_settings.py'):
        text=(WORK/'desktop_app'/name).read_text(encoding='utf-8')
        text=text.replace(", r'D:\\gallery-dl\\资料库\\vendor'",'')
        (DEST/'资料库').mkdir(exist_ok=True)
        (DEST/'资料库'/name).write_text(text,encoding='utf-8')
    copy(LOCAL/'资料库/archive.ico',DEST/'资料库/archive.ico')
    copy(WORK/'packaging/launcher-dist/推文资料库.exe',DEST/'推文资料库.exe')
    for name in ('tweet_archive.py','tweet_archive_view.html','deepl_translate.py','translation_engine.py'):
        text=(WORK/'local_archive/tools'/name).read_text(encoding='utf-8')
        if name=='deepl_translate.py':
            text=text.replace('["青木陽菜", "鈴木みのり", "MyGO!!!!!", "Ave Mujica", "BanG Dream!"]','[]')
        target=DEST/'tools'/name; target.parent.mkdir(exist_ok=True)
        target.write_text(text,encoding='utf-8')
    # Only runtime files and known dependency packages, never the local download/archive folders.
    for p in (LOCAL/'python').iterdir():
        if p.is_file(): copy(p,DEST/'python'/p.name)
    packages=['gallery_dl','PIL','requests','certifi','charset_normalizer','idna','urllib3','websocket']
    site=LOCAL/'python/Lib/site-packages'
    for name in packages: tree(site/name,DEST/'python/Lib/site-packages'/name)
    for dist in site.glob('*.dist-info'):
        if dist.name.lower().startswith(tuple(n.lower()+'-' for n in ('gallery_dl','pillow','requests','certifi','charset_normalizer','idna','urllib3','websocket_client'))):
            tree(dist,DEST/'python/Lib/site-packages'/dist.name)
    vendor=LOCAL/'资料库/vendor'; qt=vendor/'PySide6'; target=DEST/'资料库/vendor/PySide6'
    for p in qt.glob('*.py'): copy(p,target/p.name)
    for name in ('support','QtAsyncio'): tree(qt/name,target/name)
    tree(vendor/'shiboken6',DEST/'资料库/vendor/shiboken6')
    roots=[]
    for name in ('QtCore','QtGui','QtWidgets','QtNetwork','QtMultimedia','QtMultimediaWidgets','QtOpenGL','QtOpenGLWidgets','QtSvg'):
        roots.append(qt/(name+'.pyd'))
        if (qt/(name+'.pyi')).is_file(): copy(qt/(name+'.pyi'),target/(name+'.pyi'))
    roots += [qt/'pyside6.abi3.dll',qt/'opengl32sw.dll']
    roots += list(qt.glob('*140*.dll'))+list(qt.glob('av*.dll'))+list(qt.glob('sw*.dll'))
    for category in ('platforms','imageformats','iconengines','multimedia','styles','networkinformation','tls'):
        roots += [p for p in (qt/'plugins'/category).rglob('*.dll') if 'pdf' not in p.name.lower()]
    binaries={p.name.lower():p for p in vendor.rglob('*') if p.suffix.lower() in ('.dll','.pyd')}
    pending=list(roots); selected=set()
    while pending:
        p=pending.pop()
        if p in selected: continue
        if not p.is_file(): raise RuntimeError('Missing runtime: '+p.name)
        selected.add(p)
        for dep in imports(p):
            if dep in binaries: pending.append(binaries[dep])
    for p in selected: copy(p,DEST/'资料库/vendor'/p.relative_to(vendor))
    for p in (qt/'translations').glob('qtbase_*.qm'): copy(p,target/'translations'/p.name)
    for dist in vendor.glob('*.dist-info'):
        if dist.name.startswith(('pyside6-','pyside6_essentials-','pyside6_addons-','shiboken6-')):
            tree(dist,DEST/'资料库/vendor'/dist.name)
    for p in (WORK/'packaging/assets').rglob('*'):
        if p.is_file(): copy(p,DEST/p.relative_to(WORK/'packaging/assets'))
    # Preserve the complete application sources, launcher source and third-party dependency sources/notices.
    for p in (WORK/'desktop_app/launcher').glob('*'):
        if p.is_file() and p.suffix in ('.cs','.csproj','.ico'): copy(p,DEST/'源码/launcher'/p.name)
    atomic=DEST/'tools/accounts.json'
    atomic.write_text('[]\n',encoding='utf-8')
    (DEST/'config.json').write_text(json.dumps({
        'extractor':{'base-directory':'./downloads','retries':3,'timeout':30,
                     'twitter':{'filename':'{date:%Y-%m-%d}_{tweet_id}_{num:02}.{extension}',
                                'retweets':True,'quoted':True}},
        'cache':{'file':'./_推文归档/gallery-cache.sqlite'}},ensure_ascii=False,indent=2),encoding='utf-8')
    (DEST/'gallery-dl.cmd').write_text('@echo off\r\nchcp 65001 >nul\r\nset PYTHONIOENCODING=utf-8\r\n"%~dp0python\\python.exe" -m gallery_dl --config-ignore -c "%~dp0config.json" %*\r\n',encoding='utf-8')
    (DEST/'启动资料库.cmd').write_text('@echo off\r\nstart "" "%~dp0python\\pythonw.exe" "%~dp0资料库\\app.py" --root "%~dp0."\r\n',encoding='gbk')
    manifest=[]
    for p in sorted(DEST.rglob('*')):
        if p.is_file(): manifest.append(dict(path=p.relative_to(DEST).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    (DEST/'MANIFEST.json').write_text(json.dumps(dict(version=VERSION,platform='win-x64',files=manifest),ensure_ascii=False,indent=2),encoding='utf-8')
    forbidden={'cookies.txt','deepl.local.json','translation.local.json','manager.sqlite','tweets.sqlite','accounts.before-manager.json'}
    assert not [p for p in DEST.rglob('*') if p.name in forbidden]
    assert json.loads(atomic.read_text())==[]
    archive=OUTPUT/(NAME+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in DEST.rglob('*'):
            if p.is_file(): z.write(p,NAME+'/'+p.relative_to(DEST).as_posix())
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='ascii')
    print(json.dumps(dict(archive=str(archive),files=len(manifest)+1,expanded_MiB=round(sum(p.stat().st_size for p in DEST.rglob('*') if p.is_file())/1024**2,1),zip_MiB=round(archive.stat().st_size/1024**2,1),sha256=digest),ensure_ascii=False))


if __name__=='__main__': main()
