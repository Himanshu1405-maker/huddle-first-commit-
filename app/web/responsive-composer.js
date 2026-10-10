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
    node.setAttribute('title',label);
    node.setAttribute('aria-label',label);
    // Icon-only menu: tool names remain accessible to screen readers.
    node.querySelector('.h-tool-name')?.remove();
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

  const mirror=document.createElement('textarea');
  mirror.rows=1;
  mirror.tabIndex=-1;
  mirror.className='h-composer-measure';
  mirror.setAttribute('aria-hidden','true');
  composer.append(mirror);
  let open=false;
  let expanded=false;
  let normalInputWidth=0,measuredComposerWidth=0,normalPadding='8px 0px';
  let transitionVersion=0;
  const tools=[emoji,fileLabel,location,mic];
  const isRecording=()=>mic.classList.contains('recording');
  const reduceMotion=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function animateTransition(wasExpanded,willExpand,fromRects,fromMore){
    if(reduceMotion()||!document.body.contains(composer)||!app.getClientRects().length)return;
    const current=++transitionVersion;
    if(!willExpand)composer.classList.add('h-composer-restoring');
    const target=willExpand?more.getBoundingClientRect():null;
    const finalRects=willExpand?[]:tools.map(node=>node.getBoundingClientRect());
    const startRects=willExpand?fromRects:tools.map(()=>fromMore);
    const endRects=willExpand?tools.map(()=>target):finalRects;
    let tasks=0;
    const done=()=>{
      tasks--;
      if(tasks<=0&&current===transitionVersion)composer.classList.remove('h-composer-restoring');
    };
    tools.forEach((node,i)=>{
      const start=startRects[i],end=endRects[i];
      if(!start?.width||!end?.width)return;
      const ghost=document.createElement('span');
      ghost.className='h-composer-ghost';
      ghost.setAttribute('aria-hidden','true');
      const glyph=node.querySelector('svg')?.cloneNode(true);
      if(glyph)ghost.append(glyph);
      const style=getComputedStyle(node);
      ghost.style.background=style.backgroundColor;
      ghost.style.color=style.color;
      ghost.style.border='1px solid '+style.borderTopColor;
      ghost.style.width=start.width+'px';
      ghost.style.height=start.height+'px';
      ghost.style.left=start.left+'px';
      ghost.style.top=start.top+'px';
      document.body.append(ghost);
      const dx=end.left+end.width/2-(start.left+start.width/2);
      const dy=end.top+end.height/2-(start.top+start.height/2);
      const scale=Math.max(.25,Math.min(1.2,end.width/start.width));
      tasks++;
      const animation=ghost.animate([
        {transform:'translate3d(0,0,0) scale(1)',opacity:willExpand?1:0},
        {transform:`translate3d(${dx}px,${dy}px,0) scale(${scale})`,opacity:willExpand?0:1}
      ],{duration:245+17*i,delay:i*10,easing:'cubic-bezier(.2,.75,.22,1)',fill:'forwards'});
      animation.finished.catch(()=>{}).finally(()=>{ghost.remove();done()});
    });
    if(!tasks)composer.classList.remove('h-composer-restoring');
  }

  function measureIsMultiLine(){
    if(!input.value)return false;
    // Cache the actual one-line typing width with all four icons in place.
    // NEVER toggle layout classes during typing: doing so cancels animations.
    const currentComposerWidth=composer.clientWidth;
    if(!expanded){
      const current=input.getBoundingClientRect().width;
      if(current>0){
        normalInputWidth=current;
        measuredComposerWidth=currentComposerWidth;
        normalPadding=getComputedStyle(input).padding;
      }
    }
    const width=Math.max(35,normalInputWidth+currentComposerWidth-measuredComposerWidth);
    if(!normalInputWidth||currentComposerWidth<=0)return false;
    const styles=getComputedStyle(input);
    mirror.style.width=width+'px';
    mirror.style.font=styles.font;
    mirror.style.fontFamily=styles.fontFamily;
    mirror.style.fontSize=styles.fontSize;
    mirror.style.fontWeight=styles.fontWeight;
    mirror.style.letterSpacing=styles.letterSpacing;
    mirror.style.lineHeight=styles.lineHeight;
    mirror.style.boxSizing=styles.boxSizing;
    mirror.style.wordBreak=styles.wordBreak;
    mirror.style.overflowWrap=styles.overflowWrap;
    // The original input uses no extra horizontal padding.
    mirror.style.setProperty('padding',normalPadding,'important');
    mirror.value=input.value.endsWith('\n')?input.value+'\u200b':input.value;
    mirror.style.height='1px';
    const lineHeight=parseFloat(styles.lineHeight)||parseFloat(styles.fontSize)*1.4;
    const pad=(parseFloat(normalPadding)||0)*2;
    return mirror.scrollHeight>Math.ceil(lineHeight+pad)+1;
  }

  function sync(){
    const next=measureIsMultiLine();
    const changed=next!==expanded;
    const fromRects=changed&&!expanded?tools.map(node=>node.getBoundingClientRect()):null;
    const fromMore=changed&&expanded?more.getBoundingClientRect():null;
    if(!next)open=false;
    expanded=next;
    // Toggle only on state changes. Repeated class removal/readdition on every
    // keypress previously made the four buttons snap without a transition.
    if(changed)composer.classList.toggle('h-composer-expanded',expanded);
    composer.classList.toggle('h-tools-open',expanded&&open);
    const recording=isRecording();
    const showing=expanded&&open;
    more.setAttribute('aria-expanded',String(showing));
    more.classList.toggle('h-more-recording',expanded&&recording);
    const graphic=expanded&&recording?stop:showing?close:plus;
    if(more.innerHTML!==graphic)more.innerHTML=graphic;
    const label=expanded&&recording?'Stop and send voice note':showing?'Hide message tools':'Show message tools';
    more.setAttribute('aria-label',label);
    more.title=label;
    group.setAttribute('aria-hidden',String(expanded&&!open));
    for(const node of tools){
      if(expanded&&!open)node.setAttribute('tabindex','-1');
      else if(node===fileLabel)node.setAttribute('tabindex','0');
      else node.removeAttribute('tabindex');
    }
    if(!expanded)more.setAttribute('tabindex','-1');
    else more.removeAttribute('tabindex');
    if(changed)animateTransition(!next,next,fromRects,fromMore);
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
