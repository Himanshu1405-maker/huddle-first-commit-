const fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync('app/web/index.html','utf8');
const js=fs.readFileSync('app/web/app.js','utf8');
const css=fs.readFileSync('app/web/style.css','utf8');
const cloudCss=fs.readFileSync('app/web/cloud-ai.css','utf8');
for(const id of ['aiView','aiNotice','aiNoticeText','aiAvailability','aiInputRow','aiComposerHint','aiTyping','aiSuggestions','aiSend']){
 assert(html.includes('id="'+id+'"'),id+' missing');
}
assert(js.includes('function aiModeAvailable()'), 'Model availability must be checked');
assert(js.includes('button.disabled=!available||state.aiBusy'), 'Prevent sending without a cloud provider');
assert(js.includes("notice.classList.toggle('hidden',available&&!state.aiError)"), 'Show setup status or error');
assert(js.includes("$('#aiTyping').classList.remove('hidden')"), 'Pending response indicator');
assert(js.includes('state.aiError='), 'Show provider errors');
assert(js.includes('/ai/chat') && js.includes('/ai/history'), 'Use server-side AI');
assert(js.includes('payload.use_context=true'), 'Send explicit context consent');
assert(css.includes('.ai-suggestions{display:grid'), 'Keep responsive layout');
assert(cloudCss.includes('@media(max-width:720px)'), 'Responsive AI layout');
assert(!html.includes('id="aiLocalStart"') && !html.includes('id="aiQualityUpgrade"'), 'Local loading UI must be absent');
console.log('AI_UX_PASS: hosted provider status, responsive design, history, consent, errors and no local model installer');

assert(js.includes('const generated=await generatePuterImage(prompt)'), 'Real image model must generate image, not poster');
assert(!js.includes("import('/assets/poster-studio.js')"), 'Abstract poster generator must not be used for images');
assert(html.includes('data-ai-mode="image">✧ Generate image'), 'Image tab must say Generate image');
