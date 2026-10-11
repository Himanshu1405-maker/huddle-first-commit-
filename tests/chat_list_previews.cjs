const fs=require('node:fs'),assert=require('node:assert/strict');
const app=fs.readFileSync('app/web/app.js','utf8');
const api=fs.readFileSync('app/main.py','utf8');
const css=fs.readFileSync('app/web/chat-list-preview-polish.css','utf8');
const html=fs.readFileSync('app/web/index.html','utf8');
new Function(app);
assert(api.includes('"preview_kind": preview_kind'),'Authenticated API should classify media by attachment type');
assert(api.includes('"preview_label": preview_label'),'Backend should return readable media label');
assert(api.includes('"preview_caption": preview_caption'),'Caption metadata should be bounded');
assert(api.includes('FROM location_shares WHERE message_id=?'),'Location preview must use typed share records');
assert(api.includes('FROM attachments'),'Media preview must use attachment metadata');
assert(html.includes('href="/assets/chat-list-preview-polish.css"'),'New styles must load');
for(const kind of ['photo','video','location','voice','file','sticker']){
 assert(app.includes(kind+":" )||app.includes(kind+"':"),'Missing icon '+kind);
 assert(css.includes('.h-preview-symbol-'+kind),'Missing icon style '+kind);
}
assert(app.includes('function reconcileChatRows('),'Stable keyed render required');
assert(app.includes('current[i].isEqualNode(next[i])'),'Do not replace identical chat cards');
assert(app.includes('container.scrollTop=scroll'),'Preserve scroll position on reorder');
assert(app.includes('next[i].focus({preventScroll:true})'),'Keep keyboard focus');
assert(app.includes('const preview=chatPreview(c);'),'Both inbox lists should use typed previews');
assert(!app.includes('const preview=c.last_message?'),'Raw attachment filenames must not be chat previews');
assert(css.includes('scrollbar-gutter:auto!important'),'Eliminate mobile scrollbar gutter');
assert(css.includes('prefers-reduced-motion'),'Respect reduced motion');
console.log('CHAT_LIST_PREVIEW_PASS: typed badges, safe labels, keyed updates, mobile layout and motion settings');
