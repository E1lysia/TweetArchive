"""Exercise the PowerShell pipeline with local recorder stubs; no X traffic."""
import json
from pathlib import Path
import shutil
import subprocess
import time

WORK=Path(__file__).resolve().parents[1]
qa=WORK/'packaging/qa'/('下载流程 空格-'+time.strftime('%H%M%S'))
runtime=qa/'程序';data=qa/'外部资料库'
(runtime/'python').mkdir(parents=True);(runtime/'tools').mkdir();(runtime/'_setup').mkdir()
(data/'tools').mkdir(parents=True)
for path in (WORK/'release/TweetArchive-1.1.0-win-x64/python').iterdir():
    if path.is_file():shutil.copy2(path,runtime/'python'/path.name)
recorder='''import json,sys
from pathlib import Path
root=Path(__file__).resolve()
while not (root/'record.py').is_file(): root=root.parent
with (root/'calls.jsonl').open('a',encoding='utf-8') as f:
 f.write(json.dumps(dict(script=Path(__file__).name,args=sys.argv[1:]),ensure_ascii=False)+'\\n')
print('fixture ok')
'''
(runtime/'record.py').write_text(recorder,encoding='utf-8')
for name in ['tweet_archive.py','archive_months.py']:(runtime/'tools'/name).write_text(recorder,encoding='utf-8')
(runtime/'_setup/gen_sheet.py').write_text(recorder,encoding='utf-8')
(runtime/'gallery-dl.cmd').write_bytes(b'@echo off\r\n"%~dp0python\\python.exe" -X utf8 "%~dp0record.py" gallery %*\r\n')
(runtime/'cookies.txt').write_text('fixture only',encoding='utf-8')
shutil.copy2(WORK/'local_archive/tools/update.ps1',runtime/'tools/update.ps1')
(data/'tools/accounts.json').write_text(json.dumps([dict(key='fixture',name='示例',handle='@example',folder='作者')]),encoding='utf-8')
(data/'tools/archive.local.json').write_text(json.dumps(dict(post_types=['original','quote'],include_replies=False)),encoding='utf-8')
p=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(runtime/'tools/update.ps1'),'-Index','1','-DataRoot',str(data),'-RuntimeRoot',str(runtime)],capture_output=True,encoding='utf-8',errors='replace',timeout=45)
assert p.returncode==0,p.stdout+'\n'+p.stderr
calls=[json.loads(line) for line in (runtime/'calls.jsonl').read_text(encoding='utf-8').splitlines()]
tweets=[c for c in calls if c['script']=='tweet_archive.py']
assert len(tweets)==2 and '--sync-text-only' in tweets[0]['args'] and '--media-only' in tweets[1]['args']
for call in tweets:
    args=call['args'];assert args[args.index('--root')+1]==str(data)
    assert args[args.index('--runtime-root')+1]==str(runtime)
    assert args[args.index('--index')+1]=='1'
downloads=[c['args'] for c in calls if c['script']=='record.py' and '--download-archive' in c['args']]
assert len(downloads)==2
for args in downloads:
    assert args[args.index('-C')+1]==str(runtime/'cookies.txt')
    assert Path(args[args.index('-D')+1]).is_relative_to(data)
    expression=args[args.index('--filter')+1]
    assert 'not reply_id' in expression and 'quoted_id' in expression
    assert '(retweet_id)' not in expression
assert not (runtime/'作者').exists()
report=dict(powershell_flow=True,external_data_root=True,runtime_credentials_separate=True,type_filter=True,network_used=False,calls=len(calls))
(qa/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
