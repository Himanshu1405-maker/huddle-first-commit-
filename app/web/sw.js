/* Huddle PWA service worker: deliberately network-only for private chats.
   It does not cache authenticated HTML, API responses, or attachments. */
self.addEventListener('install',event=>{
  event.waitUntil(self.skipWaiting());
});
self.addEventListener('activate',event=>{
  event.waitUntil(self.clients.claim());
});
