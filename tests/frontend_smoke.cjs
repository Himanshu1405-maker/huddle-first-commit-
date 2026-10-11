// Lightweight UI event sanity check when Chrome is unavailable.
// It checks the user-facing registration pathway without a network or browser.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.join(__dirname, '..');
const src = fs.readFileSync(path.join(root, 'app/web/app.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'app/web/index.html'), 'utf8');
const identifiers = [...src.matchAll(/\$\('#([a-zA-Z][\w-]*)'\)/g)].map(m => m[1]);
const ids = [...(html + src).matchAll(/\bid=["']([a-zA-Z][\w-]*)["']/g)].map(m => m[1]);
for (const id of identifiers) assert(ids.includes(id), `UI refers to missing ID: ${id}`);

const nodes = new Map();
const calls = [];
function mockNode() {
  return {
    value: '', innerHTML: '', textContent: '', dataset: {}, style: {}, required: false,
    disabled: false, scrollHeight: 0, scrollTop: 0, clientHeight: 0, children: [],
    handlers: {}, focus() { this.focused = true; },
    addEventListener(event, handler) { this.handlers[event] = handler; },
    querySelector() { return mockNode(); },
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
  };
}
function selector(sel) {
  if (!nodes.has(sel)) nodes.set(sel, mockNode());
  return nodes.get(sel);
}
class FakeSocket {
  constructor() { this.readyState = 0; this.handlers = {}; }
  addEventListener(event, fn) { this.handlers[event] = fn; }
  close() { this.readyState = 3; }
  send() {}
}
const context = vm.createContext({
  document: {
    querySelector: selector, querySelectorAll: () => [], addEventListener() {}, visibilityState: 'visible',
    createElement(tag) {
      if (tag === 'template') return {content: {children: []}, set innerHTML(value) {this.html=value;}};
      return mockNode();
    }
  },
  window: { addEventListener() {} },
  fetch: async (url, config) => {
    calls.push({ url, config });
    if (url === '/api/me') return { ok: false, status: 401, json: async () => ({detail:'Sign in'}) };
    if (url === '/api/auth/register') return { ok: true, status: 201, json: async () => ({user: {id:'user1',name:'Alex Test',handle:'alex_test'}}) };
    if (url === '/api/conversations') return {ok:true,status:200,json:async()=>({conversations:[]})};
    throw new Error('Unexpected network call: '+url);
  },
  WebSocket: FakeSocket,
  location: {protocol:'https:',host:'huddle.example'},
  crypto: {randomUUID: () => 'nonce-1'},
  console, Date, Map, Set, Promise, URL, Math, JSON, String,
  setTimeout: () => 0, clearTimeout() {}, setInterval() {},
});
vm.runInContext(src, context, {filename:'app.js'});
const tick = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  await tick();
  selector('#switchAuth').handlers.click();
  assert.equal(selector('#authName').required,true);
  const submit = selector('#authForm').handlers.submit;
  const event = {preventDefault() {}};
  selector('#authName').value = 'Alex Test';
  selector('#authHandle').value = 'alex test';
  selector('#authPassword').value = 'ValidPass123!';
  const before = calls.length;
  await submit(event);
  assert.match(selector('#authError').textContent,/username/i);
  assert.equal(calls.length,before,'Invalid handle should not hit server');
  selector('#authHandle').value = 'alex_test';
  selector('#authName').value = ' ';
  await submit(event);
  assert.match(selector('#authError').textContent,/display name/i);
  assert.equal(calls.length,before,'Invalid display name should not hit server');
  selector('#authName').value = 'Alex Test';
  await submit(event);
  await tick();
  assert.equal(calls.filter(x=>x.url==='/api/auth/register').length,1,'Valid registration should send exactly one request');
  const payload = JSON.parse(calls.find(x=>x.url==='/api/auth/register').config.body);
  assert.deepEqual(payload,{name:'Alex Test',handle:'alex_test',password:'ValidPass123!'});
  assert.equal(selector('#selfName').textContent,'Alex Test');
  assert.equal(vm.runInContext('state.me.handle',context),'alex_test');
  vm.runInContext('signOutLocal()',context);
  assert.equal(vm.runInContext('state.isRegister',context),false,'Sign out should show sign-in view');
  assert.equal(vm.runInContext('esc(`<img src="x" onerror="hack()">`)',context),'&lt;img src=&quot;x&quot; onerror=&quot;hack()&quot;&gt;');
  console.log('FRONTEND_SMOKE_PASS: DOM references, invalid names/handles, registration request, login reset, HTML escaping');
})().catch(e=>{console.error(e);process.exitCode=1;});
