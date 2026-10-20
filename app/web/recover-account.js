/* Email-only account recovery: enabled when owner configured Brevo. */
(()=>{
const button=document.createElement('button');button.id='hRecoverStart';button.className='h-recover-link';
button.type='button';button.textContent='Forgot password?';
document.querySelector('.switch-auth')?.before(button);
const panel=document.createElement('div');panel.className='h-recover-overlay hidden';panel.id='hRecoverOverlay';
panel.innerHTML='<section class="h-recover-panel" role="dialog" aria-modal="true" aria-labelledby="hRecoverTitle">'+
 '<button type="button" id="hRecoverClose" aria-label="Close">✕</button>'+
 '<h2 id="hRecoverTitle">Recover your Huddle account</h2><p>Enter your verified email. If it is linked to Huddle, we will send a code.</p>'+
 '<form id="hRecoverEmailForm"><label>Verified email<input id="hRecoverEmail" type="email" required maxlength="254"></label><button>Send recovery code</button></form>'+
 '<form id="hRecoverFinishForm" class="hidden"><p>Enter the eight-digit code sent to your email.</p>'+
 '<label>Recovery code<input id="hRecoverCode" type="text" pattern="[0-9]{8}" maxlength="8" required inputmode="numeric"></label>'+
 '<label>New password<input id="hRecoverPassword" type="password" minlength="8" maxlength="128" required autocomplete="new-password"></label>'+
 '<button>Update password</button></form><p id="hRecoverInfo" role="status"></p></section>';
document.body.append(panel);
let ticket=null;
const hide=()=>panel.classList.add('hidden');
document.getElementById('hRecoverClose').onclick=hide;
panel.addEventListener('click',e=>{if(e.target===panel)hide()});
button.onclick=()=>{
 if(!state.config?.email_otp){
  if(typeof toast==='function')toast('Password recovery needs an email sender configured by the Huddle owner.',true);
  return;
 }
 panel.classList.remove('hidden');
};
async function request(path,payload){
 const res=await fetch('/api'+path,{method:'POST',headers:{'Content-Type':'application/json'},
  credentials:'same-origin',body:JSON.stringify(payload)});
 const data=await res.json().catch(()=>({}));
 if(!res.ok)throw Error(data.detail||'Request unsuccessful');
 return data;
}
const status=document.getElementById('hRecoverInfo');
document.getElementById('hRecoverEmailForm').onsubmit=async e=>{
 e.preventDefault();status.textContent='Sending…';
 try{
  const data=await request('/auth/recover',{email:document.getElementById('hRecoverEmail').value});
  ticket=data.ticket;status.textContent=data.message;
  document.getElementById('hRecoverEmailForm').classList.add('hidden');
  document.getElementById('hRecoverFinishForm').classList.remove('hidden');
 }catch(e){status.textContent=e.message}
};
document.getElementById('hRecoverFinishForm').onsubmit=async e=>{
 e.preventDefault();status.textContent='Updating password…';
 try{
  const data=await request('/auth/recover/finish',{ticket,
   code:document.getElementById('hRecoverCode').value,
   password:document.getElementById('hRecoverPassword').value});
  status.textContent=data.message;
  document.getElementById('hRecoverFinishForm').classList.add('hidden');
 }catch(e){status.textContent=e.message}
};
})();
