"""End-to-end Android Chromium test: voice duration/wave progress, photo viewer,
and instantaneous second-line composer collapse. Isolated temporary SQLite.
"""
from io import BytesIO
import tempfile,threading,time,wave
from pathlib import Path
import requests,uvicorn
from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from app.main import create_app

def run():
    with tempfile.TemporaryDirectory(prefix='huddle_voice_img_') as temp:
        app=create_app(str(Path(temp)/'huddle.sqlite'))
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8892,log_level='warning'))
        threading.Thread(target=server.run,daemon=True).start()
        base='http://127.0.0.1:8892'
        for _ in range(55):
            try:
                if requests.get(base+'/health',timeout=.5).status_code==200:break
            except requests.RequestException:pass
            time.sleep(.2)
        else:raise AssertionError('Local browser test server unavailable')
        def register(handle):
            sess=requests.Session()
            r=sess.post(base+'/api/auth/register',json={
                'name':handle.title(),'handle':handle,'password':'SecurePassword123!'})
            assert r.status_code==201,r.text
            return sess,r.json()['user']
        alice,me=register('alice')
        bob,other=register('bobby')
        room=alice.post(base+'/api/conversations/direct',json={'user_id':other['id']}).json()['conversation']['id']
        sound=BytesIO()
        with wave.open(sound,'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000)
            wav.writeframes(b'\0\0'*int(16000*2.4))
        sent=alice.post(base+f'/api/conversations/{room}/attachments',data=sound.getvalue(),
            headers={'content-type':'audio/wav','x-huddle-filename':'voice-note.wav'})
        assert sent.status_code==201,sent.text
        assert sent.json()['message']['attachments'][0]['duration_ms']==2400
        picture=BytesIO()
        Image.new('RGB',(500,620),'#7b61c4').save(picture,format='PNG')
        image=alice.post(base+f'/api/conversations/{room}/attachments',data=picture.getvalue(),
            headers={'content-type':'image/png','x-huddle-filename':'portrait.png'})
        assert image.status_code==201,image.text
        opts=webdriver.ChromeOptions()
        for option in ['--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1120,860']:
            opts.add_argument(option)
        driver=webdriver.Chrome(options=opts)
        try:
            for width,height in [(1120,860),(390,844),(345,740)]:
                driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',{
                    'width':width,'height':height,'deviceScaleFactor':2 if width<721 else 1,'mobile':width<721})
                driver.get(base)
                driver.add_cookie({'name':'huddle_session','value':alice.cookies.get('huddle_session'),
                                   'path':'/','sameSite':'Strict'})
                driver.refresh()
                WebDriverWait(driver,10).until(lambda d:not d.find_element(By.ID,'appScreen').get_attribute('class').split().__contains__('hidden'))
                result=driver.execute_async_script("""
                    const done=arguments[arguments.length-1];
                    openConversation(arguments[0]).then(()=>done(true)).catch(e=>done(e.message));
                """,room)
                assert result is True,result
                WebDriverWait(driver,8).until(lambda d:len(d.find_elements(By.CSS_SELECTOR,'.voice-media'))>=1
                    and len(d.find_elements(By.CSS_SELECTOR,'.image-media'))>=1)
                initial=driver.execute_script("""
                    const card=document.querySelector('.voice-media');
                    const audio=card.querySelector('audio');
                    const label=card.querySelector('.h-voice-duration');
                    const viewerLink=document.querySelector('a.image-media');
                    return {durationAttr:card.getAttribute('data-duration-ms'),
                      label:label.textContent,player:!!window.HuddleVoiceUI,
                      photoViewer:!!window.HuddlePhotos,
                      photoHasTarget:viewerLink.hasAttribute('target'),
                      photoHref:viewerLink.getAttribute('data-h-photo'),
                      width:document.documentElement.scrollWidth,viewport:innerWidth};
                """)
                print('AUDIO_GALLERY_INITIAL',width,initial,flush=True)
                assert initial['durationAttr']=='2400'
                assert initial['label']=='0:03',initial
                assert initial['player'] and initial['photoViewer']
                assert not initial['photoHasTarget']
                assert initial['width']<=initial['viewport']+3
                # Seek to half: exact fraction of waveform bars must darken.
                # Wait for browser metadata before exercising the real audio controls.
                WebDriverWait(driver,8).until(lambda d:d.execute_script("""
                    const a=document.querySelector('.voice-media audio');
                    return a.readyState>=1;
                """))
                seek=driver.execute_script("""
                    const card=document.querySelector('.voice-media');
                    const input=card.querySelector('.h-voice-progress');
                    input.value='50';input.dispatchEvent(new Event('input',{bubbles:true}));
                    const audio=card.querySelector('audio');
                    return {currentTime:audio.currentTime,total:window.HuddleVoiceUI.mediaDuration(audio),
                      played:card.querySelectorAll('.h-voice-waves .h-voice-heard').length,
                      bars:card.querySelectorAll('.h-voice-waves i').length};
                """)
                print('VOICE_WAVEFORM_SEEK',width,seek,flush=True)
                assert 1.0<=seek['currentTime']<=1.45,seek
                assert seek['played']>=10 and seek['played']<=14,seek
                # A real photo opens a dialog, never an external tab.
                driver.find_element(By.CSS_SELECTOR,'a.image-media').click()
                WebDriverWait(driver,5).until(lambda d:d.find_element(By.ID,'hPhotoViewer').is_displayed())
                assert driver.current_url==base+'/'
                assert driver.execute_script("return document.querySelector('#hPhotoFull').getAttribute('src')").startswith('/api/media/')
                driver.find_element(By.ID,'hPhotoFull').click()
                assert 'h-photo-zoomed' in driver.find_element(By.ID,'hPhotoFull').get_attribute('class')
                driver.find_element(By.ID,'hPhotoClose').click()
                WebDriverWait(driver,4).until(lambda d:len(d.find_elements(By.ID,'hPhotoViewer'))==0)

                # For line break, detect the FIRST character which creates a
                # second visual line at original four-icon width.
                line=driver.execute_script("""
                    const input=document.getElementById('messageInput');
                    input.value='A';input.dispatchEvent(new Event('input',{bubbles:true}));
                    let previousExpanded=false,firstAt=0,delta=0;
                    for(let n=2;n<=110;n++){
                      input.value='A'.repeat(n);
                      input.dispatchEvent(new Event('input',{bubbles:true}));
                      const expanded=window.HuddleComposerUI.isExpanded();
                      if(expanded){firstAt=n;delta=n-1;break;}
                      previousExpanded=expanded;
                    }
                    return {firstAt,immediate:window.HuddleComposerUI.isExpanded(),
                      normalToolsVisible:document.getElementById('hComposerToolset').getAttribute('aria-hidden')};
                """)
                print('FIRST_SECOND_LINE',width,line,flush=True)
                assert line['firstAt']>1 and line['immediate']
                assert line['normalToolsVisible']=='true'
                driver.execute_script("""
                    const input=document.getElementById('messageInput');
                    input.value='One\\ntwo';
                    input.dispatchEvent(new Event('input',{bubbles:true}));
                """)
                assert driver.execute_script('return window.HuddleComposerUI.isExpanded()'),'A literal newline must collapse on second line'
                driver.execute_script("""
                    const input=document.getElementById('messageInput');
                    input.value='Short';input.dispatchEvent(new Event('input',{bubbles:true}));
                """)
                assert not driver.execute_script('return window.HuddleComposerUI.isExpanded()')
            print('AUDIO_IMAGE_COMPOSER_BROWSER_PASS',flush=True)
        finally:
            driver.quit();server.should_exit=True

if __name__=='__main__':
    run()
