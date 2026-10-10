const assert=require('node:assert/strict');
const fs=require('node:fs');
const html=fs.readFileSync('app/web/index.html','utf8');
const css=fs.readFileSync('app/web/auth-luxe.css','utf8');
const js=fs.readFileSync('app/web/auth-luxe.js','utf8');
assert(html.includes('href="/assets/auth-luxe.css"'));
assert(html.includes('src="/assets/auth-luxe.js"'));
for(const id of ['authName','authEmail','authHandle','authPassword']){
  assert(html.includes('id="'+id+'"'), 'Missing auth field: '+id);
  const element=html.match(new RegExp('<input[^>]*id="'+id+'"[^>]*>'));
  assert(element && element[0].includes('placeholder=" "'),'Floating label requires blank placeholder '+id);
}
assert((html.match(/class="h-float-caption"/g)||[]).length===4);
assert((html.match(/class="field-icon h-luxe-field"/g)||[]).length===4);
for(const fragment of ['.auth-form-shell','backdrop-filter:blur','.h-float-caption',
  ':focus-within:before','huddleLuxeGradient','@media(max-width:720px)',
  'prefers-reduced-motion:reduce','h-auth-strength[hidden]']){
  assert(css.includes(fragment),'Missing luxe style: '+fragment);
}
assert(js.includes("new MutationObserver(updateStrength)"));
assert(js.includes("aria-pressed"));
assert(html.includes('id="googleSignInButton"')&&html.includes('id="otpPanel"'));
console.log('AUTH_LUXE_PASS: premium glass theme, floating labels and sign-in hooks maintained');
