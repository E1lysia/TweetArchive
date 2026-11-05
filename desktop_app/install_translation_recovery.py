"""Install the prepared translation fix locally. Does not create release archives."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import runpy

WORK = Path(__file__).resolve().parents[1]
ROOT = Path(r'D:\gallery-dl').resolve()
VERSION = runpy.run_path(str(WORK/'desktop_app/version.py'))['VERSION']
FILES = {
    'tools/translation_engine.py': WORK/'local_archive/tools/translation_engine.py',
    'tools/deepl_translate.py': WORK/'local_archive/tools/deepl_translate.py',
    'tools/tweet_archive.py': WORK/'local_archive/tools/tweet_archive.py',
    '资料库/app.py': WORK/'desktop_app/app.py',
    '资料库/version.py': WORK/'desktop_app/version.py',
}
for relative, source in FILES.items():
    target = (ROOT/relative).resolve()
    assert target.is_relative_to(ROOT) and source.is_file() and target.is_file()
    compile(source.read_text(encoding='utf-8-sig'), str(source), 'exec')

# The program and data may live in different locations. Only program files are
# installed; cookies, configuration, database records and media are never copied.
protected = [ROOT/'cookies.txt', ROOT/'tools/deepl.local.json',
             ROOT/'tools/translation.local.json', ROOT/'tools/accounts.json',
             ROOT/'storage.local.json']
fingerprints = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in protected if p.is_file()}
backup = ROOT/'资料库/_版本备份'/(f'before-{VERSION}-translation-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
assert backup.resolve().is_relative_to(ROOT)
backup.mkdir(parents=True, exist_ok=False)
for relative in FILES:
    saved = backup/relative
    saved.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT/relative, saved)

installed = []
try:
    for relative, source in FILES.items():
        target = ROOT/relative
        temp = target.with_name(target.name+'.update-new')
        shutil.copy2(source, temp)
        temp.replace(target)
        installed.append(relative)
        assert target.read_bytes() == source.read_bytes()
except Exception:
    for relative in reversed(installed):
        target = ROOT/relative
        temp = target.with_name(target.name+'.rollback-new')
        shutil.copy2(backup/relative, temp)
        temp.replace(target)
    raise
assert all(hashlib.sha256(p.read_bytes()).hexdigest() == value for p,value in fingerprints.items())
print(json.dumps(dict(version=VERSION, backup=str(backup), program_files=len(FILES),
                      credentials_and_accounts_unchanged=True, restart_required=True,
                      release_created=False), ensure_ascii=False))
