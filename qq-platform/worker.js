import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import {QQSocialService} from './social-service.js';

const root=process.env.QQ_AGENT_ROOT, token=process.env.QQ_ONEBOT_TOKEN, internal=process.env.QQ_AGENT_INTERNAL_TOKEN;
if(!root||!token||!internal) throw Error('Missing required local service configuration');
const read=(file,fallback)=>{try{return JSON.parse(fs.readFileSync(path.join(root,'data',file),'utf8').replace(/^\uFEFF/,''))}catch(e){if(e.code==='ENOENT')return fallback;throw e}};
const initial=read('config.json',{});
const internalPort=Number(process.env.QQ_AGENT_INTERNAL_PORT || 18765), wsPort=Number(process.env.QQ_AGENT_WS_PORT || 18766);
if(!Number.isInteger(internalPort)||internalPort<1||internalPort>65535||!Number.isInteger(wsPort)||wsPort<1||wsPort>65535)throw Error('Invalid port');
const settings=()=>{
 const c=read('config.json',{}),w=read('workspace.json',{chats:[],personas:[]});
 const personas={};for(const chat of w.chats??[]){const p=(w.personas??[]).find(x=>x.id===chat.persona_id);if(p)personas[`qq:${chat.kind ?? 'group'}:${chat.id}`]=p.prompt}
 return {accountId:String(c.qq_id??''),groups:(w.chats??[]).filter(x=>x.enabled&&(x.kind??'group')==='group').map(x=>String(x.id)),private:(w.chats??[]).filter(x=>x.enabled&&x.kind==='private').map(x=>String(x.id)),persona:String(c.persona??''),personas,dryRun:initial.dry_run!==false || c.dry_run!==false};
};
const emit=data=>process.stdout.write(JSON.stringify(data)+'\n');
const model=async(key,prompt,metadata)=>{
 const response=await fetch(`http://127.0.0.1:${internalPort}/api/engine/decide`,{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':internal},body:JSON.stringify({text:prompt,persona:metadata.persona||'',kind:key.startsWith('qq:private:')?'private':'group'}),signal:AbortSignal.timeout(50000)});
 const result=await response.json();if(!response.ok)throw Error(result.error||'model unavailable');return 'RESPOND: '+result.reply;
};
const svc=new QQSocialService({stateDir:path.join(root,'data','engine',String(initial.qq_id)),accountId:initial.qq_id,onebot:{host:'127.0.0.1',port:wsPort,path:'/onebot',token},settings,decide:model,onEvent:e=>emit(e)});
svc.adapter.on('open',()=>emit({type:'connection',connected:true}));svc.adapter.on('close',()=>emit({type:'connection',connected:false}));
let stopping=false;
async function stop(){if(stopping)return;stopping=true;await svc.stop();process.exit(0)}
readline.createInterface({input:process.stdin}).on('line',line=>{try{if(JSON.parse(line).action==='stop')void stop()}catch{}});
process.on('SIGINT',()=>void stop());process.on('SIGTERM',()=>void stop());
await svc.start();emit({type:'ready'});
