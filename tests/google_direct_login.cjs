const assert=require('node:assert/strict'),fs=require('node:fs');
const s=fs.readFileSync('app/web/app.js','utf8'),main=fs.readFileSync('app/main.py','utf8');
const st=s.indexOf('function initGoogleSignIn()'),body=s.slice(st,st+1500);
assert(body.includes('if(!state.config.google_client_id)'), 'GIS must take precedence over Firebase popup');
assert(body.includes("window.google.accounts.id.initialize"), 'Missing Google Identity Services flow');
assert(body.indexOf('if(!state.config.google_client_id)') < body.indexOf("window.google.accounts.id.initialize"));
assert(main.includes('verify_google_credential if google_ready() else verify_firebase_credential'));
console.log('GIS_PREFERENCE_PASS');
