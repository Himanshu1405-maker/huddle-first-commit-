const fs=require('node:fs'),assert=require('node:assert/strict');
const js=fs.readFileSync('app/web/app.js','utf8');
const worker=fs.readFileSync('app/web/local-ai-worker.js','utf8');
for(const part of ["env.useBrowserCache=typeof caches!=='undefined'","env.useWasmCache=env.useBrowserCache","env.cacheKey='transformers-cache'","type:'ready',cachedFiles"]){
  assert(worker.includes(part),part+' missing');
}
for(const part of ["LOCAL_AI_PREF='huddle-ai-installed-v1'","localStorage.setItem(LOCAL_AI_PREF,'yes')","async function hasLocalAIModelCache()","async function restoreLocalAIIfSaved()","await restoreLocalAIIfSaved()","navigator.storage.persist()","Opening saved AI model"]){
 assert(js.includes(part),part+' missing');
}
assert(js.includes("requests.some(item=>/\\.onnx(?:$|[?#])/.test(item.url))"), 'Must check weight files, not arbitrary cache entries');
assert(js.includes("if(cached)startLocalAI({restore:true})"), 'Only silently restore model if saved weights exist');
console.log('LOCAL_AI_CACHE_PASS: persistent browser cache, saved consent and automatic offline-safe restore');
