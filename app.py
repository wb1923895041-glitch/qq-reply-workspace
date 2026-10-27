import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from model_client import generate_reply, ModelError

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
CONFIG = DATA / 'config.json'
DEFAULT = {'group': '', 'mention': '', 'model': 'deepseek-v4-pro', 'key_env': 'DEEPSEEK_API_KEY'}
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.Lock()

def load_config():
    if not CONFIG.exists(): return DEFAULT.copy()
    try:
        data = json.loads(CONFIG.read_text(encoding='utf-8'))
        return {k: str(data.get(k, v)) for k, v in DEFAULT.items()}
    except (OSError, ValueError, TypeError):
        raise ValueError('配置文件无法读取，请检查 data/config.json')

def save_config(data):
    cfg = {}
    for k, default in DEFAULT.items():
        value = data.get(k, default)
        if not isinstance(value, str) or len(value) > 100: raise ValueError('配置字段不合法')
        cfg[k] = value.strip()
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', cfg['key_env']): raise ValueError('环境变量名不合法')
    if not re.fullmatch(r'[A-Za-z0-9._-]+', cfg['model']): raise ValueError('模型名不合法')
    with LOCK:
        DATA.mkdir(exist_ok=True)
        temp = CONFIG.with_suffix('.tmp')
        temp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, CONFIG)
    return cfg

def mentioned(text, name):
    return bool(name and re.search(r'[@＠]\s*' + re.escape(name) + r'(?![\w])', text, re.I))

def qq_status():
    if sys.platform != 'win32': return {'found': False, 'message': 'QQ 窗口检测仅支持 Windows'}
    u = ctypes.WinDLL('user32', use_last_error=True)
    cbtype = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    u.EnumWindows.argtypes = [cbtype, wt.LPARAM]
    u.GetWindowTextLengthW.argtypes = [wt.HWND]
    u.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    u.IsWindowVisible.argtypes = [wt.HWND]
    u.IsIconic.argtypes = [wt.HWND]
    found = []
    @cbtype
    def visit(hwnd, _):
        n = u.GetWindowTextLengthW(hwnd)
        b = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, b, n + 1)
        if b.value == 'QQ' and u.IsWindowVisible(hwnd): found.append(bool(u.IsIconic(hwnd)))
        return True
    u.EnumWindows(visit, 0)
    return {'found': bool(found), 'minimized': all(found) if found else False,
            'message': ('窗口已最小化' if all(found) else '已发现 QQ 窗口') if found else '未发现 QQ 窗口'}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def respond(self, status, body, kind='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status); self.send_header('Content-Type', kind); self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store'); self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/status':
            try: self.respond(200, {'qq': qq_status(), 'config': load_config(), 'adapter': 'not_implemented'})
            except ValueError as e: self.respond(500, {'error': str(e)})
            return
        files = {'/': ('index.html','text/html; charset=utf-8'), '/app.js': ('app.js','application/javascript; charset=utf-8'), '/style.css': ('style.css','text/css; charset=utf-8')}
        if path not in files: self.respond(404, {'error':'未找到'}); return
        name, mime = files[path]; data = (ROOT / 'web' / name).read_bytes()
        if path == '/': data = data.replace(b'__TOKEN__', TOKEN.encode())
        self.respond(200, data, mime)
    def do_POST(self):
        if self.headers.get('X-Local-Token') != TOKEN: self.respond(403, {'error':'请求验证失败'}); return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > 8192: raise ValueError('请求大小不合法')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict): raise ValueError('请求格式不合法')
            if self.path == '/api/config': self.respond(200, {'config': save_config(data)}); return
            if self.path == '/api/preview':
                cfg = load_config(); text = data.get('text', '')
                if not isinstance(text, str) or not text.strip() or len(text) > 1000: raise ValueError('请输入不超过 1000 字的消息')
                if not cfg['mention']: raise ValueError('请先保存被 @ 的昵称')
                if not mentioned(text, cfg['mention']): self.respond(200, {'matched': False}); return
                model = {'api_url':'https://api.deepseek.com/v1/chat/completions', 'model':cfg['model'], 'api_key_env':cfg['key_env'], 'timeout_seconds':40, 'identity_mode':'disclose_on_ask'}
                result = generate_reply(text, model, retries=0)
                self.respond(200, {'matched':True, 'reply':result.text, 'elapsed_ms':result.elapsed_ms}); return
            self.respond(404, {'error':'未找到'})
        except (ValueError, TypeError, json.JSONDecodeError, OSError, ModelError) as e: self.respond(400, {'error':str(e)})

def main():
    server = ThreadingHTTPServer(('127.0.0.1', 18765), Handler)
    print('QQ 控制台运行中：http://127.0.0.1:18765  按 Ctrl+C 停止', flush=True)
    if '--no-browser' not in sys.argv: webbrowser.open('http://127.0.0.1:18765')
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
if __name__ == '__main__': main()
