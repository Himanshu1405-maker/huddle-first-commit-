/* In-chat image viewer: smooth transitions, full-resolution photos, pinch/double
   tap not needed for ordinary open, simple zoom and accessible navigation. */
'use strict';
(() => {
  const messages=document.getElementById('messages');
  if(!messages)return;
  let viewer=null,previousFocus=null,zoomed=false,index=0,urls=[];
  const closeSvg='<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"><path d="M5 5 19 19M19 5 5 19"/></svg>';
  const downloadSvg='<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 3v12m-5-5 5 5 5-5M5 16v4h14v-4"/></svg>';
  const leftSvg='<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="m15 5-7 7 7 7"/></svg>';
  const rightSvg='<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="m9 5 7 7-7 7"/></svg>';

  function update(){
    if(!viewer)return;
    const item=urls[index];
    const image=viewer.querySelector('#hPhotoFull');
    image.classList.remove('h-photo-zoomed');
    zoomed=false;
    image.classList.add('h-photo-loading');
    image.alt=item.name||'Shared photo';
    image.src=item.src;
    viewer.querySelector('#hPhotoCaption').textContent=item.name||'Shared photo';
    viewer.querySelector('#hPhotoPosition').textContent=urls.length>1?(index+1)+' / '+urls.length:'';
    viewer.querySelector('#hPhotoPrev').hidden=urls.length<2;
    viewer.querySelector('#hPhotoNext').hidden=urls.length<2;
    viewer.querySelector('#hPhotoSave').href=item.src;
    viewer.querySelector('#hPhotoSave').setAttribute('download',item.name||'huddle-photo');
    // Once visible, images may be cached; handle both cached and loading cases.
    if(image.complete)image.classList.remove('h-photo-loading');
  }
  function close(){
    if(!viewer)return;
    const old=viewer;
    viewer=null;zoomed=false;
    old.classList.remove('h-photo-open');
    document.documentElement.classList.remove('h-photo-viewing');
    const cleanup=()=>{old.remove();previousFocus?.focus?.();previousFocus=null;};
    if(matchMedia('(prefers-reduced-motion: reduce)').matches)cleanup();
    else setTimeout(cleanup,230);
  }
  function next(dir){if(!viewer||!urls.length)return;index=(index+dir+urls.length)%urls.length;update();}
  function open(anchor){
    previousFocus=anchor;
    const anchors=[...messages.querySelectorAll('a.image-media[data-h-photo]')];
    urls=anchors.map(a=>({src:a.getAttribute('data-h-photo'),name:a.querySelector('img')?.alt?.replace(/^Shared photo:\s*/, '')||'Shared photo'}));
    index=Math.max(0,anchors.indexOf(anchor));
    if(viewer){update();return;}
    viewer=document.createElement('div');
    viewer.id='hPhotoViewer';
    viewer.className='h-photo-viewer';
    viewer.setAttribute('role','dialog');
    viewer.setAttribute('aria-modal','true');
    viewer.setAttribute('aria-label','Photo viewer');
    viewer.innerHTML='<div class="h-photo-viewer-head">'+
      '<button type="button" id="hPhotoClose" aria-label="Close image viewer">'+closeSvg+'</button>'+
      '<span class="h-photo-viewer-heading"><strong>Photo</strong><small id="hPhotoCaption"></small></span>'+
      '<span id="hPhotoPosition" class="h-photo-viewer-count"></span>'+
      '<a id="hPhotoSave" aria-label="Save full photo" title="Save photo" download>'+downloadSvg+'</a></div>'+
      '<main class="h-photo-canvas"><button type="button" class="h-photo-navigate" id="hPhotoPrev" aria-label="Previous photo">'+leftSvg+'</button>'+
      '<img id="hPhotoFull" alt="Shared photo" draggable="false" tabindex="0" title="Tap to zoom"/>'+
      '<button type="button" class="h-photo-navigate" id="hPhotoNext" aria-label="Next photo">'+rightSvg+'</button></main>'+
      '<p class="h-photo-viewer-help">Tap photo to zoom · Swipe to browse · Esc to close</p>';
    document.body.append(viewer);
    const full=viewer.querySelector('#hPhotoFull');
    full.addEventListener('load',()=>full.classList.remove('h-photo-loading'));
    full.addEventListener('error',()=>{
      full.classList.remove('h-photo-loading');
      viewer?.querySelector('#hPhotoCaption')?.replaceChildren(document.createTextNode('Could not load photo'));
    });
    full.addEventListener('click',()=>{
      zoomed=!zoomed;full.classList.toggle('h-photo-zoomed',zoomed);
    });
    viewer.querySelector('#hPhotoClose').addEventListener('click',close);
    viewer.querySelector('#hPhotoPrev').addEventListener('click',()=>next(-1));
    viewer.querySelector('#hPhotoNext').addEventListener('click',()=>next(1));
    viewer.addEventListener('click',event=>{if(event.target===viewer||event.target.classList.contains('h-photo-canvas'))close();});
    let swipeX=0;
    full.addEventListener('touchstart',e=>{swipeX=e.touches[0]?.clientX||0;},{passive:true});
    full.addEventListener('touchend',e=>{
      if(zoomed||urls.length<2)return;
      const delta=(e.changedTouches[0]?.clientX||0)-swipeX;
      if(Math.abs(delta)>65)next(delta<0?1:-1);
    },{passive:true});
    document.documentElement.classList.add('h-photo-viewing');
    update();
    requestAnimationFrame(()=>{viewer?.classList.add('h-photo-open');viewer?.querySelector('#hPhotoClose')?.focus();});
  }
  messages.addEventListener('click',event=>{
    const anchor=event.target.closest('a.image-media[data-h-photo]');
    if(!anchor)return;
    event.preventDefault();event.stopPropagation();
    open(anchor);
  },true);
  document.addEventListener('keydown',event=>{
    if(!viewer)return;
    if(event.key==='Escape'){event.preventDefault();close();}
    if(event.key==='ArrowRight'){event.preventDefault();next(1);}
    if(event.key==='ArrowLeft'){event.preventDefault();next(-1);}
    if(event.key==='Tab'){
      const controls=[...viewer.querySelectorAll('button:not([hidden]),a')].filter(el=>el.getClientRects().length);
      if(!controls.length)return;
      const first=controls[0],last=controls[controls.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
      if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
    }
  },true);
  window.HuddlePhotos={close};
})();
