/* Voice cards: native audio underneath, accessible custom play/seek controls. */
'use strict';
(() => {
  const root=document.getElementById('messages');
  if(!root)return;
  const playSvg='<svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13a1 1 0 0 0 1.54.84l10-6.5a1 1 0 0 0 0-1.68l-10-6.5A1 1 0 0 0 8 5.5Z"/></svg>';
  const pauseSvg='<svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>';
  const stamp=(time,duration=false)=>{
    if(!Number.isFinite(time)||time<0)return '0:00';
    // Even an audible clip shorter than one second should not look empty.
    const seconds=duration&&time>0?Math.max(1,Math.ceil(time)):Math.floor(time);
    return Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0');
  };
  function cardFromAudio(audio){return audio?.closest('.voice-media');}
  function update(audio){
    const card=cardFromAudio(audio);
    if(!card)return;
    const control=card.querySelector('.h-voice-play');
    const duration=card.querySelector('.h-voice-duration');
    const seek=card.querySelector('.h-voice-progress');
    const playing=!audio.paused&&!audio.ended;
    if(control){
      control.innerHTML=playing?pauseSvg:playSvg;
      control.setAttribute('aria-label',playing?'Pause voice message':'Play voice message');
      control.title=playing?'Pause':'Play';
      control.setAttribute('aria-pressed',String(playing));
    }
    card.classList.toggle('h-voice-playing',playing);
    const length=Number.isFinite(audio.duration)&&audio.duration>0?audio.duration:0;
    if(duration) duration.textContent=playing||audio.currentTime>0?stamp(audio.currentTime):stamp(length,true);
    if(seek){
      card.style.setProperty('--h-progress',length?Math.min(100,Math.round(100*audio.currentTime/length))+'%':'0%');
      seek.value=length?String(Math.round(100*audio.currentTime/length)):'0';
      seek.setAttribute('aria-valuetext',stamp(audio.currentTime)+' of '+stamp(length));
      seek.disabled=!length;
    }
  }
  function decorate(){
    root.querySelectorAll('.voice-media').forEach(card=>{
      const audio=card.querySelector('audio');
      if(!audio)return;
      card.classList.add('h-voice-ready');
      update(audio);
    });
  }
  const originalRender=renderMessages;
  renderMessages=function(...args){
    const result=originalRender.apply(this,args);
    decorate();
    return result;
  };
  root.addEventListener('click',event=>{
    const button=event.target.closest('.h-voice-play');
    if(!button)return;
    const audio=button.closest('.voice-media')?.querySelector('audio');
    if(!audio)return;
    if(audio.paused){
      for(const other of root.querySelectorAll('.voice-media audio')){
        if(other!==audio&&!other.paused)other.pause();
      }
      const start=audio.play();
      if(start&&typeof start.catch==='function'){
        start.catch(()=>{button.title='Playback unavailable';});
      }
    }else audio.pause();
  });
  root.addEventListener('input',event=>{
    const seeker=event.target.closest('.h-voice-progress');
    if(!seeker)return;
    const audio=seeker.closest('.voice-media')?.querySelector('audio');
    if(audio&&Number.isFinite(audio.duration)&&audio.duration>0){
      audio.currentTime=audio.duration*Number(seeker.value)/100;
    }
  });
  // These HTMLMediaElement events do not all bubble: use capture.
  for(const name of ['loadedmetadata','durationchange','timeupdate','playing','play','pause','ended','seeked']){
    root.addEventListener(name,event=>{
      if(event.target instanceof HTMLAudioElement)update(event.target);
    },true);
  }
  decorate();
})();
