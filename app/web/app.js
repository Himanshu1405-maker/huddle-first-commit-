/* Huddle client — no framework, build tool, or external JS library required. */
'use strict';
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const ICONS = {
  plus:'<path d="M12 5v14M5 12h14"/>',x:'<path d="M18 6 6 18M6 6l12 12"/>',
  search:'<circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>',
  info:'<circle cx="12" cy="12" r="10"/><path d="M12 11v6M12 7h.01"/>',
  sparkles:'<path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z"/><path d="m19 17 .7 1.3L21 19l-1.3.7L19 21l-.7-1.3L17 19l1.3-.7L19 17Z"/>',
  'user-round':'<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',settings:'<path d="M4 7h16M4 12h16M4 17h16"/><circle cx="9" cy="7" r="2"/><circle cx="15" cy="12" r="2"/><circle cx="9" cy="17" r="2"/>',
  'arrow-up':'<path d="M12 19V5M5 12l7-7 7 7"/>',check:'<path d="M20 6 9 17l-5-5"/>'
};
function icon(name){return `<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]||''}</svg>`}
$$('[data-icon]').forEach(node => node.innerHTML=icon(node.dataset.icon));
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state={config:{email_otp:false,ai_chat:false,ai_image:false,ai_local:true,google_login:false,google_client_id:'',firebase_config:null},googleLoaded:false,otpTicket:null,aiMode:"text",aiBusy:false,aiOpen:false,aiMessages:[],me:null,conversations:[],active:null,messages:[],ws:null,connected:false,retry:0,filter:'all',isRegister:false,groupSelected:new Set(),modalUsers:[],hasMore:false,loading:false,pending:new Map(),typers:new Map(),typingTimeout:null,emojiFor:null};
// AI inference runs in a dedicated Web Worker. No API keys, no paid services.
state.localAI={ready:false,loading:false,worker:null,job:null,active:false,history:[],progress:'',error:'',cacheFiles:0,restored:false,qualityLoading:false,quality:false};
state.lastChatId=null;
state.aiContextEnabled=false;
const LOCAL_AI_PREF='huddle-ai-installed-v1';
function localAIPreference(){
  try{return localStorage.getItem(LOCAL_AI_PREF)==='yes';}catch{return false;}
}
async function hasLocalAIModelCache(){
  if(!('caches' in window))return false;
  try{
    const bucket=await caches.open('transformers-cache');
    const requests=await bucket.keys();
    return requests.some(item=>/\.onnx(?:$|[?#])/.test(item.url));
  }catch{return false;}
}
function saveLocalAIPreference(){
  try{localStorage.setItem(LOCAL_AI_PREF,'yes');}catch{}
}
function startLocalAI({restore=false}={}){
  const local=state.localAI;
  if(local.loading||local.ready)return;
  if(!window.Worker){local.error='Your browser cannot run an on-device AI model.';aiStatus();return;}
  local.loading=true;local.error='';
  local.progress=restore?'Opening saved AI model from this device…':'Checking saved files; downloading missing model files…';
  local.active=true;local.restored=restore;
  renderAI();aiStatus();
  try{localAIWorker().postMessage({type:'load'});}
  catch{local.loading=false;local.error='Could not open the AI model on this device.';local.progress=local.error;aiStatus();}
}
async function restoreLocalAIIfSaved(){
  if(state.config.ai_chat||!localAIPreference()||state.localAI.ready||state.localAI.loading)return;
  const cached=await hasLocalAIModelCache();
  if(!state.aiOpen)return;
  if(cached)startLocalAI({restore:true});
  else{
    state.localAI.progress='Saved model files are missing or were cleared by the browser. Re-enable AI to download them again.';
    aiStatus();
  }
}
function localAIUpdate(){if(state.aiOpen)aiStatus();}
function localAIWorker(){
  const local=state.localAI;
  if(local.worker)return local.worker;
  const worker=new Worker('/assets/local-ai-worker.js',{type:'module',name:'huddle-local-ai'});
  local.worker=worker;
  worker.addEventListener('message',e=>{
    const data=e.data||{};
    if(data.type==='progress'){local.progress=data.message||'Preparing model…';localAIUpdate();return;}
    if(data.type==='ready'){
      local.loading=false;local.ready=true;local.cacheFiles=Number(data.cachedFiles)||0;
      local.progress=local.cacheFiles>0?'AI ready • model files saved in browser storage.':'AI ready • browser storage may not retain model files.';
      local.error='';saveLocalAIPreference();localAIUpdate();return;
    }
    if(data.type==='upgrade_ready'){
      local.qualityLoading=false;local.quality=true;local.progress='Enhanced local model ready • responses may still contain mistakes.';
      localAIUpdate();return;
    }
    if(data.type==='upgrade_error'){
      local.qualityLoading=false;local.quality=false;
      local.progress='Enhanced model not supported here. Standard on-device AI is still ready.';
      localAIUpdate();return;
    }
    if(data.type==='error'){
      local.debug={reason:data.reason,detail:data.detail};
      local.loading=false;local.ready=false;local.error='Model could not load here. Try Chrome on Wi-Fi, or a device with more free memory.';
      local.progress=local.error;localAIUpdate();
      if(local.job){local.job.reject(new Error(local.error));local.job=null;}
      local.worker?.terminate();local.worker=null;return;
    }
    if(data.type==='answer' && local.job && data.id===local.job.id){
      const job=local.job;local.job=null;
      job.resolve(data.text||'Sorry, I could not generate a helpful response.');
    }
    if(data.type==='answer_error' && local.job && data.id===local.job.id){
      const job=local.job;local.job=null;job.reject(new Error('This device could not complete the answer. Try a shorter question.'));
    }
  });
  worker.addEventListener('error',e=>{
    local.debug={reason:'worker_exception',detail:String(e.message||'Worker initialization error').slice(0,240)};
    local.loading=false;local.ready=false;local.progress='Could not reopen the saved AI model on this device.';
    local.error=local.progress;localAIUpdate();
    if(local.job){local.job.reject(new Error(local.error));local.job=null;}
    worker.terminate();local.worker=null;
  });
  return worker;
}
function initials(name){return String(name||'?').trim().split(/\s+/).slice(0,2).map(x=>x[0]?.toUpperCase()).join('')||'?'}
function avatar(name,id,kind='dm',online=false){const hash=[...(id||name||'')].reduce((a,c)=>a+c.charCodeAt(0),0)%6;return `<span class="avatar ${kind==='group'?'group-avatar':`avatar-${hash}`}">${kind==='group'?'✳':esc(initials(name))}${online?'<i class="presence-dot"></i>':''}</span>`}
function prettyTime(date){if(!date)return '';const d=new Date(date),today=new Date();if(d.toDateString()===today.toDateString())return d.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});return d.toLocaleDateString([],{month:'short',day:'numeric'})}
function dayLabel(date){const d=new Date(date),t=new Date();if(d.toDateString()===t.toDateString())return 'TODAY';t.setDate(t.getDate()-1);if(d.toDateString()===t.toDateString())return 'YESTERDAY';return d.toLocaleDateString([],{month:'long',day:'numeric',year:'numeric'}).toUpperCase()}
function toast(message,isError=false){
  // A single, deduplicated toast: don't cover the chat composer with a stack.
  const area=$('#toastArea');if(!area)return;
  const previous=area.querySelector('.toast');
  if(previous&&previous.textContent===message)return;
  area.querySelectorAll('.toast').forEach(node=>node.remove());
  const el=document.createElement('div');
  el.className='toast'+(isError?' error':'');
  el.setAttribute('role',isError?'alert':'status');
  el.textContent=message;
  area.append(el);
  setTimeout(()=>el.remove(),3700);
}
async function api(path,opts={}){let res;try{res=await fetch('/api'+path,{credentials:'same-origin',...opts,headers:{'Content-Type':'application/json',...(opts.headers||{})}})}catch{throw new Error('Cannot reach the server. Check your connection.')}let json=await res.json().catch(()=>({}));if(!res.ok){if(res.status===401&&state.me&&!path.startsWith('/auth/'))signOutLocal();const detail=typeof json.detail==='string'?json.detail:Array.isArray(json.detail)?json.detail.map(e=>{const field=(e.loc||[]).filter(x=>typeof x==='string').pop();return (field?field.replaceAll('_',' ') + ': ':'')+(e.msg||'Invalid value')}).join('; '):'Request failed';throw new Error(detail)}return json}
function post(path,data){return api(path,{method:'POST',body:JSON.stringify(data)})}
function patch(path,data){return api(path,{method:'PATCH',body:JSON.stringify(data)})}
function showAuth(){ $('#appScreen').classList.add('hidden');$('#authScreen').classList.remove('hidden');$('#otpPanel').classList.add('hidden');$('#authForm').classList.remove('hidden');$('.switch-auth').classList.remove('hidden');if(state.config.google_login)$('#googleAuthArea').classList.remove('hidden');$('#authError').textContent=''}
function signOutLocal(){state.lastChatId=null;state.aiContextEnabled=false;window.google?.accounts?.id?.disableAutoSelect?.();$('#aiView').classList.add('hidden');state.aiOpen=false;state.otpTicket=null;state.me=null;state.active=null;state.conversations=[];state.messages=[];state.pending.clear();state.connected=false;state.ws?.close();state.ws=null;showAuth();if(state.isRegister)toggleAuth()}
function showApp(){ $('#authScreen').classList.add('hidden');$('#appScreen').classList.remove('hidden');$('#selfName').textContent=state.me.name;$('#selfHandle').textContent='@'+state.me.handle;$('#selfAvatar').innerHTML=avatar(state.me.name,state.me.id);renderSidebar();connectWS()}
function toggleAuth(){state.isRegister=!state.isRegister;$('#authTitle').innerHTML=state.isRegister?'Join the Huddle<span class="accent">.</span>':'Welcome to Huddle<span class="accent">.</span>';$('#authSubtitle').textContent=state.isRegister?'Your people, your ideas, all in one place.':'Good to see you again. Your conversations are waiting.';$('#registerNameField').classList.toggle('hidden',!state.isRegister);$('#registerEmailField').classList.toggle('hidden',!(state.isRegister&&state.config.email_otp));$('#authEmail').required=state.isRegister&&state.config.email_otp;$('#authName').required=state.isRegister;$('#authPassword').autocomplete=state.isRegister?'new-password':'current-password';$('#authSubmit').innerHTML=state.isRegister?'Create account <span>→</span>':'Sign in <span>→</span>';$('#authSwitchPrefix').textContent=state.isRegister?'Already have an account?':'New around here?';$('#switchAuth').textContent=state.isRegister?'Sign in':'Create an account';$('#passwordHint').textContent=state.isRegister?'8+ characters':'';$('#authError').textContent=''}
$('#switchAuth').addEventListener('click',toggleAuth);
$('#togglePassword').addEventListener('click',()=>{$('#authPassword').type=$('#authPassword').type==='password'?'text':'password'});
$('#authForm').addEventListener('submit',async e=>{e.preventDefault();const submit=$('#authSubmit');submit.disabled=true;$('#authError').textContent='';try{const handle=$('#authHandle').value.trim().toLowerCase(),password=$('#authPassword').value,name=state.isRegister?$('#authName').value.trim():'';if(state.isRegister&&!/^[a-z0-9_]{3,22}$/.test(handle)){$('#authError').textContent='Check username: use 3–22 letters, numbers or underscores (_). No spaces, @ signs, dots or hyphens.';$('#authHandle').focus();return}if(state.isRegister&&name.length<2){$('#authError').textContent='Check display name: enter at least 2 characters.';$('#authName').focus();return}const payload=state.isRegister?{name,handle,password,...(state.config.email_otp?{email:$('#authEmail').value.trim()}: {})}:{handle,password};const result=await post(state.isRegister?'/auth/register':'/auth/login',payload);if(result.requires_verification){state.otpTicket=result.ticket;$('#authForm').classList.add('hidden');$('.switch-auth').classList.add('hidden');$('#googleAuthArea').classList.add('hidden');$('#otpPanel').classList.remove('hidden');$('#otpHint').textContent='Code sent to '+result.email_hint+'. Enter the 6-digit code within 10 minutes.';$('#otpCode').value='';$('#otpCode').focus();return}state.me=result.user;await loadConversations();showApp()}catch(err){$('#authError').textContent=err.message}finally{submit.disabled=false}});
async function init(){try{state.config=await api('/config')}catch{}initGoogleSignIn();try{const result=await api('/me');state.me=result.user;await loadConversations();showApp()}catch{showAuth()}}
async function loadConversations(){if(!state.me)return;const {conversations}=await api('/conversations');state.conversations=conversations;if(state.active){const active=state.conversations.find(c=>c.id===state.active.id);if(active){state.active=active;renderHeader()}else{state.active=null;showWelcome()}}renderSidebar()}
function renderSidebar(){if(!state.me)return;$('#allCount').textContent=state.conversations.length;const term=$('#sidebarSearch').value.trim().toLowerCase();const items=state.conversations.filter(c=>(state.filter==='all'||c.kind===state.filter)&&(c.name.toLowerCase().includes(term)||(c.last_message?.body||'').toLowerCase().includes(term)));$('#conversationList').innerHTML=items.length?items.map(c=>{const other=c.members.find(m=>m.id!==state.me.id);const online=c.kind==='dm'&&other?.online;const preview=c.last_message?(c.last_message.sender_id===state.me.id?'You: ':'')+c.last_message.body:(c.kind==='group'?'New circle · say hello':'Start with hello 👋');return `<button class="conv-item ${state.active?.id===c.id?'active':''}" data-conversation="${esc(c.id)}">${avatar(c.name,c.id,c.kind,online)}<span class="conv-details"><span class="conv-name-row"><span class="conv-name">${esc(c.name)}</span><span class="conv-time">${esc(prettyTime(c.last_message?.created_at||c.updated_at))}</span></span><span class="conv-preview-row"><span class="conv-preview">${esc(preview)}</span>${c.unread?`<span class="unread">${c.unread>99?'99+':c.unread}</span>`:''}</span></span></button>`}).join(''):'<div class="list-empty"><span class="big-icon">✳</span>No conversations here yet.<br/>Start with a hello.</div>'}
$('#conversationList').addEventListener('click',e=>{const btn=e.target.closest('[data-conversation]');if(btn)openConversation(btn.dataset.conversation)});
$('#sidebarSearch').addEventListener('input',renderSidebar);
$$('.filter').forEach(btn=>btn.addEventListener('click',()=>{state.filter=btn.dataset.filter;$$('.filter').forEach(b=>b.classList.toggle('selected',b===btn));renderSidebar()}));
function mobileDrawer(open){$('#sidebar').classList.toggle('open',open);$('#mobileScrim').classList.toggle('hidden',!open)}
$('#openSidebar').addEventListener('click',()=>mobileDrawer(true));$('#closeSidebar').addEventListener('click',()=>mobileDrawer(false));$('#mobileScrim').addEventListener('click',()=>mobileDrawer(false));
async function openConversation(id,focusId=null){const c=state.conversations.find(x=>x.id===id);if(!c)return;state.lastChatId=id;state.aiOpen=false;$('#aiView').classList.add('hidden');const changed=state.active?.id!==id;state.active=c;state.messages=[];state.hasMore=false;$('#welcomeChat').classList.add('hidden');$('#conversationView').classList.remove('hidden');$('#messageScroller').scrollTop=0;$('#messages').innerHTML='<div class="list-empty">Loading your conversation…</div>';renderHeader();renderSidebar();mobileDrawer(false);try{const result=await api(`/conversations/${id}/messages`);if(state.active?.id!==id)return;state.messages=result.messages;state.hasMore=result.has_more;renderMessages(true);markRead();if(focusId){scrollToMessage(focusId)}else if(changed&&window.matchMedia('(min-width: 721px)').matches){$('#messageInput').focus()}}catch(err){toast(err.message,true)}}
function showWelcome(){state.aiOpen=false;$('#aiView').classList.add('hidden');state.active=null;$('#welcomeChat').classList.remove('hidden');$('#conversationView').classList.add('hidden');$('#chatBanner').textContent='';$('#headerIdentity').innerHTML='<span class="header-placeholder">YOUR CONVERSATION SPACE</span>';renderSidebar()}
function renderHeader(){const c=state.active;if(!c)return;const other=c.members.find(m=>m.id!==state.me.id);const online=c.kind==='dm'&&other?.online;$('#headerIdentity').innerHTML=avatar(c.name,c.id,c.kind,online)+`<span><span class="header-name">${esc(c.name)}</span><span class="header-meta">${c.kind==='group'?`${c.members.length} members · Your circle`:`${online?'<i class="little-dot"></i> Online now':'Offline · @'+esc(c.handle)}`}</span></span>`;$('#chatBanner').innerHTML=`${c.kind==='group'?'✳ Welcome to <strong>'+esc(c.name)+'</strong>. Good things happen together.':'🔒 This conversation is between you and <strong>'+esc(c.name)+'</strong>.'}`;$('#messageInput').placeholder=`Message ${c.kind==='group'?'#'+c.name:c.name}…`}
function renderMessages(jumpEnd=false){const view=$('#messageScroller');const oldHeight=view.scrollHeight,oldTop=view.scrollTop;$('#loadMoreBtn').classList.toggle('hidden',!state.hasMore);let previousDay='';$('#messages').innerHTML=state.messages.map(m=>{const day=dayLabel(m.created_at);let divider='';if(day!==previousDay){divider=`<div class="date-divider">${esc(day)}</div>`;previousDay=day}const mine=m.sender_id===state.me.id;const sender=state.active?.members.find(x=>x.id===m.sender_id)||{name:'Unknown'};const group=state.active?.kind==='group';const reactions=m.reactions?.length?`<div class="reactions">${m.reactions.map(r=>`<button class="reaction ${r.users.includes(state.me.id)?'reacted':''}" data-reaction-message="${esc(m.id)}" data-reaction-emoji="${esc(r.emoji)}" title="React ${esc(r.emoji)}">${esc(r.emoji)} ${r.count}</button>`).join('')}</div>`:'';const media=(m.attachments||[]).map(a=>{const url='/api/media/'+encodeURIComponent(a.id);const mime=a.content_type||'';const label=esc(a.filename);return mime.startsWith('image/')?`<a class="media-card image-media" href="${url}" target="_blank" rel="noopener"><img src="${url}" loading="lazy" alt="Shared image: ${label}" /><span>${label}</span></a>`:mime.startsWith('audio/')?`<div class="media-card voice-media"><div>🎧 ${label}</div><audio controls preload="none" src="${url}"></audio></div>`:`<a class="media-card file-media" href="${url}" download>📎 ${label} <small>↧ Download</small></a>`;}).join('');const actions=!m.deleted_at?`<div class="message-actions"><button data-action="react" data-message="${esc(m.id)}" title="React">☺ React</button>${mine?`<button data-action="edit" data-message="${esc(m.id)}">Edit</button><button data-action="delete" data-message="${esc(m.id)}">Delete</button>`:`<button data-action="report" data-message="${esc(m.id)}" title="Report this message">⚑ Report</button>`}</div>`:'';return divider+`<div class="message-row ${mine?'mine':''}" id="msg-${esc(m.id)}">${mine?'<span class="avatar-placeholder"></span>':avatar(sender.name,sender.id)}<div class="message-stack">${group&&!mine?`<div class="sender-label">${esc(sender.name)}</div>`:''}<div class="bubble ${m.deleted_at?'deleted':''}">${m.deleted_at?'This message was deleted':esc(m.body)}</div>${m.deleted_at?'':media}<div class="bubble-meta">${esc(prettyTime(m.created_at))} ${m.edited_at?'<span class="edit-label">· edited</span>':''}${mine?`<span class="seen-check" title="${(m.seen_by||[]).length?'Seen':'Sent'}">${(m.seen_by||[]).length?'✓✓':'✓'}</span>`:''}</div>${reactions}${actions}</div></div>`}).join('')||'<div class="list-empty">No messages yet.<br/>Be the first to say hello 👋</div>';if(jumpEnd){view.scrollTop=view.scrollHeight}else{view.scrollTop=oldTop}}
function scrollToMessage(id){const el=document.getElementById('msg-'+id);if(el){el.scrollIntoView({block:'center',behavior:'smooth'});el.querySelector('.bubble')?.classList.add('highlight-bubble');setTimeout(()=>el.querySelector('.bubble')?.classList.remove('highlight-bubble'),2200)}else toast('Message is in older history — load earlier messages')}
$('#loadMoreBtn').addEventListener('click',async()=>{if(state.loading||!state.hasMore||!state.messages.length)return;state.loading=true;const cid=state.active.id;const scroller=$('#messageScroller');const beforeHeight=scroller.scrollHeight;try{const result=await api(`/conversations/${cid}/messages?before=${state.messages[0].id}`);if(state.active?.id!==cid)return;state.messages=[...result.messages,...state.messages];state.hasMore=result.has_more;renderMessages();scroller.scrollTop=scroller.scrollHeight-beforeHeight}catch(e){toast(e.message,true)}finally{state.loading=false}});
function markRead(){if(!state.active)return;const id=state.active.id;post(`/conversations/${id}/read`,{}).then(()=>{const c=state.conversations.find(c=>c.id===id);if(c){c.unread=0;renderSidebar()}}).catch(()=>{})}
async function sendMessage(){const textarea=$('#messageInput');const text=textarea.value.trim(),cid=state.active?.id;if(!cid||!text)return;textarea.value='';resizeComposer();sendTyping(false);const nonce=crypto.randomUUID?.()||String(Date.now())+Math.random();try{if(state.connected&&state.ws?.readyState===1){state.pending.set(nonce,{body:text,conversation_id:cid});state.ws.send(JSON.stringify({type:'message:send',body:text,conversation_id:cid,nonce}));setTimeout(async()=>{if(state.pending.has(nonce)){const pending=state.pending.get(nonce);state.pending.delete(nonce);try{await post(`/conversations/${pending.conversation_id}/messages`,{body:pending.body,client_nonce:nonce})}catch(e){toast(e.message,true)}}},4500)}else{await post(`/conversations/${cid}/messages`,{body:text,client_nonce:nonce});await openConversation(cid)}}catch(err){textarea.value=text;toast(err.message,true)}}
$('#sendBtn').addEventListener('click',sendMessage);$('#messageInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage()}});
function resizeComposer(){const inp=$('#messageInput');inp.style.height='auto';inp.style.height=Math.min(145,inp.scrollHeight)+'px';$('#composerCount').textContent=inp.value.length>3600?inp.value.length+'/4000':''}
$('#messageInput').addEventListener('input',()=>{resizeComposer();sendTyping(true)});
function sendTyping(value){if(state.active&&state.connected){state.ws.send(JSON.stringify({type:'typing',conversation_id:state.active.id,typing:value}));clearTimeout(state.typingTimeout);if(value)state.typingTimeout=setTimeout(()=>sendTyping(false),1400)}}
$('#emojiBtn').addEventListener('click',()=>$('#emojiPicker').classList.toggle('hidden'));
$('#emojiPicker').addEventListener('click',e=>{if(e.target.tagName==='BUTTON'){$('#messageInput').value+=e.target.textContent;resizeComposer();$('#emojiPicker').classList.add('hidden');$('#messageInput').focus()}});
$('#messages').addEventListener('click',async e=>{const reaction=e.target.closest('[data-reaction-message]');if(reaction){await applyReaction(reaction.dataset.reactionMessage,reaction.dataset.reactionEmoji);return}const action=e.target.closest('[data-action]');if(!action)return;const message=state.messages.find(m=>m.id===action.dataset.message);if(!message)return;if(action.dataset.action==='react'){state.emojiFor=message.id;openModal('react');return}
if(action.dataset.action==='report'){
 const reason=prompt('Why are you reporting this message? (harassment, spam, unsafe content, etc.)');
 if(reason===null)return;
 if(reason.trim().length<5){toast('Please add a brief reason, at least 5 characters.',true);return;}
 try{await post('/messages/'+encodeURIComponent(message.id)+'/report',{reason:reason.trim()});toast('Report submitted for review.');}
 catch(err){toast(err.message,true);}
 return;
}if(action.dataset.action==='edit'){const updated=prompt('Edit your message:',message.body);if(updated===null)return;try{await patch(`/messages/${message.id}`,{body:updated})}catch(err){toast(err.message,true)}}if(action.dataset.action==='delete'){if(!confirm('Delete this message for everyone?'))return;try{await api(`/messages/${message.id}`,{method:'DELETE'})}catch(err){toast(err.message,true)}}});
async 
/* Campus-friendly multimedia sharing and opt-in in-tab notifications. */
function setMediaProgress(text){const el=$('#mediaProgress');if(el)el.textContent=text||'';}
async function sendMediaFile(file){
  const cid=state.active?.id;if(!cid||!file)return;
  if(file.size>6*1024*1024){toast('File too large. Limit is 6 MB.',true);return;}
  const name=file.name||'attachment';
  const btn=$('#voiceNoteBtn');btn.disabled=true;setMediaProgress('Uploading '+name+'…');
  try{
    const response=await fetch('/api/conversations/'+encodeURIComponent(cid)+'/attachments',{
      method:'POST',credentials:'same-origin',
      headers:{'X-Huddle-Filename':encodeURIComponent(name),'Content-Type':file.type||'application/octet-stream'},
      body:file
    });
    const payload=await response.json().catch(()=>({}));
    if(!response.ok)throw Error(payload.detail||'Upload failed');
    toast('Shared '+name+' ✓');
    if(!state.connected&&state.active?.id===cid)await openConversation(cid);
  }catch(err){toast(err.message||'Could not share that file.',true);}
  finally{btn.disabled=false;setMediaProgress('');$('#mediaFileInput').value='';}
}
$('#mediaFileInput').addEventListener('change',e=>sendMediaFile(e.target.files?.[0]));
let voiceRecorder=null,voiceStream=null,voiceParts=[];
$('#voiceNoteBtn').addEventListener('click',async()=>{
  const button=$('#voiceNoteBtn');
  if(voiceRecorder&&voiceRecorder.state==='recording'){
    voiceRecorder.stop();return;
  }
  if(!state.active)return;
  if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){
    toast('Voice recording requires microphone support in your browser.',true);return;
  }
  try{
    const stream=await navigator.mediaDevices.getUserMedia({audio:true});
    voiceStream=stream;
    const candidates=['audio/webm;codecs=opus','audio/webm','audio/mp4','audio/ogg;codecs=opus'];
    const mimeType=candidates.find(t=>MediaRecorder.isTypeSupported(t));
    if(!mimeType)throw Error('Your browser does not support supported voice note formats');
    const recorder=new MediaRecorder(stream,{mimeType});
    voiceRecorder=recorder;voiceParts=[];
    const roomId=state.active.id;
    button.textContent='■';button.classList.add('recording');button.title='Stop recording';
    setMediaProgress('Recording — tap stop to send (max 45 seconds)');
    let deadline=setTimeout(()=>{if(recorder.state==='recording')recorder.stop();},45000);
    recorder.ondataavailable=e=>{if(e.data.size)voiceParts.push(e.data);};
    recorder.onstop=async()=>{
      clearTimeout(deadline);
      stream.getTracks().forEach(t=>t.stop());
      voiceStream=null;voiceRecorder=null;
      button.textContent='🎙';button.classList.remove('recording');button.title='Record voice note';
      const type=mimeType.split(';')[0];
      const ext=type==='audio/mp4'?'m4a':type==='audio/ogg'?'ogg':'webm';
      const file=new File(voiceParts,['voice-note.'+ext].join(''),{type});
      // Prevent sending to a different conversation if user navigates away.
      if(state.active?.id===roomId&&file.size)await sendMediaFile(file);
      else setMediaProgress('');
    };
    recorder.start(600);
  }catch(error){
    voiceStream?.getTracks().forEach(t=>t.stop());
    voiceStream=null;voiceRecorder=null;button.textContent='🎙';button.classList.remove('recording');
    setMediaProgress('');
    toast('Could not record: '+(error.message||'microphone unavailable'),true);
  }
});
$('#chatRecapBtn').addEventListener('click',async()=>{
  const c=state.active;if(!c)return;
  try{
    const recap=await api('/conversations/'+encodeURIComponent(c.id)+'/recap');
    $('#modalOverlay').classList.remove('hidden');
    setModalHeading('CHAT RECAP','Recent discussion');
    $('#modalContent').innerHTML='<p class="modal-helper">Private recent-message highlights for participants. This is not an AI-generated summary.</p>'+
      (recap.items.length?recap.items.map(m=>'<div class="recap-item"><strong>'+esc(m.speaker)+'</strong><p>'+esc(m.text)+'</p></div>').join(''):'<p class="modal-helper">No recent text messages to recap yet.</p>');
  }catch(err){toast(err.message,true);}
});
function notificationPreference(){try{return localStorage.getItem('huddle-notify-opt-in')==='yes';}catch{return false;}}
$('#notificationsBtn').addEventListener('click',async()=>{
  if(!('Notification' in window)){toast('This browser does not support notifications.',true);return;}
  if(notificationPreference()){
    localStorage.removeItem('huddle-notify-opt-in');
    $('#notificationsBtn').textContent='🔔 Enable message alerts';
    toast('Message alerts turned off.');return;
  }
  const permission=await Notification.requestPermission();
  if(permission!=='granted'){toast('Allow notifications in browser settings to turn on alerts.',true);return;}
  localStorage.setItem('huddle-notify-opt-in','yes');
  $('#notificationsBtn').textContent='🔔 Alerts on · tap to turn off';
  toast('Alerts enabled while Huddle is open.');
});
function notifyIncomingMessage(msg){
  if(!notificationPreference()||!('Notification' in window)||Notification.permission!=='granted')return;
  if(document.visibilityState==='visible'&&state.active?.id===msg.conversation_id)return;
  const conv=state.conversations.find(c=>c.id===msg.conversation_id);
  const member=conv?.members?.find(m=>m.id===msg.sender_id);
  const from=member?.name||conv?.name||'Someone';
  try{new Notification('Huddle · '+from,{body:String(msg.body||'New message').slice(0,120),tag:'huddle-'+msg.conversation_id});}catch{}
}
if(notificationPreference())$('#notificationsBtn').textContent='🔔 Alerts on · tap to turn off';
$('#aiUseChatContext').addEventListener('change',e=>{
  state.aiContextEnabled=e.target.checked;
  if(e.target.checked&&!state.lastChatId){
    toast('Open a conversation first, then return to Huddle AI to use its context.',true);
    e.target.checked=false;state.aiContextEnabled=false;
  }
});

function applyReaction(mid,emoji){try{await post(`/messages/${mid}/reactions`,{emoji})}catch(err){toast(err.message,true)}}
function onSocketMessage(data){switch(data.type){case 'hello':setStatus('online');break;case 'pong':break;case 'message:ack':state.pending.delete(data.nonce);break;case 'error':if(data.nonce){const p=state.pending.get(data.nonce);state.pending.delete(data.nonce);if(p&&state.active?.id===p.conversation_id)$('#messageInput').value=p.body}toast(data.detail,true);break;case 'message:new':{const msg=data.message;if(msg.sender_id!==state.me.id)notifyIncomingMessage(msg);if(state.active?.id===msg.conversation_id&&!state.messages.some(m=>m.id===msg.id)){const scroller=$('#messageScroller');const stick=scroller.scrollHeight-scroller.scrollTop-scroller.clientHeight<120;state.messages.push(msg);renderMessages(stick||msg.sender_id===state.me.id);if(msg.sender_id!==state.me.id)markRead()}loadConversations().catch(()=>{});break}case 'message:update':{const ix=state.messages.findIndex(m=>m.id===data.message.id);if(ix!==-1){state.messages[ix]=data.message;const scroller=$('#messageScroller');const atBottom=scroller.scrollHeight-scroller.scrollTop-scroller.clientHeight<130;renderMessages(atBottom)}loadConversations().catch(()=>{});break}case 'read:update':if(state.active?.id===data.conversation_id){state.messages.forEach(m=>{if(m.sender_id!==data.user_id&&m.created_at<=data.read_at&&!m.seen_by.includes(data.user_id))m.seen_by.push(data.user_id)});const scroller=$('#messageScroller');renderMessages(scroller.scrollHeight-scroller.scrollTop-scroller.clientHeight<140)}break;case 'conversation:refresh':case 'user:refresh':case 'presence:update':loadConversations().catch(()=>{});break;case 'typing:update':{if(data.user_id!==state.me.id){const key=data.conversation_id+':'+data.user_id;if(data.typing){state.typers.set(key,Date.now());setTimeout(()=>{if(Date.now()-(state.typers.get(key)||0)>2000){state.typers.delete(key);renderTyping()}},2700)}else state.typers.delete(key);renderTyping()}break}}}
function renderTyping(){if(!state.active)return;const cid=state.active.id;const names=[];for(const key of state.typers.keys()){const [conv,uid]=key.split(':');if(conv===cid){const member=state.active.members.find(m=>m.id===uid);if(member)names.push(member.name.split(' ')[0])}}$('#typingIndicator').innerHTML=names.length?`<span class="typing-bubbles"><span></span><span></span><span></span></span>${esc(names.join(', '))} ${names.length>1?'are':'is'} typing…`:''}
function setStatus(value){state.connected=value==='online';$('#wsStatus').className='ws-status '+(value==='online'?'online':'offline');$('#wsStatus').innerHTML=`<span></span>${value==='online'?'Live':value==='offline'?'Reconnecting':'Connecting'}`}
function connectWS(){if(!state.me)return;if(state.ws&&(state.ws.readyState===0||state.ws.readyState===1))return;const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');state.ws=ws;setStatus('connecting');ws.addEventListener('open',()=>{state.retry=0;setStatus('online');loadConversations().catch(()=>{});if(state.active){const cid=state.active.id;openConversation(cid)}});ws.addEventListener('message',e=>{try{onSocketMessage(JSON.parse(e.data))}catch(err){console.warn(err)}});ws.addEventListener('close',(ev)=>{if(state.ws!==ws)return;if(ev.code===4401){signOutLocal();return}state.connected=false;setStatus('offline');if(!state.me)return;const wait=Math.min(16000,800*Math.pow(1.65,state.retry++));setTimeout(()=>{if(state.me&&state.ws===ws)connectWS()},wait)});ws.addEventListener('error',()=>ws.close())}
setInterval(()=>{if(state.connected&&state.ws?.readyState===1)state.ws.send(JSON.stringify({type:'ping'}))},25000);
function setModalHeading(eyebrow,title){$('#modalEyebrow').textContent=eyebrow;$('#modalTitle').innerHTML=title+'<span class="accent">.</span>'}
function openModal(type){$('#modalOverlay').classList.remove('hidden');const el=$('#modalContent');if(type==='new'){setModalHeading('NEW','Start something good');state.groupSelected=new Set();el.innerHTML=`<div class="modal-tabs"><button class="modal-tab active" data-new-tab="dm">One-to-one</button><button class="modal-tab" data-new-tab="group">Create a circle</button></div><div id="newModalBody"></div>`;$$('[data-new-tab]').forEach(b=>b.addEventListener('click',()=>{$$('[data-new-tab]').forEach(x=>x.classList.toggle('active',x===b));renderNewModal(b.dataset.newTab)}));renderNewModal('dm')}else if(type==='search'){setModalHeading('FIND','Search messages');el.innerHTML=`<p class="modal-helper">Find something said in any of your conversations.</p><input class="modal-input" id="messageSearchInput" placeholder="Search your messages…" autofocus /><div id="searchResults"></div>`;let timer;$('#messageSearchInput').addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(runMessageSearch,250)});$('#messageSearchInput').focus()}else if(type==='profile'){setModalHeading('ACCOUNT','Your profile');el.innerHTML=`<p class="modal-helper">Show your people who you are.</p><label class="modal-label">Display name</label><input id="profileName" class="modal-input" maxlength="60" value="${esc(state.me.name)}" /><label class="modal-label">Bio</label><textarea id="profileBio" maxlength="160" class="modal-textarea" placeholder="Something about you…">${esc(state.me.bio||'')}</textarea><button id="saveProfile" class="btn btn-primary modal-action">Save changes →</button>${state.config.google_login?'<div class="google-link-section"><label class="modal-label">GOOGLE ACCOUNT</label><p class="modal-helper">Link Google to sign in faster next time.</p><div id="googleLinkButton" class="google-signin-wrap"></div></div>':''}<button id="signOutBtn" class="secondary-btn">Sign out of Huddle</button>`;if(state.config.firebase_config?.projectId && state.firebaseConnectGoogle){
      const box=$('#googleLinkButton');
      box.innerHTML='<button type="button" class="btn google-firebase-btn" id="linkFirebaseGoogle">Link Google account</button>';
      const linkButton=$('#linkFirebaseGoogle');
      linkButton.addEventListener('click',()=>state.firebaseConnectGoogle(true,linkButton));
    }else if(state.googleLoaded)renderGoogleButton($('#googleLinkButton'));$('#saveProfile').addEventListener('click',async()=>{try{const res=await patch('/me',{name:$('#profileName').value,bio:$('#profileBio').value});state.me=res.user;$('#selfName').textContent=state.me.name;$('#selfAvatar').innerHTML=avatar(state.me.name,state.me.id);closeModal();toast('Profile updated ✨')}catch(err){toast(err.message,true)}});$('#signOutBtn').addEventListener('click',async()=>{try{await post('/auth/logout',{})}catch{}closeModal();signOutLocal()})}else if(type==='info'){const c=state.active;if(!c){closeModal();return}setModalHeading('ABOUT','Conversation details');el.innerHTML=`<div style="display:flex;align-items:center;gap:15px;margin-bottom:22px">${avatar(c.name,c.id,c.kind)}<div><strong style="font-size:15px">${esc(c.name)}</strong><p class="modal-helper" style="margin:4px 0">${esc(c.description||'A little place to connect.')}</p></div></div><label class="modal-label">MEMBERS (${c.members.length})</label><div class="member-list">${c.members.map(m=>`<div class="member-card">${avatar(m.name,m.id,'dm',m.online)}<span><strong>${esc(m.name)}${m.id===state.me.id?' (you)':''}</strong><small>@${esc(m.handle)} · ${m.online?'Online':'Offline'}</small></span>${m.role==='admin'?'<em>ADMIN</em>':''}</div>`).join('')}</div>${c.kind==='group'&&c.members.find(m=>m.id===state.me.id)?.role==='admin'?'<button id="inviteBtn" class="secondary-btn">+ Invite more people</button>':''}`;if($('#inviteBtn'))$('#inviteBtn').addEventListener('click',()=>openModal('invite'))}else if(type==='invite'){setModalHeading('INVITE','Grow your circle');const cid=state.active?.id;if(!cid){closeModal();return}el.innerHTML=`<p class="modal-helper">Invite people to <strong>${esc(state.active.name)}</strong>. Only circle administrators can invite members.</p><input id="inviteSearch" class="modal-input" placeholder="Search people to invite…"/><div class="modal-list" id="inviteResults"></div><button class="btn btn-primary modal-action" id="sendInvites">Add selected people →</button>`;state.groupSelected=new Set();let timer;async function drawInvite(){try{const {users}=await api('/users?search='+encodeURIComponent($('#inviteSearch').value));const eligible=users.filter(u=>!state.active.members.some(m=>m.id===u.id));$('#inviteResults').innerHTML=eligible.length?eligible.map(u=>`<button class="person-row ${state.groupSelected.has(u.id)?'chosen':''}" data-invite="${esc(u.id)}">${avatar(u.name,u.id)}<span class="text"><strong>${esc(u.name)}</strong><small>@${esc(u.handle)}</small></span><span class="selected-mark">${state.groupSelected.has(u.id)?'✓':'+'}</span></button>`).join(''):'<div class="modal-empty">No new people found</div>';$$('[data-invite]').forEach(btn=>btn.addEventListener('click',()=>{const uid=btn.dataset.invite;if(state.groupSelected.has(uid))state.groupSelected.delete(uid);else state.groupSelected.add(uid);btn.classList.toggle('chosen');btn.querySelector('.selected-mark').textContent=state.groupSelected.has(uid)?'✓':'+'}))}catch(e){toast(e.message,true)}}$('#inviteSearch').addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(drawInvite,200)});$('#sendInvites').addEventListener('click',async()=>{if(!state.groupSelected.size){toast('Select at least one person',true);return}try{const result=await post(`/conversations/${cid}/members`,{member_ids:[...state.groupSelected]});closeModal();await loadConversations();toast(result.added+' person(s) invited ✨')}catch(e){toast(e.message,true)}});drawInvite()}else if(type==='react'){setModalHeading('REACT','Share a reaction');el.innerHTML='<p class="modal-helper">A little emoji can say a lot.</p><div class="emoji-reactions">'+['❤️','🔥','😂','👏','👍','🎉','💡','🚀'].map(e=>`<button data-big-reaction="${e}" style="font-size:26px;border:1px solid #e7ecf0;border-radius:10px;background:#fafcfd;padding:9px;margin:4px">${e}</button>`).join('')+'</div>';$$('[data-big-reaction]').forEach(b=>b.addEventListener('click',async()=>{await applyReaction(state.emojiFor,b.dataset.bigReaction);closeModal()}))}}
