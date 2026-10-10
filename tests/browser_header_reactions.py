"""Mobile chat header and WhatsApp-style reaction placement in real Chromium."""
import tempfile, threading, time
from pathlib import Path
import requests, uvicorn
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from app.main import create_app

def run():
    with tempfile.TemporaryDirectory(prefix="huddle_inline_") as tmp:
        app=create_app(str(Path(tmp)/"chat.sqlite"))
        server=uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=8895,log_level="warning"))
        threading.Thread(target=server.run,daemon=True).start()
        base="http://127.0.0.1:8895"
        for _ in range(50):
            try:
                if requests.get(base+"/health",timeout=.5).status_code==200:break
            except requests.RequestException:pass
            time.sleep(.2)
        else:raise RuntimeError("Huddle test app not reachable")

        def user(handle,name):
            client=requests.Session()
            response=client.post(base+"/api/auth/register",json={"name":name,"handle":handle,"password":"SafePassword123!"})
            assert response.status_code==201,response.text
            return client,response.json()["user"]

        sender, a=user("aarohi","Aarohi")
        recipient, b=user("himanshu25","Himanshu Pannu 25")
        conversation=sender.post(base+"/api/conversations/direct",json={"user_id":b["id"]}).json()["conversation"]["id"]
        message=sender.post(base+f"/api/conversations/{conversation}/messages",json={"body":"How r u"}).json()["message"]
        reaction=recipient.post(base+f"/api/messages/{message['id']}/reactions",json={"emoji":"❤️"})
        assert reaction.status_code==200,reaction.text

        options=webdriver.ChromeOptions()
        for flag in ["--headless=new","--no-sandbox","--disable-dev-shm-usage","--window-size=1160,900"]:
            options.add_argument(flag)
        browser=webdriver.Chrome(options=options)
        try:
            for width,height in [(1160,900),(390,844),(345,735)]:
                browser.execute_cdp_cmd("Emulation.setDeviceMetricsOverride",{
                    "width":width,"height":height,"deviceScaleFactor":2 if width<721 else 1,"mobile":width<721})
                browser.get(base)
                browser.add_cookie({"name":"huddle_session","value":sender.cookies.get("huddle_session"),
                                    "path":"/","sameSite":"Strict"})
                browser.refresh()
                WebDriverWait(browser,12).until(lambda d:not d.find_element(By.ID,"appScreen").get_attribute("class").split().__contains__("hidden"))
                assert browser.find_element(By.ID,"profileQuickBtn").is_displayed(),"Inbox profile shortcut must remain"
                result=browser.execute_async_script("""
                  const done=arguments[arguments.length-1];
                  openConversation(arguments[0]).then(()=>done(true)).catch(e=>done(e.message));
                """,conversation)
                assert result is True,result
                WebDriverWait(browser,10).until(lambda d:len(d.find_elements(By.CSS_SELECTOR,".h-message-visual > .reactions .reaction"))==1)
                geometry=browser.execute_script("""
                    const r=document.querySelector('#msg-'+arguments[0]);
                    const header=document.querySelector('#chatHeader');
                    const identity=document.querySelector('#headerIdentity');
                    const actions=header.querySelector('.header-actions');
                    const name=identity.querySelector('.header-name');
                    const visual=r.querySelector('.h-message-visual');
                    const bubble=visual.querySelector('.bubble');
                    const reaction=visual.querySelector('.reactions');
                    const badge=reaction.querySelector('button.reaction');
                    const box=el=>el.getBoundingClientRect();
                    return {
                      viewport:innerWidth,
                      pageWidth:document.documentElement.scrollWidth,
                      headerWidth:box(header).width,
                      identityRight:box(identity).right,
                      buttonsLeft:box(actions).left,
                      name:name.textContent,clamp:getComputedStyle(name).webkitLineClamp,
                      visibleButtons:[...actions.querySelectorAll('button')].filter(b=>getComputedStyle(b).display!=='none').map(b=>b.id),
                      placeholder:document.getElementById('messageInput').placeholder,
                      badgeTop:box(reaction).top,badgeBottom:box(reaction).bottom,
                      bubbleBottom:box(bubble).bottom,
                      nested:reaction.parentElement===visual,
                      underText:!r.querySelector('.message-stack > .reactions'),
                      badgeLabel:badge.getAttribute('aria-label'),badgeText:badge.textContent,
                      visualBackground:getComputedStyle(reaction).backgroundColor,
                      quotePresent:!!r.querySelector('.h-inline-quote')
                    };
                """,message["id"])
                print("CHAT_INLINE_QA",width,geometry,flush=True)
                assert geometry["pageWidth"]<=geometry["viewport"]+3,"Horizontal overflow"
                assert geometry["identityRight"]<=geometry["buttonsLeft"]+1,"Contact name overlaps toolbar"
                assert geometry["name"]=="Himanshu Pannu 25"
                assert geometry["clamp"]=="2"
                assert geometry["visibleButtons"]==["searchMessagesBtn","aiQuickBtn","vHeaderThemeBtn"]
                assert geometry["placeholder"]=="Message"
                assert geometry["nested"] and geometry["underText"]
                assert geometry["badgeTop"]<geometry["bubbleBottom"]+4
                assert geometry["badgeBottom"]>=geometry["bubbleBottom"]-2
                assert "Reaction" in geometry["badgeLabel"]
                assert "❤️" in geometry["badgeText"]
                # Reactions remain real toggles, never extra chat messages.
                before=len(sender.get(base+f"/api/conversations/{conversation}/messages").json()["messages"])
                browser.find_element(By.CSS_SELECTOR,".h-message-visual > .reactions button").click()
                WebDriverWait(browser,5).until(lambda d:len(d.find_elements(By.CSS_SELECTOR,".h-message-visual > .reactions button"))==1)
                after=len(sender.get(base+f"/api/conversations/{conversation}/messages").json()["messages"])
                assert before==after,"Reacting must not post a chat message"
            print("CHAT_INLINE_BROWSER_PASS",flush=True)
        finally:
            browser.quit()
            server.should_exit=True

if __name__=="__main__":
    run()
