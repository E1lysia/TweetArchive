"""User-invoked Edge login export, scoped to this portable installation."""
import argparse
import hmac
import http.server
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import threading
import time


DOMAINS = ('x.com', 'twitter.com')
LIMIT = 128 * 1024


def selected_cookies(cookies, now=None):
    if not isinstance(cookies, list) or len(cookies) > 500:
        raise ValueError('登录数据格式无效。')
    now = time.time() if now is None else now
    selected = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        domain = cookie.get('domain', '')
        if not isinstance(domain, str):
            continue
        host = domain.lstrip('.').lower()
        if not any(host == d or host.endswith('.' + d) for d in DOMAINS):
            continue
        name, value, path = cookie.get('name', ''), cookie.get('value', ''), cookie.get('path', '/')
        if not all(isinstance(v, str) and not any(c in v for c in '\t\r\n\0') for v in (domain, name, value, path)):
            raise ValueError('登录数据包含无效字符。')
        if not name or not value:
            continue
        expiry = cookie.get('expirationDate')
        if expiry is not None:
            if not isinstance(expiry, (float, int)) or isinstance(expiry, bool):
                raise ValueError('登录有效期无效。')
            if not (now < expiry < 253402300800):
                continue
        selected.append(dict(cookie, domain=domain.lower(), path=path or '/'))
    if not any(c['name'] == 'auth_token' for c in selected):
        raise ValueError('没有读到有效的 X 登录信息；请确认使用的 Edge 个人资料已经登录 X。')
    return selected


def save_cookies(cookies, target):
    cookies = selected_cookies(cookies)
    lines = ['# Netscape HTTP Cookie File', '# X login exported locally by TweetArchive', '']
    for c in cookies:
        domain = c['domain']
        prefix = '#HttpOnly_' if c.get('httpOnly') else ''
        expiry = str(int(c['expirationDate'])) if c.get('expirationDate') is not None else ''
        lines.append('\t'.join((prefix + domain, 'TRUE' if domain.startswith('.') else 'FALSE',
                                c['path'], 'TRUE' if c.get('secure') else 'FALSE',
                                expiry, c['name'], c['value'])))
    target = Path(target)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         dir=target.parent, prefix='.login-', suffix='.tmp', delete=False) as f:
            temporary = Path(f.name)
            f.write('\n'.join(lines) + '\n')
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return len(cookies)


def find_edge():
    for key in ('PROGRAMFILES(X86)', 'PROGRAMFILES', 'LOCALAPPDATA'):
        directory = os.environ.get(key)
        if directory:
            path = Path(directory) / 'Microsoft/Edge/Application/msedge.exe'
            if path.is_file():
                return path
    found = shutil.which('msedge.exe')
    return Path(found) if found else None


def make_handler(token, result, done):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            if not hmac.compare_digest(self.path, '/cookies/' + token):
                self.send_error(404)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                length = 0
            if not 0 < length <= LIMIT:
                self.send_error(413)
                return
            self.connection.settimeout(5)
            try:
                cookies = selected_cookies(json.loads(self.rfile.read(length)))
            except (ValueError, OSError):
                # Do not print browser payloads, which may contain credentials.
                self.send_error(422, 'No valid X login')
                return
            if not done.is_set():
                result['cookies'] = cookies
                done.set()
            self.send_response(200)
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'ok')

        def log_message(self, *args):
            pass
    return Handler


