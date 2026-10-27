"""QQ OneBot v11 reverse WebSocket listener. Explicit allowlist and dry-run by default."""
import asyncio
from contextlib import contextmanager
import hmac
import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed
from model_client import generate_reply, load_api_key, ModelError

class Bridge:
    def __init__(self, root, load_config):
        self.root, self.load_config = Path(root), load_config
        self.thread = self.loop = self.server = self.connection = None
        self.running = False
        self.connected = False
        self.self_id = ''
        self.last_error = ''
        self.start_time = 0
        self.seen = set()
        self.pending = {}
        self.queue = None
        self.lock = threading.Lock()

    def status(self):
        return {'running':self.running,'connected':self.connected,'self_id':self.self_id,'error':self.last_error}

    def start(self):
        if self.thread and self.thread.is_alive(): raise ValueError('服务已经运行')
        cfg = self.load_config()
        if not cfg['qq_id'].isdigit(): raise ValueError('请先保存本人的 QQ 账号')
        if not cfg['group_id'].isdigit(): raise ValueError('请先保存有效的目标群号')
        try: self.token = load_api_key('QQ_ONEBOT_TOKEN')
        except ModelError: raise ValueError('请先使用设置连接令牌入口配置 QQ_ONEBOT_TOKEN')
        self.last_error = ''; self.running = True; self.start_time = time.time(); self.seen.clear()
        ready = threading.Event()
        self.thread = threading.Thread(target=self._thread, args=(ready,), daemon=True); self.thread.start()
        if not ready.wait(5): raise ValueError('监听启动超时')
        if not self.running: raise ValueError(self.last_error or '服务启动失败')

    def _thread(self, ready):
        try:
            asyncio.run(self._run(ready))
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.last_error = str(exc)
        finally:
            self.running = self.connected = False; self.connection = None; self.loop = None; ready.set()

    async def _run(self, ready):
        self.loop = asyncio.get_running_loop(); self.queue = asyncio.Queue(maxsize=50)
        token = self.token
        async def auth(connection, request):
            supplied = request.headers.get('Authorization', '')
            if request.path != '/onebot' or request.headers.get('Origin') or not hmac.compare_digest(supplied, 'Bearer '+token):
                return connection.respond(401, 'Unauthorized\n')
        async with serve(self._handler, '127.0.0.1', 18766, process_request=auth, max_size=1024*1024):
            worker = asyncio.create_task(self._worker()); ready.set()
            try: await asyncio.Future()
            finally:
                worker.cancel()
                try: await worker
                except asyncio.CancelledError: pass

    def stop(self):
        if self.loop and self.running:
            self.loop.call_soon_threadsafe(self._cancel_all)
            self.thread.join(5)
        if self.thread and self.thread.is_alive(): raise ValueError('停止超时，请关闭工作台进程')

    def _cancel_all(self):
        for task in asyncio.all_tasks(self.loop): task.cancel()

    async def _handler(self, ws):
        if self.connection is not None:
            await ws.close(code=1008, reason='already connected'); return
        self.connection = ws; self.connected = True; self.self_id = ''
        try:
            async for raw in ws:
                try: event = json.loads(raw)
                except (ValueError, TypeError): continue
                if not isinstance(event, dict): continue
                echo = event.get('echo')
                if isinstance(echo, str) and echo in self.pending:
                    future = self.pending.pop(echo)
                    if not future.done(): future.set_result(event)
                    continue
                if event.get('post_type') != 'message' or event.get('message_type') != 'group': continue
                cfg = self.load_config(); sid = str(event.get('self_id') or '')
                if not sid or sid != cfg['qq_id'] or (self.self_id and sid != self.self_id):
                    self.last_error = 'QQ 账号不一致，连接已关闭'; await ws.close(); break
                self.self_id = sid
                if str(event.get('group_id')) != cfg['group_id'] or str(event.get('user_id')) == sid: continue
                try: timestamp = int(event.get('time', 0))
                except (ValueError, TypeError): continue
                if timestamp < self.start_time - 5: continue
                mid = str(event.get('message_id') or '')
                if not mid or mid in self.seen: continue
                segments = event.get('message')
                if not isinstance(segments, list): continue
                if any(not isinstance(x,dict) or x.get('type') not in ('text','at') for x in segments): continue
                if not any(x.get('type')=='at' and str((x.get('data') or {}).get('qq','')) == sid for x in segments): continue
                text = ''.join(str((x.get('data') or {}).get('text','')) for x in segments if x.get('type')=='text').strip()
                if not text: continue
                self.seen.add(mid)
                if len(self.seen)>5000: self.seen = {mid}
                try: self.queue.put_nowait((mid, sid, cfg['group_id'], text, ws))
                except asyncio.QueueFull: self.last_error = '消息队列已满，新消息未处理'
        except ConnectionClosed: pass
        finally:
            if self.connection is ws: self.connection = None; self.connected = False
            for future in self.pending.values():
                if not future.done(): future.cancel()
            self.pending.clear()

    @contextmanager
    def _db(self):
        path = self.root/'data'; path.mkdir(exist_ok=True)
        db = sqlite3.connect(path/'history.db')
        db.execute('CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, ts INTEGER, account TEXT, group_id TEXT, incoming TEXT, reply TEXT, outcome TEXT)')
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def history(self):
        with self._db() as db:
            rows = db.execute('SELECT ts,group_id,incoming,reply,outcome FROM messages ORDER BY id DESC LIMIT 30').fetchall()
        return [dict(zip(('time','group_id','incoming','reply','outcome'),row)) for row in rows]

    def _generate(self, sid, group, text, cfg):
        with self._db() as db:
            rows = db.execute('SELECT incoming,reply FROM messages WHERE account=? AND group_id=? AND outcome IN (?,?) ORDER BY id DESC LIMIT 8',(sid,group,'preview','accepted')).fetchall()
        context = []
        for incoming,reply in reversed(rows): context.extend([{'role':'user','content':incoming},{'role':'assistant','content':reply}])
        model = {'api_url':'https://api.deepseek.com/v1/chat/completions','model':cfg['model'],'api_key_env':cfg['key_env'],'timeout_seconds':40,'persona':cfg['persona'],'context':context}
        return generate_reply(text,model).text

    def _record(self,sid,group,text,reply,outcome):
        with self._db() as db: db.execute('INSERT INTO messages(ts,account,group_id,incoming,reply,outcome) VALUES(?,?,?,?,?,?)',(int(time.time()),sid,group,text,reply,outcome))

    async def _worker(self):
        while True:
            mid,sid,group,text,ws = await self.queue.get()
            try:
                cfg = self.load_config()
                if cfg['group_id'] != group or cfg['qq_id'] != sid or self.connection is not ws: continue
                reply = await asyncio.to_thread(self._generate,sid,group,text,cfg)
                cfg2 = self.load_config()
                if cfg2['group_id'] != group or cfg2['qq_id'] != sid or self.connection is not ws: continue
                if cfg['dry_run'] or cfg2['dry_run']:
                    await asyncio.to_thread(self._record,sid,group,text,reply,'preview'); continue
                echo = uuid.uuid4().hex; future = self.loop.create_future(); self.pending[echo] = future
                try:
                    await ws.send(json.dumps({'action':'send_group_msg','params':{'group_id':int(group),'message':[{'type':'text','data':{'text':reply}}]},'echo':echo},ensure_ascii=False))
                    response = await asyncio.wait_for(future,10)
                    outcome = 'accepted' if response.get('status')=='ok' and response.get('retcode')==0 else 'failed'
                except Exception:
                    outcome = 'uncertain'
                finally: self.pending.pop(echo,None)
                await asyncio.to_thread(self._record,sid,group,text,reply,outcome)
                if outcome != 'accepted':
                    self.last_error = '发送失败或结果不确定，已停止服务；请检查 QQ 后手动重启'
                    self.loop.call_soon(self._cancel_all)
            except Exception as exc: self.last_error = '处理失败: '+str(exc)
            finally: self.queue.task_done()
