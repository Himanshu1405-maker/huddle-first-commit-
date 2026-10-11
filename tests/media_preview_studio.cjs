// Every pre-existing media editor feature stays reachable after visual refresh.
'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync('app/web/index.html','utf8');
const script=fs.readFileSync('app/web/chat-enhancements.js','utf8');
const css=fs.readFileSync('app/web/media-preview-studio.css','utf8');
new Function(script);
assert(html.includes('href="/assets/media-preview-studio.css"'));
assert(html.lastIndexOf('media-preview-studio.css')>html.lastIndexOf('view-once.css'),
 'Media Studio should override legacy editor styles');
assert(script.includes("dialog.className='h-editor-overlay h-media-studio'"));
for(const id of ['hEditorStage','hEditorTools','hEditorCaption','hEditorFilename',
 'hEditorSend','hEditorCancel','hEditorViewOnce','hEditorZoom','hEditorZoomValue',
 'hEditorKind','hEditorTitle','hEditorRecipient']){
  assert(script.includes(id),'Lost editor control '+id);
}
for(const tool of ['free','square','portrait','wide','rotate','flip','pen','undo']){
  assert(script.includes("toolBtn('"+tool+"'"),'Lost photo tool '+tool);
}
for(const feature of ["state.active?.kind==='dm'","canvas.toBlob","video.controls=true",
 "video.playsInline=true","drawFrame=requestAnimationFrame","cancelAnimationFrame(drawFrame)",
 "if(canvas.width!==targetWidth)canvas.width=targetWidth",
 "if(canvas.height!==targetHeight)canvas.height=targetHeight",
 "aria-pressed","viewOnce=Boolean","sendMediaFile(outgoing,caption,null,viewOnce)"]){
 assert(script.includes(feature),'Missing retained behavior: '+feature);
}
assert(css.includes('@media(max-width:720px)'),'Mobile layout required');
assert(css.includes('@media(max-width:370px)'),'Small phone layout required');
assert(css.includes('prefers-reduced-motion'),'Honor reduced motion setting');
assert(css.includes('h-editor-tool-strip'),'Crop/edit tools need mobile-safe strips');
assert(css.includes('#hEditorCaption'),'Caption must remain styled');
assert(css.includes('.h-once-choice'),'View Once must remain visible');
console.log('MEDIA_PREVIEW_STUDIO_PASS: all media preview controls retained, new layout and reduced canvas jitter');
