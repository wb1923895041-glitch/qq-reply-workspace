"""Local workspace data. All files remain private and out of version control."""
import json
import os
import re
import threading
import uuid
from pathlib import Path

class Workspace:
    def __init__(self,root):
        self.path=Path(root)/'data'/'workspace.json'; self.lock=threading.RLock()
    def read(self):
        with self.lock:
            if not self.path.exists(): return {'chats':[], 'personas':[]}
            result=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(result,dict) or not isinstance(result.get('chats'),list) or not isinstance(result.get('personas'),list): raise ValueError('工作区文件格式错误')
            return result
    def write(self,data):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,self.path)
    def save_chat(self,body):
        group=str(body.get('id','')).strip(); name=str(body.get('name','')).strip(); persona=str(body.get('persona_id','')).strip(); kind=str(body.get('kind','group'))
        if kind not in ('group','private'): raise ValueError('聊天类型无效')
        if not re.fullmatch(r'[1-9][0-9]{0,15}',group) or int(group)>9007199254740991: raise ValueError('请输入有效的 QQ 号或群号')
        if len(name)>80: raise ValueError('聊天名称不能超过 80 字')
        if not isinstance(body.get('enabled'),bool): raise ValueError('启用状态无效')
        with self.lock:
            data=self.read()
            if persona and not any(p['id']==persona for p in data['personas']): raise ValueError('人格不存在')
            chat={'id':group,'kind':kind,'name':name,'persona_id':persona,'enabled':body['enabled']}
            data['chats']=[x for x in data['chats'] if (x['id'],x.get('kind','group'))!=(group,kind)]+[chat];self.write(data)
            return chat
    def delete_chat(self,body):
        with self.lock:
            data=self.read(); kind=str(body.get('kind','group'))
            if kind not in ('group','private'): raise ValueError('聊天类型无效')
            data['chats']=[x for x in data['chats'] if (x['id'],x.get('kind','group'))!=(str(body.get('id','')),kind)];self.write(data)
    def save_persona(self,body):
        pid=str(body.get('id','')).strip();name=str(body.get('name','')).strip();prompt=str(body.get('prompt','')).strip()
        if not name or len(name)>60 or not prompt or len(prompt)>1500: raise ValueError('请填写人格名称及不超过 1500 字的描述')
        if pid and not re.fullmatch(r'[0-9a-f]{32}',pid): raise ValueError('人格 ID 无效')
        with self.lock:
            data=self.read()
            if pid and not any(x['id']==pid for x in data['personas']): raise ValueError('人格不存在')
            item={'id':pid or uuid.uuid4().hex,'name':name,'prompt':prompt}
            data['personas']=[x for x in data['personas'] if x['id']!=item['id']]+[item];self.write(data)
            return item
    def delete_persona(self,body):
        pid=str(body.get('id',''))
        with self.lock:
            data=self.read()
            if any(x['persona_id']==pid for x in data['chats']): raise ValueError('人格仍被聊天使用，请先解除绑定')
            data['personas']=[x for x in data['personas'] if x['id']!=pid];self.write(data)
    def resolve(self,group,config):
        data=self.read(); chat=next((x for x in data['chats'] if x['id']==group and x.get('kind','group')=='group' and x['enabled']),None)
        if chat is None: return None
        result=dict(config);result['group_id']=group
        persona=next((p for p in data['personas'] if p['id']==chat['persona_id']),None)
        if persona: result['persona']=persona['prompt']
        return result