def make_extension(folder, port=None, token=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    manifest = dict(manifest_version=3, name='TweetArchive · 本机登录导出', version='1.0.1',
                    description='仅将本人 X 登录信息交给正在运行的本机刷新工具。',
                    permissions=['cookies'],
                    host_permissions=['*://*.x.com/*', '*://*.twitter.com/*', 'http://127.0.0.1/*'],
                    background={'service_worker': 'background.js'})
    endpoint = json.dumps(f'http://127.0.0.1:{port}/cookies/{token}' if port and token else None)
    script = '''const ENDPOINT = __ENDPOINT__;
let busy = false;
async function run() {
  if (!ENDPOINT || busy) return;
  busy = true;
  try {
    const parts = await Promise.all(['x.com', 'twitter.com'].map(domain => chrome.cookies.getAll({domain})));
    const cookies = parts.flat();
    if (!cookies.some(c => c.name === 'auth_token' && (!c.expirationDate || c.expirationDate > Date.now()/1000))) return;
    const response = await fetch(ENDPOINT, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(cookies)});
    if (response.ok) clearInterval(timer);
  } catch (_) { /* No payload or token is logged. */ }
  finally { busy = false; }
}
const timer = setInterval(run, 3000);
setTimeout(() => clearInterval(timer), 235000);
chrome.runtime.onInstalled.addListener(run);
chrome.runtime.onStartup.addListener(run);
run();
'''.replace('__ENDPOINT__', endpoint)
    (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (folder / 'background.js').write_text(script, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description='将本人 Edge 中的 X 登录信息导出到本解压目录。')
    parser.add_argument('--check', action='store_true', help='仅检查路径，不读取登录信息、不启动浏览器。')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    extension = root / 'TweetArchive-XLogin'
    edge = find_edge()
    if args.check:
        print(json.dumps(dict(root=str(root), edge_found=bool(edge), target=str(root/'cookies.txt'),
                              extension=str(extension), extension_exists=(extension/'manifest.json').is_file()), ensure_ascii=False))
        return 0
    print('TweetArchive · 刷新本人的 X 登录态\n')
    print('登录文件将保存到：' + str(root / 'cookies.txt'))
    print('请先在 Edge 中登录 X，保存网页内容，再自行完全退出 Edge（包括后台）。')
    print('本工具不会强制关闭浏览器，也不会修改其他目录中的归档。')
    print('默认读取 Edge 默认个人资料；使用其他个人资料时，请按下面的手动加载步骤操作。')
    input('\n准备好后按回车继续，取消请关闭此窗口。')
    if not edge:
        print('未找到 Edge。请使用 Netscape 格式 Cookies 导出工具，并在软件设置中导入文件。')
        return 1
    result, done = {}, threading.Event()
    token = secrets.token_urlsafe(32)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(token, result, done))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        make_extension(extension, server.server_port, token)
        print('\n正在尝试打开 Edge 并加载本地扩展，最多等待 4 分钟。')
        print('如果没有自动完成：\n  1. 在已登录 X 的 Edge 个人资料中打开 edge://extensions。')
        print('  2. 开启“开发人员模式”，点击“加载解压缩的扩展”。')
        print('  3. 选择软件目录中的 TweetArchive-XLogin 文件夹（不是其中的文件）：\n' + str(extension))
        print('  4. 如果已经加载过这个扩展，请点击扩展卡片上的“重新加载 / 刷新”按钮。')
        print('  5. 保持本窗口打开，等待出现“成功”。\n')
        try:
            subprocess.Popen([str(edge), '--no-first-run', '--load-extension=' + str(extension),
                              '--disable-features=DisableLoadExtensionCommandLineSwitch', 'https://x.com/'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            print('自动打开 Edge 失败，请自行打开 Edge 并按上面的手动加载步骤继续。')
        if not done.wait(240):
            print('未获取到有效登录信息。原 cookies.txt 保持不变。')
            print('扩展文件夹已保留在软件目录。重新运行本工具后，在 Edge 扩展页重新加载它。')
            print('请确认 Edge 个人资料与 X 登录状态，或使用导出文件后在软件设置中导入。')
            return 2
        count = save_cookies(result['cookies'], root / 'cookies.txt')
        print(f'成功：已保存 {count} 条 X 登录记录到本解压目录。')
        print('可以直接回到这份资料库点击补新，无需再次导入。')
        print('如果手动加载了“TweetArchive · 本机登录导出”，请在扩展页将它移除或关闭。')
        print('本工具没有关闭 Edge；登录文件内容不要录屏或分享。')
        return 0
    finally:
        server.shutdown()
        server.server_close()
        # Keep the installable folder, but remove the expired relay endpoint.
        make_extension(extension)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('\n已取消。')
        raise SystemExit(130)
    except Exception:
        print('刷新未完成；请检查目录写入权限后重试。原登录文件未被覆盖时可以继续使用。')
        raise SystemExit(1)
