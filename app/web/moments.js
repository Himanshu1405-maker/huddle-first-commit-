/* Huddle Moments — private, expiring stories with text/photo/video,
   tap-through player, progress rings, hearts and reply-to-chat. */
'use strict';
(()=>{
 const $=id=>document.getElementById(id);
 const clean=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
 const paletteSet=new Set(['iris','lagoon','sunrise','midnight','peach','mint']);
 const page=$('hMomentsHome'),viewer=$('hMomentViewer'),compose=$('hMomentComposeOverlay');
 if(!page||!viewer||!compose)return;
 let entries=[],account='',sequence=[],index=0,playing=false,elapsed=0,duration=5500,lastTick=0,loop=null,previewUrl=null,mode='text',palette='iris',publishing=false;
 let pendingFile=null,lastFocused=null;
 let uploadRequest=null;
 const icon=name=>name==='video'?'▶':name==='image'?'▣':'✦';
 const timeAgo=date=>{
   const mins=Math.max(0,Math.floor((Date.now()-new Date(date).getTime())/60000));
   if(mins<1)return 'Just now';
   if(mins<60)return mins+'m ago';
   return Math.floor(mins/60)+'h ago';
 };
 const apiGet=path=>api(path);
 const safePalette=value=>paletteSet.has(value)?value:'iris';
 const groups=()=>{
   const by=new Map();
   for(const moment of entries){
     if(new Date(moment.expires_at).getTime()<=Date.now())continue;
     const key=moment.author_id;
     if(!by.has(key))by.set(key,[]);
     by.get(key).push(moment);
   }
   return [...by.values()].sort((a,b)=>{
     if(a[0].mine)return -1;
     if(b[0].mine)return 1;
     return Math.max(...b.map(v=>Date.parse(v.created_at)))-Math.max(...a.map(v=>Date.parse(v.created_at)));
   });
 };
 function tile(items,small=false){
   const first=items[0],unread=items.some(m=>!m.seen&&!m.mine);
   const latest=items[items.length-1];
   return '<button type="button" class="'+(small?'h-moment-strip-item':'h-moment-person')+
     '" data-moment-owner="'+clean(first.author_id)+'" aria-label="View '+clean(first.author_name)+' Moments">'+
     '<span class="h-moment-avatar-wrap '+(unread?'unseen':'seen')+'"><span class="h-moment-avatar-inner">'+
     clean(first.author_name.trim().split(/\s+/).slice(0,2).map(n=>n[0]).join('').toUpperCase())+'</span></span>'+
     '<span class="h-moment-person-text"><strong>'+clean(first.mine?(small?'You':'My Moments'):first.author_name)+'</strong>'+
     (!small?'<small>'+items.length+' '+(items.length===1?'update':'updates')+' · '+timeAgo(latest.created_at)+'</small>':'')+
     '</span></button>';
 }
 function render(){
   const all=groups(),mine=all.find(g=>g[0].mine),friends=all.filter(g=>!g[0].mine);
   $('hMyMoments').innerHTML='<button type="button" class="h-moment-my-add" id="hMomentCardCreate"><span>＋</span><strong>Add a Moment</strong><small>Text, photo or video</small></button>'+
     (mine?tile(mine):'<div class="h-moments-empty-small">Nothing shared yet. Make today memorable.</div>');
   $('hFriendMoments').innerHTML=friends.length?friends.map(g=>tile(g)).join(''):
      '<div class="h-moments-empty">✦<strong>It’s quiet right now.</strong><span>Moments from people you share a chat with will show up here.</span></div>';
   const strip=$('hMomentsStrip');
   if(strip)strip.innerHTML=(mine?'<div class="h-moment-own-group">'+tile(mine,true)+
       '<button id="hMomentsStart" class="h-moment-mini-create" type="button" aria-label="Add another Moment" title="Add Moment">＋</button></div>':
       '<button id="hMomentsStart" class="h-moment-strip-add" type="button" aria-label="Share your Moment"><span aria-hidden="true">＋</span><small>Add Moment</small></button>')+
       friends.slice(0,10).map(g=>tile(g,true)).join('');
 }
 async function refresh(){
   if(!state.me)return;
   const id=state.me.id;
   if(id!==account){account=id;entries=[];}
   try{
     const response=await apiGet('/moments');
     if(state.me?.id!==id)return;
     entries=response.moments||[];
     render();
   }catch(error){if(!state.me)return;toast('Could not load Moments: '+error.message,true)}
 }
 function showHome(){
   if(!state.me)return;
   if(typeof showWelcome==='function')showWelcome();
   $('welcomeChat').classList.add('hidden');
   $('conversationView').classList.add('hidden');
   page.classList.remove('hidden');
   $('headerIdentity').innerHTML='<span class="header-placeholder">✦ HUDDLE MOMENTS</span>';
   $('hMomentsNav').classList.add('selected');
   if(typeof syncChatNavigation==='function')syncChatNavigation();
   if(typeof mobileDrawer==='function')mobileDrawer(false);
   refresh();
 }
 function closeHome(){
   page.classList.add('hidden');
   $('hMomentsNav').classList.remove('selected');
 }
 function clearPreview(){
   if(previewUrl){URL.revokeObjectURL(previewUrl);previewUrl=null;}
   $('hMomentMediaPreview').replaceChildren();
   pendingFile=null;
   $('hMomentFile').value='';
 }
 function chooseMode(value){
   mode=value==='media'?'media':'text';
   $('hMomentTextFields').classList.toggle('hidden',mode!=='text');
   $('hMomentMediaFields').classList.toggle('hidden',mode!=='media');
   compose.querySelectorAll('[data-moment-type]').forEach(el=>el.classList.toggle('active',el.dataset.momentType===mode));
 }
 function openComposer(){
   if(!state.me)return;
   lastFocused=document.activeElement;
   compose.classList.remove('hidden');
   hideProgress();
   chooseMode('text');
   $('hMomentComposeError').classList.add('hidden');
   $('hMomentTextInput').value='';
   clearPreview();
   requestAnimationFrame(()=>$('hMomentTextInput').focus());
 }
 function closeComposer(){
   if(publishing)return;
   clearPreview();
   hideProgress();
   compose.classList.add('hidden');
   lastFocused?.focus?.();
 }
 function errorMessage(text){
   const target=$('hMomentComposeError');
   target.textContent=text;target.classList.remove('hidden');
 }
 function progressUI(percent,label,indeterminate=false){
   const box=$('hMomentUploadProgress');
   box.classList.remove('hidden');
   box.classList.toggle('h-is-indeterminate',indeterminate);
   $('hMomentUploadText').textContent=label;
   $('hMomentUploadPercent').textContent=indeterminate?'':percent+'%';
   $('hMomentUploadBar').style.width=indeterminate?'42%':percent+'%';
 }
 function hideProgress(){
   $('hMomentUploadProgress').classList.add('hidden');
   $('hMomentUploadProgress').classList.remove('h-is-indeterminate');
   $('hMomentUploadBar').style.width='0%';
   $('hMomentUploadPercent').textContent='0%';
 }
 function uploadMomentFile(file){
   return new Promise((resolve,reject)=>{
     const xhr=new XMLHttpRequest();
     uploadRequest=xhr;
     xhr.open('POST','/api/moments/media');
     xhr.withCredentials=true;
     xhr.setRequestHeader('Content-Type',file.type);
     xhr.upload.onprogress=event=>{
       if(event.lengthComputable&&event.total>0){
         const value=Math.min(99,Math.floor(event.loaded/event.total*100));
         progressUI(value,'Uploading your Moment…');
       }else progressUI(0,'Uploading your Moment…',true);
     };
     xhr.onload=()=>{
       uploadRequest=null;
       let response={};
       try{response=JSON.parse(xhr.responseText)}catch{}
       if(xhr.status>=200&&xhr.status<300)resolve(response);
       else reject(new Error(typeof response.detail==='string'?response.detail:'Could not upload your Moment'));
     };
     xhr.onerror=()=>{uploadRequest=null;reject(new Error('Upload interrupted. Check your connection and retry.'))};
     xhr.onabort=()=>{uploadRequest=null;reject(new Error('Upload cancelled'))};
     xhr.send(file);
   });
 }
 async function publish(){
   if(publishing)return;
   let path='/moments',options={};
   try{
     $('hMomentComposeError').classList.add('hidden');
     if(mode==='text'){
       const content=$('hMomentTextInput').value.trim();
       if(!content){errorMessage('Write a little something first.');return}
       options={method:'POST',body:JSON.stringify({text:content,palette})};
     }else{
       const file=pendingFile;
       if(!file){errorMessage('Choose a photo or video first.');return}
       if(file.size>24*1024*1024){errorMessage('Choose a file up to 24 MB.');return}
       if(!['image/jpeg','image/png','image/webp','video/mp4','video/webm'].includes(file.type)){
         errorMessage('Choose a JPG, PNG, WebP, MP4 or WebM file.');return;
       }
       path='/moments/media';
       options={method:'POST',headers:{'Content-Type':file.type},body:file};
     }
     publishing=true;
     const button=$('hMomentPublish');button.disabled=true;button.textContent='Sharing Moment…';
     progressUI(0,mode==='text'?'Publishing your Moment…':'Preparing your upload…',true);
     const response=mode==='text'?await api(path,options):await uploadMomentFile(pendingFile);
     if(!response?.id)throw Error('The Moment was not saved');
     progressUI(100,'Moment shared successfully');
     publishing=false;
     clearPreview();
     compose.classList.add('hidden');
     hideProgress();
     toast('✦ Your Moment is live for 24 hours');
     await refresh();
     showHome();
   }catch(error){hideProgress();errorMessage(error.message||'Could not share Moment')}
   finally{
     publishing=false;
     $('hMomentPublish').disabled=false;$('hMomentPublish').textContent='Post Moment ↗';
   }
 }
 function stopProgress(){
   playing=false;
   if(loop!==null){clearInterval(loop);loop=null}
   const video=$('hMomentContent').querySelector('video');
   if(video)video.pause();
 }
 function closeViewer(){
   stopProgress();
   viewer.classList.add('hidden');
   sequence=[];index=0;elapsed=0;
   document.removeEventListener('keydown',handleKeys);
 }
 function handleKeys(event){
   if(viewer.classList.contains('hidden'))return;
   if(event.key==='Escape'){event.preventDefault();closeViewer()}
   if(event.key==='ArrowLeft'){event.preventDefault();previous()}
   if(event.key==='ArrowRight'){event.preventDefault();next()}
 }
 function current(){return sequence[index]}
 async function begin(group,userIndex=0){
   if(!group?.length)return;
   closeViewer();
   sequence=[...group].sort((a,b)=>Date.parse(a.created_at)-Date.parse(b.created_at));
   index=Math.min(userIndex,sequence.length-1);
   viewer.classList.remove('hidden');
   document.addEventListener('keydown',handleKeys);
   await showCurrent();
 }
 function openOwner(owner){
   const list=groups().find(g=>g[0].author_id===owner);
   if(!list)return;
   const sorted=[...list].sort((a,b)=>Date.parse(a.created_at)-Date.parse(b.created_at));
   const start=Math.max(0,sorted.findIndex(m=>!m.seen));
   begin(sorted,start);
 }
 function refreshProgress(){
   const root=$('hMomentProgress');root.innerHTML=sequence.map((_,i)=>
     '<span class="h-moment-progress-rail"><i style="width:'+(i<index?'100':i>index?'0':Math.round(Math.min(1,elapsed/duration)*100))+'%"></i></span>').join('');
 }
 async function showCurrent(){
   stopProgress();
   const moment=current();if(!moment){closeViewer();return}
   if(new Date(moment.expires_at).getTime()<=Date.now()){next();return}
   elapsed=0;duration=moment.kind==='text'?5600:moment.kind==='image'?6800:18000;
   $('hMomentAvatar').textContent=moment.author_name.split(/\s+/).slice(0,2).map(n=>n[0]).join('').toUpperCase();
   $('hMomentAuthor').textContent=moment.mine?'Your Moment':moment.author_name;
   $('hMomentPosted').textContent=timeAgo(moment.created_at);
   $('hMomentPrev').disabled=index===0;
   $('hMomentNext').textContent=index===sequence.length-1?'×':'›';
   $('hMomentDelete').classList.toggle('hidden',!moment.mine);
   $('hMomentReply').classList.toggle('hidden',!!moment.mine);
   $('hMomentViews').textContent=moment.mine?'◉ '+moment.views+' views':'';
   $('hMomentHeart').classList.toggle('active',moment.hearted);
   $('hMomentHeart').setAttribute('aria-pressed',String(moment.hearted));
   $('hMomentHeart').setAttribute('aria-label',moment.hearted?'Unlike Moment':'Like Moment');
   $('hMomentHeart').firstChild.textContent=moment.hearted?'♥ ':'♡ ';
   $('hMomentHeartCount').textContent=moment.hearts||'';
   const stage=$('hMomentStage'),content=$('hMomentContent');
   stage.className='h-moment-stage h-moment-palette-'+safePalette(moment.palette);
   content.replaceChildren();
   if(moment.kind==='text'){
     const span=document.createElement('div');span.className='h-moment-text-story';
     span.textContent=moment.text;content.append(span);
   }else {
     const src='/api/moments/'+encodeURIComponent(moment.id)+'/media';
     const media=document.createElement(moment.kind==='video'?'video':'img');
     media.className='h-moment-media';
     media.src=src;
     if(moment.kind==='video'){
       media.playsInline=true;media.autoplay=true;media.muted=false;
       media.controls=true;media.preload='metadata';
       media.addEventListener('play',()=>{playing=true;lastTick=performance.now()});
       media.addEventListener('pause',()=>{playing=false});
       media.addEventListener('loadedmetadata',()=>{
         if(current()?.id!==moment.id)return;
         const seconds=Number.isFinite(media.duration)?Math.min(30,Math.max(4,media.duration)):18;
         duration=seconds*1000;
       });
       media.addEventListener('ended',()=>{if(current()?.id===moment.id)next()});
       media.addEventListener('error',()=>toast('Video could not be played',true));
     }else media.alt='Moment shared by '+moment.author_name;
     content.append(media);
   }
   refreshProgress();
   try{
     if(!moment.mine&&!moment.seen){
       await api('/moments/'+encodeURIComponent(moment.id)+'/view',{method:'POST'});
       moment.seen=true;
     }
   }catch{}
   if(viewer.classList.contains('hidden')||current()?.id!==moment.id)return;
   playing=true;lastTick=performance.now();
   const video=content.querySelector('video');
   if(video)video.play().catch(()=>{playing=false;/* browser requires user to tap Play */});
   loop=setInterval(()=>{
     if(!playing||viewer.classList.contains('hidden'))return;
     const momentNow=performance.now();
     const delta=Math.max(0,Math.min(momentNow-lastTick,300));
     lastTick=momentNow;
     elapsed+=delta;
     if(video && Number.isFinite(video.duration)&&video.duration>0&&video.currentTime>0){
       elapsed=Math.max(elapsed,video.currentTime*1000);
     }
     refreshProgress();
     if(elapsed>=duration)next();
   },75);
 }
 function next(){
   if(index+1>=sequence.length){closeViewer();refresh();return}
   index++;showCurrent();
 }
 function previous(){
   if(index===0){elapsed=0;showCurrent();return}
   index--;showCurrent();
 }
 function pause(){
   if(!playing)return;
   playing=false;$('hMomentContent').querySelector('video')?.pause();
 }
 function resume(){
   if(playing)return;
   playing=true;lastTick=performance.now();
   $('hMomentContent').querySelector('video')?.play().catch(()=>{});
 }
 async function heart(){
   const moment=current();if(!moment)return;
   try{
     const response=await api('/moments/'+encodeURIComponent(moment.id)+'/heart',
       {method:moment.hearted?'DELETE':'PUT'});
     moment.hearted=!!response.hearted;
     moment.hearts=Math.max(0,(moment.hearts||0)+(moment.hearted?1:-1));
     $('hMomentHeart').classList.toggle('active',moment.hearted);
     $('hMomentHeart').firstChild.textContent=moment.hearted?'♥ ':'♡ ';
     $('hMomentHeartCount').textContent=moment.hearts||'';
   }catch(error){toast(error.message,true)}
 }
 async function remove(){
   const moment=current();
   if(!moment?.mine)return;
   if(!confirm('Delete this Moment now?'))return;
   try{
     await api('/moments/'+encodeURIComponent(moment.id),{method:'DELETE'});
     entries=entries.filter(m=>m.id!==moment.id);
     sequence=sequence.filter(m=>m.id!==moment.id);
     if(index>=sequence.length)index=sequence.length-1;
     if(index<0)closeViewer();else showCurrent();
     render();toast('Moment removed');
   }catch(error){toast(error.message,true)}
 }
 async function reply(){
   const moment=current();if(!moment||moment.mine)return;
   closeViewer();
   try{
     let dm=state.conversations.find(c=>c.kind==='dm'&&c.members.some(m=>m.id===moment.author_id));
     if(!dm){
       const result=await post('/conversations/direct',{user_id:moment.author_id});
       dm=result.conversation;
       if(!state.conversations.some(c=>c.id===dm.id))state.conversations.unshift(dm);
     }
     await openConversation(dm.id);
     const input=$('messageInput');
     input.value=moment.kind==='text'?'↳ Your Moment: "'+moment.text.slice(0,70)+'" — ':'↳ Your Moment '+(moment.kind==='video'?'🎬':'📸')+' — ';
     input.dispatchEvent(new Event('input',{bubbles:true}));
     input.focus();
   }catch(error){toast('Could not open that chat: '+error.message,true)}
 }
 function onInbox(){closeHome();if(state.me)refresh()}
 function nav(){
   $('hMomentsNav')?.addEventListener('click',showHome);
   $('hMomentsSeeAll')?.addEventListener('click',showHome);
   $('hMomentCreate')?.addEventListener('click',openComposer);
   $('hMomentComposeClose')?.addEventListener('click',closeComposer);
   $('hMomentPublish')?.addEventListener('click',publish);
   $('hMomentViewerClose')?.addEventListener('click',closeViewer);
   $('hMomentNext')?.addEventListener('click',next);
   $('hMomentPrev')?.addEventListener('click',previous);
   $('hMomentHeart')?.addEventListener('click',heart);
   $('hMomentReply')?.addEventListener('click',reply);
   $('hMomentDelete')?.addEventListener('click',remove);
   document.addEventListener('click',e=>{
     if(e.target.closest('#hMomentCardCreate,#hMomentsStart'))openComposer();
     const node=e.target.closest('[data-moment-owner]');
     if(node)openOwner(node.dataset.momentOwner);
   });
   compose.addEventListener('click',e=>{if(e.target===compose)closeComposer()});
   compose.querySelectorAll('[data-moment-type]').forEach(el=>el.addEventListener('click',()=>chooseMode(el.dataset.momentType)));
   compose.querySelectorAll('[data-palette]').forEach(el=>el.addEventListener('click',()=>{
     palette=safePalette(el.dataset.palette);
     compose.querySelectorAll('[data-palette]').forEach(n=>n.classList.toggle('active',n===el));
     $('hMomentTextInput').dataset.palette=palette;
   }));
   $('hMomentFile')?.addEventListener('change',event=>{
     const file=event.target.files?.[0];
     // Revoke only the previous blob preview; keep the newly selected File.
     if(previewUrl){URL.revokeObjectURL(previewUrl);previewUrl=null}
     $('hMomentMediaPreview').replaceChildren();
     if(!file)return;
     if(file.size>24*1024*1024){errorMessage('Use a file up to 24 MB');return}
     pendingFile=file;previewUrl=URL.createObjectURL(file);
     const el=document.createElement(file.type.startsWith('video/')?'video':'img');
     el.src=previewUrl;el.className='h-moment-upload-preview';
     if(el.tagName==='VIDEO'){el.controls=true;el.playsInline=true}
     $('hMomentMediaPreview').append(el);
   });
   viewer.addEventListener('click',e=>{if(e.target===viewer)closeViewer()});
   let touchX=0;
   $('hMomentStage').addEventListener('touchstart',e=>{touchX=e.touches[0].clientX},{passive:true});
   $('hMomentStage').addEventListener('touchend',e=>{
     const dx=e.changedTouches[0].clientX-touchX;
     if(Math.abs(dx)>65){dx<0?next():previous()}
   },{passive:true});
   $('hMomentContent').addEventListener('pointerdown',pause);
   $('hMomentContent').addEventListener('pointerup',resume);
   $('hMomentContent').addEventListener('pointercancel',resume);
   document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();else if(!viewer.classList.contains('hidden'))resume()});
   $('hMomentViewerClose').addEventListener('keydown',e=>{if(e.key==='Escape')closeViewer()});
 }
 nav();
 window.HuddleMoments={open:showHome,refresh,onInbox,openComposer,closeViewer,openOwner};
})();
