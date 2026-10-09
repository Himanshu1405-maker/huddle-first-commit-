// Regression guard: no on-device AI or accidental multi-hundred-megabyte downloads.
const fs=require('node:fs'), assert=require('node:assert/strict');
const html=fs.readFileSync('app/web/index.html','utf8');
const js=fs.readFileSync('app/web/app.js','utf8');
const main=fs.readFileSync('app/main.py','utf8');
const extras=fs.readFileSync('app/extras.py','utf8');
assert(!fs.existsSync('app/web/local-ai-worker.js'),'Local worker must not ship');
for(const fragment of ['startLocalAI(', 'askLocalAI(', 'localAIWorker(', 'hasLocalAIModelCache(', 'restoreLocalAIIfSaved(', 'transformers-cache', "new Worker("]){
 assert(!js.includes(fragment),fragment+' would initiate a device AI model');
}
assert(!html.includes('Enable on-device AI') && !html.includes('Opening your saved AI model'),'Legacy loading copy');
assert(main.includes('"ai_local": False'), 'Public config must disable local inference');
for(const provider of ['gemini','groq','openrouter','openai'])assert(extras.includes('"'+provider+'"'));
assert(js.includes("'/ai/chat'"),'Text requests must use server endpoint');
console.log('NO_LOCAL_AI_PASS: all assistant inference is provider-hosted, no ONNX or device model downloads');
