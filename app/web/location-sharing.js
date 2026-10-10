/* Opt-in location cards. GPS is accessed only after the sender taps Share. */
'use strict';
(function () {
  const activeMaps = new Set();
  let watchId = null;
  let myLiveMessageId = null;
  let lastSent = 0;
  let updateBusy = false;
  const button = document.createElement('button');
  button.type = 'button';
  button.id = 'shareLocationBtn';
  button.className = 'composer-media location-trigger';
  button.textContent = '📍';
  button.title = 'Share current or live location';
  button.setAttribute('aria-label', 'Share location');
  const composer = document.querySelector('#conversationView .composer');
  const fileInput = document.getElementById('mediaFileInput');
  if (composer && fileInput) composer.insertBefore(button, fileInput.nextSibling);

  function fmtTime(iso) {
    return iso ? new Date(iso).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'}) : '';
  }
  function geoAvailable() {
    if (!window.isSecureContext || !navigator.geolocation) {
      toast('Location sharing requires HTTPS and browser GPS permission.', true);
      return false;
    }
    return true;
  }
  function getPosition() {
    return new Promise((resolve,reject) => navigator.geolocation.getCurrentPosition(
      resolve, reject, {enableHighAccuracy:true, timeout:18000, maximumAge:0}
    ));
  }
  function reportGeoError(error) {
    const message = error && error.code===1 ? 'Location permission was denied. Allow location access in your browser settings.' :
      error && error.code===3 ? 'GPS timed out. Try near a window or outdoors.' :
      'Unable to get your location. Check GPS and browser permissions.';
    toast(message,true);
  }
  function payload(coords) {
    return {latitude:coords.latitude,longitude:coords.longitude,
      accuracy_m:Number.isFinite(coords.accuracy)?Math.min(100000,Math.max(0,coords.accuracy)):null};
  }
  function ingest(message) {
    if (!message || state.active?.id!==message.conversation_id) return;
    const index = state.messages.findIndex(m=>m.id===message.id);
    if (index===-1) state.messages.push(message);
    else state.messages[index]=message;
    renderMessages(true);
  }
  function clearGps() {
    if (watchId!==null) navigator.geolocation.clearWatch(watchId);
    watchId=null;myLiveMessageId=null;lastSent=0;updateBusy=false;
  }
  function beginWatching(messageId) {
    clearGps();
    myLiveMessageId=messageId;
    lastSent=Date.now();
    watchId=navigator.geolocation.watchPosition(async position=>{
      if (myLiveMessageId!==messageId || Date.now()-lastSent<8000 || updateBusy) return;
      lastSent=Date.now();updateBusy=true;
      try {
        const result=await patch('/locations/'+encodeURIComponent(messageId),payload(position.coords));
        ingest(result.message);
      } catch(err) {
        if (/not found|expired|sign in/i.test(err.message)) clearGps();
        else toast('Live location update failed: '+err.message,true);
      } finally {updateBusy=false;}
    }, err=>{
      reportGeoError(err);
      stopLive(messageId).catch(()=>{});
    }, {enableHighAccuracy:true,maximumAge:0,timeout:25000});
  }
  async function stopLive(messageId) {
    try {
      const result=await post('/locations/'+encodeURIComponent(messageId)+'/stop',{});
      if (myLiveMessageId===messageId) clearGps();
      ingest(result.message);
      toast('Live location sharing stopped');
    } catch(err) {toast(err.message,true);}
  }
  function closeSheet() {
    document.getElementById('hLocationOverlay')?.remove();
  }
  button.addEventListener('click',()=>{
    if (!state.active) {toast('Open a conversation to share location.',true);return;}
    if (!geoAvailable()) return;
    closeSheet();
    const overlay=document.createElement('div');
    overlay.id='hLocationOverlay';
    overlay.className='h-location-overlay';
    overlay.innerHTML='<section class="h-location-sheet" role="dialog" aria-modal="true" aria-labelledby="hLocationTitle">'+
      '<div class="h-location-head"><div><small>HUDDLE / LOCATION</small><h2 id="hLocationTitle">Share your location</h2></div>'+
      '<button type="button" id="hLocationClose" aria-label="Close">×</button></div>'+
      '<label class="h-location-choice"><input type="radio" name="hLocationMode" value="pin" checked> 📍 Send my current location <span>One-time map pin</span></label>'+
      '<label class="h-location-choice"><input type="radio" name="hLocationMode" value="live"> 🟢 Share live location <span>Updates while Huddle is open</span></label>'+
      '<div id="hLocationDuration" class="h-location-duration" hidden><label for="hLocationMinutes">Sharing duration</label>'+
      '<select id="hLocationMinutes"><option value="15">15 minutes</option><option value="60">1 hour</option><option value="480">8 hours</option></select></div>'+
      '<p class="h-location-privacy">Only members of this conversation can see the shared location. '+
      'Live updates require this browser to stay open. Stop sharing whenever you want. '+
      'Share your exact location only with people you trust.</p>'+
      '<button type="button" id="hLocationShare" class="h-location-submit">Share location →</button></section>';
    document.body.append(overlay);
    overlay.addEventListener('click',event=>{if(event.target===overlay)closeSheet()});
    overlay.querySelector('#hLocationClose').addEventListener('click',closeSheet);
    overlay.querySelectorAll('[name="hLocationMode"]').forEach(radio=>
      radio.addEventListener('change',()=>{overlay.querySelector('#hLocationDuration').hidden=!overlay.querySelector('[value="live"]').checked})
    );
    overlay.querySelector('#hLocationShare').addEventListener('click',async()=>{
      const send=overlay.querySelector('#hLocationShare');
      const mode=overlay.querySelector('[name="hLocationMode"]:checked').value;
      const duration=Number(overlay.querySelector('#hLocationMinutes').value);
      const conversationId=state.active?.id;
      if (!conversationId) return;
      send.disabled=true;send.textContent='Requesting GPS permission…';
      try {
        const pos=await getPosition();
        send.textContent='Sharing securely…';
        const result=await post('/conversations/'+encodeURIComponent(conversationId)+'/locations',
          {mode,...payload(pos.coords),duration_minutes:duration});
        closeSheet();
        ingest(result.message);
        if (mode==='live') beginWatching(result.message.id);
        toast(mode==='live'?'Live location started. Keep Huddle open for updates.':'Current location sent');
      } catch(err) {
        if (err && typeof err.code==='number') reportGeoError(err);
        else toast(err.message||'Could not share location',true);
        send.disabled=false;send.textContent='Share location →';
      }
    });
  });

  function mapURL(lat,lon) {
    return 'https://www.openstreetmap.org/?mlat='+encodeURIComponent(lat)+'&mlon='+encodeURIComponent(lon)+'#map=16/'+lat+'/'+lon;
  }
  function iframeURL(lat,lon) {
    const spread=0.009;
    return 'https://www.openstreetmap.org/export/embed.html?bbox='+
      encodeURIComponent((lon-spread)+','+(lat-spread)+','+(lon+spread)+','+(lat+spread))+
      '&layer=mapnik&marker='+encodeURIComponent(lat+','+lon);
  }
  function decorateLocations() {
    if (!state.me) return;
    for (const message of state.messages) {
      if (!message.location || message.deleted_at) continue;
      const row=document.getElementById('msg-'+message.id);
      if (!row) continue;
      const card=document.createElement('div');
      card.className='h-location-card';
      const loc=message.location;
      const live=loc.mode==='live';
      const active=live&&loc.active&&Date.parse(loc.expires_at)>Date.now();
      const coords=loc.latitude!==null&&loc.longitude!==null&&(!live||active);
      const mine=message.sender_id===state.me.id;
      const label=live ? (active?'Live location':'Live location ended') : 'Current location';
      let inside='<div class="h-location-map">';
      if (coords && activeMaps.has(message.id)) {
        inside+='<iframe title="Shared map location" loading="lazy" referrerpolicy="no-referrer" '+
          'src="'+iframeURL(loc.latitude,loc.longitude)+'"></iframe>';
      } else {
        inside+='<div class="h-location-art"><span>📍</span><small>'+(coords?'Map preview available':'Location no longer available')+'</small></div>';
      }
      inside+='</div><div class="h-location-card-body"><div class="h-location-card-title">'+
        (active?'<span class="h-location-live-dot"></span>':'')+label+'</div>'+
        '<p>'+(active?'Updated '+fmtTime(loc.updated_at)+' · Ends '+fmtTime(loc.expires_at):
          live?'This live share has stopped.':'Tap to see this place on a map.')+'</p>';
      if (coords) {
        inside+='<div class="h-location-actions">'+
          '<button type="button" data-h-location-map="'+esc(message.id)+'">'+
          (activeMaps.has(message.id)?'Hide map':'View map')+'</button>'+
          '<a href="'+mapURL(loc.latitude,loc.longitude)+'" target="_blank" rel="noopener noreferrer">Open in Maps ↗</a></div>';
      }
      if (mine && active) inside+='<button type="button" class="h-location-stop" data-h-location-stop="'+esc(message.id)+'">■ Stop sharing</button>';
      inside+='</div>';
      card.innerHTML=inside;
      const bubble=row.querySelector('.bubble');
      if (bubble) bubble.hidden=true;
      const stack=row.querySelector('.message-stack');
      if (stack) stack.insertBefore(card,stack.querySelector('.bubble-meta'));
    }
  }
  const originalRender=renderMessages;
  renderMessages=function(...args) {originalRender(...args);decorateLocations();};
  document.getElementById('messages')?.addEventListener('click',event=>{
    const map=event.target.closest('[data-h-location-map]');
    if (map) {
      const id=map.dataset.hLocationMap;
      if (activeMaps.has(id)) activeMaps.delete(id);else activeMaps.add(id);
      renderMessages(false);
      return;
    }
    const stop=event.target.closest('[data-h-location-stop]');
    if (stop) {
      stop.disabled=true;
      stopLive(stop.dataset.hLocationStop);
    }
  });
  document.addEventListener('visibilitychange',()=>{
    if (document.visibilityState==='visible'&&state.active) {
      const remaining=state.messages.some(m=>m.location?.mode==='live');
      if (remaining) decorateLocationStatus();
    }
  });
  function decorateLocationStatus() {
    // Re-check timeouts without waiting for a fresh WebSocket packet.
    if (state.active) renderMessages(false);
  }
  setInterval(()=>{if(state.active&&state.messages.some(m=>m.location?.active))decorateLocationStatus()},30000);
  window.addEventListener('pagehide',()=>{
    if (!myLiveMessageId) return;
    const id=myLiveMessageId;
    clearGps();
    try{navigator.sendBeacon('/api/locations/'+encodeURIComponent(id)+'/stop',new Blob([],{type:'text/plain'}));}
    catch{}
  });
})();
