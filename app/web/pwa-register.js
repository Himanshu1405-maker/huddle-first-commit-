(()=>{
'use strict';
if(!('serviceWorker' in navigator)||!window.isSecureContext)return;
window.addEventListener('load',()=>navigator.serviceWorker.register('/sw.js',{scope:'/'})
 .catch(()=>console.info('Huddle offline shell unavailable in this browser')));
let deferred=null;
window.addEventListener('beforeinstallprompt',event=>{
 event.preventDefault();deferred=event;
 let button=document.getElementById('hPwaInstall');
 if(!button){
  button=document.createElement('button');
  button.id='hPwaInstall';button.className='h-install-btn';
  button.type='button';button.textContent='＋ Install Huddle';
  document.querySelector('#sidebar .side-bottom')?.prepend(button);
 }
 button.onclick=async()=>{
  if(!deferred)return;deferred.prompt();
  await deferred.userChoice;deferred=null;button.remove();
 };
});
window.addEventListener('appinstalled',()=>{deferred=null;document.getElementById('hPwaInstall')?.remove()});
})();
