const fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync('app/web/index.html','utf8');
const css=fs.readFileSync('app/web/style.css','utf8');
for(const fragment of ['>Chats <em>✦</em>','placeholder="Search your chats"','> New chat']){
 assert(html.includes(fragment),fragment+' missing');
}
for(const frag of ['.conv-item{min-height:81px','.conv-name{font-size:15px','.searchbox input{font-size:15px','.bubble{font-size:15px','.person-row{min-height:75px','.ai-suggestions button{min-height:108px','.modal-input,.modal-textarea{font-size:16px','.sidebar{width:min(420px,95vw)',"@media(prefers-reduced-motion:reduce)"]){
 assert(css.includes(frag),frag+' missing');
}
console.log('CHAT_LAYOUT_PASS: larger inbox, chats, people search, message bubbles and thumb targets');
