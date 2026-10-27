/** QQ OneBot v11 adapter for the WeChatAgent-compatible transport boundary.
 * This module is experimental and is not wired to the existing Python service.
 */
import {EventEmitter} from 'node:events';
import {ReverseOneBotServer} from './onebot/reverse-ws-server.js';

const validId = value => /^[1-9]\d{0,15}$/.test(String(value ?? '')) && Number.isSafeInteger(Number(value));

export function normalizeQQ(event, expectedAccount) {
  if (!event || event.post_type !== 'message' || !['private','group'].includes(event.message_type)) return null;
  const self = String(event.self_id ?? ''), sender = String(event.user_id ?? ''), kind = event.message_type;
  const target = String(kind === 'group' ? event.group_id ?? '' : sender);
  if (!validId(self) || self !== String(expectedAccount) || !validId(sender) || !validId(target) || sender === self) return null;
  if (event.message_id == null || !Array.isArray(event.message)) return null;
  const segments = event.message.filter(segment => segment && typeof segment === 'object' && typeof segment.type === 'string');
  const text = segments.filter(s => s.type === 'text' && typeof s.data?.text === 'string').map(s => s.data.text).join('').trim();
  const mentioned = segments.some(s => s.type === 'at' && String(s.data?.qq ?? '') === self);
  const unsupported = segments.some(s => !['text','at'].includes(s.type));
  return {platform:'qq', kind, conversation_id:target, sender_id:sender, self_id:self,
    message_id:String(event.message_id), text, mentioned, unsupported,
    timestamp:Number(event.time ?? 0), sender_name:String(event.sender?.card ?? event.sender?.nickname ?? '')};
}

export class QQOneBotAdapter extends EventEmitter {
  constructor({accountId,server={},historyLimit=5000,allowInsecureLocalForTests=false}={}) {
    super();
    if ((!server.token || String(server.token).length < 24) && !(allowInsecureLocalForTests && ['127.0.0.1','localhost','::1'].includes(server.host ?? '127.0.0.1'))) throw new TypeError('OneBot requires a token of at least 24 characters');
    if (!validId(accountId)) throw new TypeError('A numeric QQ account ID is required');
    this.accountId=String(accountId); this.server=new ReverseOneBotServer(server); this.historyLimit=historyLimit; this.seen=new Map();
    this.server.on('event',event=>this.receive(event));
    this.server.on('open',()=>this.emit('open'));
    this.server.on('close',()=>this.emit('close'));
    this.server.on('invalid',kind=>this.emit('invalid',kind));
    this.server.on('error',error=>this.emit('adapterError',error));
  }
  receive(event) {
    const msg=normalizeQQ(event,this.accountId); if (!msg) return;
    const key=`${msg.kind}:${msg.conversation_id}:${msg.message_id}`;
    if(this.seen.has(key)) return;
    this.seen.set(key,Date.now());
    while(this.seen.size>this.historyLimit) this.seen.delete(this.seen.keys().next().value);
    this.emit('message',msg);
  }
  async start(){await this.server.start()}
  async stop(){await this.server.stop()}
  async sendText({kind,target,text}) {
    if (!['private','group'].includes(kind) || !validId(target)) throw new TypeError('Invalid QQ destination');
    if (typeof text!=='string' || !text.trim() || text.length>2000) throw new TypeError('Invalid message text');
    const params={ [kind==='group'?'group_id':'user_id']:Number(target),message:[{type:'text',data:{text:text.trim()}}]};
    const result=await this.server.action(kind==='group'?'send_group_msg':'send_private_msg',params);
    return {accepted:true,messageId:result.data?.message_id??null};
  }
}
