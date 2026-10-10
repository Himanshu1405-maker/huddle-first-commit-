"""Desktop/Android regression: compact image, unobstructed reaction badge, recorder
state and custom voice player. Only private temporary accounts and SQLite are used.
"""
from io import BytesIO
from pathlib import Path
import tempfile,threading,time,wave

import requests,uvicorn
from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from app.main import create_app


def main():
    with tempfile.TemporaryDirectory(prefix='huddle_media_polish_') as folder:
        app=create_app(str(Path(folder)/'media.sqlite'))
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8894,log_level='warning'))
        threading.Thread(target=server.run,daemon=True).start()
        base='http://127.0.0.1:8894'
        for _ in range(45):
            try:
                if requests.get(base+'/health',timeout=.5).status_code==200:break
            except requests.RequestException:pass
            time.sleep(.2)
        else:raise RuntimeError('Server did not start')
        def register(handle):
            sess=requests.Session()
            response=sess.post(base+'/api/auth/register',json={'name':handle.title(),
                'handle':handle,'password':'SafePassword123!'})
            assert response.status_code==201,response.text
            return sess,response.json()['user']
        alice,au=register('alice')
        bob,bu=register('bobby')
        room=alice.post(base+'/api/conversations/direct',json={'user_id':bu['id']}).json()['conversation']['id']
        message=alice.post(base+f'/api/conversations/{room}/messages',json={'body':'Reactions go below the bubble'}).json()['message']
        reaction=bob.post(base+f'/api/messages/{message["id"]}/reactions',json={'emoji':'❤️'})
        assert reaction.status_code==200,reaction.text
        photo=Image.new('RGB',(700,1200),'#5ea6b6')
        raw=BytesIO();photo.save(raw,format='PNG')
        pic=alice.post(base+f'/api/conversations/{room}/attachments',data=raw.getvalue(),
            headers={'content-type':'image/png','x-huddle-filename':'holiday-trip-photo.png'})
        assert pic.status_code==201,pic.text
        raw=BytesIO()
        with wave.open(raw,'wb') as out:
            out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000)
            out.writeframes(b'\0\0'*9600)
        voice=alice.post(base+f'/api/conversations/{room}/attachments',data=raw.getvalue(),
            headers={'content-type':'audio/wav','x-huddle-filename':'voice-note.wav'})
        assert voice.status_code==201,voice.text
        options=webdriver.ChromeOptions()
        for flag in ['--headless=new','--no-sandbox','--disable-dev-shm-usage',
                     '--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream',
                     '--window-size=1150,850']:
            options.add_argument(flag)
        browser=webdriver.Chrome(options=options)
        try:
            for width,height in [(1150,850),(390,844),(345,740)]:
                mobile=width<721
                browser.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',
                    {'width':width,'height':height,'deviceScaleFactor':2 if mobile else 1,'mobile':mobile})
                browser.get(base)
                browser.add_cookie({'name':'huddle_session','value':alice.cookies.get('huddle_session'),'path':'/','sameSite':'Strict'})
                browser.refresh()
                WebDriverWait(browser,12).until(lambda d:d.execute_script(
                    "return !document.querySelector('#appScreen').classList.contains('hidden')"))
                result=browser.execute_async_script("""
                    const done=arguments[arguments.length-1];
                    openConversation(arguments[0]).then(()=>done(true)).catch(e=>done(e.message));
                """,room)
                assert result is True,result
                WebDriverWait(browser,10).until(lambda d:len(d.find_elements(By.CSS_SELECTOR,'.image-media img'))>=1
                    and len(d.find_elements(By.CSS_SELECTOR,'.voice-media audio'))>=1
                    and len(d.find_elements(By.CSS_SELECTOR,'.h-message-visual .reactions'))>=1)
                dimensions=browser.execute_script("""
                    const msg=document.getElementById('msg-'+arguments[0]);
                    const bubble=msg.querySelector('.bubble');
                    const reaction=msg.querySelector('.reactions');
                    const photo=document.querySelector('.image-media');
                    const audio=document.querySelector('.voice-media');
                    const rec=document.querySelector('#chatBanner');
                    const textarea=document.querySelector('#messageInput');
                    const card=el=>el.getBoundingClientRect();
                    return {viewport:innerWidth,scrollWidth:document.documentElement.scrollWidth,
                        bannerHidden:getComputedStyle(rec).display==='none',bannerText:rec.textContent,
                        reactionTop:card(reaction).top,bubbleBottom:card(bubble).bottom,
                        photoWidth:card(photo).width,photoHeight:card(photo).height,
                        fullImageLink:photo.href.includes('/api/media/'),
                        photoOverlay:!!photo.querySelector('.h-photo-overlay'),
                        voiceWidth:card(audio).width,voiceButton:!!audio.querySelector('.h-voice-play svg'),
                        waveform:audio.querySelectorAll('.h-voice-waves i').length,
                        seek:!!audio.querySelector('.h-voice-progress'),
                        nativeAudio:!!audio.querySelector('audio'),
                        scrollbar:getComputedStyle(textarea).scrollbarWidth,
                        countHidden:getComputedStyle(document.querySelector('#composerCount')).display,
                        recordIcon:!!document.querySelector('#voiceNoteBtn svg')};
                """,message['id'])
                print('MEDIA_POLISH_LAYOUT',width,dimensions,flush=True)
                assert dimensions['scrollWidth']<=dimensions['viewport']+3
                assert dimensions['bannerHidden'] and dimensions['bannerText']==''
                assert dimensions['reactionTop']>=dimensions['bubbleBottom']-3,'Reaction overlaps message contents'
                assert dimensions['photoWidth']<=235 and dimensions['photoHeight']<=214
                if mobile: assert dimensions['photoWidth']<=208
                assert dimensions['photoOverlay'] and dimensions['fullImageLink']
                assert dimensions['voiceWidth']<=290 and dimensions['waveform']>=20
                assert dimensions['seek'] and dimensions['nativeAudio'] and dimensions['voiceButton']
                assert dimensions['scrollbar']=='none' and dimensions['countHidden']=='none'
                assert dimensions['recordIcon']
                browser.find_element(By.ID,'voiceNoteBtn').click()
                WebDriverWait(browser,8).until(lambda d:d.find_element(By.ID,'voiceNoteBtn').get_attribute('class').find('recording')>=0)
                live=browser.execute_script("""
                    const b=document.getElementById('voiceNoteBtn');
                    return {hasStop:!!b.querySelector('svg rect'),statusVisible:!document.getElementById('hVoiceStatus').hidden,
                            buttonLabel:b.getAttribute('aria-label'),hasCancel:!!document.getElementById('hVoiceCancel')};
                """)
                assert live['hasStop'] and live['statusVisible'] and live['hasCancel'],live
                assert 'Stop' in live['buttonLabel'],live
                browser.find_element(By.ID,'hVoiceCancel').click()
                WebDriverWait(browser,8).until(lambda d:not d.find_element(By.ID,'voiceNoteBtn').get_attribute('class').find('recording')>=0)
                restored=browser.execute_script("""
                    return {mic:!!document.querySelector('#voiceNoteBtn svg rect[rx="3"]'),
                            hide:document.getElementById('hVoiceStatus').hidden};
                """)
                assert restored['mic'] and restored['hide'],restored
            print('MEDIA_POLISH_BROWSER_PASS: reaction spacing, compact photos, audio controls, responsive mic and discard',flush=True)
        finally:
            browser.quit();server.should_exit=True

if __name__=='__main__':main()
