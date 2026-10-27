import asyncio
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch
from websockets.asyncio.client import connect
from bridge import Bridge

class OneBotIntegrationTest(unittest.TestCase):
    def test_group_at_dry_run_and_send(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'QQ_ONEBOT_TOKEN':'test-token'}):
            cfg = {'group_id':'12345','qq_id':'999','model':'test','key_env':'TEST_KEY','persona':'','dry_run':True}
            bridge = Bridge(d, lambda:cfg.copy())
            with patch.object(bridge, '_generate', return_value='测试回复'):
                bridge.start()
                try: asyncio.run(self.exercise(bridge,cfg))
                finally: bridge.stop()
            self.assertFalse(bridge.running)
            self.assertEqual([x['outcome'] for x in bridge.history()], ['accepted','preview'])

    async def exercise(self,bridge,cfg):
        uri='ws://127.0.0.1:18766/onebot'
        async with connect(uri, additional_headers={'Authorization':'Bearer test-token'}) as ws:
            event={'post_type':'message','message_type':'group','group_id':12345,'self_id':999,'user_id':123,'message_id':1,'time':int(time.time()),'message':[{'type':'at','data':{'qq':'999'}},{'type':'text','data':{'text':'你好'}}]}
            await ws.send(json.dumps(event))
            for _ in range(50):
                if len(bridge.history())==1: break
                await asyncio.sleep(.05)
            self.assertEqual(bridge.history()[0]['outcome'],'preview')
            await ws.send(json.dumps(event))
            event['message_id']=2; event['group_id']=22222
            await ws.send(json.dumps(event))
            await asyncio.sleep(.1)
            self.assertEqual(len(bridge.history()),1)
            cfg['dry_run']=False; event['group_id']=12345;event['message_id']=3
            await ws.send(json.dumps(event))
            action=json.loads(await asyncio.wait_for(ws.recv(),3))
            self.assertEqual(action['action'],'send_group_msg')
            self.assertEqual(action['params']['group_id'],12345)
            await ws.send(json.dumps({'echo':action['echo'],'status':'ok','retcode':0,'data':{'message_id':456}}))
            for _ in range(50):
                if len(bridge.history())==2: break
                await asyncio.sleep(.05)
            self.assertEqual(bridge.history()[0]['outcome'],'accepted')

if __name__=='__main__': unittest.main()
