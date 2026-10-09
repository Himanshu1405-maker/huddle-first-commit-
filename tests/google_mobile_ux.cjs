const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.join(__dirname,'..');
const js=fs.readFileSync(path.join(root,'app/web/app.js'),'utf8');
const html=fs.readFileSync(path.join(root,'app/web/index.html'),'utf8');
const css=fs.readFileSync(path.join(root,'app/web/style.css'),'utf8');
for(const id of ['googleBrowserHelp','openChromeGoogle','copyGoogleLink','googleBrowserLink'])assert(html.includes('id="'+id+'"'),id+' missing');
assert(js.includes('prepareGoogleBrowserHelp();'));
assert(js.includes('auth/internal-error') && js.includes('googleSignInError(code,reason)'));
assert(js.includes('intent://huddle-web-production-76f3.up.railway.app/'));
assert(css.includes('.google-browser-help'));
assert(!js.includes("else{$('#authError').textContent=error.message;toast(error.message,true)}"));
console.log('GOOGLE_MOBILE_RECOVERY_PASS: help card, Chrome intent, clipboard fallback, single error');

assert(js.includes('const embedded='), 'Normal Android Chrome must not be mislabeled as an embedded browser');
