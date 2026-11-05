"""Generate portable scripts/docs and collect public third-party license texts."""
import shutil
import runpy
import urllib.request
from pathlib import Path

WORK=Path(__file__).resolve().parents[1]
ASSETS=WORK/'packaging/assets'


def write(relative,text,encoding='utf-8'):
    path=ASSETS/relative; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text,encoding=encoding)


def main():
    login=runpy.run_path(str(WORK/'packaging/login_refresh/grab_cookies.py'))
    login['make_extension'](ASSETS/'TweetArchive-XLogin')
    for source_name,target_name in (
        ('grab_cookies.py','_setup/grab_cookies.py'),
        ('刷新登录态.cmd','刷新登录态.cmd'),
        ('刷新登录态说明.txt','刷新登录态说明.txt'),
    ):
        text=(WORK/'packaging/login_refresh'/source_name).read_text(encoding='utf-8')
        if source_name.endswith('.cmd'):
            path=ASSETS/target_name; path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(text.replace('\n','\r\n').encode('utf-8'))
        else:
            write(target_name,text)
    update=(WORK/'local_archive/tools/update.ps1').read_text(encoding='utf-8-sig')
    write('tools/update.ps1',update,'utf-8-sig')
    months=Path(r'D:\gallery-dl\tools\archive_months.py').read_text(encoding='utf-8')
    months=months.replace('默认: D:\\\\gallery-dl\\\\青木阳菜','默认: 当前工作目录')
    months=months.replace('Path(r"D:\\gallery-dl\\青木阳菜")','Path.cwd()')
    write('tools/archive_months.py',months)
    sheet=Path(r'D:\gallery-dl\_setup\gen_sheet.py').read_text(encoding='utf-8')
    sheet=sheet.replace('默认: D:\\\\gallery-dl\\\\青木阳菜  @aoki__hina  青木陽菜','默认: 当前工作目录')
    sheet=sheet.replace('Path(r"D:\\gallery-dl\\青木阳菜")','Path.cwd()').replace('"@aoki__hina"','""').replace('"青木陽菜"','ROOT.name')
    sheet=sheet.replace('sys.exit("no images found")','print("no images found"); sys.exit(0)')
    sheet=sheet.replace('font_big = ImageFont.truetype(r"C:\\Windows\\Fonts\\msyh.ttc", 30)\nfont_small = ImageFont.truetype(r"C:\\Windows\\Fonts\\msyh.ttc", 22)',
        'fonts = [Path(__import__("os").environ.get("WINDIR", r"C:\\Windows")) / "Fonts" / name for name in ("msyh.ttc", "segoeui.ttf", "arial.ttf")]\nfont_path = next((p for p in fonts if p.exists()), None)\nfont_big = ImageFont.truetype(str(font_path), 30) if font_path else ImageFont.load_default()\nfont_small = ImageFont.truetype(str(font_path), 22) if font_path else ImageFont.load_default()')
    write('_setup/gen_sheet.py',sheet)
    guide=(WORK/'desktop_app/使用说明.md').read_text(encoding='utf-8')
    guide=guide.replace('D:\\gallery-dl\\推文资料库.exe','解压目录中的“推文资料库.exe”').replace('推文资料库.cmd','启动资料库.cmd')
    guide=guide.replace('使用原来的“刷新登录态.cmd”','在“设置与翻译”中重新导入本人 X 登录文件')
    write('功能说明.md',guide)
    write('先读我.txt','''推文资料库 1.1.0 · Windows x64 便携版

1. 将 ZIP 完整解压到自己有写入权限的普通目录，例如 D:\\TweetArchive。
2. 双击“推文资料库.exe”。不要在压缩包内直接运行，不要只复制启动 EXE。
3. 点击左侧“归档账号”旁的“＋”，填写想归档的 X 用户名。
4. 双击“刷新登录态.cmd”，按提示先在 Edge 登录 X、保存并完全退出 Edge，再按回车获取登录态。
   未自动完成时，在 Edge 扩展页加载本目录的“TweetArchive-XLogin”文件夹；已加载过则点重新加载。
   该扩展文件夹随包提供，不会在超时后删除。详见“刷新登录态说明.txt”。
   也可在“设置与翻译”中导入本人准备的 Netscape 格式 cookies.txt。
   本工具不索取账号密码、不强制关闭浏览器；只在你主动运行并按回车后读取本人 X 登录信息。
5. 需要中文翻译时，在设置中选择 DeepL、DeepSeek、通义千问、Kimi 或自定义兼容接口，填写本人 API 密钥。
   可先“保存并试译固定样例”。API 费用由服务商按其规则收取。
6. 点击“补新当前账号”；任务队列可查看下载、归档、翻译进度。

运行环境：Windows 10 22H2 / Windows 11，64 位 x64；本包已包含 Python、Qt 和独立启动器，
不要求另装 Python 或 .NET。建议保留至少 1GB 可用磁盘，图片、视频下载需要额外空间。
本包无数字签名；请核对随包提供的 SHA-256，只运行来源可信的文件，不要关闭系统安全防护。

本包是空资料库，不包含原作者的推文、图片、视频、关注账号、收藏、标签、Cookies 或 API 密钥。
补新保存账号正文（含纯文字）并下载媒体；保留原创 / 引用 / 转推来源区分，回复默认关闭。
内容类型支持多选。设置中的“存储与归档”可更改数据位置、复制迁移或新建教学空库。
旧的纯文字可用补新菜单中的“补历史正文”加入，支持日期、扫描上限与继续未完成任务。
默认数据保存在本目录；更改存储位置后，备份时需要同时保存程序目录和外部资料库目录。
使用“复制现有资料并切换”迁移时会保留原目录；登录文件和 API 密钥留在程序目录。

故障排查：
- 无法启动：先确认已完整解压、目录可写、系统为 Windows x64，再运行“启动资料库.cmd”。
  如果仍失败，查看“资料库/启动错误.log”。
- 登录失效：运行本目录“刷新登录态.cmd”，或重新导入本人 X 登录文件；不要把登录文件发给他人。
- 翻译失败：在任务队列查看原因，确认密钥、模型、地址与服务商余额后重试。
- 视频格式不兼容：使用“更多 → 打开媒体 / 系统播放器”。

使用后如需再次分享，请重新使用原始 ZIP；自己的运行目录会包含登录文件、密钥和私人归档。
第三方许可证和源码来源见“第三方组件声明.md”与“LICENSES”。
''')
    write('第三方组件声明.md','''# 第三方组件与源码

本包的界面、归档、翻译代码以可读 Python 源文件提供；启动器源代码在“源码/launcher”。
本包不包含个人登录信息或媒体，配置由收件人自行建立。

| 组件 | 版本 | 许可证与上游 |
| --- | --- | --- |
| Python | 3.12 | PSF；python/LICENSE.txt；https://www.python.org/downloads/source/ |
| PySide6 / Shiboken6 / Qt | 6.12.0 | 按 LGPLv3 使用适用模块；原元数据与许可文字位于 vendor 各 dist-info；https://download.qt.io/official_releases/QtForPython/pyside6/ |
| Qt 源码 | 6.12.0 | https://download.qt.io/official_releases/qt/6.12/6.12.0/submodules/ |
| gallery-dl | 1.32.17 | GPL-2.0-only；完整 Python 源码与许可证随包；https://codeberg.org/mikf/gallery-dl |
| Pillow | 13.0.0 | MIT-CMU；许可证随 dist-info/licenses；https://github.com/python-pillow/Pillow |
| requests / urllib3 / certifi / idna / charset-normalizer / websocket-client | 见随包 METADATA | 许可证保留于各 dist-info；组件源代码均保留 |
| .NET 启动器运行时 | 8.0.32 | MIT / 第三方声明，见 LICENSES/dotnet；https://github.com/dotnet/runtime/tree/v8.0.32 |

Qt 的第三方组件说明：https://doc.qt.io/qt-6/licenses-used-in-qt.html
Qt Multimedia / FFmpeg：https://doc.qt.io/qt-6/qtmultimedia-attribution-ffmpeg.html

Qt / PySide6 共享库保持独立、未修改并可替换；未打包 WebEngine、Charts 等不需要的模块。
为调试自行修改的 LGPL 库版本而进行的逆向工程不受本应用额外限制。
运行时中保留的商业许可文字是上游发行包原始文件；本包使用其公开元数据列明的开源许可选项。
请保留第三方的版权、许可证及对应源码获取信息。
''')
    urls={
        'LGPL-3.0.txt':'https://raw.githubusercontent.com/qt/qtbase/dev/LICENSES/LGPL-3.0-only.txt',
        'GPL-3.0.txt':'https://raw.githubusercontent.com/qt/qtbase/dev/LICENSES/GPL-3.0-only.txt',
        'Qt-Exception-1.0.txt':'https://raw.githubusercontent.com/qt/qtbase/dev/LICENSES/Qt-GPL-exception-1.0.txt',
    }
    for name,url in urls.items():
        path=ASSETS/'LICENSES'/name
        if path.exists(): continue
        try:
            with urllib.request.urlopen(url,timeout=45) as response: data=response.read()
        except Exception:
            if name=='Qt-Exception-1.0.txt': continue
            raise
        path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
    runtime=Path.home()/'.nuget/packages/microsoft.netcore.app.runtime.win-x64/8.0.32'
    for name in ('LICENSE.TXT','THIRD-PARTY-NOTICES.TXT'):
        found=next((p for p in runtime.rglob('*') if p.name.upper()==name),None)
        if found:
            target=ASSETS/'LICENSES/dotnet'/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(found,target)
    print('Portable assets and notices prepared.')


if __name__=='__main__': main()
