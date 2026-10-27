/** QQ text routing around the verified WeChatAgent social engine.
 * The host supplies configuration, a model callback and a secure OneBot listener.
 * This component does not enable assistant tools, media or active posting.
 */
import fs from 'node:fs';
import path from 'node:path';
import {QQOneBotAdapter} from './qq-onebot-adapter.js';
import {MessageBuffer} from './vendor/wechatagent/components/qq-bridge/src/core/message-buffer.js';
import {SocialEngine} from './vendor/wechatagent/components/qq-bridge/src/core/social-engine.js';

function allowed(msg,config){
 const entries=msg.kind==='group'?config.groups:config.private;
 return (!config.accountId || config.accountId === msg.self_id) && Array.isArray(entries) && entries.map(String).includes(msg.conversation_id);
}
export class QQSocialService {
 constructor({stateDir,accountId,onebot,settings,decide,onEvent=()=>{},allowInsecureLocalForTests=false}){
  if(typeof settings!=='function'||typeof decide!=='function')throw TypeError('settings and decide callbacks required');
  this.settings=settings;this.decide=decide;this.onEvent=onEvent;this.startedAt=0;this.epoch=0;
  fs.mkdirSync(stateDir,{recursive:true});
  this.buffer=new MessageBuffer(path.join(stateDir,'social-messages.json'));
  // Do not replay old unprocessed inputs after restart.
  this.buffer.skipOfflineInputs({reason:'service_restart'});
  this.adapter=new QQOneBotAdapter({accountId,server:onebot,allowInsecureLocalForTests});
  this.engine=new SocialEngine({buffer:this.buffer, mode:'mention',modeFor:()=> 'mention',
    roleFor:key=>String(this.settings().personas?.[key]??this.settings().persona??''),
    personaNameFor:()=>'',batchMs:3000,minIntervalMs:15000,privateMinIntervalMs:1000,maxPerMinute:3,maxPerTenMinutes:10,
    stickerPolicyFor:()=>({enabled:false,labelCache:false}),maxTextPartsFor:()=>1,
    decide:async(key,prompt,meta)=>{const epoch=this.epoch;let reply;try{reply=await this.decide(key,prompt.replaceAll('微信群','QQ群').replaceAll('微信好友','QQ好友').replaceAll('微信','QQ'),meta)}catch(error){this.onEvent({type:'model_error'});throw error}if(epoch!==this.epoch)throw Error('QQ_CONNECTION_CHANGED');return reply;},
    send:async(message,text)=>{
      const cfg=this.settings();
      if(!allowed(message,cfg)) {const e=new Error('Authorization changed');e.code='NATIVE_SEND_REJECTED';throw e;}
      if(cfg.dryRun!==false){this.onEvent({type:'preview',account:message.self_id,kind:message.kind,target:message.conversation_id,incoming:message.text,text,time:Date.now()/1000});return {delivered:'preview'};}
      try {const result=await this.adapter.sendText({kind:message.kind,target:message.conversation_id,text});
        this.onEvent({type:'submitted',account:message.self_id,kind:message.kind,target:message.conversation_id,incoming:message.text,text,time:Date.now()/1000,messageId:result.messageId});
        // OneBot acknowledgement is not proof of recipient delivery.
        return {delivered:'unconfirmed'};
      } catch(error){
        // Once a request may have been sent, never let the upstream outbox retry it.
        this.onEvent({type:'send_unconfirmed',account:message.self_id,kind:message.kind,target:message.conversation_id,incoming:message.text,text,time:Date.now()/1000});
        const uncertain=new Error('OneBot action timeout: delivery unknown');uncertain.cause=error;throw uncertain;
      }
    },log:line=>this.onEvent({type:'log',line})});
  // Existing outbox items are not replayed on startup: send outcome may be unknown.
  this.engine.suspendConnection();
  this.adapter.on('open',()=>{this.epoch++});
  this.adapter.on('close',()=>{this.epoch++;this.engine.suspendConnection()});
  this.adapter.on('message',msg=>this.receive(msg));
  this.adapter.on('adapterError',error=>this.onEvent({type:error.message==='QQ_ACCOUNT_MISMATCH'?'identity_mismatch':'error'}));
 }
 receive(msg){
  const cfg=this.settings();
  if(!allowed(msg,cfg)||msg.unsupported||!msg.text||!Number.isFinite(msg.timestamp)||msg.timestamp<this.startedAt-5)return false;
  if(msg.kind==='group'&&!msg.mentioned)return false;
  this.engine.receive(msg);return true;
 }
 async start(){this.startedAt=Date.now()/1000;await this.adapter.start()}
 async stop(){this.epoch++;this.engine.stop();await this.adapter.stop()}
}
