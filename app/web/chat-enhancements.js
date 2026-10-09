/* Huddle interaction upgrades: optional image editor, contextual actions, emoji and motion stickers.
   Uses the existing authenticated API and leaves existing conversations unchanged. */
'use strict';

const HUDDLE_EMOJI_GROUPS={
  'Smileys':'😀 😃 😄 😁 😆 😅 😂 🤣 😊 😇 🙂 🙃 😉 😌 😍 🥰 😘 😗 😙 😚 😋 😛 😜 🤪 😝 🤑 🤗 🤭 🫢 🤫 🤔 🫡 🤐 🤨 😐 😑 😶 😏 😒 🙄 😬 😮‍💨 😴 🥱 😷 🤒 🤕 🥳 😎 🤓 🥹 😢 😭 😤 😡 🤯 😱 🫠'.split(' '),
  'Gestures':'👍 👎 👏 🙌 👐 🤲 🤝 🙏 💪 👊 ✊ 🤛 🤜 ✌️ 🤞 🫰 🤟 🤘 👌 🤏 👈 👉 👆 👇 ☝️ ✋ 🤚 🖐️ 🖖 👋 🫶 💅'.split(' '),
  'Love':'❤️ 🧡 💛 💚 💙 💜 🖤 🤍 🤎 💖 💗 💓 💞 💕 💘 💝 💟 ❣️ 💔 ❤️‍🔥 💌 🌹 🪷 🌸 🌷'.split(' '),
  'Nature':'🌼 🌻 🍀 🌿 🌱 🌳 🌴 🍁 🍂 🌊 🌍 🌎 ⭐ 🌟 ✨ 🌙 ☀️ 🌈 ☁️ ❄️ 🔥 💧 🐶 🐱 🐼 🦋 🐝 🦄'.split(' '),
  'Food':'🍕 🍔 🍟 🍣 🍜 🍝 🥗 🥪 🥐 🍩 🍪 🎂 🍰 🍓 🍉 🍊 🍋 🍒 🍎 🍇 ☕ 🧋 🥛'.split(' '),
  'Activity':'⚽ 🏀 🏏 🏸 🎮 🎲 🎧 🎤 🎸 🎨 🎬 📷 💻 📱 📚 📝 💡 🚀 ✈️ 🚲 🏆 🥇 🎯 🎉 🎊 🎁 ✅ 💯 🤩'.split(' ')
};
const HUDDLE_STICKERS=['🥳','🚀','💖','🔥','🎉','✨','😎','🫶','😂','🙌','💯','🌈','🤩','💪','👏','💜','🌟','🎂','🦄','👀','🌻','🎸'];
const STICKER_PREFIX='[[huddle-sticker:';
let emojiTab='Smileys';

