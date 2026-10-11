"""Check modern vector chat previews and stable list updates in real Chrome."""
import tempfile, threading, time
from pathlib import Path
import requests, uvicorn
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from app.main import create_app


def main():
    with tempfile.TemporaryDirectory(prefix="huddle_chat_preview_") as folder:
        base="http://127.0.0.1:8898"
        server=uvicorn.Server(uvicorn.Config(create_app(str(Path(folder)/"app.db")),
                             host="127.0.0.1",port=8898,log_level="warning"))
        threading.Thread(target=server.run,daemon=True).start()
        for _ in range(60):
            try:
                if requests.get(base+"/health",timeout=.5).status_code==200:break
            except requests.RequestException:pass
            time.sleep(.2)
        else:raise AssertionError("Server not started")
        session=requests.Session()
        result=session.post(base+"/api/auth/register",json={
            "handle":"alice","name":"Alice","password":"TestPassword123!"})
        assert result.status_code==201,result.text
        opts=webdriver.ChromeOptions()
        for flag in ("--headless=new","--no-sandbox","--disable-dev-shm-usage","--window-size=1100,850"):
            opts.add_argument(flag)
        browser=webdriver.Chrome(options=opts)
        try:
            for width,height in ((1100,850),(390,844),(345,740)):
                browser.execute_cdp_cmd("Emulation.setDeviceMetricsOverride",{
                    "width":width,"height":height,"deviceScaleFactor":2,
                    "mobile":width<=720})
                browser.get(base)
                browser.add_cookie({"name":"huddle_session",
                    "value":session.cookies.get("huddle_session"),"path":"/","sameSite":"Strict"})
                browser.refresh()
                WebDriverWait(browser,12).until(lambda d:
                    d.find_element(By.ID,"appScreen").is_displayed())
                check=browser.execute_script("""
                    const base=[
                      ['photo','Edited photo','🖼️ IMG-20261011-WA0011-edited.jpg'],
                      ['location','Location','📍 Shared location'],
                      ['video','Video','🎬 old-video.mp4'],
                      ['voice','Voice message','🎤 voice.wav'],
                      ['file','Document','📎 notes.pdf'],
                      ['sticker','Sticker','🎉 Animated sticker'],
                      ['text','','We should meet tomorrow']
                    ];
                    const me=state.me.id;
                    state.filter='all';state.homeFilter='all';state.active=null;
                    document.getElementById('sidebarSearch').value='';
                    document.getElementById('homeSearch').value='';
                    state.conversations=Array.from({length:21},(_,n)=>{
                      const [kind,label,body]=base[n%base.length];
                      return {
                        id:'qa-'+n,kind:'dm',name:n===20?'<img src=x onerror=alert(1)>':('Friend '+n),
                        members:[{id:me,name:'Alice'}, {id:'other-'+n,name:'Friend'}],
                        unread:0,updated_at:'2026-10-11T07:30:00',
                        last_message:{body,preview_kind:kind,preview_label:label,
                            preview_caption:n===0?'Our trip at the lake':'',
                            sender_id:me,created_at:'2026-10-11T07:30:00'}
                      };
                    });
                    renderSidebar();
                    const home=document.getElementById('homeChatList');
                    const side=document.getElementById('conversationList');
                    const rows=[...home.querySelectorAll('.inbox-chat')];
                    const previews=base.map((x,i)=>{
                      const row=rows[i];
                      const holder=row.querySelector('.h-preview-wrap');
                      return {kind:x[0],text:holder?.textContent,icon:!!holder?.querySelector('svg'),
                        rawFile:holder?.textContent.includes('.jpg')||
                          holder?.textContent.includes('.mp4')||holder?.textContent.includes('.pdf')};
                    });
                    const first=home.querySelector('.inbox-chat');
                    const initial=home.scrollTop;
                    home.scrollTop=130;
                    const scrolled=home.scrollTop;
                    first.focus({preventScroll:true});
                    renderSidebar();
                    const stable=home.querySelector('.inbox-chat')===first;
                    const focused=document.activeElement===first;
                    const scrollKept=Math.abs(home.scrollTop-scrolled)<2;
                    const changing=state.conversations[1];
                    changing.last_message.preview_label='Live location';
                    renderSidebar();
                    const unaffected=home.querySelector('.inbox-chat')===first;
                    return {
                      previews,stable,focused,unaffected,scrollKept,scrolled,initial,
                      homeRows:rows.length,sideRows:side.querySelectorAll('.conv-item').length,
                      svgIcons:home.querySelectorAll('.h-preview-symbol svg').length,
                      sideIcons:side.querySelectorAll('.h-preview-symbol svg').length,
                      maliciousImage:!!home.querySelector('.inbox-chat img'),
                      overflow:document.documentElement.scrollWidth-innerWidth,
                      width:innerWidth,
                      motion:getComputedStyle(first).transitionProperty,
                      updatedLocation:home.querySelector('[data-home-conversation="qa-1"] .h-preview-label')?.textContent
                    };
                """)
                print("CHAT_PREVIEW_QA",width,check,flush=True)
                assert check["homeRows"]==21 and check["sideRows"]==21,check
                assert check["svgIcons"]>=17 and check["sideIcons"]>=17,check
                assert check["stable"] and check["focused"] and check["unaffected"],check
                assert check["scrollKept"] and check["overflow"]<=3,check
                assert not check["maliciousImage"],check
                assert check["updatedLocation"]=="Live location",check
                for preview in check["previews"][:6]:
                    assert preview["icon"] and not preview["rawFile"],preview
                    assert preview["text"].startswith("You"),preview
                assert check["previews"][6]["text"]=="You·We should meet tomorrow" or (
                    "We should meet tomorrow" in check["previews"][6]["text"])
            print("CHAT_PREVIEW_BROWSER_PASS",flush=True)
        finally:
            browser.quit()
            server.should_exit=True


if __name__=="__main__":
    main()
