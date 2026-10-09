/* Free on-device Huddle AI: no credentials or paid provider. Runs in a Web Worker. */
'use strict';
const MODEL='onnx-community/SmolLM2-135M-Instruct-ONNX-GQA';
const QUALITY_MODEL='onnx-community/SmolLM2-360M-Instruct-ONNX';
let qualityGenerator=null;
let generator=null;
let loading=null;
function progress(message){self.postMessage({type:'progress',message});}
async function improveQuality(){
  if(qualityGenerator){self.postMessage({type:'upgrade_ready'});return;}
  if(!generator)await load();
  progress('Downloading better-quality model (about 360 MB once); saved for later visits…');
  try{
    const {pipeline,env}=await import('https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1/+esm');
    env.allowLocalModels=false;env.useBrowserCache=typeof caches!=='undefined';env.cacheKey='transformers-cache';
    qualityGenerator=await pipeline('text-generation',QUALITY_MODEL,{device:'wasm',dtype:'q8',
      progress_callback:(x)=>{if(x.status==='progress'&&typeof x.progress==='number')progress('Better answers model: '+Math.round(x.progress)+'% ('+String(x.file||'weights')+')');}});
    self.postMessage({type:'upgrade_ready'});
  }catch(error){
    console.warn('Optional better-quality model unavailable:',String(error?.message||'').slice(0,170));
    self.postMessage({type:'upgrade_error'});
  }
}
async function load(){
  if(generator)return;
  if(loading)return loading;
  loading=(async()=>{
    progress('Loading the open-source inference engine…');
    const {pipeline,env}=await import('https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1/+esm');
    env.allowLocalModels=false;
    // Keep model weights + WASM binaries across reloads via the browser Cache API.
    // Use the library's default cache key to reuse files from earlier Huddle versions.
    env.useBrowserCache=typeof caches!=='undefined';
    env.useWasmCache=env.useBrowserCache;
    env.cacheKey='transformers-cache';
    // navigator.gpu can exist even when Chrome has no usable adapter.
    let available=false;
    try{available=Boolean(await navigator.gpu?.requestAdapter({powerPreference:'low-power'}));}catch{available=false;}
    const options={
      device:available?'webgpu':'wasm',
      dtype:available?'q4f16':'q8',
      progress_callback:(entry)=>{
        if(entry.status==='progress'&&typeof entry.progress==='number'){
          progress('Downloading local model: '+Math.round(entry.progress)+'% ('+String(entry.file||'model')+')');
        }else if(entry.status==='initiate')progress('Downloading '+String(entry.file||'model files')+'…');
      }
    };
    progress(available?'Using device GPU; preparing model…':'Using device CPU; first load and answers may be slower…');
    try{
      generator=await pipeline('text-generation',MODEL,options);
    }catch(error){
      // Some devices expose WebGPU but don't support this model's GPU operations.
      console.warn('Local AI GPU load failed:',String(error?.name||'Error'),String(error?.message||'').slice(0,230));
      if(!available)throw error;
      progress('GPU unavailable for this model. Trying CPU mode…');
      generator=await pipeline('text-generation',MODEL,{...options,device:'wasm',dtype:'q8'});
    }
    // Don't claim permanent storage unless the model has actually been cached.
    let cachedFiles=0;
    if(env.useBrowserCache){
      try{cachedFiles=(await (await caches.open(env.cacheKey)).keys()).length;}catch{}
    }
    self.postMessage({type:'ready',cachedFiles});
  })().catch(err=>{loading=null;console.warn('Local AI initialization failure:',String(err?.name||'Error'),String(err?.message||'').slice(0,240));progress('Could not load local AI. A Wi-Fi connection and available device memory are needed.');self.postMessage({type:'error',code:'load_failed',reason:String(err?.name||'Error').slice(0,55),detail:String(err?.message||'').slice(0,240)});return null;});
  return loading;
}
self.addEventListener('message',async event=>{
  const data=event.data||{};
  if(data.type==='load'){try{await load()}catch{}return;}
  if(data.type==='upgrade'){await improveQuality();return;}
  if(data.type!=='ask')return;
  try{
    await load();
    const recent=(Array.isArray(data.messages)?data.messages:[]).slice(-7)
      .map(m=>({role:m.role==='assistant'?'assistant':'user',content:String(m.content||'').slice(0,700)}));
    if(!recent.length)throw Error('empty');
    const messages=[
      {role:'system',content:'You are Huddle, a warm, reliable learning assistant. Answer the most recent question directly. Be specific and explain in plain words, with a short example when helpful. Do not repeat the question or repeat yourself. If you do not know a fact, say so rather than inventing it. Never claim to access private chats, files, websites or live news. Keep responses age-appropriate. Avoid unnecessary greetings and filler.'},
      ...recent
    ];
    const tokens=Number.isFinite(Number(data.max_new_tokens)) && data.max_new_tokens ? Math.min(240,Math.max(12,Number(data.max_new_tokens))) : 195;
    const active=qualityGenerator||generator;
    const result=await active(messages,{max_new_tokens:tokens,do_sample:false,return_full_text:false,repetition_penalty:1.15});
    const dataOut=result?.[0]?.generated_text;
    const value=typeof dataOut==='string'?dataOut:Array.isArray(dataOut)?String(dataOut.at(-1)?.content||''):dataOut&&typeof dataOut==='object'?String(dataOut.content||''):'';
    const answer=value.trim().slice(0,2400)||'I could not generate a clear answer. Try a simpler question.';
    self.postMessage({type:'answer',id:data.id,text:answer});
  }catch(error){self.postMessage({type:'answer_error',id:data.id,code:'generation_failed'});}
});