function drawEmojiPicker(query=''){
  const picker=$('#emojiPicker');
  if(!picker)return;
  const tabs=[...Object.keys(HUDDLE_EMOJI_GROUPS),'Stickers'];
  const values=emojiTab==='Stickers'?HUDDLE_STICKERS:(HUDDLE_EMOJI_GROUPS[emojiTab]||[]);
  // Text search by associated common keywords, with the emoji itself also searchable.
  const synonyms={'❤️':'heart love','😂':'laugh happy','🥰':'love heart','🥳':'celebrate party','🎉':'celebrate party','👍':'thumbs yes','🔥':'fire','🙏':'thanks please','😢':'sad crying','🚀':'rocket','💖':'heart','🌈':'rainbow','😊':'smile','😎':'cool','🤔':'thinking','📚':'study','💪':'strong','✨':'sparkle','🫶':'love'};
  const items=query?values.filter(emoji=>emoji.includes(query)||((synonyms[emoji]||'').includes(query.toLowerCase()))):values;
  picker.innerHTML='<div class="h-emoji-tabs">'+tabs.map(name=>'<button type="button" data-emoji-tab="'+esc(name)+'" class="'+(emojiTab===name?'selected':'')+'">'+esc(name)+'</button>').join('')+'</div>'+
    '<div class="h-emoji-search"><input id="hEmojiSearch" aria-label="Search emoji" placeholder="Search emoji…" maxlength="25"></div>'+
    '<div class="h-emoji-grid">'+items.map(emoji=>'<button type="button" data-'+(emojiTab==='Stickers'?'sticker':'emoji')+'="'+esc(emoji)+'" aria-label="'+(emojiTab==='Stickers'?'Send animated sticker':'Insert emoji')+' '+esc(emoji)+'" class="'+(emojiTab==='Stickers'?'sticker-option':'')+'">'+esc(emoji)+'</button>').join('')+'</div>'+
    (emojiTab==='Stickers'?'<p class="sticker-note">Animated Huddle stickers · tap to send</p>':'');
  const input=$('#hEmojiSearch');
  input.value=query;
  input.addEventListener('input',e=>{const start=e.target.selectionStart;drawEmojiPicker(e.target.value);$('#hEmojiSearch')?.focus();$('#hEmojiSearch')?.setSelectionRange(start,start)});
}
function handleEmojiPickerClick(e){
  const btn=e.target.closest('button');
  if(!btn)return;
  if(btn.dataset.emojiTab){emojiTab=btn.dataset.emojiTab;drawEmojiPicker();return}
  const emoji=btn.dataset.emoji;
  if(emoji){const input=$('#messageInput');input.setRangeText(emoji,input.selectionStart,input.selectionEnd,'end');resizeComposer();input.focus();return;}
  if(btn.dataset.sticker){sendSticker(btn.dataset.sticker);}
}
async function sendSticker(emoji){
  if(!state.active||!HUDDLE_STICKERS.includes(emoji))return;
  const cid=state.active.id;
  $('#emojiPicker').classList.add('hidden');
  try{
    await post('/conversations/'+encodeURIComponent(cid)+'/messages',{body:STICKER_PREFIX+emoji+']]'});
    if(!state.connected&&state.active?.id===cid)await openConversation(cid);
  }catch(error){toast(error.message,true);}
}
drawEmojiPicker();

function decorateHuddleMessages(){
  if(!state.active||!state.me)return;
  for(const msg of state.messages){
    const row=document.getElementById('msg-'+msg.id);
    if(!row)continue;
    const bubble=row.querySelector('.bubble');
    if(!bubble||msg.deleted_at)continue;
    const attachments=msg.attachments||[];
    const first=attachments[0];
    if(first){
      const marker=first.content_type.startsWith('image/')?'🖼️':first.content_type.startsWith('video/')?'🎬':first.content_type.startsWith('audio/')?'🎤':'📎';
      const prefix=marker+' '+first.filename;
      if(msg.body===prefix){bubble.hidden=true;row.classList.add('has-attachment');}
      else if(msg.body.startsWith(prefix+'\n')){
        bubble.textContent=msg.body.slice(prefix.length+1);
        row.classList.add('has-attachment');
      }
    }else if(msg.body.startsWith(STICKER_PREFIX)&&msg.body.endsWith(']]')){
      const emoji=msg.body.slice(STICKER_PREFIX.length,-2);
      if(HUDDLE_STICKERS.includes(emoji)){
        bubble.textContent=emoji;
        bubble.classList.add('h-animated-sticker');
        bubble.setAttribute('aria-label','Animated '+emoji+' sticker');
      }
    }
    bubble.dataset.huddleMessageId=msg.id;
    bubble.tabIndex=0;
    bubble.setAttribute('role','button');
    bubble.setAttribute('aria-label','Message options: double-tap, press and hold, or right click');
  }
}
// Existing event handlers invoke this binding dynamically. No markup or migrations required.
const _huddleBaseRenderMessages=renderMessages;
renderMessages=function(...args){_huddleBaseRenderMessages(...args);decorateHuddleMessages();};

