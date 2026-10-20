"""Chrome regression: entire Chats home page scrolls together, not just the card list."""
import tempfile,threading,time
from pathlib import Path
import requests,uvicorn
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from app.main import create_app

def main():
    with tempfile.TemporaryDirectory(prefix="huddle_home_full_scroll_") as folder:
        base="http://127.0.0.1:8894"
        server=uvicorn.Server(uvicorn.Config(create_app(str(Path(folder)/"app.db")),
                             host="127.0.0.1",port=8894,log_level="error"))
        threading.Thread(target=server.run,daemon=True).start()
        for _ in range(60):
            try:
                if requests.get(base+"/health",timeout=.5).status_code==200:break
            except requests.RequestException:pass
            time.sleep(.2)
        else:raise AssertionError("Huddle fixture unavailable")
        def register(handle):
            session=requests.Session()
            response=session.post(base+"/api/auth/register",json={
                "name":handle.title(),"handle":handle,"password":"TestPassword123!"})
            assert response.status_code==201,response.text
            return session,response.json()["user"]
        alice,_=register("alice")
        _,bob=register("bobby")
        cid=alice.post(base+"/api/conversations/direct",
                       json={"user_id":bob["id"]}).json()["conversation"]["id"]
        group=alice.post(base+"/api/conversations/group",json={
            "name":"Real group filter fixture","member_ids":[bob["id"]]})
        assert group.status_code==201,group.text
        opts=webdriver.ChromeOptions()
        for arg in ["--headless=new","--no-sandbox","--disable-dev-shm-usage",
                    "--window-size=1280,850"]:
            opts.add_argument(arg)
        browser=webdriver.Chrome(options=opts)
        try:
            for width,height in [(1280,850),(1100,580),(390,740),(345,650)]:
                mobile=width<=720
                browser.execute_cdp_cmd("Emulation.setDeviceMetricsOverride",{
                    "width":width,"height":height,"deviceScaleFactor":2,
                    "mobile":mobile})
                browser.get(base)
                browser.add_cookie({"name":"huddle_session",
                    "value":alice.cookies.get("huddle_session"),"path":"/","sameSite":"Strict"})
                browser.refresh()
                WebDriverWait(browser,12).until(
                    lambda d:d.find_element(By.ID,"appScreen").is_displayed())
                check=browser.execute_script("""
                    const home=document.getElementById('welcomeChat');
                    const list=document.getElementById('homeChatList');
                    const stateBefore=state.conversations.length;
                    const currentUser=state.me.id;
                    for(let i=0;i<24;i++){
                      state.conversations.push({
                        id:'extra-'+i,kind:i%3===0?'group':'dm',
                        name:'Friendly Group '+i,members:[{id:currentUser,name:'Alice'}],
                        unread:0,updated_at:'2026-10-11T09:00:00',
                        last_message:{
                          body:'Looking forward to seeing you!',
                          sender_id:'other-user',created_at:'2026-10-11T09:00:00',
                          preview_kind:'text'
                        }
                      });
                    }
                    renderSidebar();
                    const outer=getComputedStyle(home);
                    const inner=getComputedStyle(list);
                    const topHeader=document.querySelector('#welcomeChat .inbox-home-header');
                    const moments=document.querySelector('#welcomeChat .h-moments-strip-section');
                    const search=document.querySelector('#welcomeChat .inbox-search-wrap');
                    const filters=document.querySelector('#welcomeChat .inbox-filters');
                    const cards=list.querySelectorAll('.inbox-chat');
                    const before=home.scrollTop;
                    home.scrollTop=home.scrollHeight;
                    const after=home.scrollTop;
                    const first=topHeader.getBoundingClientRect();
                    const last=cards[cards.length-1].getBoundingClientRect();
                    const view=home.getBoundingClientRect();
                    const header=document.getElementById('chatHeader').getBoundingClientRect();
                    return {
                      before,after,rows:cards.length,stateBefore,
                      homeOverflow:outer.overflowY,listOverflow:inner.overflowY,
                      homeHeight:home.clientHeight,homeScrollHeight:home.scrollHeight,
                      listHeight:list.clientHeight,listScrollHeight:list.scrollHeight,
                      firstBottom:first.bottom,lastBottom:last.bottom,viewportBottom:view.bottom,
                      headerBottom:header.bottom,
                      momentsHeight:moments.getBoundingClientRect().height,
                      searchHeight:search.getBoundingClientRect().height,
                      filtersHeight:filters.getBoundingClientRect().height,
                      sideOverflow:getComputedStyle(document.getElementById('sidebar')).overflowY,
                      width:document.documentElement.scrollWidth,viewport:innerWidth
                    };
                """)
                print("FULL_HOME_SCROLL",width,check,flush=True)
                assert check["rows"]>=25,check
                assert check["homeOverflow"]=="auto",check
                assert check["listOverflow"]=="visible",check
                assert check["homeScrollHeight"]>check["homeHeight"]+220,check
                assert check["after"]>220,check
                assert check["firstBottom"]<check["headerBottom"]+5,check
                assert check["lastBottom"]<=check["viewportBottom"]+4,check
                assert check["momentsHeight"]>10 and check["searchHeight"]>25,check
                assert check["filtersHeight"]>25,check
                assert check["width"]<=check["viewport"]+3,check
                assert check["sideOverflow"]=="auto",check

                # Changing filters resets the outer home scroll and keeps pills usable.
                browser.execute_script("""
                    const home=document.getElementById('welcomeChat');
                    document.querySelector('[data-home-filter="group"]').click();
                """)
                filtered=browser.execute_script("""
                    return {scroll:document.getElementById('welcomeChat').scrollTop,
                      active:document.querySelector('[data-home-filter="group"]').classList.contains('selected'),
                      rows:document.querySelectorAll('#homeChatList .inbox-chat').length};
                """)
                assert filtered["scroll"]<=1 and filtered["active"] and filtered["rows"]>0,filtered
                browser.execute_script("document.querySelector('[data-home-filter=all]').click()")
                browser.execute_script("document.getElementById('welcomeChat').scrollTop=210")
                start=browser.execute_script("return document.getElementById('welcomeChat').scrollTop")
                assert start>150,start

                # Opening a real chat and using Back must restore the inbox;
                # returning should not jump back to the very top.
                result=browser.execute_async_script("""
                    const done=arguments[arguments.length-1];
                    openConversation(arguments[0]).then(()=>done(true)).catch(e=>done(e.message));
                """,cid)
                assert result is True,result
                assert browser.find_element(By.ID,"conversationView").is_displayed()
                assert not browser.find_element(By.ID,"welcomeChat").is_displayed()
                browser.find_element(By.ID,"backToChats").click()
                assert browser.find_element(By.ID,"welcomeChat").is_displayed()
                returned=browser.execute_script("""
                    return {pos:document.getElementById('welcomeChat').scrollTop,
                      visible:getComputedStyle(document.getElementById('welcomeChat')).display,
                      rows:document.querySelectorAll('#homeChatList .inbox-chat').length};
                """)
                print("HOME_SCROLL_BACK",width,returned,flush=True)
                assert returned["rows"]>=25,returned
                assert returned["pos"]>120,returned
                # Scroll to the beginning to confirm header and search come back.
                browser.execute_script("document.getElementById('welcomeChat').scrollTop=0")
                pos=browser.execute_script("""
                    return {top:document.getElementById('welcomeChat').scrollTop,
                      title:document.querySelector('#welcomeChat h1').textContent,
                      search:document.querySelector('#welcomeChat .inbox-search-wrap').getBoundingClientRect().height};
                """)
                assert pos["top"]==0 and pos["title"]=="Chats" and pos["search"]>25,pos
            print("FULL_HOME_SCROLL_BROWSER_PASS",flush=True)
        finally:
            browser.quit()
            server.should_exit=True

if __name__=="__main__":main()
