/* Browser-managed opt-in background notifications, VAPID configured by owner. */
(()=>{
'use strict';
const toBytes=raw=>{
 const base=raw.replace(/-/g,'+').replace(/_/g,'/');
 const bin=atob(base+'='.repeat((4-base.length%4)%4));
 return Uint8Array.from(bin,c=>c.charCodeAt(0));
};
const post=async(endpoint,obj)=>{
 const r=await fetch('/api/push/'+endpoint,{method:'POST',credentials:'same-origin',
  headers:{'Content-Type':'application/json'},body:JSON.stringify(obj)});
 if(!r.ok)throw Error('Push subscription unavailable');
};
async function subscribe(){
 if(!('serviceWorker' in navigator)||!('PushManager' in window)||Notification.permission!=='granted')return false;
 const config=await fetch('/api/push/config',{credentials:'same-origin'}).then(r=>r.json());
 if(!config.enabled||!config.public_key)return false;
 const reg=await navigator.serviceWorker.ready;
 const existing=await reg.pushManager.getSubscription();
 const sub=existing||await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:toBytes(config.public_key)});
 await post('subscribe',sub.toJSON());
 return true;
}
async function unsubscribe(){
 if(!('serviceWorker' in navigator)||!('PushManager' in window)return;
 const reg=await navigator.serviceWorker.ready;
 const sub=await reg.pushManager.getSubscription();
 if(sub){await post('unsubscribe',sub.toJSON()).catch(()=>{});await sub.unsubscribe();}
}
window.HuddlePush={subscribe,unsubscribe};
})();
