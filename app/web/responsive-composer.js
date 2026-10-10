/* Huddle responsive composer: all existing tool buttons remain the original DOM
   nodes, so recordings, location permissions, emoji and attachments keep working.
   Use measured text reflow at the *normal four-button width* to avoid a
   collapse/expand loop when the text input becomes wider. */
'use strict';
(() => {
  const app=document.getElementById('appScreen');
  const composer=document.querySelector('#conversationView .composer');
  const input=document.getElementById('messageInput');
  const send=document.getElementById('sendBtn');
  const picker=document.getElementById('emojiPicker');
  if(!app||!composer||!input||!send)return;
  const emoji=document.getElementById('emojiBtn');
  const fileLabel=composer.querySelector('label[for="mediaFileInput"]');
  const fileInput=document.getElementById('mediaFileInput');
  const location=document.getElementById('shareLocationBtn');
  const mic=document.getElementById('voiceNoteBtn');
  if(!emoji||!fileLabel||!fileInput||!location||!mic)return;

  const group=document.createElement('div');
  group.id='hComposerToolset';
  group.className='h-composer-toolset';
  group.setAttribute('role','group');
  group.setAttribute('aria-label','Message attachments and tools');
  composer.insertBefore(group,emoji);
  for(const el of [emoji,fileLabel,fileInput,location,mic])group.append(el);
  for(const [node,label] of [[emoji,'Emojis'],[fileLabel,'Attach'],[location,'Location'],[mic,'Voice note']]){
    node.dataset.hToolName=label;
    const tag=document.createElement('span');
    tag.className='h-tool-name';
    tag.textContent=label;
    tag.setAttribute('aria-hidden','true');
    node.append(tag);
  }

  const more=document.createElement('button');
  more.type='button';
  more.id='hComposerMore';
  more.className='h-composer-more';
  more.title='More message tools';
  more.setAttribute('aria-label','Show message tools');
  more.setAttribute('aria-expanded','false');
  more.setAttribute('aria-controls','hComposerToolset');
  const plus='<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>';
  const close='<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"><path d="M5 5l14 14M19 5 5 19"/></svg>';
  const stop='<svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="3"/></svg>';
  more.innerHTML=plus;
  group.after(more);

  const mirror=document.createElement('div');
  mirror.className='h-composer-measure';
  mirror.setAttribute('aria-hidden','true');
  composer.append(mirror);
  let open=false;
  let expanded=false;
  const isRecording=()=>mic.classList.contains('recording');

  function measureIsMultiLine(){
    if(!input.value)return false;
    const styles=getComputedStyle(input);
    const cs=getComputedStyle(composer);
    const padding=(parseFloat(cs.paddingLeft)||0)+(parseFloat(cs.paddingRight)||0);
    const gap=parseFloat(cs.columnGap)||4;
    const sampleWidth=window.innerWidth<=365?30:window.innerWidth<=720?33:36;
    const buttonWidth=send.offsetWidth||40;
    // Four tool icons + gaps plus the send button, as in the short-message UI.
    const normalWidth=Math.max(54,composer.clientWidth-padding-(4*sampleWidth+3*gap)-buttonWidth-2*gap-8);
    mirror.style.width=normalWidth+'px';
    mirror.style.font=styles.font;
    mirror.style.fontFamily=styles.fontFamily;
    mirror.style.fontSize=styles.fontSize;
    mirror.style.fontWeight=styles.fontWeight;
    mirror.style.letterSpacing=styles.letterSpacing;
    mirror.style.lineHeight=styles.lineHeight;
    mirror.textContent=input.value.endsWith('\n')?input.value+'\u200b':input.value;
    const lineHeight=parseFloat(styles.lineHeight)||parseFloat(styles.fontSize)*1.42;
    return mirror.getBoundingClientRect().height>lineHeight*1.5;
  }

  function sync(){
    const next=measureIsMultiLine();
    if(!next)open=false;
    expanded=next;
    composer.classList.toggle('h-composer-expanded',expanded);
    composer.classList.toggle('h-tools-open',expanded&&open);
    const recording=isRecording();
    const showing=expanded&&open;
    more.setAttribute('aria-expanded',String(showing));
    more.classList.toggle('h-more-recording',expanded&&recording);
    more.innerHTML=expanded&&recording?stop:showing?close:plus;
    const label=expanded&&recording?'Stop and send voice note':showing?'Hide message tools':'Show message tools';
    more.setAttribute('aria-label',label);
    more.title=label;
    group.setAttribute('aria-hidden',String(expanded&&!open));
    // Hide tab access to controls inside a closed tool menu.
    for(const node of [emoji,fileLabel,location,mic]){
      if(expanded&&!open)node.setAttribute('tabindex','-1');
      else if(node===fileLabel)node.setAttribute('tabindex','0');
      else node.removeAttribute('tabindex');
    }
    if(!expanded)more.setAttribute('tabindex','-1');
    else more.removeAttribute('tabindex');
  }

  more.addEventListener('click',()=>{
    if(expanded&&isRecording()){
      mic.click();return;
    }
    open=!open;
    sync();
  });
  group.addEventListener('click',e=>{
    if(!expanded||!e.target.closest('button,label'))return;
    open=false;
    requestAnimationFrame(sync);
  });
  document.addEventListener('pointerdown',event=>{
    if(!open)return;
    if(!event.target.closest('#hComposerMore,#hComposerToolset')){
      open=false;sync();
    }
  },true);
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape'&&open){
      open=false;sync();more.focus();
    }
  });
  input.addEventListener('input',sync);
  input.addEventListener('change',sync);
  picker?.addEventListener('click',()=>requestAnimationFrame(sync));
  send.addEventListener('click',()=>requestAnimationFrame(sync));
  input.addEventListener('keydown',e=>{
    if(e.key==='Enter'&&!e.shiftKey)requestAnimationFrame(sync);
  });
  window.addEventListener('resize',sync,{passive:true});
  const resizeObserver=typeof ResizeObserver==='function'?new ResizeObserver(()=>sync()):null;
  resizeObserver?.observe(composer);
  const micObserver=new MutationObserver(sync);
  micObserver.observe(mic,{attributes:true,attributeFilter:['class']});
  const oldSend=sendMessage;
  sendMessage=function(...args){
    const result=oldSend.apply(this,args);
    requestAnimationFrame(sync);
    Promise.resolve(result).finally(()=>requestAnimationFrame(sync));
    return result;
  };
  sync();
  window.HuddleComposerUI={sync,isExpanded:()=>expanded,isOpen:()=>open};
})();
