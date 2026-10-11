/* Inline chat AI is private and opt-in; never broadcasts AI output. */
const fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync('app/web/index.html','utf8');
const app=fs.readFileSync('app/web/app.js','utf8');
const source=fs.readFileSync('app/web/chat-ai.js','utf8');
const css=fs.readFileSync('app/web/chat-ai.css','utf8');
new Function(source);new Function(app);
for(const id of ['hChatAiPanel','hChatAiOpen','hChatAiClose','hChatAiMessages',
 'hChatAiPrompt','hChatAiConnect','hChatAiStatus','hChatAiForm','hChatAiQuote',
 'hChatAiUseDraft','hChatAiClear','hChatAiSend']){
  assert(html.includes('id="'+id+'"'),'Missing assistant control '+id);
}
assert(html.includes('src="/assets/chat-ai.js" defer'));
assert(html.includes('href="/assets/chat-ai.css"'));
assert(html.indexOf('src="/assets/puter-ai.js"')<html.indexOf('src="/assets/chat-ai.js"'));
assert(/@\(\?:huddleai\|huddle\\s\+ai\)/i.test(app)||app.includes("const aiMention=text.match"),'Mention must be intercepted before normal sending');
const beforeSend=app.indexOf('const aiMention=text.match'),beforeSocket=app.indexOf("state.ws.send(JSON.stringify({type:'message:send'");
assert(beforeSend>=0&&beforeSend<beforeSocket,'AI mention must not broadcast');
assert(app.includes("window.HuddleChatAI?.reset?.()"),'Private assistant state must be cleared at logout');
assert(source.includes('checkbox.checked=false'),'Conversation quote must be unchecked by default');
assert(source.includes('const includeQuote=checkbox.checked'),'Context must require explicit consent');
assert(source.includes('use_context:false'),'Server AI must not retrieve whole conversation implicitly');
assert(source.includes("const request=(prompt+quoted).slice(0,2500)"),'Optional context must be bounded');
assert(source.includes("await post('/ai/chat'"),'Configured hosted AI should work');
assert(source.includes('window.puter.ai.chat(turns'),'Connected Puter AI should work');
assert(source.includes('window.puter.auth.signIn()'),'Sign-in requires user authorization');
assert(source.includes("const composer=$('messageInput')"),'AI answers must be used as editable drafts');
assert(!source.includes("'/conversations/'+"),'No AI response may be auto-sent as a regular chat message');
assert(css.includes('@media(max-width:720px)'),'Assistant must work on mobile');
assert(css.includes('.h-chat-ai-panel[hidden]'),'Assistant must be hidden when not opened');
console.log('CHAT_AI_INLINE_PASS: opt-in context, hosted AI, explicit draft sharing, mobile panel, logout reset');
