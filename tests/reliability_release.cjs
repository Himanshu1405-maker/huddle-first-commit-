/* Static integration checks for the reliability release. */
const assert=require('node:assert/strict'),fs=require('node:fs');
const html=fs.readFileSync('app/web/index.html','utf8');
const app=fs.readFileSync('app/web/app.js','utf8');
const sw=fs.readFileSync('app/web/sw.js','utf8');
const calls=fs.readFileSync('app/web/webrtc-calls.js','utf8');
const offline=fs.readFileSync('app/web/offline-text-queue.js','utf8');
const plus=fs.readFileSync('app/web/reliability-ui.js','utf8');
const trim=fs.readFileSync('app/web/video-trim.js','utf8');
const check=['reliability-ui.js','pwa-register.js','push-register.js','recover-account.js',
 'offline-text-queue.js','webrtc-calls.js','video-trim.js'];
for(const name of check){const code=fs.readFileSync('app/web/'+name,'utf8');new Function(code);
 assert(html.includes('src="/assets/'+name+'"'),'Missing integrated script '+name);}
assert(html.includes('href="/manifest.webmanifest"'));
assert(html.includes('href="/assets/reliability-ui.css"'));
assert(html.includes('href="/assets/webrtc-calls.css"'));
assert(sw.includes("url.pathname.startsWith('/api/')"),'Service Worker must avoid private API caching');
assert(!sw.includes('cache.put(req'), 'No automatic caching of private responses');
assert(sw.includes("self.addEventListener('push'"));
assert(app.includes('window.HuddlePlus?.isMuted?.(msg.conversation_id)'),'Mute user alerts');
assert(app.includes('window.HuddlePlus?.sync?.()'),'Chat controls follow navigation');
assert(app.includes("case 'call:signal':window.HuddleCalls?.signal?.(data)"),'RTC signaling wired');
assert(app.includes("window.HuddleOffline?.enqueue?.(cid,text,nonce)"),'Offline composer queue');
assert(calls.includes('navigator.mediaDevices.getUserMedia'),'Request user media on opt-in');
assert(calls.includes('getMedia(Boolean(offer.video))'),'Remote must accept before media');
assert(calls.includes("RTCPeerConnection"),'Peer connection required');
assert(calls.includes("call.local.getTracks().forEach"),'Call media tracks must close');
assert(offline.includes('client_nonce:msg.nonce'),'Offline replay must be idempotent');
assert(offline.includes("huddle-failed-text-"),'Failed queue items must be recoverable locally');
assert(plus.includes("'/users/'+other.id+'/block'"),'Blocking command required');
assert(plus.includes('Polls and events'),'Collaboration UI required');
assert(trim.includes('MediaRecorder'),'Browser export required');
assert(trim.includes('end-start>45'),'Bound video recode duration');
console.log('HUDDLE_RELIABILITY_STATIC_PASS: UI scripts valid, PWA privacy, call consent, blocks, offline nonces, trim');