function closeModal(){$('#modalOverlay').classList.add('hidden');$('#modalContent').innerHTML=''}
$('#closeModal').addEventListener('click',closeModal);$('#modalOverlay').addEventListener('click',e=>{if(e.target===$('#modalOverlay'))closeModal()});document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeModal();$('#emojiPicker').classList.add('hidden')}});
async function renderNewModal(tab){const el=$('#newModalBody');el.innerHTML=`${tab==='group'?'<label class="modal-label">Circle name</label><input class="modal-input" maxlength="64" id="groupName" placeholder="e.g. Hackathon dream team" /><label class="modal-label">What\'s this circle about?</label><input class="modal-input" maxlength="200" id="groupDescription" placeholder="Ideas, projects, and everything between" />':''}<p class="modal-helper">${tab==='dm'?'Say hello to someone on campus.':'Invite the people you want in your circle.'}</p><input class="modal-input" id="userSearch" placeholder="Search people by name or username…"/><div class="modal-list" id="newUsersList"><div class="modal-empty">Finding people…</div></div>${tab==='group'?'<button id="createGroupBtn" class="btn btn-primary modal-action">Create your circle ↗</button>':''}`;let timer;$('#userSearch').addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>fetchModalUsers(tab),220)});if(tab==='group')$('#createGroupBtn').addEventListener('click',async()=>{const name=$('#groupName').value.trim();if(name.length<3){toast('Add a circle name (3+ characters)',true);return}if(!state.groupSelected.size){toast('Invite at least one person',true);return}try{const result=await post('/conversations/group',{name,description:$('#groupDescription').value,member_ids:[...state.groupSelected]});closeModal();await loadConversations();openConversation(result.conversation.id);toast('Your circle is ready ✳')}catch(err){toast(err.message,true)}});await fetchModalUsers(tab)}
async function fetchModalUsers(tab){const input=$('#userSearch');if(!input)return;try{const result=await api('/users?search='+encodeURIComponent(input.value));state.modalUsers=result.users;$('#newUsersList').innerHTML=result.users.length?result.users.map(u=>`<button class="person-row ${state.groupSelected.has(u.id)?'chosen':''}" data-person="${esc(u.id)}">${avatar(u.name,u.id,'dm',u.online)}<span class="text"><strong>${esc(u.name)}</strong><small>@${esc(u.handle)} · ${u.online?'Online now':'Offline'}</small></span>${tab==='group'?`<span class="selected-mark">${state.groupSelected.has(u.id)?'✓':'+'}</span>`:'<span class="selected-mark">↗</span>'}</button>`).join(''):'<div class="modal-empty">No people found. Invite a friend to join Huddle!</div>';$$('[data-person]').forEach(btn=>btn.addEventListener('click',async()=>{const uid=btn.dataset.person;if(tab==='group'){if(state.groupSelected.has(uid))state.groupSelected.delete(uid);else state.groupSelected.add(uid);btn.classList.toggle('chosen');btn.querySelector('.selected-mark').textContent=state.groupSelected.has(uid)?'✓':'+'}else{try{const result=await post('/conversations/direct',{user_id:uid});closeModal();await loadConversations();openConversation(result.conversation.id)}catch(e){toast(e.message,true)}}}))}catch(err){toast(err.message,true)}}
async function runMessageSearch(){const q=$('#messageSearchInput')?.value.trim(),target=$('#searchResults');if(!target)return;if(!q||q.length<2){target.innerHTML='<div class="modal-empty">Enter at least 2 characters</div>';return}try{const {results}=await api('/search/messages?q='+encodeURIComponent(q));if(!$('#searchResults'))return;target.innerHTML=results.length?results.map(r=>`<button class="search-result" data-result-conv="${esc(r.conversation_id)}" data-result-msg="${esc(r.id)}"><div class="result-title">${esc(r.sender_name)} <span style="color:#95a3b4;font-weight:400">· ${esc(state.conversations.find(c=>c.id===r.conversation_id)?.name||r.group_name||'Message')}</span></div><div class="result-body">${esc(r.body)}</div><div class="result-date">${esc(prettyTime(r.created_at))}</div></button>`).join(''):'<div class="modal-empty">Nothing found. Try a different keyword.</div>';$$('[data-result-conv]').forEach(b=>b.addEventListener('click',()=>{const cid=b.dataset.resultConv,mid=b.dataset.resultMsg;closeModal();openConversation(cid,mid)}))}catch(err){target.textContent=err.message}}
$('#newChatBtn').addEventListener('click',()=>openModal('new'));$('#welcomeNewBtn').addEventListener('click',()=>openModal('new'));$('#profileButton').addEventListener('click',()=>openModal('profile'));$('#searchMessagesBtn').addEventListener('click',()=>openModal('search'));$('#aiQuickBtn').addEventListener('click',openAI);$('#profileQuickBtn').addEventListener('click',()=>openModal('profile'));
$('#headerIdentity').addEventListener('click',()=>{if(state.active)openModal('info');});
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&state.me){if(state.active)markRead();if(!state.connected)connectWS()}});

