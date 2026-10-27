import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {QQSocialService} from '../social-service.js';

const timeout=(promise,ms=2500)=>Promise.race([promise,new Promise((_,reject)=>setTimeout(()=>reject(Error('timed out')),ms))]);
test('OneBot -> WeChatAgent engine -> preview, with group and private authorization',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qq-agent-engine-'));const events=[],calls=[];
 const cfg={groups:['333'],private:['222'],persona:'默认人格',personas:{'qq:group:333':'群人格'},dryRun:true};
 const service=new QQSocialService({stateDir:dir,accountId:'111',onebot:{host:'127.0.0.1',port:0,path:'/ws',timeoutMs:1000},allowInsecureLocalForTests:true,settings:()=>cfg,
  decide:async(key,prompt,metadata)=>{calls.push({key,prompt,persona:metadata.persona});return 'RESPOND: 收到啦';},onEvent:e=>events.push(e)});
 let ws;
 try{
  await service.start();ws=new WebSocket(`ws://127.0.0.1:${service.adapter.server.server.address().port}/ws`);
  await timeout(new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject}));
  const base={post_type:'message',message_type:'group',self_id:111,user_id:222,group_id:333,time:Math.floor(Date.now()/1000),message_id:1,message:[{type:'at',data:{qq:'111'}},{type:'text',data:{text:'你好'}}]};
  ws.send(JSON.stringify({...base,group_id:444}));
  ws.send(JSON.stringify({...base,message_id:2,message:[{type:'text',data:{text:'普通消息'}}]}));
  ws.send(JSON.stringify({...base,message_id:3}));
  await timeout(new Promise((resolve,reject)=>{let n=0;const t=setInterval(()=>{if(events.some(e=>e.type==='preview')){clearInterval(t);resolve()}else if(++n>40){clearInterval(t);reject(Error('preview missing: '+JSON.stringify(events)))}},50)}));
  assert.equal(calls.length,1);assert.equal(calls[0].key,'qq:group:333');assert.equal(calls[0].persona,'群人格');assert.match(calls[0].prompt,/QQ群/);assert.equal(events.find(e=>e.type==='preview').text,'收到啦');
  ws.send(JSON.stringify({...base,message_type:'private',message_id:4,message:[{type:'text',data:{text:'私聊消息'}}]}));
  await timeout(new Promise((resolve,reject)=>{let n=0;const t=setInterval(()=>{if(events.filter(e=>e.type==='preview').length===2){clearInterval(t);resolve()}else if(++n>40){clearInterval(t);reject(Error('private preview missing: '+JSON.stringify(events)))}},50)}));
  assert.equal(calls[1].key,'qq:private:222');assert.equal(calls[1].persona,'默认人格');
 }finally{ws?.close();await service.stop();fs.rmSync(dir,{recursive:true,force:true})}
});
test('disconnect during model generation cannot send after reconnection',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qq-agent-offline-'));let resolveModel,startedModel;const started=new Promise(r=>startedModel=r);const events=[];
 const cfg={groups:['333'],private:[],dryRun:false};
 const service=new QQSocialService({stateDir:dir,accountId:'111',onebot:{host:'127.0.0.1',port:0,path:'/ws',timeoutMs:1000},allowInsecureLocalForTests:true,settings:()=>cfg,
  decide:async()=>{startedModel();return await new Promise(r=>resolveModel=r)},onEvent:e=>events.push(e)});
 let first,second;
 try{
  await service.start();const url=`ws://127.0.0.1:${service.adapter.server.server.address().port}/ws`;
  first=new WebSocket(url);await timeout(new Promise((r,j)=>{first.onopen=r;first.onerror=j}));
  first.send(JSON.stringify({post_type:'message',message_type:'group',self_id:111,user_id:222,group_id:333,message_id:9,time:Math.floor(Date.now()/1000),message:[{type:'at',data:{qq:'111'}},{type:'text',data:{text:'你好'}}]}));
  await timeout(started);await timeout(new Promise(r=>{first.onclose=r;first.close()}));
  second=new WebSocket(url);await timeout(new Promise((r,j)=>{second.onopen=r;second.onerror=j}));let sent=false;second.onmessage=()=>sent=true;
  resolveModel('RESPOND: 回复');await new Promise(r=>setTimeout(r,250));assert.equal(sent,false);assert.equal(events.some(e=>e.type==='submitted'),false);
 }finally{first?.close();second?.close();await service.stop();fs.rmSync(dir,{recursive:true,force:true})}
});
test('successful OneBot action is reported as submitted, not delivery proof',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qq-agent-send-'));const events=[];
 const service=new QQSocialService({stateDir:dir,accountId:'111',onebot:{host:'127.0.0.1',port:0,path:'/ws',timeoutMs:1000},allowInsecureLocalForTests:true,
  settings:()=>({accountId:'111',groups:['333'],private:[],dryRun:false}),decide:async()=> 'RESPOND: 收到',onEvent:e=>events.push(e)});
 let ws;try{
  await service.start();ws=new WebSocket(`ws://127.0.0.1:${service.adapter.server.server.address().port}/ws`);await timeout(new Promise((r,j)=>{ws.onopen=r;ws.onerror=j}));
  let action;ws.onmessage=e=>{action=JSON.parse(e.data);ws.send(JSON.stringify({echo:action.echo,status:'ok',retcode:0,data:{message_id:55}}))};
  ws.send(JSON.stringify({post_type:'message',message_type:'group',self_id:111,user_id:222,group_id:333,message_id:12,time:Math.floor(Date.now()/1000),message:[{type:'at',data:{qq:'111'}},{type:'text',data:{text:'你好'}}]}));
  await timeout(new Promise((resolve,reject)=>{let n=0;const t=setInterval(()=>{if(events.some(e=>e.type==='submitted')){clearInterval(t);resolve()}else if(++n>40){clearInterval(t);reject(Error(JSON.stringify(events)))}},50)}));
  assert.equal(action.action,'send_group_msg');assert.equal(action.params.group_id,333);
  const rows=service.buffer.recent('qq:group:333',10);assert.equal(rows.find(row=>row.outgoing).delivery_status,'unconfirmed');
 }finally{ws?.close();await service.stop();fs.rmSync(dir,{recursive:true,force:true})}
});
