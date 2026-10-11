"""Real browser test of collapsing Huddle composer and modern sent voice note UI.
Uses isolated temporary users, SQLite and a tiny test-only WAV audio attachment.
"""
import tempfile,threading,time,wave
from io import BytesIO
from pathlib import Path
from PIL import Image
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
                      progress:!!card.querySelector('.h-voice-progress'),
                      alignment:(()=>{
                        const group=document.querySelector('#hComposerToolset'),buttons=
                         [...group.querySelectorAll('button,label')].filter(n=>n.id||n.matches('label[for="mediaFileInput"]'));
                        const send=document.querySelector('#sendBtn');
                        const rects=buttons.map(n=>n.getBoundingClientRect());
                        return {heights:rects.map(r=>r.height),centers:rects.map(r=>r.top+r.height/2),
                         gap:rects.slice(1).map((r,i)=>r.left-rects[i].right),
                         sendCenter:send.getBoundingClientRect().top+send.getBoundingClientRect().height/2,
                         slotWidth:document.querySelector('#hComposerSlot').getBoundingClientRect().width};
                      })()};
                """)
                print('COMPOSER_SHORT',width,first,flush=True)
                assert first['width']<=first['viewport']+3
                assert not first['expanded'] and first['buttons']==4 and float(first['moreVisible'])==0
                assert first['cardWidth']<=280 and first['waves']>=20
                assert first['voiceTitle']=='Voice note' and first['progress']
                assert first['cardHeight']<=110
                assert first['waveformRadius'] != '50%'
                centers=first['alignment']['centers']
                assert len(centers)==4 and max(centers)-min(centers)<2,first['alignment']
                assert max(abs(x-first['alignment']['sendCenter']) for x in centers)<4,first['alignment']
                assert all(0<=g<=8 for g in first['alignment']['gap']),first['alignment']
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
                      viewport:innerWidth,
                      menuSlot:document.querySelector('#hComposerSlot').getBoundingClientRect().width,
                      hasVerticalMenu:!!document.getElementById('hComposerToolset')};
                """)
                print('COMPOSER_LONG',width,long,flush=True)
                assert long['outerWidth']<=long['viewport']+3
                assert long['expanded'] and float(long['moreVisible'])==1
                assert long['toolsHidden']=='true'
                # Reproduce reported Android screenshot: a visible plus sitting over
                # first and second lines of a long draft. Assert the actual button
                # occupies its OWN flex item, and text begins beyond its right edge.
                overlap=browser.execute_script("""
                    const composer=document.querySelector('#conversationView .composer');
                    const input=document.querySelector('#messageInput');
                    const plus=document.querySelector('#hComposerMore');
                    input.value='Hi hid\\nibbdubhjsbhsjbsnnsjsjjisjjsjh';
                    input.dispatchEvent(new Event('input',{bubbles:true}));
                    const text=input.getBoundingClientRect();
                    const button=plus.getBoundingClientRect();
                    return {expanded:window.HuddleComposerUI.isExpanded(),
                      plusParentIsComposer:plus.parentElement===composer,
                      plusLeft:button.left,plusRight:button.right,plusWidth:button.width,
                      inputLeft:text.left,inputRight:text.right,inputWidth:text.width,
                      composerWidth:composer.getBoundingClientRect().width};
                """)
                print('COMPOSER_NO_OVERLAP',width,overlap,flush=True)
                assert overlap['expanded'] and overlap['plusParentIsComposer'],overlap
                assert overlap['plusWidth']>=34 and overlap['inputWidth']>=65,overlap
                assert overlap['inputLeft']>=overlap['plusRight']-0.5,overlap
                browser.find_element(By.ID,'hComposerMore').click()
                WebDriverWait(browser,5).until(lambda d:d.execute_script("""
                    const menu=document.getElementById('hComposerToolset');
                    if(!menu||getComputedStyle(menu).visibility!=='visible')return false;
                    const bounds=menu.getBoundingClientRect();
                    const first=menu.querySelector('#emojiBtn')?.getBoundingClientRect();
                    return !!first && Math.abs(first.width-(innerWidth<=365?40:42))<1.5
                       && Math.abs(bounds.width-(innerWidth<=365?56:58))<1.5;
                """))
                popup=browser.execute_script("""
                    const set=document.getElementById('hComposerToolset');
                    const cs=getComputedStyle(set);
                    return {open:window.HuddleComposerUI.isOpen(),visible:cs.visibility,
                      icons:[...set.querySelectorAll('button,label')].filter(n=>n.id||n.matches('label[for="mediaFileInput"]')).map(n=>({
                          id:n.id||'attachLabel',accessible:n.getAttribute('aria-label'),width:n.getBoundingClientRect().width,
                          icon:!!n.querySelector('svg')})),
                      textLabels:set.querySelectorAll('.h-tool-name').length,
                      layout:cs.display,direction:cs.flexDirection,
                      positions:[...set.querySelectorAll('button,label')].filter(n=>n.id||n.matches('label[for="mediaFileInput"]')).map(n=>n.getBoundingClientRect().toJSON()),
                      bounds:set.getBoundingClientRect().toJSON(),
                      plus:document.getElementById('hComposerMore').getBoundingClientRect().toJSON(),
                      menuGap:getComputedStyle(set).rowGap,
                      menuPadding:getComputedStyle(set).padding,
                      glyphOffsets:[...set.querySelectorAll('button,label')].filter(n=>n.id||n.matches('label[for="mediaFileInput"]')).map(n=>{
                        const box=n.getBoundingClientRect(),glyph=n.querySelector('svg');
                        if(!glyph)return {name:n.dataset.hToolName,missing:true};
                        const g=glyph.getBoundingClientRect();
                        return {name:n.dataset.hToolName,missing:false,
                          horizontal:Math.abs((box.left+box.right)/2-(g.left+g.right)/2),
                          vertical:Math.abs((box.top+box.bottom)/2-(g.top+g.bottom)/2)};
                      })};
                """)
                print('COMPOSER_MENU',width,popup,flush=True)
                assert popup['open'] and popup['visible']=='visible'
                assert popup['textLabels']==0 and popup['layout']=='flex' and popup['direction']=='column',popup
                rects=popup['positions']
                assert len(rects)==4 and all(rects[i+1]['top']>rects[i]['bottom'] for i in range(3)),popup
                assert max(abs(r['x']-rects[0]['x']) for r in rects)<2,popup
                # Visual QA for screenshot: the tray is a tight vertical rail,
                # precisely centered over the +, rather than a wide detached card.
                mid=lambda rect:rect['left']+rect['width']/2
                assert abs(mid(popup['bounds'])-mid(popup['plus']))<2.5,popup
                assert max(abs(mid(rect)-mid(popup['plus'])) for rect in rects)<2.5,popup
                assert max(r['height'] for r in rects)-min(r['height'] for r in rects)<1,popup
                assert max(rect['width'] for rect in rects)-min(rect['width'] for rect in rects)<1,popup
                assert popup['bounds']['height']<210,popup
                assert 4<=rects[0]['top']-popup['bounds']['top']<=11,popup
                assert 4<=popup['plus']['top']-popup['bounds']['bottom']<=18,popup
                assert all(2<=rects[i+1]['top']-rects[i]['bottom']<=7 for i in range(3)),popup
                assert len(popup['icons'])==4,popup
                assert [item['accessible'] for item in popup['icons']]==['Emojis','Attach','Location','Voice note'],popup
                assert all(item['icon'] and 38<=item['width']<=44 for item in popup['icons']),popup
                # Test the SVG itself, not just the colored button's position.
                assert all(not g['missing'] and g['horizontal']<=2.5 and g['vertical']<=2.5
                    for g in popup['glyphOffsets']),popup
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
                # The theme/settings drawer now supports readable, persistent
                # text sizing without colliding with three chat toolbar actions.
                browser.find_element(By.ID,'vHeaderThemeBtn').click()
                WebDriverWait(browser,5).until(lambda d:d.find_element(By.ID,'vThemePanel').is_displayed())
                settings=browser.execute_script("""
                    const slider=document.getElementById('vTextSize');
                    const before=parseFloat(getComputedStyle(document.querySelector('.header-name')).fontSize);
                    slider.value='125';slider.dispatchEvent(new Event('input',{bubbles:true}));
                    const name=document.querySelector('.header-name').getBoundingClientRect();
                    const buttons=document.querySelector('.header-actions').getBoundingClientRect();
                    return {before,after:parseFloat(getComputedStyle(document.querySelector('.header-name')).fontSize),
                      value:slider.value,readout:document.getElementById('vTextSizeValue').textContent,
                      nameRight:name.right,actionsLeft:buttons.left,
                      bubbleFont:getComputedStyle(document.querySelector('.bubble')).fontSize,
                      saved:localStorage.getItem('huddle.visual.prefs.v1.'+state.me.id)};
                """)
                print('READABLE_SETTINGS',width,settings,flush=True)
                assert settings['after']>settings['before']>=16,settings
                assert settings['value']=='125',settings
                assert '125%' in settings['readout'],settings
                assert settings['nameRight']<=settings['actionsLeft']+1,settings
                assert '"textSize":125' in settings['saved'],settings
                browser.find_element(By.ID,'vPanelClose').click()
                browser.refresh()
                WebDriverWait(browser,10).until(lambda d:not d.find_element(By.ID,'appScreen').get_attribute('class').split().__contains__('hidden'))
                result=browser.execute_async_script("""
                    const done=arguments[arguments.length-1];
                    openConversation(arguments[0]).then(()=>done(true)).catch(e=>done(e.message));
                """,room)
                assert result is True,result
                restored=browser.execute_script("""
                    return {scale:document.getElementById('appScreen').style.getPropertyValue('--h-text-scale'),
                      font:parseFloat(getComputedStyle(document.querySelector('.header-name')).fontSize)};
                """)
                assert restored['scale']=='1.25' and abs(restored['font']-settings['after'])<1,restored
                browser.find_element(By.ID,'vHeaderThemeBtn').click()
                browser.find_element(By.ID,'vTextDefault').click()
                assert browser.find_element(By.ID,'vTextSize').get_attribute('value')=='100'
                browser.find_element(By.ID,'vPanelClose').click()
                # Huddle Moments is a real working feature in the same mobile UI.
                browser.execute_script("window.HuddleMoments.open()")
                WebDriverWait(browser,8).until(lambda b:b.find_element(By.ID,'hMomentsHome').is_displayed())
                browser.find_element(By.ID,'hMomentCreate').click()
                browser.find_element(By.ID,'hMomentTextInput').send_keys('A little Huddle Moment')
                browser.find_element(By.ID,'hMomentPublish').click()
                WebDriverWait(browser,9).until(lambda b:
                    not b.find_element(By.ID,'hMomentComposeOverlay').is_displayed())
                WebDriverWait(browser,8).until(lambda b:
                    len(b.find_elements(By.CSS_SELECTOR,'#hMyMoments [data-moment-owner]'))>=1)
                dims=browser.execute_script("""
                    return {width:document.documentElement.scrollWidth,viewport:innerWidth,
                       momentVisible:document.getElementById('hMomentsHome').offsetWidth>0,
                       ring:!!document.querySelector('#hMomentsStrip [data-moment-owner]')};
                """)
                assert dims['width']<=dims['viewport']+3 and dims['momentVisible'] and dims['ring'],dims
                browser.execute_script("window.HuddleMoments.openOwner(state.me.id)")
                WebDriverWait(browser,6).until(lambda b:b.find_element(By.ID,'hMomentViewer').is_displayed())
                assert len(browser.find_elements(By.CSS_SELECTOR,'.h-moment-progress-rail'))>=1
                browser.find_element(By.ID,'hMomentViewerClose').click()
                if width==390:
                    photo=Path(folder)/'story.jpg'
                    Image.new('RGB',(65,88),'#7d67d9').save(photo,'JPEG')
                    browser.find_element(By.ID,'hMomentCreate').click()
                    browser.find_element(By.CSS_SELECTOR,'[data-moment-type="media"]').click()
                    browser.find_element(By.ID,'hMomentFile').send_keys(str(photo))
                    WebDriverWait(browser,5).until(lambda b:
                        len(b.find_elements(By.CSS_SELECTOR,'#hMomentMediaPreview img'))==1)
                    browser.find_element(By.ID,'hMomentPublish').click()
                    WebDriverWait(browser,9).until(lambda b:
                        not b.find_element(By.ID,'hMomentComposeOverlay').is_displayed())
                    images=[m for m in alice.get(base+'/api/moments').json()['moments']
                            if m['kind']=='image' and m['has_media']]
                    assert images,'Moments image upload failed'
                    assert bob.get(base+'/api/moments/'+images[0]['id']+'/media').status_code==200
                    assert not browser.find_element(By.ID,'hMomentUploadProgress').is_displayed()
                    assert len(browser.find_elements(By.CSS_SELECTOR,'#hMomentsStrip .h-moment-own-group'))==1
                browser.execute_script("showWelcome()")
                # Screenshot regression: selected pill must be fully visible,
                # all filters remain separate from the scrollable chat list.
                inbox=browser.execute_script("""
                  const f=document.querySelector('.inbox-filters');
                  const list=document.getElementById('homeChatList');
                  const outer=f.getBoundingClientRect(),item=list.getBoundingClientRect();
                  const pills=[...f.querySelectorAll('button')].map(n=>n.getBoundingClientRect().toJSON());
                  const ring=document.querySelectorAll('#hMomentsStrip .h-moment-own-group').length;
                  return {top:outer.top,bottom:outer.bottom,listTop:item.top,listHeight:item.height,
                    pills,ring,footer:!!document.querySelector('.inbox-home-footer'),
                    duplicateTheme:!!document.getElementById('vInboxThemeBtn'),
                    scrollOverflow:document.documentElement.scrollWidth-innerWidth};
                """)
                print('INBOX_REFINEMENT',width,inbox,flush=True)
                assert inbox['listTop']>=inbox['bottom']-2,inbox
                assert inbox['listHeight']>45 and inbox['ring']==1,inbox
                assert not inbox['footer'] and not inbox['duplicateTheme'],inbox
                assert inbox['scrollOverflow']<=2,inbox
                assert all(pill['top']>=inbox['top']-1 and pill['bottom']<=inbox['bottom']+1
                           for pill in inbox['pills']),inbox
                # Opening AI must fully hide Chats, with the connection card
                # inside a scrollable region and an always-reachable composer.
                browser.find_element(By.ID,'aiQuickBtn').click()
                WebDriverWait(browser,8).until(lambda b:b.find_element(By.ID,'aiView').is_displayed())
                ai=browser.execute_script("""
                  const ai=document.getElementById('aiView');
                  const inbox=document.getElementById('welcomeChat');
                  const scroll=document.getElementById('aiScroll');
                  const form=document.getElementById('aiForm');
                  const input=document.getElementById('aiPrompt');
                  const header=document.getElementById('chatHeader').getBoundingClientRect();
                  const r=form.getBoundingClientRect(),view=ai.getBoundingClientRect();
                  return {inboxHidden:getComputedStyle(inbox).display==='none',
                    aiShown:getComputedStyle(ai).display!=='none',
                    scrollContainsConsent:scroll.contains(document.getElementById('aiNotice')),
                    scrollHeight:scroll.scrollHeight,scrollClient:scroll.clientHeight,
                    regionHeight:view.height,headerBottom:header.bottom,
                    formTop:r.top,formBottom:r.bottom,screenHeight:innerHeight,
                    promptVisible:input.getBoundingClientRect().height>0,
                    overflow:document.documentElement.scrollWidth-innerWidth};
                """)
                print('AI_MOBILE_LAYOUT',width,ai,flush=True)
                assert ai['inboxHidden'] and ai['aiShown'] and ai['scrollContainsConsent'],ai
                assert ai['regionHeight']>250 and ai['scrollClient']>40,ai
                assert ai['formTop']>=ai['headerBottom'] and ai['formBottom']<=ai['screenHeight']+2,ai
                assert ai['promptVisible'] and ai['overflow']<=2,ai
                browser.execute_script("document.getElementById('aiScroll').scrollTop=99999")
                reached=browser.execute_script("""
                  const scroll=document.getElementById('aiScroll');
                  return {actual:scroll.scrollTop,max:scroll.scrollHeight-scroll.clientHeight};
                """)
                assert reached['max']<2 or reached['actual']>=reached['max']-2,reached
                browser.execute_script("showWelcome()")
                assert browser.find_element(By.ID,'welcomeChat').is_displayed()
                assert not browser.find_element(By.ID,'aiView').is_displayed()
            print('MODERN_COMPOSER_BROWSER_PASS',flush=True)
        finally:
            browser.quit();server.should_exit=True

if __name__=='__main__':
    main()