let huddleContextMenu=null;
function closeHuddleContextMenu(){
  huddleContextMenu?.remove();huddleContextMenu=null;
}
async function chooseReaction(mid,emoji){
  closeHuddleContextMenu();
  await applyReaction(mid,emoji);
}
function openHuddleContextMenu(messageId,anchor){
  closeHuddleContextMenu();
  const message=state.messages.find(m=>m.id===messageId);
  if(!message||message.deleted_at)return;
  const mine=message.sender_id===state.me?.id;
  const menu=document.createElement('div');
  menu.className='h-message-menu';menu.setAttribute('role','menu');
  menu.innerHTML='<div class="h-message-reactions">'+['❤️','😂','😮','👍','🙏','🔥','🥰','🎉'].map(e=>'<button type="button" data-h-reaction="'+esc(e)+'" aria-label="React '+esc(e)+'">'+esc(e)+'</button>').join('')+
    '</div><div class="h-message-commands">'+
    (mine?'<button type="button" data-h-command="edit">✎ Edit message</button><button type="button" data-h-command="delete" class="danger">🗑 Delete for everyone</button>':
    '<button type="button" data-h-command="report">⚑ Report message</button>')+
    '<button type="button" data-h-command="copy">⧉ Copy text</button></div>';
  document.body.append(menu);
  huddleContextMenu=menu;
  const rect=anchor.getBoundingClientRect();
  menu.style.left=Math.max(8,Math.min(window.innerWidth-menu.offsetWidth-8,rect.left))+'px';
  menu.style.top=Math.max(8,Math.min(window.innerHeight-menu.offsetHeight-8,rect.top-menu.offsetHeight-12))+'px';
  menu.addEventListener('click',async e=>{
    const r=e.target.closest('[data-h-reaction]');if(r){await chooseReaction(messageId,r.dataset.hReaction);return}
    const command=e.target.closest('[data-h-command]')?.dataset.hCommand;
    if(!command)return;closeHuddleContextMenu();
    if(command==='copy'){
      try{await navigator.clipboard.writeText(message.body);toast('Copied to clipboard');}
      catch{toast('Clipboard unavailable',true)}
      return;
    }
    const original=anchor.closest('.message-row')?.querySelector('.message-actions [data-action="'+command+'"]');
    if(original)original.click();
  });
}
let huddleHoldTimer=null,huddleHoldStart=null;
$('#messages').addEventListener('contextmenu',e=>{
  const bubble=e.target.closest('.bubble');
  if(!bubble||bubble.closest('.deleted'))return;
  e.preventDefault();openHuddleContextMenu(bubble.dataset.huddleMessageId,bubble);
});
$('#messages').addEventListener('pointerdown',e=>{
  const bubble=e.target.closest('.bubble');
  if(!bubble||e.button!==0||!bubble.dataset.huddleMessageId)return;
  huddleHoldStart={x:e.clientX,y:e.clientY};
  clearTimeout(huddleHoldTimer);
  huddleHoldTimer=setTimeout(()=>openHuddleContextMenu(bubble.dataset.huddleMessageId,bubble),530);
});
['pointerup','pointercancel','pointerleave'].forEach(type=>$('#messages').addEventListener(type,()=>clearTimeout(huddleHoldTimer)));
$('#messages').addEventListener('pointermove',e=>{
  if(huddleHoldStart&&Math.hypot(e.clientX-huddleHoldStart.x,e.clientY-huddleHoldStart.y)>9)clearTimeout(huddleHoldTimer);
});
$('#messages').addEventListener('dblclick',e=>{const bubble=e.target.closest('.bubble');if(bubble?.dataset.huddleMessageId)openHuddleContextMenu(bubble.dataset.huddleMessageId,bubble);});
$('#messages').addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('.bubble[data-huddle-message-id]')){e.preventDefault();openHuddleContextMenu(e.target.dataset.huddleMessageId,e.target)}});
document.addEventListener('pointerdown',e=>{if(huddleContextMenu&&!huddleContextMenu.contains(e.target))closeHuddleContextMenu()},{capture:true});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeHuddleContextMenu()});
window.addEventListener('scroll',closeHuddleContextMenu,true);

