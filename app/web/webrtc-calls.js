/* Opt-in peer-to-peer audio/video calls, experimental.
 * Media permissions are requested only on deliberate Call/Accept clicks.
 * No TURN service is configured by default: NAT/firewalls can prevent calls.
 */
(()=>{
'use strict';
const el=id=>document.getElementById(id);
let call=null,pending=null;
const modal=document.createElement('div');
modal.className='h-call-overlay hidden';modal.id='hCallOverlay';
modal.innerHTML='<section class="h-call-panel" role="dialog" aria-modal="true" aria-label="Huddle call">'+
 '<header><strong id="hCallTitle">Huddle call</strong><small id="hCallState"></small></header>'+
 '<div class="h-call-video"><video id="hCallRemote" autoplay playsinline></video><video id="hCallLocal" autoplay muted playsinline></video></div>'+
 '<div class="h-call-buttons"><button type="button" id="hCallAccept" class="hidden">Accept</button>'+
 '<button type="button" id="hCallReject" class="hidden">Decline</button>'+
 '<button type="button" id="hCallMute" class="hidden">Mute mic</button>'+
 '<button type="button" id="hCallCamera" class="hidden">Camera off</button>'+
 '<button type="button" id="hCallEnd">End call</button></div>'+
 '<p>Experimental peer-to-peer calls. Connections may fail without TURN on restricted networks.</p></section>';
document.body.append(modal);
const alerts=(s,bad=false)=>typeof toast==='function'?toast(s,bad):console.log(s);
const hidden=id=>el(id).classList.add('hidden');
const shown=id=>el(id).classList.remove('hidden');
const show=(title,status)=>{
 el('hCallTitle').textContent=title;el('hCallState').textContent=status;
 modal.classList.remove('hidden');
};
const send=(action,payload={})=>{
 const ws=state.ws;if(ws?.readyState!==WebSocket.OPEN||!call)return false;
 ws.send(JSON.stringify({type:'call:signal',conversation_id:call.cid,
   recipient_id:call.peer,action,payload}));return true;
};
function reset(notify=true){
 if(notify&&call)send('hangup');
 if(call?.pc){call.pc.onicecandidate=null;call.pc.ontrack=null;call.pc.close();}
 call?.local?.getTracks().forEach(t=>t.stop());
 const localVideo=el('hCallLocal'),remoteVideo=el('hCallRemote');
 for(const video of [localVideo,remoteVideo]){video.pause();video.srcObject=null;}
 call=null;pending=null;
 modal.classList.add('hidden');
 hidden('hCallAccept');hidden('hCallReject');hidden('hCallMute');hidden('hCallCamera');
}
const createConnection=()=>{
 const pc=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});
 call.pc=pc;
 pc.onicecandidate=e=>{
   if(e.candidate)send('candidate',e.candidate.toJSON());
 };
 pc.ontrack=e=>{
   const media=e.streams?.[0]||new MediaStream([e.track]);
   el('hCallRemote').srcObject=media;
   el('hCallRemote').play().catch(()=>{});
 };
 pc.onconnectionstatechange=()=>{
   if(!call||call.pc!==pc)return;
   el('hCallState').textContent=pc.connectionState==='connected'?'Connected':pc.connectionState;
   if(['closed','failed'].includes(pc.connectionState)){alerts('Call connection ended.',true);reset(false)}
 };
 return pc;
};
async function getMedia(video){
 if(!navigator.mediaDevices?.getUserMedia||!window.RTCPeerConnection)
   throw Error('Calls need Chrome/Firefox on HTTPS with microphone support.');
 return navigator.mediaDevices.getUserMedia({audio:true,video:video?{facingMode:'user'}:false});
}
const enabledButtons=video=>{
 shown('hCallMute');if(video)shown('hCallCamera');else hidden('hCallCamera');
 hidden('hCallAccept');hidden('hCallReject');
};
async function startCall(video){
 const c=state.active,other=c?.members.find(m=>m.id!==state.me?.id);
 if(!c||c.kind!=='dm'||!other)return alerts('Calls are available only in direct chats.',true);
 if(call)return alerts('Finish the current call first.',true);
 if(state.ws?.readyState!==WebSocket.OPEN)return alerts('Reconnect to Huddle before calling.',true);
 call={cid:c.id,peer:other.id,video,local:null,pc:null,candidates:[]};
 show('Calling '+other.name,video?'Requesting microphone and camera…':'Requesting microphone…');
 try{
  call.local=await getMedia(video);
  el('hCallLocal').srcObject=call.local;el('hCallLocal').classList.toggle('hidden',!video);
  const pc=createConnection();
  call.local.getTracks().forEach(track=>pc.addTrack(track,call.local));
  const offer=await pc.createOffer();await pc.setLocalDescription(offer);
  if(!send('offer',{type:'offer',sdp:offer.sdp,video})){
    throw Error('Call signaling disconnected');
  }
  enabledButtons(video);el('hCallState').textContent='Ringing…';
 }catch(err){alerts('Could not start call: '+(err.message||'permission unavailable'),true);reset(false)}
}
async function accept(){
 if(!pending||!call)return;
 try{
  const offer=pending;pending=null;
  call.local=await getMedia(Boolean(offer.video));
  el('hCallLocal').srcObject=call.local;el('hCallLocal').classList.toggle('hidden',!offer.video);
  const pc=createConnection();
  call.local.getTracks().forEach(track=>pc.addTrack(track,call.local));
  await pc.setRemoteDescription({type:'offer',sdp:offer.sdp});
  const answer=await pc.createAnswer();await pc.setLocalDescription(answer);
  send('answer',{type:'answer',sdp:answer.sdp});
  for(const c of call.candidates.splice(0)){await pc.addIceCandidate(c).catch(()=>{})}
  enabledButtons(offer.video);el('hCallState').textContent='Connecting…';
 }catch(err){alerts('Could not accept call: '+err.message,true);reset()}
}
async function signal(data){
 if(!data||!['offer','answer','candidate','reject','busy','hangup'].includes(data.action))return;
 if(data.action==='offer'){
  if(call){
   state.ws?.send(JSON.stringify({type:'call:signal',conversation_id:data.conversation_id,
    recipient_id:data.from_user_id,action:'busy',payload:{}}));return;
  }
  if(!data.payload?.sdp||data.payload.type!=='offer')return;
  const id=data.from_user_id;
  call={cid:data.conversation_id,peer:id,video:!!data.payload.video,local:null,pc:null,candidates:[]};
  pending=data.payload;
  const name=state.conversations.find(c=>c.id===data.conversation_id)?.members.find(m=>m.id===id)?.name||'Huddle user';
  show('Incoming call from '+name,data.payload.video?'Video call':'Voice call');
  shown('hCallAccept');shown('hCallReject');
  return;
 }
 if(!call||data.conversation_id!==call.cid||data.from_user_id!==call.peer)return;
 if(['hangup','busy','reject'].includes(data.action)){
  alerts(data.action==='busy'?'This person is busy.':data.action==='reject'?'Call declined.':'Call ended.');
  reset(false);return;
 }
 if(data.action==='answer'&&call.pc&&data.payload?.sdp&&data.payload.type==='answer'){
  try{
   await call.pc.setRemoteDescription({type:'answer',sdp:data.payload.sdp});
   for(const c of call.candidates.splice(0))await call.pc.addIceCandidate(c).catch(()=>{});
  }catch(e){alerts('Call handshake failed.',true);reset();}
 }
 if(data.action==='candidate'&&data.payload?.candidate){
  const pc=call.pc;
  if(pc?.remoteDescription){
   try{await pc.addIceCandidate(data.payload)}catch{}
  }else call.candidates.push(data.payload);
 }
}
const callAudio=document.createElement('button'),callVideo=document.createElement('button');
callAudio.type=callVideo.type='button';callAudio.className=callVideo.className='h-call-header hidden';
callAudio.textContent='☎';callVideo.textContent='▣';
callAudio.title='Start voice call (beta)';callVideo.title='Start video call (beta)';
callAudio.setAttribute('aria-label','Start voice call beta');
callVideo.setAttribute('aria-label','Start video call beta');
const header=el('chatHeader');header?.append(callAudio,callVideo);
callAudio.onclick=()=>void startCall(false);
callVideo.onclick=()=>void startCall(true);
el('hCallAccept').onclick=()=>void accept();
el('hCallReject').onclick=()=>reset();
el('hCallEnd').onclick=()=>reset();
el('hCallMute').onclick=()=>{
 if(!call?.local)return;const tracks=call.local.getAudioTracks();
 tracks.forEach(t=>t.enabled=!t.enabled);
 el('hCallMute').textContent=tracks[0]?.enabled?'Mute mic':'Unmute mic';
};
el('hCallCamera').onclick=()=>{
 if(!call?.local)return;const tracks=call.local.getVideoTracks();
 tracks.forEach(t=>t.enabled=!t.enabled);
 el('hCallCamera').textContent=tracks[0]?.enabled?'Camera off':'Camera on';
};
window.HuddleCalls={signal,hangup:reset,sync:()=>{
 const enabled=Boolean(state.active?.kind==='dm'&&!state.aiOpen);
 callAudio.classList.toggle('hidden',!enabled);callVideo.classList.toggle('hidden',!enabled);
}};
})();
