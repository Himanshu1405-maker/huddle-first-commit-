"""Real-Chromium smoke test of Huddle's themes and per-conversation wallpapers.
Runs only against temporary SQLite; never modifies the public app's messages.
"""
import tempfile,threading,time
from pathlib import Path
import requests,uvicorn
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from app.main import create_app


def main():
    with tempfile.TemporaryDirectory(prefix='huddle_vivid_') as folder:
        app=create_app(str(Path(folder)/'vivid.sqlite'))
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8897,log_level='warning'))
        threading.Thread(target=server.run,daemon=True).start()
        base='http://127.0.0.1:8897'
        for _ in range(45):
            try:
                if requests.get(base+'/health',timeout=.5).status_code==200:break
            except requests.RequestException:pass
            time.sleep(.2)
        else:raise AssertionError('Cannot start app')
        session=requests.Session()
        def register(handle):
            c=requests.Session()
            r=c.post(base+'/api/auth/register',json={'name':handle.title(),'handle':handle,'password':'SafeTestPass123!'})
            assert r.status_code==201,r.text
            return c,r.json()['user']
        session,me=register('alice')
        bob_session,bob=register('bobby')
        carl_session,carl=register('carlx')
        cid=session.post(base+'/api/conversations/direct',json={'user_id':bob['id']}).json()['conversation']['id']
        other=session.post(base+'/api/conversations/direct',json={'user_id':carl['id']}).json()['conversation']['id']
        options=webdriver.ChromeOptions()
        for arg in ['--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1120,880']:
            options.add_argument(arg)
        browser=webdriver.Chrome(options=options)
        try:
            for width,height in [(1120,880),(390,844),(360,740)]:
                mobile=width<720
                browser.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':2 if mobile else 1,'mobile':mobile})
                browser.get(base)
                browser.add_cookie({'name':'huddle_session','value':session.cookies.get('huddle_session'),'path':'/','sameSite':'Strict'})
                browser.refresh()
                WebDriverWait(browser,10).until(lambda b:not b.find_element(By.ID,'appScreen').get_attribute('class').find('hidden')>=0)
                WebDriverWait(browser,5).until(lambda b:len(b.find_elements(By.CSS_SELECTOR,'#homeChatList .inbox-chat'))>=2)
                initial=browser.execute_script("""
                  const app=document.getElementById('appScreen'),card=document.querySelector('.inbox-chat');
                  return {appWidth:document.documentElement.scrollWidth,viewport:innerWidth,
                    theme:app.dataset.vTheme,wallpaper:app.dataset.vWallpaper,
                    cardBorder:getComputedStyle(card).borderRadius,
                    listVisible:!!card.getClientRects().length,
                    themeButton:!!document.getElementById('vHeaderThemeBtn') && !document.getElementById('vInboxThemeBtn')};
                """)
                print('VIVID_INBOX',width,initial,flush=True)
                assert initial['appWidth']<=initial['viewport']+3
                assert initial['themeButton'] and initial['listVisible']
                assert initial['wallpaper']=='doodles'
                browser.find_element(By.ID,'vHeaderThemeBtn').click()
                assert browser.find_element(By.ID,'vThemePanel').is_displayed()
                assert len(browser.find_elements(By.CSS_SELECTOR,'[data-v-kind="wallpaper"]'))==8
                before=browser.execute_script("return document.getElementById('appScreen').style.getPropertyValue('--h-text-scale')")
                browser.find_element(By.ID,'hTextLarger').click()
                after=browser.execute_script("return document.getElementById('appScreen').style.getPropertyValue('--h-text-scale')")
                assert float(after)>float(before) and browser.find_element(By.ID,'hTextQuickValue').text=='105%',(before,after)
                browser.find_element(By.ID,'hTextSmaller').click()
                assert browser.find_element(By.ID,'hTextQuickValue').text=='100%'
                browser.find_element(By.CSS_SELECTOR,'[data-v-kind="theme"][data-v-value="lavender"]').click()
                browser.find_element(By.CSS_SELECTOR,'[data-v-kind="wallpaper"][data-v-value="waves"]').click()
                assert browser.execute_script("return document.getElementById('appScreen').dataset.vTheme")=='lavender'
                browser.find_element(By.ID,'vPanelClose').click()
                assert not browser.find_element(By.ID,'vThemePanel').is_displayed()
                browser.execute_async_script("""
                    let done=arguments[arguments.length-1];
                    openConversation(arguments[0]).then(()=>done(true)).catch(err=>done(err.message));
                """,cid)
                assert browser.execute_script("return document.getElementById('appScreen').dataset.vWallpaper")=='waves'
                browser.find_element(By.ID,'vHeaderThemeBtn').click()
                browser.find_element(By.CSS_SELECTOR,'[data-v-scope="chat"]').click()
                browser.find_element(By.CSS_SELECTOR,'[data-v-kind="wallpaper"][data-v-value="sunset"]').click()
                assert browser.execute_script("return document.getElementById('appScreen').dataset.vWallpaper")=='sunset'
                browser.find_element(By.ID,'vPanelClose').click()
                browser.execute_async_script("""
                    let done=arguments[arguments.length-1];
                    openConversation(arguments[0]).then(()=>done(true)).catch(err=>done(err.message));
                """,other)
                assert browser.execute_script("return document.getElementById('appScreen').dataset.vWallpaper")=='waves', 'Global wallpaper not respected in other chat'
                browser.execute_async_script("""
                    let done=arguments[arguments.length-1];
                    openConversation(arguments[0]).then(()=>done(true)).catch(err=>done(err.message));
                """,cid)
                assert browser.execute_script("return document.getElementById('appScreen').dataset.vWallpaper")=='sunset'
                browser.find_element(By.ID,'vHeaderThemeBtn').click()
                browser.find_element(By.CSS_SELECTOR,'[data-v-kind="composer"][data-v-value="glass"]').click()
                assert browser.execute_script("return document.getElementById('appScreen').dataset.vComposer")=='glass'
                browser.find_element(By.CSS_SELECTOR,'[data-v-kind="theme"][data-v-value="midnight"]').click()
                assert browser.execute_script("return document.getElementById('appScreen').dataset.vTheme")=='midnight'
                browser.find_element(By.ID,'vClearChatWallpaper').click()
                assert browser.execute_script("return document.getElementById('appScreen').dataset.vWallpaper")=='waves'
                browser.find_element(By.ID,'vPanelClose').click()
                browser.refresh()
                WebDriverWait(browser,10).until(lambda b:not b.find_element(By.ID,'appScreen').get_attribute('class').find('hidden')>=0)
                assert browser.execute_script("return document.getElementById('appScreen').dataset.vTheme")=='midnight','Theme did not survive reload'
                assert browser.execute_script("return document.getElementById('appScreen').dataset.vComposer")=='glass','Composer choice did not persist'
                browser.find_element(By.ID,'vHeaderThemeBtn').click()
                browser.find_element(By.ID,'vResetVisuals').click()
                assert browser.execute_script("return document.getElementById('appScreen').dataset.vWallpaper")=='doodles'
                browser.find_element(By.ID,'vPanelClose').click()
            print('VIVID_BROWSER_PASS: layout, previews, themes, per-chat persistence, reset and responsive flow',flush=True)
        finally:
            browser.quit()
            server.should_exit=True

if __name__=='__main__':main()
