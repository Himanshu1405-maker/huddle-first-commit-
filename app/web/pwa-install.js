/* Install shell for supported browsers; never prompt automatically. */
(()=>{
  'use strict';
  if(!('serviceWorker' in navigator) || !window.isSecureContext)return;
  window.addEventListener('load',()=>{
    navigator.serviceWorker.register('/sw.js',{scope:'/',updateViaCache:'none'})
      .catch(err=>console.warn('Huddle install support is unavailable:',err?.message||err));
  },{once:true});
})();
