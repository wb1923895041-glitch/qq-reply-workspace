import asyncio
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch
from websockets.asyncio.client import connect
from bridge import Bridge
from workspace import Workspace

class MultiGroupTest(unittest.TestCase):
    def test_only_enabled_group_and_persona_reach_model(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'QQ_ONEBOT_TOKEN':'test-token'}):
            w=Workspace(d);p=w.save_persona({'name':'A','prompt':'persona A'})
            w.save_chat({'id':'111','name':'A','persona_id':p['id'],'enabled':True})
            w.save_chat({'id':'222','name':'B','persona_id':'','enabled':False})
            cfg={'qq_id':'999','group_id':'','persona':'default','model':'test','key_env':'x','dry_run':True}
            bridge=Bridge(d,lambda:cfg.copy(),w.resolve,lambda c:[x['id'] for x in w.read()['chats'] if x['enabled']])
            calls=[]
            def generate(sid,group,text,config): calls.append((group,config['persona']));return 'ok'
            with patch.object(bridge,'_generate',side_effect=generate):
                bridge.start()
                try: asyncio.run(self.exercise(bridge,w))
                finally: bridge.stop()
            self.assertEqual(calls,[('111','persona A'),('222','default')])
    async def exercise(self,bridge,w):
        async with connect('ws://127.0.0.1:18766/onebot',additional_headers={'Authorization':'Bearer test-token'}) as ws:
            msg={'post_type':'message','message_type':'group','group_id':222,'self_id':999,'user_id':123,'message_id':1,'time':int(time.time()),'message':[{'type':'at','data':{'qq':'999'}},{'type':'text','data':{'text':'hi'}}]}
            await ws.send(json.dumps(msg)); msg.update(group_id=111,message_id=2);await ws.send(json.dumps(msg))
            for _ in range(50):
                if len(bridge.history())==1: break
                await asyncio.sleep(.05)
            self.assertEqual(len(bridge.history()),1)
            w.save_chat({'id':'222','name':'B','persona_id':'','enabled':True});msg.update(group_id=222,message_id=3);await ws.send(json.dumps(msg))
            for _ in range(50):
                if len(bridge.history())==2: break
                await asyncio.sleep(.05)
            self.assertEqual(len(bridge.history()),2)
