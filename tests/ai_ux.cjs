const fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync('app/web/index.html','utf8');
const js=fs.readFileSync('app/web/app.js','utf8');
const css=fs.readFileSync('app/web/style.css','utf8');
for(const id of ['aiView','aiNotice','aiNoticeText','aiAvailability','aiInputRow','aiComposerHint','aiTyping','aiSuggestions','aiSend']){
  assert(html.includes('id="'+id+'"'),id+' missing');
}
assert(js.includes('function aiModeAvailable()'), 'Model availability must be checked');
assert(js.includes('button.disabled=!available||state.aiBusy'), 'Prevent sending when provider not configured');
assert(!js.includes("toast(image?'Image generation needs"), 'Must not spam AI unavailable toasts');
assert(js.includes("area.querySelectorAll('.toast').forEach(node=>node.remove())"), 'Global toast dedup required');
assert(js.includes("notice.classList.toggle('hidden',available)"), 'Show one clear AI status banner');
assert(js.includes("$('#aiTyping').classList.remove('hidden')"), 'Pending responses need a visible state');
assert(css.includes('@media(prefers-reduced-motion:reduce)'),'Respect reduced motion');
assert(css.includes('.ai-suggestions{display:grid'),'Suggestion cards must use compact responsive layout');
console.log('AI_UX_PASS: missing provider handled inline, duplicate toasts removed, creative responsive layout wired');