// Email OTP is only enabled when the server has a working transactional email provider.
// Google Identity Services: an ID token is verified on the server before
// creating a local HttpOnly session. No OAuth secret is stored in the browser.
function renderGoogleButton(container){
  if(!container||!state.googleLoaded||!window.google?.accounts?.id)return;
  container.replaceChildren();
  window.google.accounts.id.renderButton(container,{type:'standard',theme:'outline',size:'large',text:'continue_with',shape:'pill',width:280,logo_alignment:'left'});
}
async function onGoogleCredential(result){
  if(!result?.credential)return false;
  const linkMode=Boolean(state.me);
  try{
    const response=await api(linkMode?'/auth/google/link':'/auth/google',{method:'POST',headers:{'X-Huddle-Client':'web'},body:JSON.stringify({credential:result.credential})});
    if(linkMode){toast(response.already_linked?'Google already connected':'Google account linked successfully ✨');return true}
    state.otpTicket=null;$('#otpPanel').classList.add('hidden');$('#authForm').classList.remove('hidden');$('.switch-auth').classList.remove('hidden');
    state.me=response.user;await loadConversations();showApp();toast('Welcome to Huddle! ✨');return true;
  }catch(error){if(linkMode){toast(error.message,true)}else{$('#authError').textContent=error.message}return false}
}
// Mobile Google OAuth is often blocked inside embedded app browsers.
// Provide a user-initiated handoff that keeps tokens and account data out of URLs.
const HUDDLE_PUBLIC_URL='https://huddle-web-production-76f3.up.railway.app/';
function prepareGoogleBrowserHelp(){
  const help=$('#googleBrowserHelp');
  if(!help)return;
  const ua=navigator.userAgent||'';
  const android=/Android/i.test(ua);
  // Normal Android Chrome isn't an embedded browser.
  const embedded=/;\s*wv\)|FBAN\/|FBAV\/|Instagram|ChatGPT|Line\/|MicroMessenger|GSA\//i.test(ua);
  if(embedded)help.classList.remove('hidden');
  const launch=$('#openChromeGoogle');
  if(launch){
    // Chrome's intent URL can open an external browser from Android Custom Tabs.
    // A conventional, copyable HTTPS URL is always provided as a fallback.
    launch.href='intent://huddle-web-production-76f3.up.railway.app/#Intent;scheme=https;package=com.android.chrome;end';
    if(!android)launch.classList.add('hidden');
  }
  $('#copyGoogleLink')?.addEventListener('click',async()=>{
    try{await navigator.clipboard.writeText(HUDDLE_PUBLIC_URL);toast('Link copied. Paste it in Chrome to sign in.')}catch{
      const output=$('#googleBrowserLink');
      output.classList.remove('hidden');output.focus();output.select?.();
    }
  });
}
function googleSignInError(code,reason='unknown'){
  const messages={
    'auth/unauthorized-domain':'This website is not authorized in Firebase. Contact the Huddle administrator.',
    'auth/popup-blocked':'Your browser blocked Google sign-in. Allow the popup and try again.',
    'auth/popup-closed-by-user':'The Google sign-in window closed before completion.',
    'auth/cancelled-popup-request':'Another sign-in attempt interrupted this one. Tap only once.',
    'auth/network-request-failed':'Google could not connect. Check your internet connection.',
    'auth/operation-not-allowed':'The Google provider is disabled in Firebase.',
    'auth/operation-not-supported-in-this-environment':'This browser cannot complete Google sign-in. Try Chrome.',
    'auth/web-storage-unsupported':'Enable browser storage and leave private browsing mode.',
    'auth/invalid-api-key':'The Firebase project API configuration is invalid.',
    'auth/internal-error':'Google and Firebase could not complete sign-in. This is an authentication-provider problem, not your Huddle password.'
  };
  const result=messages[code]||'Google sign-in could not complete.';
  return result+(reason!=='unknown'?' (reason: '+reason+')':' (code: '+code+')');
}
// Log ONLY a standardized Firebase code and sanitized reason, never a provider URL,
// OAuth state, ID token, email address, or provider error message.
function firebaseErrorReason(error){
  const message=String(error?.message||'').slice(0,1600);
  if(/INVALID_OAUTH_CLIENT_ID|invalid.oauth.client/i.test(message))return 'invalid_oauth_client';
  if(/INVALID_IDP_RESPONSE|invalid.idp.response/i.test(message))return 'invalid_idp_response';
  if(/CONFIGURATION_NOT_FOUND/i.test(message))return 'configuration_missing';
  if(/API_KEY_INVALID|API_KEY_NOT_VALID/i.test(message))return 'invalid_api_key';
  if(/OPERATION_NOT_ALLOWED/i.test(message))return 'provider_disabled';
  if(/popup.blocked/i.test(message))return 'popup_blocked';
  return 'unknown';
}
function reportGoogleIssue(stage,code,reason='unknown'){
  if(!/^auth\/[a-z0-9-]+$/.test(code))code='auth/unknown';
  if(!/^[a-z_]{3,36}$/.test(reason))reason='unknown';
  fetch('/api/diagnostics/google',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({stage,code,reason})}).catch(()=>{});
}
async function initFirebaseSignIn(){
  prepareGoogleBrowserHelp();
  const container=$('#googleSignInButton');
  $('#googleAuthArea').classList.remove('hidden');
  container.innerHTML='<button type="button" class="btn btn-wide google-firebase-btn" id="firebaseGoogleBtn" disabled>Connecting to Google…</button>';
  const button=$('#firebaseGoogleBtn');
  try{
    // Use a maintained SDK release. 10.14.1 was more than two years old.
    const [{initializeApp},{getAuth,GoogleAuthProvider,signInWithPopup,signOut}]=await Promise.all([
      import('https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js'),
      import('https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js')
    ]);
    const auth=getAuth(initializeApp(state.config.firebase_config));
    const provider=new GoogleAuthProvider();
    const useGoogle=async(linkMode=false,entry=button)=>{
      if(entry.disabled)return;
      entry.disabled=true;
      let stage='popup';
      try{
        // Popup is started directly from a user click, before any awaits.
        const result=await signInWithPopup(auth,provider);
        stage='token';
        // Sign-in already created a valid token; forcing another refresh may
        // fail unnecessarily on constrained mobile networks.
        const token=await result.user.getIdToken();
        stage='server';
        await onGoogleCredential({credential:token});
      }catch(error){
        const code=typeof error?.code==='string'&&/^auth\/[a-z0-9-]+$/.test(error.code)?error.code:'auth/unknown';
        const reason=firebaseErrorReason(error);
        reportGoogleIssue(stage,code,reason);
        console.warn('Huddle Google sign-in failure:',stage,code,reason);
        const message=googleSignInError(code,reason);
        if(code==='auth/popup-blocked'||code==='auth/operation-not-supported-in-this-environment')$('#googleBrowserHelp')?.classList.remove('hidden');
        if(!state.me){$('#authError').textContent=message;$('#authError').scrollIntoView({block:'nearest'});}
        else toast(message,true);
      }finally{
        try{await signOut(auth)}catch{};
        entry.disabled=false;
      }
    };
    state.firebaseConnectGoogle=useGoogle;
    button.disabled=false;
    button.textContent='Continue with Google';
    button.addEventListener('click',()=>useGoogle(false,button));
  }catch(error){
    console.warn('Firebase Google SDK failed to initialize');
    container.textContent='Google sign-in is temporarily unavailable. Password login still works.';
  }
}
function initGoogleSignIn(){
  // Use the native Google Identity Services flow instead of the failing
  // Firebase intermediary popup whenever a Google OAuth Web client is ready.
  if(!state.config.google_client_id){
    if(state.config.firebase_config?.projectId)initFirebaseSignIn();
    return;
  }
  if(!state.config.google_login)return;
  $('#googleAuthArea').classList.remove('hidden');
  const script=document.createElement('script');script.src='https://accounts.google.com/gsi/client';script.async=true;
  script.onload=()=>{try{window.google.accounts.id.initialize({client_id:state.config.google_client_id,callback:onGoogleCredential,ux_mode:'popup',auto_select:false});state.googleLoaded=true;renderGoogleButton($('#googleSignInButton'))}catch(error){console.warn('Google sign-in unavailable',error)}};
  script.onerror=()=>{$('#googleSignInButton').textContent='Google sign-in is temporarily unavailable.'};
  document.head.appendChild(script);
}
$('#otpForm').addEventListener('submit',async e=>{e.preventDefault();$('#otpError').textContent='';const btn=$('#otpSubmit');btn.disabled=true;try{const result=await post('/auth/verify',{ticket:state.otpTicket,code:$('#otpCode').value.trim()});state.otpTicket=null;state.me=result.user;$('#otpPanel').classList.add('hidden');$('#authForm').classList.remove('hidden');$('.switch-auth').classList.remove('hidden');await loadConversations();showApp();toast('Email verified. Welcome to Huddle! ✨')}catch(err){$('#otpError').textContent=err.message}finally{btn.disabled=false}});
$('#otpBack').addEventListener('click',()=>{state.otpTicket=null;$('#otpPanel').classList.add('hidden');$('#authForm').classList.remove('hidden');$('.switch-auth').classList.remove('hidden');if(state.config.google_login)$('#googleAuthArea').classList.remove('hidden');$('#authEmail').focus()});
$('#resendOtp').addEventListener('click',async()=>{const button=$('#resendOtp');button.disabled=true;try{await post('/auth/resend',{ticket:state.otpTicket});toast('A fresh code was sent to your email')}catch(err){$('#otpError').textContent=err.message}finally{button.disabled=false}});


