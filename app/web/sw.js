/* Safe offline shell: NEVER cache messages, API responses, uploaded media or credentials. */
const CACHE='huddle-shell-v1';
const SHELL=['/','/assets/style.css','/assets/app.js','/assets/index.html','/assets/huddle-icon.svg'];
self.addEventListener('install',event=>{
 event.waitUntil(caches.open(CACHE).then(cache=>Promise.allSettled(SHELL.map(url=>cache.add(url)))));
 self.skipWaiting();
});
self.addEventListener('activate',event=>{
 event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('huddle-shell-')&&k!==CACHE).map(k=>caches.delete(k)))));
 self.clients.claim();
});
self.addEventListener('fetch',event=>{
 const req=event.request,url=new URL(req.url);
 if(req.method!=='GET'||url.origin!==self.location.origin)return;
 // Private content must always go to the server, never CacheStorage.
 if(url.pathname.startsWith('/api/')||url.pathname.startsWith('/ws')||
    url.pathname.startsWith('/assets/sw.js')||url.pathname==='/sw.js')return;
 if(req.mode==='navigate'){
  event.respondWith(fetch(req,{cache:'no-store'}).catch(async()=>{
    const cached=await caches.match('/');
    return cached||new Response('Huddle is offline. Reconnect to load chats.',{status:503,headers:{'Content-Type':'text/plain'}});
  }));
 }else if(url.pathname.startsWith('/assets/')){
  event.respondWith(fetch(req).catch(async()=>await caches.match(req)||Response.error()));
 }
});

/* Push is opt-in and sends no private message text to the operating system. */
self.addEventListener('push',event=>{
 let info={title:'Huddle',body:'You have a new message.',url:'/'};
 try{const payload=event.data?.json();if(payload&&payload.title==='Huddle')info=payload}catch{}
 event.waitUntil(self.registration.showNotification('Huddle',{
   body:info.body,icon:'/assets/huddle-icon.svg',badge:'/assets/huddle-icon.svg',
   tag:'huddle-new-message',data:{url:'/'}
 }));
});
self.addEventListener('notificationclick',event=>{
 event.notification.close();
 event.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(async clients=>{
   for(const client of clients){if(new URL(client.url).origin===self.location.origin){
     await client.focus();return;}}
   await self.clients.openWindow('/');
 }));
});
