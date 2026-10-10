"""Real Chromium test for message selection, replies, forwarding and composer icons.
Uses private SQLite and temporary accounts only. No production messages modified.
"""
import tempfile,threading,time
from pathlib import Path
import requests,uvicorn
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from app.main import create_app


def main():
    with tempfile.TemporaryDirectory(prefix='huddle_msg_actions_') as folder:
        app=create_app(str(Path(folder)/'chat.sqlite'))
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8896,log_level='warning'))
        threading.Thread(target=server.run,daemon=True).start()
        base='http://127.0.0.1:8896'
        for _ in range(55):
            try:
                if requests.get(base+'/health',timeout=.5).status_code==200:break
            except requests.RequestException:pass
            time.sleep(.2)
        else:raise RuntimeError('Test app unavailable')
        def register(handle):
            s=requests.Session()
            r=s.post(base+'/api/auth/register',json={
                'name':handle.title(),'handle':handle,'password':'SecurePass123!'})
            assert r.status_code==201,r.text
            return s,r.json()['user']
        alice,alice_user=register('alice')
        bob,bob_user=register('bobby')
        carl,carl_user=register('carlx')
        conversation=alice.post(base+'/api/conversations/direct',json={
            'user_id':bob_user['id']}).json()['conversation']['id']
        destination=alice.post(base+'/api/conversations/direct',json={
            'user_id':carl_user['id']}).json()['conversation']['id']
        first=alice.post(base+f'/api/conversations/{conversation}/messages',json={
            'body':'Original Huddle message'}).json()['message']
        opts=webdriver.ChromeOptions()
        for flag in ['--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1160,870']:
            opts.add_argument(flag)
        browser=webdriver.Chrome(options=opts)
        try:
            for width,height in [(1160,870),(390,844)]:
                browser.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',{
                    'width':width,'height':height,'deviceScaleFactor':2 if width<720 else 1,'mobile':width<720})
                browser.get(base)
                browser.add_cookie({'name':'huddle_session','value':alice.cookies.get('huddle_session'),
                                    'path':'/','sameSite':'Strict'})
                browser.refresh()
                WebDriverWait(browser,12).until(lambda b:
                    not b.find_element(By.ID,'appScreen').get_attribute('class').split().__contains__('hidden'))
                ready=browser.execute_async_script("""
                   const done=arguments[arguments.length-1];
                   openConversation(arguments[0]).then(()=>done(true)).catch(e=>done(e.message));
                """,conversation)
                assert ready is True,ready
                WebDriverWait(browser,10).until(lambda b:
                    len(b.find_elements(By.CSS_SELECTOR,'.bubble[data-huddle-message-id]'))>=1)
                appearance=browser.execute_script("""
                  const icons=['emojiBtn','voiceNoteBtn','shareLocationBtn','sendBtn'];
                  const bar=document.querySelector('#hSelectedBar');
                  return {viewport:innerWidth,width:document.documentElement.scrollWidth,
                    iconCount:icons.filter(id=>!!document.querySelector('#'+id+' svg')).length,
                    selectedBar:!!bar,header:!!document.querySelector('#hForwardOverlay'),
                    keyboardLabel:document.querySelector('#messageInput')?.getAttribute('aria-label')};
                """)
                print('INTERACTION_INITIAL',width,appearance,flush=True)
                assert appearance['width']<=appearance['viewport']+3
                assert appearance['iconCount']==4 and appearance['selectedBar']
                bubble=browser.find_element(By.CSS_SELECTOR,'.bubble[data-huddle-message-id]')
                browser.execute_script("""
                  arguments[0].dispatchEvent(new MouseEvent('dblclick',{bubbles:true,cancelable:true}));
                """,bubble)
                WebDriverWait(browser,5).until(lambda b:
                    b.find_element(By.ID,'hSelectedBar').is_displayed() and
                    len(b.find_elements(By.CSS_SELECTOR,'.h-message-menu [data-h-command="reply"]'))==1)
                assert browser.find_element(By.CSS_SELECTOR,'.message-row.h-msg-selected')
                browser.find_element(By.CSS_SELECTOR,'.h-message-menu [data-h-command="reply"]').click()
                assert browser.find_element(By.ID,'hReplyPreview').is_displayed()
                browser.find_element(By.ID,'messageInput').send_keys('A reply from the test')
                browser.find_element(By.ID,'sendBtn').click()
                WebDriverWait(browser,9).until(lambda b:
                    len(b.find_elements(By.CSS_SELECTOR,'#messages .h-inline-quote'))>=1)
                assert 'Original Huddle message' in browser.find_element(By.CSS_SELECTOR,'.h-inline-quote').text
                fresh=alice.get(base+f'/api/conversations/{conversation}/messages').json()['messages']
                assert fresh[-1]['reply_to']['id']==first['id']
                browser.execute_script("""
                    const m=[...document.querySelectorAll('.bubble[data-huddle-message-id]')]
                      .find(x=>x.dataset.huddleMessageId===arguments[0]);
                    m.dispatchEvent(new MouseEvent('dblclick',{bubbles:true,cancelable:true}));
                """,first['id'])
                WebDriverWait(browser,5).until(lambda b:
                    len(b.find_elements(By.CSS_SELECTOR,'.h-message-menu [data-h-command="forward"]'))==1)
                browser.find_element(By.CSS_SELECTOR,'.h-message-menu [data-h-command="forward"]').click()
                assert browser.find_element(By.ID,'hForwardOverlay').is_displayed()
                browser.find_element(By.ID,'hForwardSearch').send_keys('Carl')
                destination_button=browser.find_element(By.CSS_SELECTOR,'[data-h-forward-to="'+destination+'"]')
                destination_button.click()
                WebDriverWait(browser,10).until(lambda b:
                    len(b.find_elements(By.ID,'hForwardOverlay'))==0)
                sent=carl.get(base+f'/api/conversations/{destination}/messages').json()['messages']
                assert sent[-1]['forwarded'] and sent[-1]['body']=='Original Huddle message'
                assert not browser.find_element(By.ID,'hSelectedBar').is_displayed()
            print('MESSAGE_INTERACTIONS_BROWSER_PASS',flush=True)
        finally:
            browser.quit();server.should_exit=True

if __name__=='__main__':main()
