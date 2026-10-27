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
from node_bridge import NodeBridge
from workspace import Workspace

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
CONFIG = DATA / 'config.json'
DEFAULT = {'group': '', 'mention': '', 'model': 'deepseek-v4-pro', 'key_env': 'DEEPSEEK_API_KEY', 'group_id': '', 'qq_id': '', 'persona': '自然、友善，简短回应。', 'dry_run': True}
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.Lock()

def load_config():
    if not CONFIG.exists(): return DEFAULT.copy()
    try:
        data = json.loads(CONFIG.read_text(encoding='utf-8'))
        return {k: (data.get(k, v) if isinstance(data.get(k, v), bool) else v) if k == 'dry_run' else str(data.get(k, v)) for k, v in DEFAULT.items()}
    except (OSError, ValueError, TypeError):
        raise ValueError('配置文件无法读取，请检查 data/config.json')

def save_config(data):
    cfg = {}
    for k, default in DEFAULT.items():
        value = data.get(k, default)
        if k == 'dry_run':
            if not isinstance(value, bool): raise ValueError('演练开关不合法')
            cfg[k] = value
        else:
            if not isinstance(value, str) or len(value) > (1500 if k == 'persona' else 100): raise ValueError('配置字段不合法')
            cfg[k] = value.strip()
    if cfg['qq_id'] and not re.fullmatch(r'[0-9]{1,16}', cfg['qq_id']): raise ValueError('QQ 账号必须为数字')
    if cfg['group_id'] and not re.fullmatch(r'[0-9]{1,16}', cfg['group_id']): raise ValueError('群号必须为数字')
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

workspace = Workspace(ROOT)
# Upgrade a previously saved single-group configuration only when no workspace exists.
if not workspace.path.exists():
    previous = load_config()
    if previous['group_id'].isdigit():
        workspace.save_chat({'id':previous['group_id'],'name':previous['group'],'persona_id':'','enabled':True})
bridge = NodeBridge(ROOT, load_config, workspace, TOKEN)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def respond(self, status, body, kind='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status); self.send_header('Content-Type', kind); self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store'); self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/status':
            try: self.respond(200, {'qq': qq_status(), 'config': load_config(), 'bridge': bridge.status()})
            except ValueError as e: self.respond(500, {'error': str(e)})
            return
        if path == '/api/workspace':
            try: self.respond(200, workspace.read())
            except (OSError, ValueError): self.respond(500, {'error':'无法读取工作区'})
            return
        if path == '/api/history':
            try: self.respond(200, {'items': bridge.history()})
            except Exception: self.respond(500, {'error':'无法读取历史记录'})
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
            if length <= 0 or length > (65536 if self.path == '/api/engine/decide' else 8192): raise ValueError('请求大小不合法')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict): raise ValueError('请求格式不合法')
            if self.path == '/api/chat/save': self.respond(200, {'chat':workspace.save_chat(data)}); return
            if self.path == '/api/chat/delete': workspace.delete_chat(data); self.respond(200, {'ok':True}); return
            if self.path == '/api/persona/save': self.respond(200, {'persona':workspace.save_persona(data)}); return
            if self.path == '/api/persona/delete': workspace.delete_persona(data); self.respond(200, {'ok':True}); return
            if self.path == '/api/config':
                old = load_config()
                if bridge.status()['running'] and (data.get('dry_run', old['dry_run']) != old['dry_run'] or data.get('qq_id', old['qq_id']) != old['qq_id']): raise ValueError('请先停止服务，再切换账号或演练模式')
                self.respond(200, {'config': save_config(data)}); return
            if self.path == '/api/start': bridge.start(); self.respond(200, {'bridge':bridge.status()}); return
            if self.path == '/api/stop': bridge.stop(); self.respond(200, {'bridge':bridge.status()}); return
            if self.path == '/api/engine/decide':
                cfg = load_config(); text = data.get('text', ''); persona = data.get('persona', '')
                if not isinstance(text,str) or not text.strip() or len(text)>32000 or not isinstance(persona,str) or len(persona)>1500: raise ValueError('模型请求不合法')
                model = {'api_url':'https://api.deepseek.com/v1/chat/completions','model':cfg['model'],'api_key_env':cfg['key_env'],'timeout_seconds':40,'persona':persona}
                result = generate_reply(text,model,retries=0); self.respond(200,{'reply':result.text}); return
            if self.path == '/api/preview':
                cfg = load_config(); text = data.get('text', '')
                if not isinstance(text, str) or not text.strip() or len(text) > 1000: raise ValueError('请输入不超过 1000 字的消息')
                model = {'api_url':'https://api.deepseek.com/v1/chat/completions', 'model':cfg['model'], 'api_key_env':cfg['key_env'], 'timeout_seconds':40, 'persona':cfg['persona']}
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
    finally:
        bridge.stop()
        server.server_close()
if __name__ == '__main__': main()
