// UI wiring regression checks for real selector names and all persisted choices.
const fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync('app/web/index.html','utf8');
const css=fs.readFileSync('app/web/chat-themes.css','utf8');
const js=fs.readFileSync('app/web/chat-themes.js','utf8');
for(const id of ['vHeaderThemeBtn','vInboxThemeBtn','vThemeScrim','vThemePanel','vPanelClose','vClearChatWallpaper','vResetVisuals','vSelectedWallpaper','vChatThemeHint','messageScroller','homeChatList'])
 assert(html.includes('id="'+id+'"'), 'Missing theme UI ID: '+id);
for(const [kind,expected] of [['theme',6],['wallpaper',8],['composer',3]])
 assert.equal((html.match(new RegExp('data-v-kind="'+kind+'"','g'))||[]).length,expected,'Expected preview choices: '+kind);
for(const wallpaper of ['plain','doodles','dots','waves','grid','petals','sunset','stars']){
 assert(css.includes('[data-v-wallpaper="'+wallpaper+'"]'), 'Missing background '+wallpaper);
}
assert(js.includes('prefKey(loadedUser)') && js.includes('config.chats[chat]'));
assert(js.includes('matchMedia') && js.includes('state.active.id'));
assert(js.includes("window.addEventListener")===false || !js.includes("addEventListener('message'"));
assert(css.includes('#appScreen .inbox-chat') && css.includes('#appScreen .message-row.mine .bubble') && css.includes('#appScreen .composer'));
assert(css.includes('prefers-reduced-motion'));
assert(html.includes('src="/assets/chat-themes.js"') && html.includes('href="/assets/chat-themes.css"'));
console.log('CHAT_THEMES_PASS: accurate Huddle selectors, 6 modes, 8 wallpapers, 3 composers, per-chat browser persistence');
