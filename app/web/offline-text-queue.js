/* Idempotent offline text queue, scoped to the signed-in user on this device.
 * Drafts and unsent text remain in this browser's local storage; use shared
 * devices carefully. Attachments are never cached or queued.
 */
(()=>{
'use strict';
const key=()=>state.me?.id?'huddle-offline-text-'+state.me.id:null;
let flushing=false;
function read(){
 try{return JSON.parse(localStorage.getItem(key())||'[]').filter(x=>
   x&&typeof x.body==='string'&&typeof x.cid==='string'&&typeof x.nonce==='string').slice(-50)}
 catch{return []}
}
function save(items){try{if(key())localStorage.setItem(key(),JSON.stringify(items.slice(-50)))}catch{}}
function enqueue(cid,body,nonce){
 if(!key()||!cid||!body||body.length>4000)return false;
 const rows=read();
 if(!rows.some(m=>m.nonce===nonce))rows.push({cid,body,nonce,created:Date.now()});
 save(rows);
 if(typeof toast==='function')toast('Message queued. Huddle will send it when connected.');
 return true;
}
async function flush(){
 if(flushing||!key()||!navigator.onLine)return;
 flushing=true;const originalUser=state.me?.id;
 try{
  const rows=read();
  for(const msg of rows){
   if(state.me?.id!==originalUser||!navigator.onLine)break;
   let res;
   try{res=await fetch('/api/conversations/'+encodeURIComponent(msg.cid)+'/messages',{
    method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({body:msg.body,client_nonce:msg.nonce})
   })}catch{break}
   if(res.status===401)break;
   if(res.ok){
    save(read().filter(m=>m.nonce!==msg.nonce));
    if(typeof loadConversations==='function')loadConversations().catch(()=>{});
    continue;
   }
   if(res.status>=500||res.status===429)break;
   // Authorization, blocked chat or malformed message. Remove to avoid
   // retrying irrecoverably, but keep a local copy under failed drafts.
   try{
    const failures=JSON.parse(localStorage.getItem('huddle-failed-text-'+originalUser)||'[]');
    failures.push(msg);
    localStorage.setItem('huddle-failed-text-'+originalUser,JSON.stringify(failures.slice(-20)));
   }catch{}
   save(read().filter(m=>m.nonce!==msg.nonce));
   if(typeof toast==='function')toast('A queued message could not be sent; it was saved as a failed draft.',true);
  }
 }finally{flushing=false}
}
window.HuddleOffline={enqueue,flush,clear:()=>{const k=key();if(k){localStorage.removeItem(k);localStorage.removeItem('huddle-failed-text-'+state.me.id)}},
 count:()=>read().length};
window.addEventListener('online',()=>void flush());
document.addEventListener('visibilitychange',()=>{if(!document.hidden)void flush()});
})();
