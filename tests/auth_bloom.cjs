// Authentication makeover regression: preserve every functional hook.
const fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync('app/web/index.html','utf8');
const css=fs.readFileSync('app/web/auth-bloom.css','utf8');
const src=fs.readFileSync('app/web/app.js','utf8');
const auth=html.slice(html.indexOf('<div class="auth-screen"'),html.indexOf('<div class="app-screen'));
for(const id of ['authScreen','authForm','authTitle','authSubtitle','authHandle','authPassword','authName','authEmail','registerNameField','registerEmailField','authError','authSubmit','togglePassword','otpPanel','otpForm','otpCode','otpSubmit','resendOtp','otpBack','googleAuthArea','googleSignInButton','googleBrowserHelp','openChromeGoogle','copyGoogleLink','googleBrowserLink','switchAuth','authSwitchPrefix','passwordHint']){
  assert(auth.includes('id="'+id+'"'),'Missing '+id);
  assert.equal((auth.match(new RegExp('id="'+id+'"','g'))||[]).length,1,'Duplicate '+id);
}
assert(html.includes('href="/assets/auth-bloom.css"'));
assert(html.includes('class="auth-hero"')&&html.includes('class="showcase-phone"'));
assert(html.includes('label for="authHandle"')&&html.includes('label for="authPassword"'));
assert(auth.includes('autocomplete="one-time-code"')&&auth.includes('autocomplete="username"'));
assert(src.includes("$('#switchAuth').addEventListener('click',toggleAuth)"));
for(const fragment of ['#authScreen.auth-screen','linear-gradient(','.showcase-phone','.auth-form-shell','#authScreen .form-field input:focus','max-width:720px','prefers-reduced-motion:reduce'])
  assert(css.includes(fragment),'Missing visual style '+fragment);
console.log('AUTH_BLOOM_PASS: auth, signup, OTP and Google hooks intact; responsive themes present');
