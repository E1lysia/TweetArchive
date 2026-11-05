"""Render the user guide and add it to the verified portable release."""
import hashlib
import html
import json
import re
import zipfile
from pathlib import Path

WORK=Path(__file__).resolve().parents[1]
RELEASE=WORK/'release'
VERSION=globals().get('RELEASE_VERSION','1.1.0')
NAME='TweetArchive-'+VERSION+'-win-x64'
source=(WORK/'docs/操作指南.md').read_text(encoding='utf-8')


def inline(value):
    return re.sub(r'`([^`]+)`',lambda m:'<code>'+m[1]+'</code>',html.escape(value))


lines=source.splitlines()
body=[]; toc=[]; paragraph=[]; listing=None
def flush():
    if paragraph:
        body.append('<p>'+inline(' '.join(paragraph))+'</p>'); paragraph.clear()
def close_list():
    global listing
    if listing:
        body.append('</'+listing+'>'); listing=None
i=0
while i<len(lines):
    line=lines[i]
    if not line.strip():
        flush(); close_list(); i+=1; continue
    heading=re.match(r'^(#{1,3})\s+(.+)',line)
    if heading:
        flush(); close_list()
        level=len(heading[1]); title=heading[2]
        anchor='section-'+str(len(toc)+1) if level==2 else ''
        if level==2: toc.append((anchor,title))
        body.append(f'<h{level}'+(f' id="{anchor}"' if anchor else '')+'>'+inline(title)+f'</h{level}>')
        i+=1; continue
    if line.startswith('|') and i+1<len(lines) and re.match(r'^\|[\s:|\-]+$',lines[i+1]):
        flush(); close_list()
        cells=[v.strip() for v in line.strip('|').split('|')]
        body.append('<div class="table-wrap"><table><thead><tr>'+''.join('<th scope="col">'+inline(v)+'</th>' for v in cells)+'</tr></thead><tbody>')
        i+=2
        while i<len(lines) and lines[i].startswith('|'):
            cells=[v.strip() for v in lines[i].strip('|').split('|')]
            body.append('<tr>'+''.join('<td>'+inline(v)+'</td>' for v in cells)+'</tr>'); i+=1
        body.append('</tbody></table></div>'); continue
    item=re.match(r'^(?:\d+\.\s+|(-)\s+)(.+)',line)
    if item:
        flush(); tag='ul' if item[1] else 'ol'
        if listing!=tag:
            close_list(); listing=tag; body.append('<'+tag+'>')
        body.append('<li>'+inline(item[2])+'</li>'); i+=1; continue
    close_list(); paragraph.append(line); i+=1
