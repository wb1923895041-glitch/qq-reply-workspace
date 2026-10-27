import asyncio
import json
import os
import socket
import tempfile
import threading
import time
import urllib.request
import urllib.error
import unittest
from pathlib import Path
from unittest.mock import patch
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus
import app
from model_client import ModelResult
from node_bridge import NodeBridge
from workspace import Workspace

class WorkbenchEngineTest(unittest.TestCase):
    def test_console_worker_model_and_history(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'QQ_ONEBOT_TOKEN':'t'*32}):
            root=Path(directory); data=root/'data';data.mkdir()
            cfg={'qq_id':'111','model':'fake','key_env':'FAKE','persona':'默认','dry_run':True}
            (data/'config.json').write_text(json.dumps(cfg),encoding='utf-8')
            workspace=Workspace(root);p=workspace.save_persona({'name':'友好','prompt':'温暖'})
            workspace.save_chat({'id':'333','name':'测试','persona_id':p['id'],'enabled':True})
            workspace.save_chat({'id':'222','kind':'private','name':'好友','persona_id':'','enabled':True})
            token='internal-token'
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0)); ws_port=sock.getsockname()[1]
            http=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
            bridge=NodeBridge(root,lambda:cfg,workspace,token,internal_port=http.server_address[1],ws_port=ws_port)
            fake=ModelResult(text='收到啦',elapsed_ms=1)
            with patch.object(app,'load_config',return_value=cfg),patch.object(app,'TOKEN',token),patch.object(app,'bridge',bridge),patch.object(app,'generate_reply',return_value=fake) as model:
                thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
                try:
                    bridge.start()
                    request=urllib.request.Request(f'http://127.0.0.1:{http.server_address[1]}/api/config',data=json.dumps({**cfg,'dry_run':False}).encode(),headers={'Content-Type':'application/json','X-Local-Token':token},method='POST')
                    with self.assertRaises(urllib.error.HTTPError) as denied:urllib.request.urlopen(request)
                    self.assertEqual(denied.exception.code,400)
                    asyncio.run(self.exercise(bridge));self.assertTrue(model.called)
                    self.assertEqual(bridge.history()[0]['reply'],'收到啦')
                    self.assertEqual(bridge.history()[0]['outcome'],'preview')
                    args,kwargs=model.call_args;self.assertIn('QQ好友',args[0]);self.assertEqual(args[1]['chat_kind'],'private')
                    first_args=model.call_args_list[0].args;self.assertIn('QQ群',first_args[0]);self.assertEqual(first_args[1]['persona'],'温暖')
                finally:
                    bridge.stop();http.shutdown();http.server_close();thread.join()
            self.assertFalse(bridge.status()['running'])
    async def exercise(self,bridge):
        async with connect(f'ws://127.0.0.1:{bridge.ws_port}/onebot',additional_headers={'Authorization':'Bearer '+'t'*32}) as ws:
            request=json.loads(await asyncio.wait_for(ws.recv(),2))
            self.assertEqual(request['action'],'get_login_info')
            await ws.send(json.dumps({'echo':request['echo'],'status':'ok','retcode':0,'data':{'user_id':111}}))
            for _ in range(40):
                if bridge.status()['connected']:break
                await asyncio.sleep(.05)
            self.assertTrue(bridge.status()['connected'])
            event={'post_type':'message','message_type':'group','group_id':333,'self_id':111,'user_id':222,'message_id':1,'time':int(time.time()),'message':[{'type':'at','data':{'qq':'111'}},{'type':'text','data':{'text':'你好'}}]}
            await ws.send(json.dumps(event))
            for _ in range(100):
                if bridge.history():break
                await asyncio.sleep(.05)
            self.assertEqual(len(bridge.history()),1)
            private={**event,'message_type':'private','message_id':2,'message':[{'type':'text','data':{'text':'私聊你好'}}]}
            await ws.send(json.dumps(private))
            for _ in range(100):
                if len(bridge.history())==2:break
                await asyncio.sleep(.05)
            self.assertEqual(len(bridge.history()),2)
            self.assertEqual(bridge.history()[0]['kind'],'private')
            with self.assertRaises(TimeoutError):await asyncio.wait_for(ws.recv(),.15)

    def test_mismatched_qq_never_becomes_connected(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'QQ_ONEBOT_TOKEN':'t'*32}):
            root=Path(directory); data=root/'data';data.mkdir()
            cfg={'qq_id':'111','model':'fake','key_env':'FAKE','persona':'','dry_run':True}
            (data/'config.json').write_text(json.dumps(cfg),encoding='utf-8')
            workspace=Workspace(root);workspace.save_chat({'id':'333','name':'测试','persona_id':'','enabled':True})
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0)); ws_port=sock.getsockname()[1]
            bridge=NodeBridge(root,lambda:cfg,workspace,'local-token',internal_port=18765,ws_port=ws_port)
            try:
                bridge.start();asyncio.run(self.wrong_account(bridge))
            finally:bridge.stop()
    async def wrong_account(self,bridge):
        with self.assertRaises(InvalidStatus):
            async with connect(f'ws://127.0.0.1:{bridge.ws_port}/onebot',additional_headers={'Authorization':'Bearer wrong-token'}):pass
        async with connect(f'ws://127.0.0.1:{bridge.ws_port}/onebot',additional_headers={'Authorization':'Bearer '+'t'*32}) as ws:
            request=json.loads(await asyncio.wait_for(ws.recv(),2))
            self.assertEqual(request['action'],'get_login_info')
            await ws.send(json.dumps({'echo':request['echo'],'status':'ok','retcode':0,'data':{'user_id':999}}))
            for _ in range(50):
                if bridge.status()['error']:break
                await asyncio.sleep(.05)
            self.assertFalse(bridge.status()['connected'])
            self.assertIn('账号',bridge.status()['error'])

if __name__=='__main__':unittest.main()
