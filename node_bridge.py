"""Host the QQ social engine as an isolated child process owned by this console."""
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from model_client import load_api_key, ModelError

class NodeBridge:
    def __init__(self,root,load_config,workspace,internal_token,internal_port=18765,ws_port=18766):
        self.root=Path(root);self.load_config=load_config;self.workspace=workspace;self.internal_token=internal_token;self.internal_port=internal_port;self.ws_port=ws_port
        self.process=None;self.ready=threading.Event();self.connected=False;self.last_error='';self.lock=threading.RLock()
    def status(self):
        with self.lock:
            alive=bool(self.process and self.process.poll() is None)
            return {'running':alive and self.ready.is_set(),'connected':alive and self.connected,'self_id':'','error':self.last_error}
    def start(self):
        with self.lock:
            if self.process and self.process.poll() is None: raise ValueError('服务已经运行')
            cfg=self.load_config()
            if not cfg['qq_id'].isdigit(): raise ValueError('请先保存本人的 QQ 账号')
            if not any(c.get('enabled') for c in self.workspace.read()['chats']): raise ValueError('请先添加并启用目标群聊')
            try: onebot=load_api_key('QQ_ONEBOT_TOKEN')
            except ModelError: raise ValueError('请先通过设置连接令牌入口配置 QQ_ONEBOT_TOKEN')
            if len(onebot)<24: raise ValueError('QQ 连接令牌至少需要 24 个字符')
            node=shutil.which('node')
            if not node: raise ValueError('未找到 Node.js，请安装 Node.js 22 或以上版本')
            env=dict(os.environ,QQ_AGENT_ROOT=str(self.root),QQ_ONEBOT_TOKEN=onebot,QQ_AGENT_INTERNAL_TOKEN=self.internal_token,QQ_AGENT_INTERNAL_PORT=str(self.internal_port),QQ_AGENT_WS_PORT=str(self.ws_port))
            self.ready.clear();self.connected=False;self.last_error=''
            self.process=subprocess.Popen([node,str(Path(__file__).resolve().parent/'qq-platform'/'worker.js')],cwd=self.root,env=env,
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            process=self.process
            threading.Thread(target=self._stdout,args=(process,),daemon=True).start()
            threading.Thread(target=self._stderr,args=(process,),daemon=True).start()
        if not self.ready.wait(8):
            self.stop();raise ValueError(self.last_error or 'QQ 社交引擎启动超时')
        if process.poll() is not None: raise ValueError(self.last_error or 'QQ 社交引擎未启动')
    def _stdout(self,process):
        for line in process.stdout:
            try: item=json.loads(line)
            except ValueError: continue
            if not isinstance(item,dict):continue
            with self.lock:
                if self.process is not process:break
                if item.get('type')=='ready':self.ready.set()
                elif item.get('type')=='connection':self.connected=item.get('connected') is True
                elif item.get('type') in ('error','send_unconfirmed'):self.last_error='QQ 通道异常或发送结果未确认，请检查连接'
                if item.get('type') in ('preview','submitted','send_unconfirmed'):
                    self._append_event(item)
        with self.lock:
            if self.process is process:self.connected=False
    def _stderr(self,process):
        # Do not persist child output: it may contain local paths or private information.
        for _ in process.stderr:
            with self.lock:
                if self.process is process:self.last_error='QQ 社交引擎发生错误，请检查配置和 Node.js 版本'
    def stop(self):
        with self.lock:
            process=self.process
            if not process or process.poll() is not None:self.connected=False;return
            try:process.stdin.write('{"action":"stop"}\n');process.stdin.flush()
            except (OSError,ValueError):pass
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:raise ValueError('停止服务超时，请关闭工作台')
        with self.lock:self.connected=False
    def _append_event(self,item):
        fields=('type','account','kind','target','incoming','text','time')
        record={k:item.get(k) for k in fields}
        path=self.root/'data'/'engine-events.jsonl';path.parent.mkdir(exist_ok=True)
        try:
            with path.open('a',encoding='utf-8') as handle:handle.write(json.dumps(record,ensure_ascii=False)+'\n')
        except OSError:self.last_error='无法保存聊天记录'
    def history(self):
        account=self.load_config().get('qq_id','');file=self.root/'data'/'engine-events.jsonl'
        if not account.isdigit() or not file.exists():return []
        records=[]
        with file.open(encoding='utf-8') as handle:
            for line in handle:
                try:item=json.loads(line)
                except ValueError:continue
                if item.get('account')!=account:continue
                records.append({'time':item.get('time',0),'group_id':item.get('target',''),'incoming':item.get('incoming',''),'reply':item.get('text',''),'outcome':{'preview':'preview','submitted':'accepted','send_unconfirmed':'uncertain'}.get(item.get('type'),'uncertain')})
        return list(reversed(records[-30:]))
