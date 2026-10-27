const token=document.querySelector('meta[name="local-token"]').content;
const $=id=>document.getElementById(id);
async function request(path,body){const options=body?{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':token},body:JSON.stringify(body)}:{};const r=await fetch(path,options);const d=await r.json();if(!r.ok)throw Error(d.error||'请求失败');return d}
function toast(text){const el=$('toast');el.textContent=text;el.className='show';clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>el.className='',3000)}
async function refresh(){try{const d=await request('/api/status');$('qq-state').textContent=d.qq.found?'已发现':'未发现';$('qq-detail').textContent=d.qq.message;$('group-state').textContent=d.config.group||'未配置';for(const k of ['group','mention','model','key_env'])$(k).value=d.config[k]}catch(e){toast(e.message)}}
$('refresh').addEventListener('click',refresh);
$('settings-form').addEventListener('submit',async e=>{e.preventDefault();const data={};for(const k of ['group','mention','model','key_env'])data[k]=$(k).value;try{await request('/api/config',data);$('group-state').textContent=data.group||'未配置';toast('配置已保存')}catch(e){toast(e.message)}});
$('test').addEventListener('click',async()=>{const b=$('test');b.disabled=true;$('result').textContent='正在生成，请稍候…';try{const d=await request('/api/preview',{text:$('message').value});$('result').textContent=d.matched?d.reply+'\n\n生成耗时 '+(d.elapsed_ms/1000).toFixed(1)+' 秒':'没有匹配到 @，不会生成回复。'}catch(e){$('result').textContent=e.message}finally{b.disabled=false}});
refresh();
