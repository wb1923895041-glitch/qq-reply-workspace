import test from 'node:test';
import assert from 'node:assert/strict';
import {QQOneBotAdapter,normalizeQQ} from '../qq-onebot-adapter.js';
const event={post_type:'message',message_type:'group',self_id:111,user_id:222,group_id:333,message_id:1,time:123,message:[{type:'at',data:{qq:'111'}},{type:'text',data:{text:' 你好 '}}]};
test('normalize group mention and account identity',()=>{const m=normalizeQQ(event,'111');assert.equal(m.text,'你好');assert.equal(m.mentioned,true);assert.equal(m.conversation_id,'333');assert.equal(normalizeQQ(event,'112'),null)});
test('private messages and unsupported segments are explicit',()=>{const m=normalizeQQ({...event,message_type:'private',message:[{type:'image',data:{file:'abc'}}]},'111');assert.equal(m.kind,'private');assert.equal(m.unsupported,true);assert.equal(m.conversation_id,'222')});
test('duplicate suppression includes conversation',()=>{const a=new QQOneBotAdapter({accountId:'111',allowInsecureLocalForTests:true});const messages=[];a.on('message',m=>messages.push(m));a.receive(event);a.receive(event);a.receive({...event,group_id:444});assert.equal(messages.length,2)});
test('send text builds OneBot action and propagates failure',async()=>{const a=new QQOneBotAdapter({accountId:'111',allowInsecureLocalForTests:true});let call;a.server.action=async(action,params)=>{call={action,params};return {data:{message_id:42}}};assert.deepEqual(await a.sendText({kind:'group',target:'333',text:' hello '}),{accepted:true,messageId:42});assert.equal(call.action,'send_group_msg');assert.equal(call.params.group_id,333);a.server.action=async()=>{throw Error('failure')};await assert.rejects(a.sendText({kind:'private',target:'222',text:'hello'}),/failure/);await assert.rejects(a.sendText({kind:'group',target:'invalid',text:'hello'}),/Invalid/)});
test('reverse WebSocket receives QQ events and exchanges send acknowledgements',async()=>{
 const a=new QQOneBotAdapter({accountId:'111',allowInsecureLocalForTests:true,server:{host:'127.0.0.1',port:0,path:'/ws',timeoutMs:1000}});
 await a.start();let ws;
 try{
  const port=a.server.server.address().port;ws=new WebSocket(`ws://127.0.0.1:${port}/ws`);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
  const received=new Promise(resolve=>a.once('message',resolve));
  ws.send(JSON.stringify(event));assert.equal((await received).text,'你好');
  ws.onmessage=e=>{const action=JSON.parse(e.data);ws.send(JSON.stringify({status:'ok',retcode:0,data:{message_id:44},echo:action.echo}))};
  assert.deepEqual(await a.sendText({kind:'group',target:'333',text:'测试'}),{accepted:true,messageId:44});
 }finally{ws?.close();await a.stop()}
});

test('listener requires an authentication token by default',()=>{assert.throws(()=>new QQOneBotAdapter({accountId:'111'}),/token/)});
