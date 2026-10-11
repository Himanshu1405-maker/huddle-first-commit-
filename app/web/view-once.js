/* View Once photos/videos: explicit POST, temporary in-memory object URL.
 * The server enforces redemption and deletes the stored blob after opening.
 * Browser screenshots/screen recordings cannot be reliably blocked.
 */
'use strict';
(()=>{
 const messages=document.getElementById('messages');
 if(!messages)return;
 let overlay=null,objectURL=null,openedFor=null;
 function close(){
   if(!overlay){if(objectURL){URL.revokeObjectURL(objectURL);objectURL=null;}openedFor=null;return;}
   const media=overlay.querySelector('video');
   if(media){media.pause();media.removeAttribute('src');media.load();}
   overlay.remove();overlay=null;
   if(objectURL){URL.revokeObjectURL(objectURL);objectURL=null;}
   openedFor=null;
   document.documentElement.classList.remove('h-once-showing');
 }
 async function open(button){
   const id=button.dataset.viewOnce;
   if(!/^[a-f0-9]{32}$/.test(id)||overlay||button.disabled)return;
   const room=state.active?.id;
   if(!room)return;
   const msg=state.messages.find(m=>m.attachments?.some(a=>a.id===id));
   const att=msg?.attachments?.find(a=>a.id===id);
   if(!att||!att.view_once||att.opened_at||msg.sender_id===state.me?.id)return;
   button.disabled=true;
   button.textContent='Opening…';
   try{
     const response=await fetch('/api/media/'+id+'/view-once',{
       method:'POST',credentials:'same-origin',cache:'no-store'
     });
     if(!response.ok){
       const detail=await response.json().catch(()=>null);
       throw Error(detail?.detail||'This media has already been opened or is unavailable.');
     }
     const blob=await response.blob();
     const isVideo=att.content_type.startsWith('video/');
     if(!blob.size||!(att.content_type.startsWith('image/')||isVideo))
       throw Error('This media could not be displayed.');
     objectURL=URL.createObjectURL(blob);
     att.opened_at=new Date().toISOString();
     if(state.active?.id!==room){close();return;}
     renderMessages(false);
     overlay=document.createElement('div');
     overlay.id='hViewOnceViewer';
     overlay.className='h-once-viewer';
     overlay.setAttribute('role','dialog');overlay.setAttribute('aria-modal','true');
     overlay.setAttribute('aria-label','View Once '+(isVideo?'video':'photo'));
     const top=document.createElement('header');
     top.className='h-once-viewer-head';
     const heading=document.createElement('div');
     const title=document.createElement('strong');title.textContent='① View Once';
     const note=document.createElement('small');note.textContent='This media cannot be opened again after closing.';
     heading.append(title,note);
     const exit=document.createElement('button');exit.type='button';exit.textContent='Close ✕';
     exit.setAttribute('aria-label','Close View Once media');exit.addEventListener('click',close);
     top.append(heading,exit);
     const stage=document.createElement('main');stage.className='h-once-stage';
     const media=document.createElement(isVideo?'video':'img');
     media.src=objectURL;
     if(isVideo){
       media.controls=true;media.playsInline=true;media.autoplay=false;
       media.controlsList='nodownload noplaybackrate';
       media.disablePictureInPicture=true;
       media.setAttribute('aria-label','View Once video');
     }else{
       media.alt='View Once photo';media.draggable=false;
     }
     stage.append(media);
     const foot=document.createElement('p');foot.className='h-once-warning';
     foot.textContent='View Once helps limit reopening, but does not prevent screenshots, recording, or another device photographing the screen.';
     overlay.append(top,stage,foot);document.body.append(overlay);
     document.documentElement.classList.add('h-once-showing');
     openedFor=id;
     exit.focus();
   }catch(error){
     // Some network errors can happen after the one-time server claim.
     // Never tell the recipient that retrying is guaranteed to work.
     if(typeof toast==='function')toast(String(error.message||'Unable to open View Once media.'),true);
   }finally{
     button.disabled=false;
     button.textContent='Open →';
   }
 }
 messages.addEventListener('click',e=>{
   const btn=e.target.closest('button[data-view-once]');
   if(btn){e.preventDefault();e.stopPropagation();void open(btn);}
 });
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&overlay)close();});
 window.HuddleViewOnce={close,isOpen:()=>!!overlay};
})();