$('#aiQualityUpgrade').addEventListener('click',()=>{
  const local=state.localAI;
  if(!local.ready||local.qualityLoading||local.quality)return;
  local.qualityLoading=true;local.progress='Preparing a larger local model. One-time download, ideally on Wi-Fi.';aiStatus();
  try{localAIWorker().postMessage({type:'upgrade'});}
  catch{local.qualityLoading=false;local.progress='Could not start enhanced local AI.';aiStatus();}
});
$('#aiLocalStart').addEventListener('click',()=>{
  // Storage persistence requires a user gesture. This never grants billing or
  // forces browser storage quotas; the browser may still evict files.
  if(navigator.storage?.persist)navigator.storage.persist().catch(()=>{});
  startLocalAI();
});
function askLocalAI(history){
  const local=state.localAI;
  if(!local.ready)return Promise.reject(new Error('Local AI has not loaded'));
  return new Promise((resolve,reject)=>{
    if(local.job){reject(new Error('An answer is still being prepared'));return;}
    const id=Date.now()+'-'+Math.random().toString(36).slice(2);
    local.job={resolve,reject,id};
    try{localAIWorker().postMessage({type:'ask',id,messages:history.slice(-7)});}
    catch{local.job=null;reject(new Error('Could not start a local AI response'));}
  });
}

