"""Optional local end-to-end smoke test / screenshot capture with Playwright.
Requires: pip install playwright; chromium browser installed.
"""
import os
import subprocess
import time
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'screenshots'
OUT.mkdir(exist_ok=True, parents=True)
server = subprocess.Popen(['uvicorn','app.main:app','--host','127.0.0.1','--port','8878'],cwd=ROOT,env={**os.environ,'HUDDLE_DB':str(ROOT/'demo.db'),'SEED_DEMO':'1'},stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
try:
    for _ in range(70):
        try:
            if requests.get('http://127.0.0.1:8878/health',timeout=.2).ok:break
        except Exception:pass
        time.sleep(.2)
    else:raise RuntimeError('Server failed to start: '+server.stderr.read().decode())
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--no-proxy-server','--disable-web-security','--disable-features=BlockInsecurePrivateNetworkRequests'])
        context=browser.new_context(viewport={'width':1450,'height':900},device_scale_factor=1)
        page=context.new_page()
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:8878/',wait_until='networkidle')
        page.screenshot(path=str(OUT/'01-login.png'))
        page.locator('#authHandle').fill('aarya')
        page.locator('#authPassword').fill('DemoPass123!')
        page.locator('#authSubmit').click()
        page.locator('#newChatBtn').wait_for(timeout=15000)
        page.screenshot(path=str(OUT/'02-home.png'))
        page.get_by_text('First Commit Builders').first.click()
        page.get_by_text('Welcome to First Commit Builders!',exact=False).wait_for(timeout=10000)
        page.screenshot(path=str(OUT/'03-group-chat.png'))
        # Browser B: distinct account, same group, real WebSocket broadcast.
        other=browser.new_context(viewport={'width':1100,'height':850},device_scale_factor=1)
        bob=other.new_page()
        bob.goto('http://127.0.0.1:8878/',wait_until='networkidle')
        bob.locator('#authHandle').fill('meera')
        bob.locator('#authPassword').fill('DemoPass123!')
        bob.locator('#authSubmit').click()
        bob.locator('#newChatBtn').wait_for(timeout=12000)
        bob.get_by_text('First Commit Builders').first.click()
        bob.locator('#messageInput').fill('Real-time verified across two browser sessions ✅')
        bob.locator('#sendBtn').click()
        page.get_by_text('Real-time verified across two browser sessions',exact=False).wait_for(timeout=15000)
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT/'04-realtime-demo.png'))
        # Check private chat creation, posting and search.
        page.locator('#newChatBtn').click()
        page.locator('#newUsersList').get_by_text('Kabir Mehta').click()
        page.locator('#messageInput').fill('Hey Kabir — ready for the hackathon?')
        page.locator('#sendBtn').click()
        page.get_by_text('Hey Kabir — ready for the hackathon?').wait_for(timeout=10000)
        page.screenshot(path=str(OUT/'05-direct-chat.png'))
        page.locator('#searchMessagesBtn').click()
        page.locator('#messageSearchInput').fill('hackathon')
        page.get_by_text('Hey Kabir — ready for the hackathon?').last.wait_for(timeout=10000)
        page.screenshot(path=str(OUT/'06-search.png'))
        page.locator('#closeModal').click()
        mobile = browser.new_context(viewport={'width':390,'height':844},device_scale_factor=1,is_mobile=True,has_touch=True)
        mp=mobile.new_page()
        mp.goto('http://127.0.0.1:8878/')
        mp.locator('#authHandle').fill('kabir')
        mp.locator('#authPassword').fill('DemoPass123!')
        mp.locator('#authSubmit').click()
        mp.locator('#openSidebar').wait_for(timeout=10000)
        mp.screenshot(path=str(OUT/'07-mobile.png'))
        print('BROWSER_SMOKE_PASS: signin; group chat; WebSocket cross-client; direct chat; search; mobile')
        print('Browser JS errors:',errors)
        print('Screenshots:',sorted(p.name for p in OUT.glob('*.png')))
        browser.close()
finally:
    server.terminate()
    try:server.wait(timeout=7)
    except subprocess.TimeoutExpired:server.kill()
