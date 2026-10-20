"""End-to-end desktop/mobile QA for Back to Chats and whole-sidebar scrolling."""
import tempfile,threading,time
from pathlib import Path
import requests,uvicorn
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from app.main import create_app

def main():
    with tempfile.TemporaryDirectory(prefix="huddle_nav_") as folder:
        base="http://127.0.0.1:8899"
        server=uvicorn.Server(uvicorn.Config(create_app(str(Path(folder)/"chat.db")),
                             host="127.0.0.1",port=8899,log_level="error"))
        threading.Thread(target=server.run,daemon=True).start()
        for _ in range(60):
            try:
                if requests.get(base+"/health",timeout=.5).status_code==200:break
            except requests.RequestException:pass
            time.sleep(.2)
        else:raise AssertionError("Huddle test app did not start")
        def register(handle):
            c=requests.Session()
            r=c.post(base+"/api/auth/register",json={
              "handle":handle,"name":handle.capitalize(),"password":"TestPassword123!"})
            assert r.status_code==201,r.text
            return c,r.json()["user"]
        alice,_=register("alice")
        _,b=register("bobby")
        cid=alice.post(base+"/api/conversations/direct",
                       json={"user_id":b["id"]}).json()["conversation"]["id"]
        opts=webdriver.ChromeOptions()
        for arg in ["--headless=new","--no-sandbox","--disable-dev-shm-usage","--window-size=1100,730"]:
            opts.add_argument(arg)
        browser=webdriver.Chrome(options=opts)
        try:
            for width,height in [(1280,860),(1100,580),(390,740),(345,650)]:
                mobile=width<=720
                browser.execute_cdp_cmd("Emulation.setDeviceMetricsOverride",{
                    "width":width,"height":height,"deviceScaleFactor":2,"mobile":mobile})
                browser.get(base)
                browser.add_cookie({"name":"huddle_session","value":alice.cookies.get("huddle_session"),
                    "path":"/","sameSite":"Strict"})
                browser.refresh()
                WebDriverWait(browser,12).until(lambda d:
                    d.find_element(By.ID,"appScreen").is_displayed())
                assert browser.find_element(By.ID,"welcomeChat").is_displayed()
                assert not browser.find_element(By.ID,"backToChats").is_displayed()
                if mobile:
                    browser.find_element(By.ID,"openSidebar").click()
                    assert "open" in browser.find_element(By.ID,"sidebar").get_attribute("class")
                # Long content must scroll the entire sidebar — including the top
                # controls, Moments, people, and account profile at its bottom.
                before=browser.execute_script("""
                    const side=document.getElementById('sidebar');
                    const list=document.getElementById('conversationList');
                    for(let n=0;n<22;n++){
                      const button=document.createElement('button');
                      button.className='conv-item';
                      button.textContent='Example conversation '+n;
                      button.style.minHeight='83px';
                      list.append(button);
                    }
                    const css=getComputedStyle(side);
                    const listCSS=getComputedStyle(list);
                    const before=side.scrollTop;
                    side.scrollTop=side.scrollHeight;
                    const footer=document.getElementById('profileButton').getBoundingClientRect();
                    const bounds=side.getBoundingClientRect();
                    return {scrollHeight:side.scrollHeight,clientHeight:side.clientHeight,
                       scrollTop:side.scrollTop,startedAt:before,
                       footerBottom:footer.bottom,sidebarBottom:bounds.bottom,
                       footerVisible:footer.bottom<=bounds.bottom+3,
                       overflowY:css.overflowY,listOverflow:listCSS.overflowY,
                       sideWidth:bounds.width,innerWidth:innerWidth};
                """)
                print("SIDEBAR_SCROLL_QA",width,before,flush=True)
                assert before["scrollHeight"]>before["clientHeight"]+180,before
                assert before["scrollTop"]>180,before
                assert before["overflowY"]=="auto" and before["listOverflow"]=="visible",before
                assert before["footerVisible"],before
                browser.execute_script("document.getElementById('sidebar').scrollTop=0;")
                if mobile:
                    # Headless Chrome can mark the sticky drawer icon offscreen
                    # immediately after programmatic scroll; verify handler and
                    # actual drawer state using a single browser task.
                    browser.execute_script("document.getElementById('closeSidebar').click()")
                    assert "open" not in browser.find_element(By.ID,"sidebar").get_attribute("class")
                # Open a real conversation and then return to the full inbox.
                result=browser.execute_async_script("""
                    const done=arguments[arguments.length-1];
                    openConversation(arguments[0]).then(()=>done('ok')).catch(e=>done(e.message));
                """,cid)
                assert result=="ok",result
                assert browser.find_element(By.ID,"conversationView").is_displayed()
                assert not browser.find_element(By.ID,"welcomeChat").is_displayed()
                back=browser.find_element(By.ID,"backToChats")
                assert back.is_displayed()
                assert back.get_attribute("aria-label")=="Back to all chats"
                if mobile:
                    assert not browser.find_element(By.ID,"openSidebar").is_displayed()
                back.click()
                assert browser.find_element(By.ID,"welcomeChat").is_displayed()
                assert browser.find_element(By.ID,"homeChatList").is_displayed()
                assert browser.find_elements(By.CSS_SELECTOR,"#homeChatList .inbox-chat")
                assert not browser.find_element(By.ID,"conversationView").is_displayed()
                assert not browser.find_element(By.ID,"backToChats").is_displayed()
                assert mobile==browser.find_element(By.ID,"openSidebar").is_displayed()

                # A user can also return from the AI workspace and Moments.
                browser.execute_async_script("""
                    const done=arguments[arguments.length-1];
                    openAI().then(()=>done(true)).catch(e=>done(e.message));
                """)
                assert browser.find_element(By.ID,"aiView").is_displayed()
                assert browser.find_element(By.ID,"backToChats").is_displayed()
                browser.find_element(By.ID,"backToChats").click()
                assert browser.find_element(By.ID,"welcomeChat").is_displayed()
                browser.execute_script("HuddleMoments.open()")
                assert browser.find_element(By.ID,"hMomentsHome").is_displayed()
                assert browser.find_element(By.ID,"backToChats").is_displayed()
                browser.find_element(By.ID,"backToChats").click()
                assert browser.find_element(By.ID,"welcomeChat").is_displayed()
                assert not browser.find_element(By.ID,"hMomentsHome").is_displayed()
                print("BACK_TO_CHATS_PASS",width,flush=True)
            print("SIDEBAR_AND_NAVIGATION_BROWSER_PASS",flush=True)
        finally:
            browser.quit()
            server.should_exit=True

if __name__=="__main__": main()
