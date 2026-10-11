"""Browser QA for private Huddle AI in existing direct and group chats."""
import tempfile
import threading
import time
from pathlib import Path
import requests
import uvicorn
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from app.main import create_app


def main():
    with tempfile.TemporaryDirectory(prefix="huddle_inline_ai_") as folder:
        application=create_app(str(Path(folder)/"test.db"))
        server=uvicorn.Server(uvicorn.Config(application,host="127.0.0.1",port=8895,log_level="error"))
        thread=threading.Thread(target=server.run,daemon=True)
        thread.start()
        base="http://127.0.0.1:8895"
        for _ in range(60):
            try:
                if requests.get(base+"/health",timeout=.4).status_code==200:break
            except requests.RequestException:pass
            time.sleep(.2)
        else:raise AssertionError("Server did not start")

        def user(handle):
            session=requests.Session()
            r=session.post(base+"/api/auth/register",json={"name":handle.title(),
               "handle":handle,"password":"TestPassword123!"})
            assert r.status_code==201,r.text
            return session,r.json()["user"]

        alice,alice_account=user("alice")
        bob,bob_account=user("bobby")
        conversation=alice.post(base+"/api/conversations/direct",json={"user_id":bob_account["id"]})
        assert conversation.status_code==200,conversation.text
        cid=conversation.json()["conversation"]["id"]
        original=bob.post(base+f"/api/conversations/{cid}/messages",json={
            "body":"Project plans for the demo are on Wednesday."})
        assert original.status_code==201,original.text
        opts=webdriver.ChromeOptions()
        for flag in ["--headless=new","--no-sandbox","--disable-dev-shm-usage","--window-size=390,844"]:
            opts.add_argument(flag)
        browser=webdriver.Chrome(options=opts)
        try:
            for width,height in [(390,844),(345,740)]:
                browser.execute_cdp_cmd("Emulation.setDeviceMetricsOverride",{
                    "width":width,"height":height,"deviceScaleFactor":2,"mobile":True})
                browser.get(base)
                browser.add_cookie({"name":"huddle_session",
                    "value":alice.cookies.get("huddle_session"),"path":"/","sameSite":"Strict"})
                browser.refresh()
                WebDriverWait(browser,12).until(lambda b:b.find_element(By.ID,"appScreen").is_displayed())
                browser.execute_async_script("""
                    const done=arguments[arguments.length-1];
                    openConversation(arguments[0]).then(()=>done(true)).catch(e=>done(e.message));
                """,cid)
                browser.execute_script("""
                    window.__huddleAiRequests=[];
                    window.puter={
                      auth:{isSignedIn:()=>true,signIn:()=>Promise.resolve({username:'test'})},
                      ai:{chat:async turns=>{
                        window.__huddleAiRequests.push(turns);
                        return {message:{content:'Suggested thoughtful reply '+window.__huddleAiRequests.length}};
                      }}
                    };
                    state.puter.connected=true;
                """)
                trigger=browser.execute_script("""
                    const button=document.getElementById('hChatAiOpen');
                    const view=document.getElementById('conversationView');
                    const parent=button.parentElement;
                    const r=button.getBoundingClientRect();
                    const p=parent.getBoundingClientRect();
                    const comp=document.querySelector('.composer-area').getBoundingClientRect();
                    const style=getComputedStyle(button),ps=getComputedStyle(parent);
                    return {buttonRect:{top:r.top,bottom:r.bottom,width:r.width,height:r.height},
                      parentRect:{top:p.top,bottom:p.bottom,width:p.width,height:p.height},
                      composerRect:{top:comp.top,bottom:comp.bottom,height:comp.height},
                      display:style.display,visibility:style.visibility,parentDisplay:ps.display,
                      active:state.active?.id,conversationDisplay:getComputedStyle(view).display,
                      elementAt:document.elementFromPoint(r.left+r.width/2,r.top+r.height/2)?.id};
                """)
                print("INLINE_AI_TRIGGER",width,trigger,flush=True)
                assert trigger['buttonRect']['height']>15 and trigger['buttonRect']['width']>25,trigger
                browser.find_element(By.ID,"hChatAiOpen").click()
                assert browser.find_element(By.ID,"hChatAiPanel").is_displayed()
                view=browser.execute_script("""
                    const p=document.querySelector('#hChatAiPanel').getBoundingClientRect();
                    const form=document.querySelector('#hChatAiForm').getBoundingClientRect();
                    return {width:document.documentElement.scrollWidth,viewport:innerWidth,
                        panelTop:p.top,panelBottom:p.bottom,formBottom:form.bottom,height:innerHeight,
                        quoteChecked:document.querySelector('#hChatAiQuote').checked};
                """)
                print("INLINE_AI_LAYOUT",width,view,flush=True)
                assert view["width"]<=view["viewport"]+2,view
                assert view["panelBottom"]<=view["height"]+2,view
                assert view["formBottom"]<=view["height"]+2,view
                assert not view["quoteChecked"],view

                browser.find_element(By.ID,"hChatAiPrompt").send_keys("Help me reply politely")
                browser.find_element(By.ID,"hChatAiSend").click()
                WebDriverWait(browser,8).until(lambda b:
                    "Suggested thoughtful reply 1" in b.find_element(By.ID,"hChatAiMessages").text)
                first=browser.execute_script("""
                    return JSON.stringify(window.__huddleAiRequests[0]);
                """)
                assert "Project plans for the demo" not in first,"Chat messages must not be shared without consent"
                assert len(alice.get(base+f"/api/conversations/{cid}/messages").json()["messages"])==1

                browser.find_element(By.ID,"hChatAiQuote").click()
                browser.find_element(By.ID,"hChatAiPrompt").send_keys("Summarize it")
                browser.find_element(By.ID,"hChatAiSend").click()
                WebDriverWait(browser,8).until(lambda b:
                    "Suggested thoughtful reply 2" in b.find_element(By.ID,"hChatAiMessages").text)
                second=browser.execute_script("return JSON.stringify(window.__huddleAiRequests[1]);")
                assert "Project plans for the demo" in second,"Explicitly opted-in quote should reach the provider"
                assert len(alice.get(base+f"/api/conversations/{cid}/messages").json()["messages"])==1

                browser.execute_script("""
                    document.querySelector('#hChatAiMessages .h-chat-ai-reply:last-child button').click();
                """)
                assert not browser.find_element(By.ID,"hChatAiPanel").is_displayed()
                assert "Suggested thoughtful reply" in browser.find_element(By.ID,"messageInput").get_attribute("value")
                assert len(alice.get(base+f"/api/conversations/{cid}/messages").json()["messages"])==1

                browser.execute_script("""
                    document.getElementById('messageInput').value='@HuddleAI What is a polite follow-up?';
                    document.getElementById('sendBtn').click();
                """)
                assert browser.find_element(By.ID,"hChatAiPanel").is_displayed()
                assert "polite follow-up" in browser.find_element(By.ID,"hChatAiPrompt").get_attribute("value")
                assert len(alice.get(base+f"/api/conversations/{cid}/messages").json()["messages"])==1
                browser.execute_script("signOutLocal()")
                assert not browser.find_element(By.ID,"hChatAiPanel").is_displayed()
                assert browser.execute_script("return window.HuddleChatAI.isOpen()") is False
            print("CHAT_AI_BROWSER_PASS",flush=True)
        finally:
            browser.quit()
            server.should_exit=True


if __name__=="__main__":
    main()
