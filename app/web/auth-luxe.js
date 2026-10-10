/* Huddle After Dark: lightweight visual enhancements; no auth requests or secrets. */
(() => {
  'use strict';
  const password=document.getElementById('authPassword');
  const registration=document.getElementById('registerNameField');
  const meter=document.getElementById('authPasswordStrength');
  const fill=document.getElementById('authStrengthFill');
  const description=document.getElementById('authStrengthText');
  const eye=document.getElementById('togglePassword');
  if(!password||!registration||!meter||!fill||!description)return;

  function updateStrength(){
    const isRegister=!registration.classList.contains('hidden');
    meter.hidden=!isRegister;
    if(!isRegister)return;
    const value=password.value;
    let points=0;
    if(value.length>=8)points++;
    if(value.length>=12)points++;
    if(/[a-z]/.test(value)&&/[A-Z]/.test(value))points++;
    if(/[0-9]/.test(value))points++;
    if(/[^a-zA-Z0-9]/.test(value))points++;
    const level=value.length===0?0:Math.min(5,points);
    meter.dataset.level=level>=4?'strong':level>=2?'medium':'weak';
    fill.style.width=(value.length===0?0:Math.max(12,level*20))+'%';
    description.textContent=!value?'Use at least 8 characters':level>=4?'Strong password':level>=2?'Getting stronger':'Add more variety';
  }
  password.addEventListener('input',updateStrength);
  new MutationObserver(updateStrength).observe(registration,{attributes:true,attributeFilter:['class']});
  if(eye){
    const updateEye=()=>{
      const visible=password.type==='text';
      eye.setAttribute('aria-pressed',String(visible));
      eye.setAttribute('aria-label',visible?'Hide password':'Show password');
    };
    eye.addEventListener('click',updateEye);
    updateEye();
  }
  window.addEventListener('pageshow',updateStrength);
  updateStrength();
})();
