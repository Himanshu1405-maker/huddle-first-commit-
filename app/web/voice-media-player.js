/* Accessible, browser-compatible voice playback: real duration, progress-coloured
   waveform, accurate seek position and one playing note at a time. */
'use strict';
(() => {
  const root=document.getElementById('messages');
  if(!root)return;
  const playSvg='<svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13a1 1 0 0 0 1.54.84l10-6.5a1 1 0 0 0 0-1.68l-10-6.5A1 1 0 0 0 8 5.5Z"/></svg>';
  const pauseSvg='<svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>';
  const timeText=seconds=>{
    if(!Number.isFinite(seconds)||seconds<0)return '--:--';
    const s=seconds>0?Math.max(1,Math.ceil(seconds)):0;
    return Math.floor(s/60)+':'+String(s%60).padStart(2,'0');
  };
  let current=null,frame=0;
  const stopFrames=()=>{if(frame)cancelAnimationFrame(frame);frame=0;};
  function cardOf(audio){return audio?.closest('.voice-media');}
  function mediaDuration(audio){
    if(Number.isFinite(audio.duration)&&audio.duration>0)return audio.duration;
    const saved=Number(cardOf(audio)?.dataset.durationMs);
    if(Number.isFinite(saved)&&saved>0)return saved/1000;
    if(audio.seekable?.length){
      try{const end=audio.seekable.end(audio.seekable.length-1);if(Number.isFinite(end)&&end>0)return end;}catch{}
    }
    return 0;
  }
  function apply(audio){
    if(!audio)return;
    const card=cardOf(audio);
    if(!card)return;
    const playing=!audio.paused&&!audio.ended;
    const duration=mediaDuration(audio);
    const elapsed=Number.isFinite(audio.currentTime)?Math.min(duration||Infinity,audio.currentTime):0;
    const fraction=duration?Math.max(0,Math.min(1,elapsed/duration)):0;
    const control=card.querySelector('.h-voice-play');
    const label=card.querySelector('.h-voice-duration');
    const seek=card.querySelector('.h-voice-progress');
    card.classList.toggle('h-voice-playing',playing);
    card.classList.toggle('h-voice-has-duration',duration>0);
    if(control){
      control.innerHTML=playing?pauseSvg:playSvg;
      control.setAttribute('aria-label',playing?'Pause voice note':'Play voice note');
      control.setAttribute('aria-pressed',String(playing));
      control.title=playing?'Pause':'Play';
    }
    if(label){
      // Show the total duration while idle and remaining duration while playing.
      label.textContent=duration?timeText(playing?Math.max(0,duration-elapsed):duration):'--:--';
      label.title=duration?'Total voice note duration '+timeText(duration):'Loading voice duration';
      label.setAttribute('aria-label',label.title);
    }
    if(seek){
      seek.disabled=false; // Even WebM clips with no Duration element can seek after loading.
      seek.value=String(Math.round(fraction*100));
      seek.style.setProperty('--h-progress',(fraction*100).toFixed(2)+'%');
      seek.setAttribute('aria-valuetext',timeText(elapsed)+' of '+(duration?timeText(duration):'unknown duration'));
    }
    const bars=card.querySelectorAll('.h-voice-waves i');
    const complete=Math.round(fraction*bars.length);
    bars.forEach((bar,i)=>bar.classList.toggle('h-voice-heard',i<complete));
    card.style.setProperty('--h-progress',(fraction*100).toFixed(2)+'%');
  }
  function refreshLoop(){
    frame=0;
    if(current&&!current.paused&&!current.ended&&current.isConnected){
      apply(current);
      frame=requestAnimationFrame(refreshLoop);
    }else current=null;
  }
  function tryRecoverWebMDuration(audio){
    // MediaRecorder can write WebM without a Duration field. Chromium then
    // reports Infinity despite a perfectly playable recording. Seeking to the
    // buffered end lets Chromium determine its duration, then we rewind.
    if(!audio||audio.dataset.hDurationRecovery==='done')return;
    if(Number.isFinite(audio.duration)&&audio.duration>0)return;
    if(!audio.currentSrc)return;
    if(audio.networkState===HTMLMediaElement.NETWORK_NO_SOURCE)return;
    if(audio.readyState<HTMLMediaElement.HAVE_METADATA)return;
    if(audio.seekable?.length){
      try{
        const end=audio.seekable.end(audio.seekable.length-1);
        if(Number.isFinite(end)&&end>0){apply(audio);return;}
      }catch{}
    }
    if(!Number.isFinite(audio.duration)){
      audio.dataset.hDurationRecovery='done';
      audio.dataset.hRewindAfterSeek='yes';
      try{audio.currentTime=1e8;}catch{audio.dataset.hRewindAfterSeek='';}
    }
  }
  function onDuration(event){
    const audio=event.target;
    if(!(audio instanceof HTMLAudioElement)||!cardOf(audio))return;
    if(event.type==='seeked'&&audio.dataset.hRewindAfterSeek==='yes'){
      audio.dataset.hRewindAfterSeek='';
      try{audio.currentTime=0;}catch{}
    }
    apply(audio);
    if(event.type==='loadedmetadata'||event.type==='durationchange')tryRecoverWebMDuration(audio);
  }
  function decorate(){
    root.querySelectorAll('.voice-media').forEach(card=>{
      const audio=card.querySelector('audio');
      if(!audio)return;
      audio.preload='metadata';
      card.classList.add('h-voice-ready');
      apply(audio);
      if(audio.readyState>=HTMLMediaElement.HAVE_METADATA)tryRecoverWebMDuration(audio);
    });
  }
  const originalRender=renderMessages;
  renderMessages=function(...args){
    const result=originalRender.apply(this,args);
    if(current&&!current.isConnected){stopFrames();current=null;}
    decorate();
    return result;
  };
  root.addEventListener('click',event=>{
    const button=event.target.closest('.h-voice-play');
    if(!button)return;
    const audio=button.closest('.voice-media')?.querySelector('audio');
    if(!audio)return;
    if(audio.paused){
      root.querySelectorAll('.voice-media audio').forEach(other=>{
        if(other!==audio&&!other.paused)other.pause();
      });
      if(current&&current!==audio)current.pause();
      current=audio;
      const played=audio.play();
      if(played?.catch)played.catch(()=>{stopFrames();current=null;button.title='Audio playback unavailable';});
    }else audio.pause();
  });
  root.addEventListener('input',event=>{
    const seeker=event.target.closest('.h-voice-progress');
    if(!seeker)return;
    const audio=seeker.closest('.voice-media')?.querySelector('audio');
    if(!audio)return;
    const duration=mediaDuration(audio);
    if(duration){
      audio.currentTime=duration*Number(seeker.value)/100;
      apply(audio);
    }
  });
  for(const name of ['loadedmetadata','loadeddata','durationchange','timeupdate','playing','play','pause','ended','seeked','error']){
    root.addEventListener(name,event=>{
      onDuration(event);
      if(!(event.target instanceof HTMLAudioElement))return;
      const audio=event.target;
      if(name==='playing'||name==='play'){
        current=audio;stopFrames();frame=requestAnimationFrame(refreshLoop);
      }
      if(name==='pause'||name==='ended'||name==='error'){
        if(current===audio){stopFrames();current=null;}
      }
    },true);
  }
  decorate();
  window.HuddleVoiceUI={mediaDuration,refresh:decorate};
})();