function aiCard(m){
  const mine=m.role==='user',image=m.kind==='image'&&/^[0-9a-f]{32}$/.test(m.image_id||'');
  const poster=m.kind==='poster'&&/^data:image\/png;base64,/.test(m.image_data||'');
  return `<article class="ai-line ${mine?'from-user':'from-ai'}"><span class="ai-face">${mine?'YOU':'✦'}</span><div class="ai-bubble">${poster?
   `<img class="ai-generated-img" src="${esc(m.image_data)}" alt="Graphic poster designed in Huddle" /><p>${esc(m.body)}</p><button class="poster-download" data-poster-id="${esc(m.id)}">↓ Save PNG poster</button>`
   :image?`<img class="ai-generated-img" loading="lazy" src="/api/ai/image/${m.image_id}" alt="AI-generated image" /><p>${esc(m.body)}</p><a href="/api/ai/image/${m.image_id}" download="huddle-ai.jpg">Save image ↧</a>`
   :esc(m.body)}</div></article>`;
}
$('#aiMessages').addEventListener('click',event=>{
  const btn=event.target.closest('[data-poster-id]');
  if(!btn)return;
  const messages=state.localAI.active?state.localAI.history:state.aiMessages;
  const poster=messages.find(x=>x.id===btn.dataset.posterId && x.kind==='poster');
  if(!poster)return;
  const a=document.createElement('a');a.href=poster.image_data;a.download='huddle-studio-poster.png';
  document.body.appendChild(a);a.click();a.remove();
});
function renderAI(){
  const box=$('#aiMessages');
  const messages=state.localAI.active?state.localAI.history:state.aiMessages;
  box.innerHTML=messages.map(aiCard).join('');
  $('#aiSuggestions').classList.toggle('hidden',messages.length>0);
  $('#aiView').classList.toggle('ai-has-history',messages.length>0);
  const scroller=$('#aiScroll');
  requestAnimationFrame(()=>{scroller.scrollTop=scroller.scrollHeight});
}
function aiModeAvailable(){return state.aiMode==='image'?true:Boolean(state.config.ai_chat||state.localAI.ready)}
function aiStatus(){
  const local=state.localAI,textReady=Boolean(state.config.ai_chat),imageReady=Boolean(state.config.ai_image),available=aiModeAvailable(),isImage=state.aiMode==='image';
  const status=$('#aiAvailability'),notice=$('#aiNotice'),body=$('#aiNoticeText'),button=$('#aiSend'),hint=$('#aiComposerHint'),start=$('#aiLocalStart');
  status.textContent=isImage?'✦ Poster Studio ready':textReady?'✦ Online AI connected':local.quality?'✦ Enhanced local AI':local.ready?'✦ Local AI ready':local.loading?'◌ Opening local AI':'◌ Free local AI available';
  status.classList.toggle('is-online',textReady||local.ready);
  notice.classList.toggle('hidden',available);
  $('#aiNoticeTitle').textContent=isImage?'Poster Studio works offline':local.error?'Local AI could not start':local.loading?'Getting your local AI ready':local.ready?'Local AI ready':'Free AI — right on your device';
  body.textContent=isImage?'Create downloadable graphic posters and wallpapers from a prompt. This is a local design tool, not photorealistic AI image generation.':local.error||'Enable on-device answers, with an optional larger model for better wording. No paid API or card required. Answers may still be inaccurate.';
  start.classList.toggle('hidden',isImage||textReady||local.ready);
  start.disabled=local.loading;
  start.textContent=local.loading?'Opening your saved AI model…':localAIPreference()?'✨ Restore on-device AI':'✨ Enable on-device AI (free)';
  $('#aiLocalProgress').textContent=local.progress||'Your first download is saved where browser storage permits. Following visits reload the model from local storage.';
  const upgrade=$('#aiQualityUpgrade');
  upgrade.classList.toggle('hidden',isImage||textReady||!local.ready||local.quality);
  upgrade.disabled=local.qualityLoading;
  upgrade.textContent=local.qualityLoading?'Getting better answers ready…':'✧ Improve answers • optional 360 MB download';
  button.disabled=!available||state.aiBusy;
  button.setAttribute('aria-label',available?(isImage?'Create graphic poster':'Send to Huddle AI'):'AI is not ready yet');
  button.title=available?'Send':'Enable local AI first';
  $('#aiInputRow').classList.toggle('ai-input-offline',!available);
  hint.textContent=isImage?'Poster Studio makes graphic designs and PNG wallpapers, not AI-generated photos.':available?'Small language models can make mistakes. Avoid sharing private information.':'Enable local AI to ask questions, or switch to Poster Studio.';
  $('#aiPrompt').placeholder=isImage?'e.g. sunset mountain poster with a dreamy vibe':'Ask me a question, or tell me what to explain…';
}
async function openAI(){
  state.aiOpen=true;state.active=null;
  $('#welcomeChat').classList.add('hidden');$('#conversationView').classList.add('hidden');
  $('#aiView').classList.remove('hidden');mobileDrawer(false);renderSidebar();
  $('#headerIdentity').innerHTML='<span class="header-placeholder">✦ HUDDLE AI</span>';
  aiStatus();
  if(state.localAI.active){renderAI();return;}
  if(localAIPreference()&&!state.config.ai_chat){
    state.localAI.active=true;
    state.localAI.progress='Checking saved model files on this device…';
    renderAI();aiStatus();
    await restoreLocalAIIfSaved();
    return;
  }
  try{const result=await api('/ai/history');state.aiMessages=result.messages;renderAI()}
  catch(err){
    // A temporary history failure should not spam errors over the AI screen.
    state.aiMessages=[];renderAI();
    console.warn('Could not load Huddle AI history');
  }
}
$('#aiSidebarBtn').addEventListener('click',openAI);
$$('[data-ai-prompt]').forEach(button=>button.addEventListener('click',()=>{
  $('#aiPrompt').value=button.dataset.aiPrompt;
  $('#aiPrompt').focus();
  $('#aiPrompt').scrollIntoView({block:'nearest',behavior:'auto'});
}));
$$('[data-ai-mode]').forEach(button=>button.addEventListener('click',()=>{
  state.aiMode=button.dataset.aiMode;
  $$('[data-ai-mode]').forEach(el=>el.classList.toggle('selected',el===button));
  aiStatus();
}));
$('#aiForm').addEventListener('submit',async e=>{
  e.preventDefault();if(state.aiBusy)return;
  if(!aiModeAvailable()){aiStatus();return;}
  const prompt=$('#aiPrompt').value.trim();if(!prompt)return;
  const image=state.aiMode==='image';
  const localMode=!image&&!state.config.ai_chat&&state.localAI.ready;
  // Poster Studio works without text AI or image-provider credentials.
  if(image&&!state.config.ai_image)state.localAI.active=true;
  state.aiBusy=true;aiStatus();$('#aiPrompt').value='';
  const messages=(localMode||(image&&!state.config.ai_image))?state.localAI.history:state.aiMessages;
  messages.push({role:'user',kind:'text',body:(image?'Design a poster: ':'')+prompt});
  $('#aiTyping').classList.remove('hidden');renderAI();
  let aiFailure=null;
  try{
    if(image&&!state.config.ai_image){
      const {createPoster}=await import('/assets/poster-studio.js');
      const result=await createPoster(prompt);
      messages.push({id:'poster-'+Date.now(),role:'assistant',kind:'poster',body:result.description,image_data:result.dataUrl});
    }else if(localMode){
      const context=messages.slice(-7).map(m=>({role:m.role==='assistant'?'assistant':'user',content:m.body}));
      if(state.aiContextEnabled&&state.lastChatId){
        const summary=await api('/conversations/'+encodeURIComponent(state.lastChatId)+'/recap');
        const notes=summary.items.map(x=>x.speaker+': '+x.text).join('\n').slice(0,1500);
        if(notes)context.unshift({role:'user',content:'Reference notes from my own conversation (user consented):\n'+notes+'\nPlease use them only if helpful to the next question.'});
      }
      const text=await askLocalAI(context);
      messages.push({role:'assistant',kind:'text',body:text});
    }else{
      const result=await post(image?'/ai/image':'/ai/chat',{prompt});
      messages.push(result.reply);
    }
    renderAI();
  }catch(err){
    messages.pop();$('#aiPrompt').value=prompt;
    aiFailure=image?'Poster Studio could not draw on this browser. Please try Chrome.':localMode?'Your device could not finish this answer. Try a shorter question.':err.message;
    renderAI();
  }finally{
    $('#aiTyping').classList.add('hidden');state.aiBusy=false;aiStatus();
    if(aiFailure){$('#aiNoticeText').textContent=aiFailure;$('#aiNotice').classList.remove('hidden');}
  }
});
$('#aiPrompt').addEventListener('keydown',e=>{
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();if(aiModeAvailable())$('#aiForm').requestSubmit();}
});

init();
