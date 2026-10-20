/* Huddle Extras: durable chat settings and private collaboration panels. */
(()=>{
'use strict';
const q=id=>document.getElementById(id);
const safe=s=>String(s??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const api=async(url,method='GET',body)=>{
 const r=await fetch('/api'+url,{method,credentials:'same-origin',headers:{'Content-Type':'application/json'},
  ...(body?{body:JSON.stringify(body)}:{})});
 const j=await r.json().catch(()=>({}));
 if(!r.ok)throw Error(j.detail||'Something went wrong');
 return j;
};
const overlay=document.createElement('div');overlay.id='hPlusOverlay';overlay.className='h-plus-overlay hidden';
overlay.innerHTML='<section class="h-plus-panel" role="dialog" aria-modal="true" aria-labelledby="hPlusTitle"><header><div><small>HUDDLE EXTRAS</small><h2 id="hPlusTitle"></h2></div><button id="hPlusClose" aria-label="Close">✕</button></header><div id="hPlusContent" class="h-plus-content"></div></section>';
document.body.append(overlay);
const contentEl=q('hPlusContent');
const show=(title,html)=>{q('hPlusTitle').textContent=title;contentEl.innerHTML=html;overlay.classList.remove('hidden');q('hPlusClose').focus()};
const hide=()=>overlay.classList.add('hidden');
q('hPlusClose').onclick=hide;
overlay.addEventListener('click',e=>{if(e.target===overlay)hide()});
document.addEventListener('keydown',e=>{if(e.key==='Escape')hide()});
const say=(s,bad=false)=>typeof toast==='function'?toast(s,bad):console.log(s);
let showArchived=false;
const redraw=()=>{state.conversations.sort((a,b)=>Number(Boolean(b.preferences?.pinned))-Number(Boolean(a.preferences?.pinned))||String(b.updated_at).localeCompare(String(a.updated_at)));renderSidebar()};
const prefs=c=>({pinned:!!c.preferences?.pinned,archived:!!c.preferences?.archived,muted:!!c.preferences?.muted});
const navBtn=document.createElement('button');navBtn.id='hPlusTrigger';navBtn.className='h-plus-trigger hidden';navBtn.type='button';navBtn.textContent='☷';
navBtn.title='Chat settings, polls and events';navBtn.setAttribute('aria-label',navBtn.title);
q('chatHeader')?.append(navBtn);
const archiveBtn=document.createElement('button');archiveBtn.id='hArchiveToggle';archiveBtn.className='h-archive-toggle';archiveBtn.textContent='▤ Archived';archiveBtn.type='button';
const chatList=q('conversationList');chatList?.parentElement?.insertBefore(archiveBtn,chatList);
archiveBtn.onclick=()=>{showArchived=!showArchived;archiveBtn.textContent=showArchived?'← All conversations':'▤ Archived';redraw()};
function settings(){
 const c=state.active;if(!c)return;
 const p=prefs(c);
 show('Chat settings','<p class="h-plus-muted">'+safe(c.name)+'</p>'+
 ['pinned','archived','muted'].map(k=>'<button class="h-plus-action" data-pref="'+k+'"><b>'+(
 k==='pinned'?'Pin to top':k==='archived'?'Archive chat':'Mute notifications')+'</b><span>'+(p[k]?'✓ On':'Off')+'</span></button>').join('')+
 (c.kind==='dm'?'<button id="hBlockChat" class="h-plus-danger">Block this person</button>':'')+
 '<button id="hPlanChat" class="h-plus-primary">Polls and events →</button>');
 contentEl.querySelectorAll('[data-pref]').forEach(el=>el.onclick=async()=>{
   const next=prefs(c);next[el.dataset.pref]=!next[el.dataset.pref];
   try{await api('/conversations/'+c.id+'/preferences','PATCH',next);c.preferences=next;redraw();settings()}
   catch(e){say(e.message,true)}
 });
 q('hBlockChat')?.addEventListener('click',async()=>{
  const other=c.members.find(m=>m.id!==state.me?.id);
  if(!other||!confirm('Block '+other.name+' from direct messaging?'))return;
  try{await api('/users/'+other.id+'/block','PUT');hide();showWelcome();say('User blocked')}
  catch(e){say(e.message,true)}
 });
 q('hPlanChat').onclick=planning;
}
async function planning(){
 const c=state.active;if(!c)return;
 show('Polls and events','<p class="h-plus-muted">Only members of '+safe(c.name)+' can participate.</p>'+
 '<div class="h-plus-buttons"><button id="hCreatePoll" class="h-plus-primary">＋ Poll</button><button id="hCreateEvent" class="h-plus-primary">＋ Event</button></div><div id="hPlanningResults">Loading…</div>');
 q('hCreatePoll').onclick=()=>{
  show('New poll','<form id="hPollForm" class="h-plus-form"><label>Question<input name="q" maxlength="180" required minlength="4"></label>'+
   '<label>Option A<input name="a" maxlength="100" required></label><label>Option B<input name="b" maxlength="100" required></label>'+
   '<label>Option C (optional)<input name="c" maxlength="100"></label><button class="h-plus-primary">Post poll</button></form>');
  q('hPollForm').onsubmit=async e=>{
   e.preventDefault();const f=new FormData(e.target);
   try{await api('/conversations/'+c.id+'/polls','POST',{question:f.get('q'),options:['a','b','c'].map(k=>String(f.get(k)||'').trim()).filter(Boolean)});await planning()}
   catch(e){say(e.message,true)}
  };
 };
 q('hCreateEvent').onclick=()=>{
  show('New event','<form id="hEventForm" class="h-plus-form"><label>Title<input name="title" maxlength="120" required></label>'+
   '<label>When<input name="date" type="datetime-local" required></label>'+
   '<label>Details<textarea name="details" maxlength="500"></textarea></label>'+
   '<button class="h-plus-primary">Schedule event</button></form>');
  q('hEventForm').onsubmit=async e=>{
   e.preventDefault();const f=new FormData(e.target),when=new Date(f.get('date'));
   if(Number.isNaN(when.getTime()))return say('Choose a valid date',true);
   try{await api('/conversations/'+c.id+'/events','POST',{title:f.get('title'),starts_at:when.toISOString(),details:f.get('details')});await planning()}
   catch(e){say(e.message,true)}
  };
 };
 const target=q('hPlanningResults');
 try{
  const [p,ev]=await Promise.all([api('/conversations/'+c.id+'/polls'),api('/conversations/'+c.id+'/events')]);
  if(q('hPlanningResults')!==target)return;
  target.innerHTML='<h3>Polls</h3>'+p.polls.map(poll=>
    '<article class="h-plus-card"><b>'+safe(poll.question)+'</b>'+poll.options.map(o=>
    '<button class="h-plus-choice" data-poll="'+safe(poll.id)+'" data-option="'+safe(o.id)+'">'+
    (poll.my_vote===o.id?'✓ ':'')+safe(o.label)+' · '+Number(o.count)+'</button>').join('')+'</article>').join('')+
    (!p.polls.length?'<p class="h-plus-muted">No polls yet.</p>':'')+
    '<h3>Events</h3>'+ev.events.map(item=>
    '<article class="h-plus-card"><b>'+safe(item.title)+'</b><p>'+
    safe(new Date(item.starts_at).toLocaleString())+'</p><p>'+safe(item.details)+'</p>'+
    ['going','maybe','not_going'].map(answer=>'<button class="h-plus-choice" data-event="'+safe(item.id)+'" data-answer="'+answer+'">'+
      (item.my_rsvp===answer?'✓ ':'')+answer.replace('_',' ')+'</button>').join('')+'</article>').join('')+
    (!ev.events.length?'<p class="h-plus-muted">No events yet.</p>':'');
  target.querySelectorAll('[data-poll]').forEach(el=>el.onclick=async()=>{
    try{await api('/polls/'+el.dataset.poll+'/vote','PUT',{option_id:el.dataset.option});await planning()}catch(e){say(e.message,true)}
  });
  target.querySelectorAll('[data-event]').forEach(el=>el.onclick=async()=>{
    try{await api('/events/'+el.dataset.event+'/rsvp','PUT',{answer:el.dataset.answer});await planning()}catch(e){say(e.message,true)}
  });
 }catch(e){target.textContent=e.message}
}
navBtn.onclick=settings;
window.HuddlePlus={
 sync:()=>{navBtn.classList.toggle('hidden',!state.active);if(!state.active)hide()},
 visible:c=>Boolean(c?.preferences?.archived)===showArchived,
 isMuted:id=>Boolean(state.conversations.find(c=>c.id===id)?.preferences?.muted),
 sort:redraw,reset:()=>{showArchived=false;archiveBtn.textContent='▤ Archived';hide();},
 refresh:()=>{if(!overlay.classList.contains('hidden')&&q('hPlusTitle').textContent==='Polls and events')void planning()}
};
})();