let mediaEditorDialog=null;
function closeMediaEditor(){
  if(!mediaEditorDialog)return;
  mediaEditorDialog.remove();mediaEditorDialog=null;
  $('#mediaFileInput').value='';
}
async function openMediaEditor(file){
  if(!file)return;
  if(mediaEditorDialog)closeMediaEditor();
  const isImage=file.type.startsWith('image/');
  const isVideo=file.type.startsWith('video/');
  const max=isVideo?20:6;
  if(file.size>max*1024*1024){toast('Maximum file size is '+max+' MB.',true);$('#mediaFileInput').value='';return;}
  const dialog=document.createElement('div');
  dialog.className='h-editor-overlay';
  dialog.setAttribute('role','dialog');dialog.setAttribute('aria-modal','true');dialog.setAttribute('aria-label','Preview file before sharing');
  dialog.innerHTML='<section class="h-editor-panel"><header class="h-editor-head"><div><small>PREVIEW BEFORE SENDING</small><h2>Ready to share?</h2></div><button type="button" class="h-editor-close" aria-label="Cancel upload">✕</button></header>'+
    '<div class="h-editor-stage" id="hEditorStage"></div>'+
    '<div class="h-editor-tools" id="hEditorTools"></div>'+
    '<div class="h-editor-bottom"><label>Caption <span>(optional)</span><textarea id="hEditorCaption" rows="2" maxlength="500" placeholder="Add a message with your file…"></textarea></label>'+
    '<div class="h-editor-footer"><span id="hEditorFilename"></span><div><button type="button" id="hEditorCancel" class="h-editor-secondary">Cancel</button><button type="button" id="hEditorSend" class="h-editor-submit">Send ↗</button></div></div></div></section>';
  document.body.append(dialog);
  mediaEditorDialog=dialog;
  dialog.querySelector('.h-editor-close').addEventListener('click',closeMediaEditor);
  dialog.querySelector('#hEditorCancel').addEventListener('click',closeMediaEditor);
  dialog.addEventListener('click',e=>{if(e.target===dialog)closeMediaEditor()});
  dialog.querySelector('#hEditorFilename').textContent=file.name;
  const stage=dialog.querySelector('#hEditorStage');
  const tools=dialog.querySelector('#hEditorTools');
  let buildFile=()=>Promise.resolve(file);
  let resource=null;
  const cleanup=()=>{if(resource)URL.revokeObjectURL(resource);};
  if(isImage){
    resource=URL.createObjectURL(file);
    const image=new Image();
    try{await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;image.src=resource;});}
    catch{cleanup();closeMediaEditor();toast('Could not preview this picture.',true);return}
    if(mediaEditorDialog!==dialog){cleanup();return}
    const canvas=document.createElement('canvas');
    canvas.className='h-photo-canvas';canvas.setAttribute('aria-label','Photo preview and markup canvas');
    const context=canvas.getContext('2d');
    if(!context){cleanup();closeMediaEditor();toast('Image editing is not supported here.',true);return}
    stage.append(canvas);
    let ratio=0,zoom=1,rot=0,flipped=false,panX=0,panY=0,pen=false,strokes=[],line=null;
    const maxOutput=1200;
    const render=()=>{
      const originalRatio= (rot%180===0?image.width/image.height:image.height/image.width);
      const useRatio=ratio||originalRatio;
      canvas.width=Math.min(maxOutput,Math.max(240,Math.round(maxOutput*Math.min(1,useRatio))));
      canvas.height=Math.min(maxOutput,Math.max(240,Math.round(canvas.width/useRatio)));
      // Ensure the photo can cover every output pixel at every rotation.
      const rotatedWidth=rot%180===0?image.width:image.height;
      const rotatedHeight=rot%180===0?image.height:image.width;
      const scale=Math.max(canvas.width/rotatedWidth,canvas.height/rotatedHeight)*zoom;
      context.clearRect(0,0,canvas.width,canvas.height);
      context.save();
      context.translate(canvas.width/2+panX*canvas.width,canvas.height/2+panY*canvas.height);
      context.rotate(rot*Math.PI/180);
      context.scale((flipped?-1:1)*scale,scale);
      context.drawImage(image,-image.width/2,-image.height/2);
      context.restore();
      const paths=[...strokes,...(line?[line]:[])];
      for(const points of paths){
        if(points.length<1)continue;
        context.strokeStyle='#ffffff';context.lineWidth=Math.max(3,canvas.width*.007);
        context.lineJoin='round';context.lineCap='round';context.beginPath();
        points.forEach(([x,y],i)=>i?context.lineTo(x*canvas.width,y*canvas.height):context.moveTo(x*canvas.width,y*canvas.height));
        if(points.length===1){context.lineTo(points[0][0]*canvas.width+.1,points[0][1]*canvas.height+.1)}
        context.stroke();
      }
    };
    const toolBtn=(id,title)=>'<button type="button" data-photo-tool="'+id+'">'+title+'</button>';
    tools.innerHTML=toolBtn('free','Original')+toolBtn('square','1:1 crop')+toolBtn('portrait','4:5 crop')+toolBtn('wide','16:9 crop')+toolBtn('rotate','↻ Rotate')+toolBtn('flip','⇄ Flip')+toolBtn('pen','✎ Draw')+toolBtn('undo','↶ Undo')+
      '<label class="h-zoom">Zoom <input type="range" id="hEditorZoom" min="100" max="250" step="5" value="100"></label>'+
      '<small>Drag image to reposition. Draw to annotate.</small>';
    tools.addEventListener('click',e=>{
      const cmd=e.target.closest('[data-photo-tool]')?.dataset.photoTool;
      if(!cmd)return;
      if(cmd==='square')ratio=1;
      if(cmd==='portrait')ratio=4/5;
      if(cmd==='wide')ratio=16/9;
      if(cmd==='free')ratio=0;
      if(cmd==='rotate'){rot=(rot+90)%360;panX=0;panY=0;}
      if(cmd==='flip')flipped=!flipped;
      if(cmd==='undo')strokes.pop();
      if(cmd==='pen'){pen=!pen;tools.querySelector('[data-photo-tool="pen"]').classList.toggle('is-active',pen)}
      render();
    });
    tools.querySelector('#hEditorZoom').addEventListener('input',e=>{zoom=Number(e.target.value)/100;render()});
    let tracking=false,prev=null;
    const point=e=>{const rect=canvas.getBoundingClientRect();return [(e.clientX-rect.left)/rect.width,(e.clientY-rect.top)/rect.height]};
    canvas.addEventListener('pointerdown',e=>{
      tracking=true;canvas.setPointerCapture(e.pointerId);prev=point(e);
      if(pen){line=[prev];render()}
    });
    canvas.addEventListener('pointermove',e=>{
      if(!tracking)return;
      const current=point(e);
      if(pen&&line){line.push(current)}
      else if(prev){panX=Math.max(-.65,Math.min(.65,panX+current[0]-prev[0]));panY=Math.max(-.65,Math.min(.65,panY+current[1]-prev[1]));}
      prev=current;render();
    });
    const end=()=>{tracking=false;if(line){strokes.push(line);line=null;}prev=null;render()};
    canvas.addEventListener('pointerup',end);canvas.addEventListener('pointercancel',end);
    render();
    buildFile=async()=>{
      render();
      const out=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.87));
      if(!out)throw Error('Could not export edited photo');
      return new File([out],(file.name.replace(/\.[^/.]+$/,'')||'image')+'-edited.jpg',{type:'image/jpeg'});
    };
  }else if(isVideo){
    resource=URL.createObjectURL(file);
    const video=document.createElement('video');video.controls=true;video.playsInline=true;video.preload='metadata';video.src=resource;
    stage.append(video);
    tools.innerHTML='<p class="h-editor-tip">Preview your clip and add a caption before sending. Video trimming is not available yet.</p>';
  }else{
    stage.innerHTML='<div class="h-document-preview"><span>📄</span><strong></strong><small></small></div>';
    stage.querySelector('strong').textContent=file.name;
    stage.querySelector('small').textContent=(file.size/1024).toFixed(1)+' KB · '+(file.type||'Document');
    tools.innerHTML='<p class="h-editor-tip">Check the document and add a caption before sharing.</p>';
  }
  const send=dialog.querySelector('#hEditorSend');
  send.addEventListener('click',async()=>{
    if(!state.active){toast('Choose a conversation before sharing.',true);return;}
    send.disabled=true;send.textContent='Preparing…';
    try{
      const outgoing=await buildFile();
      if(outgoing.size>(outgoing.type.startsWith('video/')?20:6)*1024*1024)throw Error('Edited file is too large.');
      const caption=dialog.querySelector('#hEditorCaption').value.trim();
      // sendMediaFile handles authorization, transport errors and message updates.
      closeMediaEditor();cleanup();
      await sendMediaFile(outgoing,caption);
    }catch(err){send.disabled=false;send.textContent='Send ↗';toast(err.message||'Failed to prepare file',true);}
  });
  dialog.addEventListener('keydown',e=>{if(e.key==='Escape'){cleanup();closeMediaEditor();}});
  dialog.querySelector('.h-editor-close').addEventListener('click',cleanup,{once:true});
  dialog.querySelector('#hEditorCancel').addEventListener('click',cleanup,{once:true});
  dialog.addEventListener('click',e=>{if(e.target===dialog)cleanup()});
}
