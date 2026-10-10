/* Huddle Vivid — client-side visual preferences, scoped to the signed-in account.
   The settings never read or transmit messages or location data. */
(() => {
  'use strict';
  const app = document.getElementById('appScreen');
  const drawer = document.getElementById('vThemePanel');
  const scrim = document.getElementById('vThemeScrim');
  if (!app || !drawer || !scrim) return;

  const themes = ['system','mint','peach','lavender','ocean','midnight'];
  const wallpapers = ['doodles','plain','dots','waves','grid','petals','sunset','stars'];
  const composers = ['soft','glass','compact'];
  const defaults = () => ({theme:'system',wallpaper:'doodles',composer:'soft',textSize:100,chats:{}});
  const platformDark = window.matchMedia?.('(prefers-color-scheme: dark)');
  let config = defaults();
  let loadedUser = null;
  let chosenScope = 'all';
  let lastFocus = null;
  const $ = selector => drawer.querySelector(selector);
  const $$ = selector => [...drawer.querySelectorAll(selector)];
  const valid = (kind,value) => ({theme:themes,wallpaper:wallpapers,composer:composers}[kind]||[]).includes(value);

  function accountId() {
    // No profile or conversation content is written to these local preferences.
    return (typeof state !== 'undefined' && state.me?.id) || null;
  }
  function prefKey(id) {return 'huddle.visual.prefs.v1.'+id;}
  function readPrefs(id) {
    if (!id) return defaults();
    try {
      const saved = JSON.parse(localStorage.getItem(prefKey(id))||'null');
      if (!saved || typeof saved !== 'object') return defaults();
      const prefs=defaults();
      const scale=Number(saved.textSize);
      if(Number.isInteger(scale)&&scale>=90&&scale<=135&&scale%5===0) prefs.textSize=scale;
      for(const kind of ['theme','wallpaper','composer'])
        if(valid(kind,saved[kind])) prefs[kind]=saved[kind];
      if(saved.chats && typeof saved.chats==='object' && !Array.isArray(saved.chats)){
        for(const [chat,wallpaper] of Object.entries(saved.chats).slice(-200)){
          if (/^[a-f0-9]{32}$/i.test(chat) && valid('wallpaper',wallpaper))
            prefs.chats[chat]=wallpaper;
        }
      }
      return prefs;
    } catch {return defaults();}
  }
  function persist() {
    if(!loadedUser)return;
    try {localStorage.setItem(prefKey(loadedUser),JSON.stringify(config));}
    catch { /* Private browsing or storage disabled: choices work for this tab. */ }
  }
  function checkAccount() {
    const user=accountId();
    if(user!==loadedUser){
      loadedUser=user;
      config=readPrefs(user);
      if(drawerOpen()) closeDrawer();
    }
  }
  function resolvedTheme() {
    return config.theme==='system'
      ? (platformDark?.matches?'midnight':'mint')
      : config.theme;
  }
  function activeChatId() {
    if (typeof state==='undefined' || !state.me || !state.active) return null;
    return state.active.id;
  }
  function currentWallpaper() {
    const id=activeChatId();
    return (id && config.chats[id]) || config.wallpaper;
  }
  function apply() {
    checkAccount();
    app.dataset.vTheme=resolvedTheme();
    app.dataset.vWallpaper=currentWallpaper();
    app.dataset.vComposer=config.composer;
    app.dataset.vThemeChoice=config.theme;
    const value=Math.max(90,Math.min(135,config.textSize));
    app.style.setProperty('--h-text-scale',String(value/100));
    const slider=$('#vTextSize'),readout=$('#vTextSizeValue');
    if(slider){
      slider.value=String(value);
      slider.setAttribute('aria-valuenow',String(value));
      slider.setAttribute('aria-valuetext',value+' percent');
    }
    if(readout)readout.value=value+'%';
    const preview=$('#vTextPreview');
    if(preview)preview.style.fontSize=(14*value/100)+'px';
    const note=document.getElementById('vChatThemeHint');
    if(note) note.textContent=activeChatId()?'Only this chat, on this device':'Affects your default wallpaper for every chat';
    const choice=$('[data-v-scope="chat"]');
    if(choice){
      choice.disabled=!activeChatId();
      choice.textContent=activeChatId()?'This chat':'This chat (open one)';
    }
    if(!activeChatId() && chosenScope==='chat') chosenScope='all';
    const currentScope=$('[data-v-scope="all"]');
    if(currentScope) currentScope.setAttribute('aria-pressed',String(chosenScope==='all'));
    if(choice) choice.setAttribute('aria-pressed',String(chosenScope==='chat'));
    const remove=$('#vClearChatWallpaper');
    if(remove) remove.hidden=!(activeChatId()&&chosenScope==='chat'&&Object.hasOwn(config.chats,activeChatId()));
    for(const button of $$('[data-v-kind]')){
      const kind=button.dataset.vKind;
      const value=button.dataset.vValue;
      const selected=kind==='theme'?config.theme===value
        :kind==='composer'?config.composer===value
        :(chosenScope==='all'?config.wallpaper:currentWallpaper())===value;
      button.setAttribute('aria-pressed',String(selected));
    }
    const badge=$('#vSelectedWallpaper');
    if(badge) badge.textContent=chosenScope==='chat'?'Current chat':'All chats';
  }
  function drawerOpen(){return !drawer.hidden;}
  function openDrawer() {
    if(!accountId())return;
    lastFocus=document.activeElement;
    chosenScope=activeChatId()?'chat':'all';
    drawer.hidden=false;scrim.hidden=false;
    apply();
    document.body.classList.add('v-customize-open');
    $('#vPanelClose')?.focus();
  }
  function closeDrawer() {
    drawer.hidden=true;scrim.hidden=true;
    document.body.classList.remove('v-customize-open');
    if(lastFocus?.isConnected)lastFocus.focus();
    lastFocus=null;
  }
  document.getElementById('vHeaderThemeBtn')?.addEventListener('click',openDrawer);
  document.getElementById('vInboxThemeBtn')?.addEventListener('click',openDrawer);
  $('#vPanelClose')?.addEventListener('click',closeDrawer);
  scrim.addEventListener('click',closeDrawer);
  document.addEventListener('keydown',event=>{
    if(!drawerOpen())return;
    if(event.key==='Escape'){event.preventDefault();closeDrawer();return;}
    if(event.key==='Tab'){
      const elements=$$('button:not([disabled]):not([hidden])').filter(el=>el.getClientRects().length);
      const first=elements[0],last=elements[elements.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    }
  });
  $('#vTextSize')?.addEventListener('input',event=>{
    const value=Number(event.target.value);
    if(!Number.isInteger(value)||value<90||value>135||value%5!==0)return;
    config.textSize=value;persist();apply();
  });
  $('#vTextDefault')?.addEventListener('click',()=>{
    config.textSize=100;persist();apply();
  });
  drawer.addEventListener('click',event=>{
    const scope=event.target.closest('[data-v-scope]');
    if(scope){
      if(scope.dataset.vScope==='chat'&&!activeChatId())return;
      chosenScope=scope.dataset.vScope;
      apply();return;
    }
    if(event.target.closest('#vClearChatWallpaper')){
      const chat=activeChatId();
      if(chat){delete config.chats[chat];persist();apply();}
      return;
    }
    if(event.target.closest('#vResetVisuals')){
      config=defaults();persist();apply();return;
    }
    const button=event.target.closest('[data-v-kind]');
    if(!button)return;
    const kind=button.dataset.vKind,value=button.dataset.vValue;
    if(!valid(kind,value))return;
    if(kind==='wallpaper'){
      const chat=activeChatId();
      if(chosenScope==='chat'&&chat)config.chats[chat]=value;
      else config.wallpaper=value;
    }else config[kind]=value;
    persist();apply();
  });

  if(platformDark){
    const onChange=()=>{if(config.theme==='system')apply();};
    if(platformDark.addEventListener)platformDark.addEventListener('change',onChange);
    else platformDark.addListener?.(onChange);
  }
  // Keep the selected chat's wallpaper in sync with navigation and reconnects.
  // Preserve the existing functions' returned values and message behavior.
  if(typeof openConversation==='function'){
    const previousOpen=openConversation;
    openConversation=async function(...args){
      const result=await previousOpen.apply(this,args);
      apply();
      return result;
    };
  }
  if(typeof showWelcome==='function'){
    const previousWelcome=showWelcome;
    showWelcome=function(...args){
      const result=previousWelcome.apply(this,args);
      apply();
      return result;
    };
  }
  apply();
})();
