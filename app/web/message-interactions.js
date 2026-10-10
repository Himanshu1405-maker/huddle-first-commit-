/* Huddle message interactions — full bubble selection, reply, forward, swipe,
   selected-message action bar, better timestamps and clean vector composer tools.
   Hooks the existing chat and media code; original IDs and endpoints stay intact. */
'use strict';
(() => {
  const root=document.getElementById('messages');
  const view=document.getElementById('conversationView');
  const composer=document.querySelector('#conversationView .composer');
  if(!root||!view||!composer)return;

  const vector=(name)=>({
    smile:'<circle cx="12" cy="12" r="9"/><path d="M8 15c2 2.6 6 2.6 8 0M9 9.5h.01M15 9.5h.01"/>',
    clip:'<path d="m20.5 11-8.8 8.8a5.3 5.3 0 0 1-7.5-7.5l9-9a3.5 3.5 0 0 1 5 5l-9 9a1.5 1.5 0 1 1-2.1-2.1l8-8"/>',
    mic:'<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v4M8 22h8"/>',
    pin:'<path d="M20 10c0 5.2-8 11-8 11S4 15.2 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>',
    send:'<path d="M12 19V5m-7 7 7-7 7 7"/>',
    reply:'<path d="m10 8-5 4 5 4M5 12h9c4 0 6 2.5 6 6"/>',
    forward:'<path fill="currentColor" stroke="none" d="M13.2 3.1c-.5-.4-1.2 0-1.2.6v3.5C5 7.6 1.9 12.3 1.3 19.5c-.1.9 1.1 1.3 1.5.5 2.3-4.2 4.7-5.8 9.2-5.9v3.8c0 .7.8 1 1.3.6l9-7.1a.8.8 0 0 0 0-1.3l-9.1-7Z"/>',
    copy:'<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    edit:'<path d="m15 5 4 4M4 20l4.5-1 11-11a2.5 2.5 0 0 0-3.5-3.5l-11 11L4 20Z"/>',
    trash:'<path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5m4-5v5"/>',
    star:'<path d="m12 2.8 2.9 6 6.6 1-4.8 4.7 1.1 6.6-5.8-3.1-5.8 3.1 1.1-6.6-4.8-4.7 6.6-1L12 2.8Z"/>',
    close:'<path d="m5 5 14 14M19 5 5 19"/>',
    check:'<path d="m4 12 5 5L20 6"/>',
    double:'<path d="m2 12 5 5L18 6m-5 11 3 0 6-8"/>',
    arrow:'<path d="M4 12h16m-7-7 7 7-7 7"/>'
  })[name]||'';
  const svg=(name,size=21)=>'<svg aria-hidden="true" viewBox="0 0 24 24" width="'+size+'" height="'+size+'" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">'+vector(name)+'</svg>';
  const getMsg=id=>(typeof state!=='undefined'&&state.messages||[]).find(m=>m.id===id);
  const getRow=el=>el?.closest?.('.message-row[id^="msg-"]')||null;
  const messageFromRow=row=>row?getMsg(row.id.slice(4)):null;
  const activeConv=()=>typeof state!=='undefined'?state.active?.id:null;
  let selectedId=null;
  let replyTo=null;
  let touch=null;
  let holdTimer=null;
  let longPressed=false;
  let lastTouchHandled=0;
  let starredIds=new Set();
  let starsLoadedFor=null;
  const clearTimer=()=>{if(holdTimer!==null)clearTimeout(holdTimer);holdTimer=null;};

  const bar=document.createElement('div');
  bar.id='hSelectedBar';
  bar.className='h-selected-bar hidden';
  bar.setAttribute('role','toolbar');
  bar.setAttribute('aria-label','Selected message actions');
  // Single-row action toolbar: no redundant selected-message text or close X.
  bar.innerHTML='<div class="h-selection-actions">'+
    '<button type="button" id="hTopReply" aria-label="Reply to selected message" title="Reply">'+svg('reply')+'<span>Reply</span></button>'+
    '<button type="button" id="hTopForward" aria-label="Forward selected message" title="Forward">'+svg('forward')+'<span>Forward</span></button>'+
    '<button type="button" id="hTopCopy" aria-label="Copy selected message" title="Copy">'+svg('copy')+'<span>Copy</span></button>'+
    '<button type="button" id="hTopEdit" aria-label="Edit selected message" title="Edit">'+svg('edit')+'<span>Edit</span></button>'+
    '<button type="button" id="hTopStar" aria-label="Star selected message" title="Star">'+svg('star')+'<span>Star</span></button>'+
    '<button type="button" id="hTopDelete" class="h-action-danger" aria-label="Delete selected message for everyone" title="Delete">'+svg('trash')+'<span>Delete</span></button>'+
    '<button type="button" id="hTopReport" aria-label="Report selected message" title="Report"><span aria-hidden="true">⚑</span><span>Report</span></button>'+
    '</div>';
  view.insertBefore(bar,view.querySelector('.chat-banner'));
  const replyBox=document.createElement('div');
  replyBox.id='hReplyPreview';
  replyBox.className='h-reply-preview hidden';
  replyBox.setAttribute('aria-live','polite');
  composer.parentNode.insertBefore(replyBox,composer);

  function selectionTarget(row){
    // Highlight only actual message content, never the flex row's empty width.
    return [...(row?.querySelectorAll('.bubble:not(.deleted),.h-location-card,.media-card')||[])]
      .find(element=>element.getClientRects().length>0 && getComputedStyle(element).visibility!=='hidden'
        && getComputedStyle(element).display!=='none');
  }
  function visibleSelection(){
    for(const row of root.querySelectorAll('.h-msg-selected'))row.classList.remove('h-msg-selected');
    for(const element of root.querySelectorAll('.h-selected-target'))element.classList.remove('h-selected-target');
    if(!selectedId){bar.classList.add('hidden');return;}
    const row=document.getElementById('msg-'+selectedId);
    const msg=getMsg(selectedId);
    if(!msg||msg.deleted_at||!row){clearSelection();return;}
    const bubble=selectionTarget(row);
    if(!bubble){clearSelection();return;}
    row.classList.add('h-msg-selected');
    bubble.classList.add('h-selected-target');
    const starred=starredIds.has(selectedId);
    const starButton=bar.querySelector('#hTopStar');
    starButton.classList.toggle('is-starred',starred);
    starButton.setAttribute('aria-label',starred?'Unstar selected message':'Star selected message');
    starButton.title=starred?'Unstar':'Star';
    starButton.querySelector('span').textContent=starred?'Unstar':'Star';
    const mine=msg.sender_id===state.me?.id;
    const editable=mine && !msg.location && !(msg.attachments?.length);
    const copyable=!msg.location && !msg.attachments?.length && !!msg.body;
    bar.querySelector('#hTopCopy').disabled=!copyable;
    bar.querySelector('#hTopForward').disabled=!!msg.location;
    bar.querySelector('#hTopEdit').hidden=!editable;
    bar.querySelector('#hTopDelete').hidden=!mine;
    bar.querySelector('#hTopReport').hidden=mine;
    bar.classList.remove('hidden');
  }
  function clearSelection(){
    selectedId=null;
    bar.classList.add('hidden');
    for(const row of root.querySelectorAll('.h-msg-selected'))row.classList.remove('h-msg-selected');
    for(const element of root.querySelectorAll('.h-selected-target'))element.classList.remove('h-selected-target');
    if(typeof closeHuddleContextMenu==='function')closeHuddleContextMenu();
  }
  function selectMessage(id,showMenu=false,anchor=null){
    const message=getMsg(id);
    if(!message||message.deleted_at)return;
    selectedId=id;
    visibleSelection();
    if(showMenu)openHuddleContextMenu(id,anchor||selectionTarget(document.getElementById('msg-'+id)));
  }
  function clearReply(){
    replyTo=null;
    replyBox.classList.add('hidden');
    replyBox.innerHTML='';
  }
  function startReply(id){
    const msg=getMsg(id);
    if(!msg||msg.deleted_at||!activeConv())return;
    replyTo={id,conversation_id:activeConv()};
    const member=state.active.members.find(m=>m.id===msg.sender_id);
    const author=msg.sender_id===state.me.id?'You':member?.name||'Someone';
    const preview=msg.location?'📍 Location':msg.attachments?.length?'📎 '+msg.attachments[0].filename:msg.body||'Message';
    replyBox.innerHTML='<div class="h-reply-line">'+svg('reply')+'<div class="h-reply-text"><strong>'+esc('Replying to '+author)+'</strong><span>'+esc(preview.slice(0,140))+'</span></div></div>'+
      '<button id="hCancelReply" type="button" title="Cancel reply" aria-label="Cancel reply">'+svg('close')+'</button>';
    replyBox.classList.remove('hidden');
    clearSelection();
    $('#messageInput').focus();
  }
  replyBox.addEventListener('click',e=>{if(e.target.closest('#hCancelReply'))clearReply()});

  // Existing click listeners resolve sendMessage at event-time: override only
  // when a reply is being sent; leave ordinary websocket sends unchanged.
  const previousSend=sendMessage;
  sendMessage=async function(...args){
    const reply=replyTo;
    if(!reply)return previousSend.apply(this,args);
    const text=$('#messageInput').value.trim();
    if(!text||reply.conversation_id!==activeConv())return;
    $('#emojiPicker').classList.add('hidden');
    const button=$('#sendBtn');button.disabled=true;
    try{
      const result=await post('/conversations/'+encodeURIComponent(reply.conversation_id)+
        '/messages/context',{action:'reply',source_message_id:reply.id,body:text,
        client_nonce:crypto.randomUUID?.()||String(Date.now())+Math.random()});
      $('#messageInput').value='';
      resizeComposer();clearReply();
      if(!state.connected&&state.active?.id===reply.conversation_id)await openConversation(reply.conversation_id);
      return result;
    }catch(err){toast(err.message,true);}
    finally{button.disabled=false;}
  };

  function formatStamp(iso){
    const date=new Date(iso);
    return Number.isNaN(date.getTime())?'':new Intl.DateTimeFormat(undefined,{hour:'numeric',minute:'2-digit'}).format(date);
  }
  function decorateMessages(){
    const current=activeConv();
    if(!current){clearSelection();return;}
    for(const msg of state.messages){
      const row=document.getElementById('msg-'+msg.id);
      if(!row)continue;
      row.dataset.messageId=msg.id;
      if(msg.deleted_at)continue;
      const stack=row.querySelector('.message-stack');
      const bubble=stack?.querySelector('.bubble');
      if(!stack)continue;
      if(bubble){
        bubble.setAttribute('aria-label','Message. Double click or hold for actions, swipe right to reply');
      }
      if(msg.forwarded){
        const badge=document.createElement('div');
        badge.className='h-forwarded-flag';
        badge.textContent='➦ Forwarded';
        if(bubble)stack.insertBefore(badge,bubble.closest('.h-message-visual')||bubble);
      }
      if(msg.reply_to){
        const quote=document.createElement('button');
        quote.type='button';
        quote.className='h-inline-quote';
        quote.dataset.replyTarget=msg.reply_to.id;
        quote.innerHTML='<strong>'+esc(msg.reply_to.name)+'</strong><span>'+esc(msg.reply_to.preview)+'</span>';
        if(bubble)stack.insertBefore(quote,bubble.closest('.h-message-visual')||bubble);
      }
      if(starredIds.has(msg.id)){
        const star=document.createElement('span');
        star.className='h-message-star';
        star.setAttribute('aria-label','Starred message');
        star.title='You starred this message';
        star.innerHTML=svg('star',12);
        stack.querySelector('.h-message-visual')?.append(star);
      }
      const meta=stack.querySelector('.bubble-meta');
      if(meta){
        const time=document.createElement('time');time.dateTime=msg.created_at;
        time.title=new Date(msg.created_at).toLocaleString();
        time.textContent=formatStamp(msg.created_at);
        meta.replaceChildren(time);
        if(msg.edited_at){const edited=document.createElement('span');edited.className='edit-label';edited.textContent='edited';meta.append(edited);}
        if(msg.sender_id===state.me?.id){
          const isRead=(msg.seen_by||[]).length>0;
          const tick=document.createElement('span');
          tick.className='h-read-ticks'+(isRead?' is-read':'');
          tick.title=isRead?'Read by at least one member':'Sent';
          tick.setAttribute('aria-label',tick.title);
          tick.innerHTML=svg(isRead?'double':'check',17);
          meta.append(tick);
        }
      }
    }
    if(selectedId)visibleSelection();
  }
  const previousRender=renderMessages;
  renderMessages=function(...args){
    const result=previousRender.apply(this,args);
    decorateMessages();
    return result;
  };
  root.addEventListener('click',e=>{
    const quote=e.target.closest('[data-reply-target]');
    if(quote){const target=quote.dataset.replyTarget;scrollToMessage(target);}
  });

  async function copyMessage(){
    const m=getMsg(selectedId);
    if(!m||m.location)return;
    try{await navigator.clipboard.writeText(m.body||'');toast('Message copied');clearSelection();}
    catch{toast('Clipboard unavailable',true);}
  }

  function closeForwardDialog(){
    document.getElementById('hForwardOverlay')?.remove();
  }
  function forwardMessage(id){
    const msg=getMsg(id);
    if(!msg||msg.deleted_at||msg.location)return;
    clearSelection();
    closeForwardDialog();
    const overlay=document.createElement('div');
    overlay.id='hForwardOverlay';
    overlay.className='h-forward-overlay';
    overlay.setAttribute('role','presentation');
    const dialog=document.createElement('section');
    dialog.className='h-forward-dialog';dialog.setAttribute('role','dialog');
    dialog.setAttribute('aria-modal','true');dialog.setAttribute('aria-labelledby','hForwardTitle');
    dialog.innerHTML='<div class="h-forward-head"><div><small>HUDDLE / SHARE</small><h2 id="hForwardTitle">Forward message</h2></div>'+
      '<button type="button" id="hForwardClose" aria-label="Cancel forwarding">'+svg('close')+'</button></div>'+
      '<p class="h-forward-intro">Choose a conversation. Your message will be sent as a forward.</p>'+
      '<input id="hForwardSearch" type="search" maxlength="80" placeholder="Search chats and circles…" aria-label="Search destination conversations"/>'+
      '<div id="hForwardList" class="h-forward-list"></div>';
    overlay.append(dialog);document.body.append(overlay);
    const conversations=(state.conversations||[]).filter(c=>c.id && c.members?.some(m=>m.id===state.me?.id));
    const draw=(term='')=>{
      const filtered=conversations.filter(c=>c.name.toLocaleLowerCase().includes(term.toLocaleLowerCase()));
      dialog.querySelector('#hForwardList').innerHTML=filtered.length?filtered.map(c=>'<button type="button" class="h-forward-target" data-h-forward-to="'+esc(c.id)+'">'+
        '<span class="h-forward-avatar">'+esc((c.name||'?').slice(0,1).toUpperCase())+'</span><span><strong>'+esc(c.name)+'</strong><small>'+esc(c.kind==='group'?'Group chat':'Direct message')+'</small></span><span class="h-forward-arrow">'+svg('arrow')+'</span></button>').join(''):
        '<p class="h-forward-empty">No matching conversations.</p>';
    };
    draw();
    const close=()=>{closeForwardDialog();};
    overlay.addEventListener('click',e=>{if(e.target===overlay)close()});
    dialog.querySelector('#hForwardClose').addEventListener('click',close);
    dialog.querySelector('#hForwardSearch').addEventListener('input',e=>draw(e.target.value.trim()));
    dialog.querySelector('#hForwardList').addEventListener('click',async e=>{
      const btn=e.target.closest('[data-h-forward-to]');
      if(!btn)return;
      btn.disabled=true;
      try{
        await post('/conversations/'+encodeURIComponent(btn.dataset.hForwardTo)+
          '/messages/context',{action:'forward',source_message_id:id});
        close();
        toast('Message forwarded');
      }catch(err){toast(err.message,true);btn.disabled=false;}
    });
    dialog.querySelector('#hForwardSearch').focus();
    const escape=e=>{if(e.key==='Escape'){close();document.removeEventListener('keydown',escape);}};
    document.addEventListener('keydown',escape);
    // Ensure later dialogs don't accumulate old Escape handlers.
    overlay.addEventListener('click',()=>{if(!document.getElementById('hForwardOverlay'))document.removeEventListener('keydown',escape)});
  }

  // Long press opens a small reaction-only floating tray. Message actions
  // appear in the clearly labeled selected-message toolbar above the chat.
  // Legacy desktop double-click/contextmenu continues through this binding.
  openHuddleContextMenu=function(messageId,anchor){
    const msg=getMsg(messageId);
    if(!msg||msg.deleted_at)return;
    selectMessage(messageId);
    closeHuddleContextMenu();
    const menu=document.createElement('div');
    menu.className='h-message-menu h-message-menu-polished h-quick-reactions';
    menu.setAttribute('role','group');
    menu.setAttribute('aria-label','React to selected message');
    const emojis=['❤️','😂','😮','👍','🙏','🔥','🥰','🎉'];
    menu.innerHTML='<div class="h-message-reactions">'+emojis.map(emoji=>
      '<button type="button" data-h-reaction="'+esc(emoji)+'" aria-label="React '+esc(emoji)+'">'+esc(emoji)+'</button>').join('')+'</div>';
    document.body.append(menu);
    huddleContextMenu=menu;
    const rect=(anchor?.getBoundingClientRect?.()||document.getElementById('msg-'+messageId)?.getBoundingClientRect())||{left:0,top:140,bottom:170};
    const width=menu.offsetWidth,height=menu.offsetHeight;
    const left=Math.max(9,Math.min(innerWidth-width-9,rect.left+(rect.width-width)/2));
    const top=rect.top-height-11>=10?rect.top-height-11:
      Math.min(innerHeight-height-10,rect.bottom+11);
    menu.style.left=left+'px';
    menu.style.top=Math.max(10,top)+'px';
    menu.addEventListener('click',async e=>{
      const emoji=e.target.closest('[data-h-reaction]')?.dataset.hReaction;
      if(!emoji)return;
      clearSelection();
      await applyReaction(messageId,emoji);
    });
  };

  // WhatsApp-like gestures start ONLY on a bubble/media card, not blank chat-row
  // space. The stack itself follows a rightward drag with a spring return.
  function clearSwipe(row){
    if(!row)return;
    row.style.removeProperty('--h-swipe-x');
    row.classList.remove('h-swiping');
  }
  root.addEventListener('pointerdown',e=>{
    if(e.pointerType!=='touch'||e.button!==0)return;
    const content=e.target.closest('.bubble:not(.deleted),.h-location-card,.media-card');
    const row=getRow(content);
    const msg=messageFromRow(row);
    if(!content||!row||!msg||msg.deleted_at||
       e.target.closest('button,audio,video,.reactions,.h-inline-quote'))return;
    e.stopPropagation(); // suppress old bubble-only hold listener
    e.preventDefault(); // Android WebView: do not begin native text selection.
    clearTimer();longPressed=false;
    touch={pointerId:e.pointerId,x:e.clientX,y:e.clientY,row,id:msg.id,content};
    holdTimer=setTimeout(()=>{
      if(!touch)return;
      longPressed=true;
      lastTouchHandled=Date.now();
      selectMessage(touch.id,true,touch.content);
      navigator.vibrate?.(15);
      try{getSelection()?.removeAllRanges();}catch{}
    },460);
  },true);
  root.addEventListener('pointermove',e=>{
    if(!touch||touch.pointerId!==e.pointerId)return;
    const dx=e.clientX-touch.x,dy=e.clientY-touch.y;
    if(Math.hypot(dx,dy)>13)clearTimer();
    if(Math.abs(dy)>34&&Math.abs(dy)>Math.abs(dx)){
      clearSwipe(touch.row);touch=null;return;
    }
    if(dx>9 && dx>Math.abs(dy)*1.2 && !longPressed){
      touch.row.classList.add('h-swiping');
      touch.row.style.setProperty('--h-swipe-x',Math.round(Math.min(72,dx*.66))+'px');
      // Mark the intent when the reply threshold is reached.
      touch.row.classList.toggle('h-swipe-ready',dx>=65);
    }else if(dx<=0){
      clearSwipe(touch.row);
      touch.row.classList.remove('h-swipe-ready');
    }
  },true);
  function finishTouch(e){
    if(!touch||touch.pointerId!==e.pointerId)return;
    const {x,y,id,row}=touch;
    const dx=e.clientX-x,dy=e.clientY-y;
    clearTimer();touch=null;
    clearSwipe(row);row.classList.remove('h-swipe-ready');
    if(e.type==='pointerup'&&!longPressed&&dx>=65&&Math.abs(dy)<42){
      lastTouchHandled=Date.now();
      startReply(id);navigator.vibrate?.(10);
      e.preventDefault();e.stopPropagation();
    }
    longPressed=false;
  }
  root.addEventListener('pointerup',finishTouch,true);
  root.addEventListener('pointercancel',finishTouch,true);
  root.addEventListener('contextmenu',e=>{
    // Android's native Copy / Select all popover must never appear when a
    // text message is being held for Huddle message actions.
    if(e.target.closest('.bubble,.h-location-card,.media-card')){
      e.preventDefault();e.stopImmediatePropagation();
      return;
    }
    if(Date.now()-lastTouchHandled<850){e.preventDefault();e.stopImmediatePropagation();}
  },true);
  root.addEventListener('selectstart',e=>{
    if(e.target.closest('.bubble,.h-location-card,.media-card'))e.preventDefault();
  },true);
  root.addEventListener('click',e=>{
    const selectedRow=e.target.closest('.message-row.h-msg-selected');
    if(selectedRow&&Date.now()-lastTouchHandled>=650&& !e.target.closest('button,a,.reactions')){
      clearSelection();return;
    }
    if(Date.now()-lastTouchHandled<650 && e.target.closest('.message-row')){
      e.preventDefault();e.stopImmediatePropagation();
    }
  },true);
  // The existing message context menu on desktop is kept; outside click clears
  // the selection only when no menu is visible.
  document.addEventListener('pointerdown',e=>{
    if(!selectedId || e.target.closest('.h-message-menu,#hSelectedBar,.message-row,.h-forward-overlay'))return;
    clearSelection();
  });
  function performOriginalAction(id,action){
    const button=document.getElementById('msg-'+id)?.querySelector('[data-action="'+action+'"]');
    clearSelection();
    button?.click();  // Reuse existing edit/delete/report APIs and confirmations.
  }
  // Starred state is private to the signed-in account, not broadcast to others.
  async function loadStarred(force=false){
    const account=state.me?.id||null;
    if(!account){starredIds.clear();starsLoadedFor=null;return [];}
    if(!force&&starsLoadedFor===account)return [];
    const result=await api('/messages/starred');
    if(state.me?.id!==account)return [];
    starredIds=new Set(result.items.map(entry=>entry.message.id));
    starsLoadedFor=account;
    if(state.active)renderMessages(false);
    return result.items;
  }
  async function toggleStar(id){
    if(!id)return;
    const previous=starredIds.has(id);
    const method=previous?'DELETE':'PUT';
    try{
      await api('/messages/'+encodeURIComponent(id)+'/star',{method});
      if(previous)starredIds.delete(id);else starredIds.add(id);
      clearSelection();
      if(state.active)renderMessages(false);
      toast(previous?'Removed from starred messages':'Message starred');
    }catch(err){toast(err.message,true)}
  }
  function closeStars(){document.getElementById('hStarsOverlay')?.remove();}
  async function openStarred(){
    closeStars();
    const overlay=document.createElement('div');
    overlay.id='hStarsOverlay';
    overlay.className='h-stars-overlay';
    overlay.innerHTML='<section class="h-stars-dialog" role="dialog" aria-modal="true" aria-label="Starred messages">'+
      '<header><div><small>YOUR SAVED MESSAGES</small><h2>Starred messages</h2></div>'+
      '<button type="button" id="hStarsClose" aria-label="Close starred messages">'+svg('close')+'</button></header>'+
      '<div id="hStarsItems" class="h-stars-items" aria-live="polite">Loading starred messages…</div></section>';
    document.body.append(overlay);
    const container=overlay.querySelector('#hStarsItems');
    const close=()=>{closeStars()};
    overlay.addEventListener('click',e=>{if(e.target===overlay)close()});
    overlay.querySelector('#hStarsClose').addEventListener('click',close);
    const escHandler=e=>{if(e.key==='Escape'&&overlay.isConnected){close();document.removeEventListener('keydown',escHandler)}};
    document.addEventListener('keydown',escHandler);
    try{
      const result=await api('/messages/starred');
      if(!overlay.isConnected)return;
      starredIds=new Set(result.items.map(e=>e.message.id));
      starsLoadedFor=state.me?.id||null;
      const items=result.items;
      container.innerHTML=items.length?items.map(({message,conversation_name})=>{
        const preview=message.location?'📍 Location':message.attachments?.length?
          '📎 '+message.attachments[0].filename:(message.body||'Message').replace(/^\\s+/,'');
        return '<button type="button" data-star-conv="'+esc(message.conversation_id)+'" data-star-msg="'+esc(message.id)+'">'+
          '<span aria-hidden="true" class="h-stars-icon">'+svg('star',18)+'</span>'+
          '<span class="h-star-list-copy"><strong>'+esc(conversation_name||'Conversation')+'</strong><small>'+esc(preview.slice(0,125))+'</small></span>'+
          '<span class="h-stars-chevron" aria-hidden="true">›</span></button>';
      }).join(''):'<div class="h-stars-empty">No starred messages yet. Long-press a message and tap Star.</div>';
      if(state.active)renderMessages(false);
    }catch(error){container.textContent=error.message||'Could not load starred messages';}
    container.addEventListener('click',async e=>{
      const item=e.target.closest('[data-star-msg]');if(!item)return;
      const cid=item.dataset.starConv,id=item.dataset.starMsg;
      close();document.removeEventListener('keydown',escHandler);
      if(typeof openConversation==='function')await openConversation(cid,id);
    });
    overlay.querySelector('#hStarsClose').focus();
  }
  document.getElementById('hOpenStarred')?.addEventListener('click',openStarred);
  document.getElementById('hProfileStars')?.addEventListener('click',openStarred);
  // Account-specific storage is kept server-side; reload when account changes.
  const originalOpenStars=openConversation;
  openConversation=async function(...args){
    if(starsLoadedFor!==state.me?.id){try{await loadStarred()}catch{}}
    return originalOpenStars.apply(this,args);
  };
  bar.addEventListener('click',async e=>{
    const btn=e.target.closest('button');
    if(!btn || btn.disabled || btn.hidden)return;
    const id=selectedId;
    if(btn.id==='hClearSelection'){clearSelection();return;}
    if(!id)return;
    if(btn.id==='hTopReply')startReply(id);
    if(btn.id==='hTopForward')forwardMessage(id);
    if(btn.id==='hTopCopy')await copyMessage();
    if(btn.id==='hTopStar')await toggleStar(id);
    if(btn.id==='hTopEdit')performOriginalAction(id,'edit');
    if(btn.id==='hTopDelete')performOriginalAction(id,'delete');
    if(btn.id==='hTopReport')performOriginalAction(id,'report');
  });

  const olderOpen=openConversation;
  openConversation=async function(id,...rest){
    if(activeConv()!==id){clearSelection();clearReply();}
    return olderOpen.call(this,id,...rest);
  };
  const olderWelcome=showWelcome;
  showWelcome=function(...args){clearSelection();clearReply();return olderWelcome.apply(this,args);};

  function installIcons(){
    const pairs=[['emojiBtn','smile'],['voiceNoteBtn','mic'],['shareLocationBtn','pin'],['sendBtn','send']];
    for(const [id,name] of pairs){
      const element=document.getElementById(id);
      if(!element||element.dataset.hIcon===name)continue;
      element.dataset.hIcon=name;
      element.innerHTML=svg(name,21);
      element.classList.add('h-tool-icon');
    }
    const file=document.querySelector('.composer label[for="mediaFileInput"]');
    if(file&&!file.dataset.hIcon){file.dataset.hIcon='clip';file.innerHTML=svg('clip',21);file.classList.add('h-tool-icon');}
  }
  installIcons();

  // Help automated interaction checks without exposing conversation content.
  window.HuddleMessageUI={selectMessage,startReply,clearReply,getReply:()=>replyTo,clearSelection,openStarred,loadStarred,isStarred:id=>starredIds.has(id)};
})();