flush(); close_list()
nav=''.join(f'<a href="#{anchor}">{html.escape(title)}</a>' for anchor,title in toc)
page='''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TweetArchive · 操作指南</title><style>
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}body{margin:0;color:#243447;background:#f3f6f8;font-family:"Microsoft YaHei UI","Segoe UI",sans-serif;line-height:1.85;font-size:16px}
.bar{background:#14212c;color:#f0f7f9;padding:20px 36px;font-weight:600;letter-spacing:.5px}.bar span{font-size:13px;color:#a8c3cb;margin-left:18px;font-weight:400}
.layout{display:grid;grid-template-columns:240px minmax(0,860px);gap:36px;max-width:1180px;padding:36px 24px 80px;margin:auto}
nav{align-self:start;position:sticky;top:20px;font-size:13px}nav strong{display:block;margin:0 0 12px;color:#607385}nav a{display:block;color:#485e72;text-decoration:none;padding:6px 0;border-bottom:1px solid #e0e7ec}nav a:hover{color:#0c7661}
article{min-width:0;background:white;border:1px solid #e0e7ec;border-radius:12px;padding:38px 44px;box-shadow:0 4px 20px #17344706}h1{font-size:30px;line-height:1.4;margin:0 0 12px;color:#142b3b}h2{font-size:22px;line-height:1.5;margin:40px 0 16px;padding-top:16px;border-top:1px solid #dce6eb;color:#146b60}h3{font-size:17px;line-height:1.6;margin:26px 0 8px;color:#23465c}p{margin:12px 0}li{padding-left:4px;margin:6px 0}ol,ul{padding-left:25px}code{font-family:Consolas,"Microsoft YaHei UI",monospace;background:#edf4f4;border-radius:4px;padding:2px 5px;overflow-wrap:anywhere;font-size:.91em}.table-wrap{overflow-x:auto;margin:18px 0}table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.7}th{text-align:left;background:#edf5f3;color:#24584f}th,td{padding:11px 13px;border:1px solid #dbe5e9;vertical-align:top}td:first-child{min-width:120px}footer{font-size:12px;color:#7b8b98;margin-top:36px}
@media(max-width:850px){.layout{display:block;padding:20px 12px}.bar{padding:18px}.bar span{display:block;margin-left:0}nav{position:static;margin:0 8px 24px;column-count:2}nav strong{column-span:all}article{padding:26px 22px}h1{font-size:26px}}
@media print{body{background:white;font-size:10.5pt}.bar,nav{display:none}.layout{display:block;padding:0;margin:0;max-width:none}article{border:0;padding:0;box-shadow:none}h1{font-size:23pt}h2{font-size:16pt;break-after:avoid}h3{font-size:12pt;break-after:avoid}p,li{orphans:3;widows:3}table{font-size:9pt}tr{break-inside:avoid}.table-wrap{overflow:visible}html{scroll-behavior:auto}}
</style></head><body><header class="bar">TweetArchive · 操作指南<span>Windows x64 便携版 1.0.0 / 可离线阅读，也可用浏览器打印</span></header>
<div class="layout"><nav aria-label="章节目录"><strong>快速目录</strong>'''+nav+'</nav><article>'+''.join(body)+'''<footer>本指南按分享版 1.0.0 的实际界面与功能编写。首次使用建议先完成第 1～6 节。</footer></article></div></body></html>'''
assert len(toc)==12
page=page.replace('1.0.0',VERSION)
assert '<script' not in page and len(re.findall('<table>',page))==4
outputs={
    '推文资料库操作指南.html':page.encode('utf-8'),
    '推文资料库操作指南.txt':re.sub(r'`([^`]+)`',r'\1',re.sub(r'^#{1,3}\s+','',source,flags=re.M)).replace('\n','\r\n').encode('utf-8-sig'),
}
if globals().get('GUIDE_ONLY',False):
    for name,value in outputs.items(): (RELEASE/name).write_bytes(value)
else:
    for name,value in outputs.items():
        (RELEASE/name).write_bytes(value)
        (RELEASE/NAME/name).write_bytes(value)
    archive=RELEASE/(NAME+'.zip')
    old_digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    temp=archive.with_suffix('.guide.tmp')
    with zipfile.ZipFile(archive) as original:
        manifest=json.loads(original.read(NAME+'/MANIFEST.json').decode('utf-8'))
        manifest['files']=[entry for entry in manifest['files'] if entry['path'] not in outputs]
        for name,value in outputs.items():
            manifest['files'].append(dict(path=name,bytes=len(value),sha256=hashlib.sha256(value).hexdigest()))
        manifest['files'].sort(key=lambda entry:entry['path'])
        manifest_bytes=json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as target:
            for entry in original.infolist():
                if entry.filename not in [NAME+'/MANIFEST.json',*[NAME+'/'+name for name in outputs]]:
                    target.writestr(entry,original.read(entry))
            for name,value in outputs.items(): target.writestr(NAME+'/'+name,value)
            target.writestr(NAME+'/MANIFEST.json',manifest_bytes)
    with zipfile.ZipFile(temp) as checked:
        assert checked.testzip() is None
        for entry in manifest['files']:
            assert hashlib.sha256(checked.read(NAME+'/'+entry['path'])).hexdigest()==entry['sha256']
        assert json.loads(checked.read(NAME+'/tools/accounts.json'))==[]
    temp.replace(archive)
    (RELEASE/NAME/'MANIFEST.json').write_bytes(manifest_bytes)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='ascii')
    print(json.dumps(dict(guide_sections=len(toc),guide_characters=len(source),zip_verified=True,old_sha256=old_digest,new_sha256=digest),ensure_ascii=False))
