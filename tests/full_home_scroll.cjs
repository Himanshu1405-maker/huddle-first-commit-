/* Only one vertical scroll container on the Chats home page. */
const fs=require('node:fs'),assert=require('node:assert/strict');
const css=fs.readFileSync('app/web/chat-home-full-scroll.css','utf8');
const html=fs.readFileSync('app/web/index.html','utf8');
const js=fs.readFileSync('app/web/app.js','utf8');
new Function(js);
assert(html.includes('href="/assets/chat-home-full-scroll.css"'));
assert(html.lastIndexOf('chat-home-full-scroll.css')>html.lastIndexOf('inbox-moments-refinement.css'));
assert(css.includes('#appScreen #welcomeChat:not(.hidden)'));
assert(css.includes('overflow-y:auto!important'));
assert(css.includes('#appScreen #welcomeChat:not(.hidden)>.inbox-list'));
assert(css.includes('overflow-y:visible!important'));
assert(css.includes('flex:0 0 auto!important'));
assert(css.includes('scrollbar-width:thin'),'Show scrollbar feedback');
assert(css.includes('#appScreen #welcomeChat.hidden{display:none!important}'),'Do not overlap chat/AI');
assert(css.includes('@media(max-width:720px)'),'Mobile scrolling');
assert(js.includes("renderInboxHome();$('#welcomeChat').scrollTop=0"),'Filters reset outer scroll');
assert(!js.includes("renderInboxHome();$('#homeChatList').scrollTop=0"),'Old inner list scroll reset removed');
console.log('FULL_HOME_SCROLL_STATIC_PASS');
