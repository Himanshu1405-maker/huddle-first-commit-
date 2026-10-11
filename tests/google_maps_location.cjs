// Google Maps location URLs, consent, and message-card rendering regression.
'use strict';
const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const src=fs.readFileSync('app/web/location-sharing.js','utf8');
const css=fs.readFileSync('app/web/location-sharing.css','utf8');
const main=fs.readFileSync('app/main.py','utf8');
assert(!/openstreetmap|iframeURL|activeMaps|data-h-location-map/i.test(src),'Legacy map provider must be removed');
assert(!main.includes('https://www.openstreetmap.org'),'Unused third-party frame permission must be removed');
assert(!/\.h-location-map iframe/.test(css),'No unwanted third-party iframe');
assert(src.includes('Opening Google Maps sends the shared pin to Google'),'Sharing privacy notice is required');
assert(src.includes('target="_blank" rel="noopener noreferrer"'),'Maps links must not control the Huddle window');

const helpers=src.slice(src.indexOf('  function coordinatePair('),src.indexOf('  function decorateLocations()'));
assert(helpers.includes('function mapURL(')&&helpers.includes('function directionsURL('));
const functions=vm.createContext({});
vm.runInContext(helpers+'\nthis.urls={coordinatePair,mapURL,directionsURL};',functions);
const {mapURL,directionsURL,coordinatePair}=functions.urls;
assert.equal(mapURL(31.77,76.98),'https://www.google.com/maps/search/?api=1&query=31.77%2C76.98');
assert.equal(directionsURL(31.77,76.98),'https://www.google.com/maps/dir/?api=1&destination=31.77%2C76.98');
assert.equal(mapURL(100,78),null);
assert.equal(directionsURL('bad',78),null);
assert.equal(coordinatePair(null,78),null);
assert.equal(mapURL(0,0),'https://www.google.com/maps/search/?api=1&query=0%2C0');

const rendered=[];
const bubble={hidden:false};
const stack={insertBefore(card){rendered.push(card.innerHTML)},querySelector(){return null}};
const row={querySelector(selector){return selector==='.bubble'?bubble:selector==='.message-stack'?stack:null}};
const composer={insertBefore(){}};
const messagesElement={addEventListener(){}};
function fakeNode(){return {setAttribute(){},addEventListener(){},textContent:'',dataset:{},classList:{add(){},remove(){}}}}
const state={
  me:{id:'sender'},active:{id:'chat-1'},
  messages:[{id:'pin-msg',conversation_id:'chat-1',sender_id:'sender',
    location:{mode:'pin',latitude:31.77,longitude:76.98}}]
};
const document={
  createElement(){return fakeNode()},
  querySelector(selector){return selector==='#conversationView .composer'?composer:null},
  getElementById(id){return id==='mediaFileInput'?{}:id==='messages'?messagesElement:id==='msg-pin-msg'?row:null},
  addEventListener(){}
};
const context=vm.createContext({document,window:{addEventListener(){},isSecureContext:true},state,
  renderMessages(){},setInterval(){},navigator:{},Date,Number,Math,console,
  toast(){},post(){},patch(){},esc:x=>String(x),encodeURIComponent});
vm.runInContext(src,context,{filename:'location-sharing.js'});
vm.runInContext('renderMessages(false)',context);
assert.equal(rendered.length,1);
assert(rendered[0].includes('Google Maps ↗'),'Pin link must be visible');
assert(rendered[0].includes('Directions ↗'),'Directions link must be visible');
assert(rendered[0].includes('31.77%2C76.98'),'Correct pin coordinates must be encoded');
assert(!rendered[0].includes('<iframe'),'Maps must not be loaded before user taps a link');
assert(bubble.hidden,'Original location text must be replaced by a map card');
rendered.length=0;
state.messages=[{id:'pin-msg',conversation_id:'chat-1',sender_id:'sender',
  location:{mode:'live',active:false,latitude:null,longitude:null,expires_at:'2020-01-01T00:00:00Z'}}];
vm.runInContext('renderMessages(false)',context);
assert.equal(rendered.length,1);
assert(!rendered[0].includes('www.google.com/maps/'),'Stopped live shares must not reveal coordinates');
assert(rendered[0].includes('Live location ended'),'Ended share state must be clear');
rendered.length=0;
state.messages=[{id:'pin-msg',conversation_id:'chat-1',sender_id:'sender',
  location:{mode:'live',active:true,latitude:31.78,longitude:77.02,
    expires_at:new Date(Date.now()+600000).toISOString(),updated_at:new Date().toISOString()}}];
vm.runInContext('renderMessages(false)',context);
assert(rendered[0].includes('31.78%2C77.02'),'Live coordinates should be the latest received update');
assert(rendered[0].includes('Reopen Google Maps'),'Explain that external maps show a snapshot');
assert(rendered[0].includes('Stop sharing'),'Owners must keep a stop-sharing control');
console.log('GOOGLE_MAPS_LOCATION_PASS: map links, directions, active and expired live shares, no third-party auto-load');
