const fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync('app/web/index.html','utf8');
const js=fs.readFileSync('app/web/app.js','utf8');
for(const id of ['otpPanel','otpCode','otpForm','registerEmailField','aiView','aiSidebarBtn','aiForm','aiMessages']){
 assert(html.includes(`id="${id}"`),`Missing UI control: ${id}`);
}
for(const route of ['/auth/verify','/auth/resend','/ai/chat','/ai/image','/ai/history']){
 assert(js.includes(route),`Missing UI connection: ${route}`);
}
console.log('FRONTEND_FEATURE_WIRING_PASS');
