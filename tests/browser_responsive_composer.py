"""Real browser test of collapsing Huddle composer and modern sent voice note UI.
Uses isolated temporary users, SQLite and a tiny test-only WAV audio attachment.
"""
import tempfile,threading,time,wave
from io import BytesIO
from pathlib import Path
import requests,uvicorn
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from app.main import create_app

def main():
    with tempfile.TemporaryDirectory(prefix='huddle_compose_') as folder:
        app=create_app(str(Path(folder)/'test.sqlite'))
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8893,log_level='warning'))
        threading.Thread(target=server.run,daemon=True).start()
        base='http://127.0.0.1:8893'
        for _ in range(50):
            try:
                if requests.get(base+'/health',timeout=.5).status_code==200:break
            except requests.RequestException:pass
            time.sleep(.2)
        else:raise AssertionError('Unable to start Huddle test server')

        def register(handle):
            session=requests.Session()
            r=session.post(base+'/api/auth/register',json={'name':handle.title(),
                'handle':handle,'password':'TestPassword123!'})
            assert r.status_code==201,r.text
            return session,r.json()['user']
        alice,au=register('alice')
        bob,bu=register('bobby')
        room=alice.post(base+'/api/conversations/direct',json={'user_id':bu['id']}).json()['conversation']['id']
        wav=BytesIO()
        with wave.open(wav,'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000)
            f.writeframes(b'\0\0'*9600)
        audio=alice.post(base+f'/api/conversations/{room}/attachments',data=wav.getvalue(),
            headers={'content-type':'audio/wav','x-huddle-filename':'audio.wav'})
        assert audio.status_code==201,audio.text

        opts=webdriver.ChromeOptions()
        for flag in ['--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1120,900']:
            opts.add_argument(flag)
        browser=webdriver.Chrome(options=opts)
        try:
            for width,height in [(1120,900),(390,844),(345,740)]:
                mobile=width<721
                browser.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':2 if mobile else 1,'mobile':mobile})
                browser.get(base)
                browser.add_cookie({'name':'huddle_session','value':alice.cookies.get('huddle_session'),'path':'/','sameSite':'Strict'})
                browser.refresh()
                WebDriverWait(browser,11).until(lambda b:not b.find_element(By.ID,'appScreen').get_attribute('class').split().__contains__('hidden'))
                opened=browser.execute_async_script("""
                    const done=arguments[arguments.length-1];
                    openConversation(arguments[0]).then(()=>done(true)).catch(e=>done(e.message));
                """,room)
                assert opened is True,opened
                WebDriverWait(browser,6).until(lambda b:len(b.find_elements(By.CSS_SELECTOR,'.voice-media .h-voice-play'))>0)
                first=browser.execute_script("""
                    const composer=document.querySelector('#conversationView .composer');
                    const card=document.querySelector('.voice-media'),btn=card.querySelector('.h-voice-play');
                    return {width:document.documentElement.scrollWidth,viewport:innerWidth,
                      expanded:composer.classList.contains('h-composer-expanded'),
                      buttons:document.querySelectorAll('#hComposerToolset > button,#hComposerToolset > label').length,
                      moreVisible:getComputedStyle(document.querySelector('#hComposerMore')).opacity,
                      cardWidth:card.getBoundingClientRect().width,
                      cardHeight:card.getBoundingClientRect().height,
                      voiceTitle:card.querySelector('.h-voice-title').textContent,
                      waves:card.querySelectorAll('.h-voice-waves i').length,
                      waveformRadius:getComputedStyle(btn).borderRadius,
                      progress:!!card.querySelector('.h-voice-progress')};
                """)
                print('COMPOSER_SHORT',width,first,flush=True)
                assert first['width']<=first['viewport']+3
                assert not first['expanded'] and first['buttons']==4 and float(first['moreVisible'])==0
                assert first['cardWidth']<=280 and first['waves']>=20
                assert first['voiceTitle']=='Voice note' and first['progress']
                assert first['cardHeight']<=110
                assert first['waveformRadius'] != '50%'
                status=browser.execute_script("""
                    return document.querySelector('#headerIdentity .header-meta')?.textContent || '';
                """)
                assert '@' not in status,status
                transition=browser.execute_script("""
                    const input=document.getElementById('messageInput');
                    input.value=('This is an intentionally long message with more than enough words to make '
                      +'the typing area wrap properly on even large screens. ').repeat(8);
                    input.dispatchEvent(new Event('input',{bubbles:true}));
                    return {
                      ghostCount:document.querySelectorAll('.h-composer-ghost').length,
                      expanded:window.HuddleComposerUI.isExpanded(),
                      motion:document.querySelector('.h-composer-ghost')?.getAnimations()[0]?.playState
                    };
                """)
                print('COLLAPSE_MOTION',width,transition,flush=True)
                assert transition['expanded'] and transition['ghostCount']==4,transition
                WebDriverWait(browser,6).until(lambda b:b.execute_script("""
                    return window.HuddleComposerUI?.isExpanded() &&
                      Number(getComputedStyle(document.querySelector('#hComposerMore')).opacity)>0.95;
                """))
                long=browser.execute_script("""
                    const composer=document.querySelector('#conversationView .composer'),
                    btn=document.getElementById('hComposerMore'),
                    set=document.getElementById('hComposerToolset');
                    return {expanded:composer.classList.contains('h-composer-expanded'),
                      moreVisible:getComputedStyle(btn).opacity,
                      toolsHidden:set.getAttribute('aria-hidden'),
                      caretWidth:document.getElementById('messageInput').getBoundingClientRect().width,
                      outerWidth:document.documentElement.scrollWidth,
                      viewport:innerWidth};
                """)
                print('COMPOSER_LONG',width,long,flush=True)
                assert long['outerWidth']<=long['viewport']+3
                assert long['expanded'] and float(long['moreVisible'])==1
                assert long['toolsHidden']=='true'
                browser.find_element(By.ID,'hComposerMore').click()
                popup=browser.execute_script("""
                    const set=document.getElementById('hComposerToolset');
                    const cs=getComputedStyle(set);
                    return {open:window.HuddleComposerUI.isOpen(),visible:cs.visibility,
                      icons:[...set.querySelectorAll('button,label')].filter(n=>n.id||n.matches('label[for="mediaFileInput"]')).map(n=>({
                          id:n.id||'attachLabel',accessible:n.getAttribute('aria-label'),width:n.getBoundingClientRect().width,
                          icon:!!n.querySelector('svg')})),
                      textLabels:set.querySelectorAll('.h-tool-name').length,
                      layout:cs.display,
                      bounds:set.getBoundingClientRect().toJSON()};
                """)
                print('COMPOSER_MENU',width,popup,flush=True)
                assert popup['open'] and popup['visible']=='visible'
                assert popup['textLabels']==0 and popup['layout']=='grid',popup
                assert len(popup['icons'])==4,popup
                assert [item['accessible'] for item in popup['icons']]==['Emojis','Attach','Location','Voice note'],popup
                assert all(item['icon'] and 35<=item['width']<=44 for item in popup['icons']),popup
                assert popup['bounds']['left']>=-1 and popup['bounds']['right']<=width+2
                browser.find_element(By.ID,'hComposerMore').click()
                assert not browser.execute_script("return window.HuddleComposerUI.isOpen()")
                # Reset to short text and verify all four original buttons reappear.
                reversal=browser.execute_script("""
                    const input=document.getElementById('messageInput');
                    input.value='Hi';input.dispatchEvent(new Event('input',{bubbles:true}));
                    return {ghostCount:document.querySelectorAll('.h-composer-ghost').length,
                        restoring:document.querySelector('.composer').classList.contains('h-composer-restoring')};
                """)
                print('EXPAND_MOTION',width,reversal,flush=True)
                assert reversal['ghostCount']>=3 and reversal['restoring'],reversal
                WebDriverWait(browser,5).until(lambda b:not b.execute_script("return window.HuddleComposerUI.isExpanded()"))
                again=browser.execute_script("""
                  const group=document.getElementById('hComposerToolset');
                  return {normal:getComputedStyle(group).position==='relative',
                    emojiVisible:document.getElementById('emojiBtn').getBoundingClientRect().width>=28,
                    micVisible:document.getElementById('voiceNoteBtn').getBoundingClientRect().width>=28};
                """)
                assert again['normal'] and again['emojiVisible'] and again['micVisible'],again
                # Picking emoji keeps the original control functional after moving it into group.
                browser.find_element(By.ID,'emojiBtn').click()
                WebDriverWait(browser,5).until(lambda b:b.find_element(By.ID,'emojiPicker').is_displayed())
                browser.find_element(By.CSS_SELECTOR,'#emojiPicker [data-emoji]').click()
                assert not browser.find_element(By.ID,'emojiPicker').is_displayed()
            print('MODERN_COMPOSER_BROWSER_PASS',flush=True)
        finally:
            browser.quit();server.should_exit=True

if __name__=='__main__':
    main()
