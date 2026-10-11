"""One-time photo in real Chrome at 390 and 345px widths, without auto-preview."""
import tempfile,threading,time
from pathlib import Path
from PIL import Image
import requests,uvicorn
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from app.main import create_app

def main():
  with tempfile.TemporaryDirectory(prefix="huddle_once_") as folder:
    app=create_app(str(Path(folder)/"test.db"))
    server=uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=8896,log_level="warning"))
    threading.Thread(target=server.run,daemon=True).start()
    base="http://127.0.0.1:8896"
    for _ in range(60):
      try:
        if requests.get(base+"/health",timeout=.5).status_code==200:break
      except requests.RequestException:pass
      time.sleep(.2)
    else:raise AssertionError("Huddle test app did not start")
    def signup(handle):
      c=requests.Session()
      r=c.post(base+"/api/auth/register",json={"handle":handle,"name":handle.title(),
             "password":"TestPassword123!"})
      assert r.status_code==201,r.text
      return c,r.json()["user"]
    alice,a=signup("alice")
    bob,b=signup("bobby")
    cid=alice.post(base+"/api/conversations/direct",json={"user_id":b["id"]}).json()["conversation"]["id"]
    image_path=Path(folder)/"sample.png"
    Image.new("RGB",(90,70),"orange").save(image_path)
    opts=webdriver.ChromeOptions()
    for arg in ["--headless=new","--no-sandbox","--disable-dev-shm-usage","--window-size=390,844"]:
      opts.add_argument(arg)
    browser=webdriver.Chrome(options=opts)
    try:
      for attempt,(width,height) in enumerate([(390,844),(345,740)],start=1):
        browser.execute_cdp_cmd("Emulation.setDeviceMetricsOverride",{
          "width":width,"height":height,"deviceScaleFactor":2,"mobile":True})
        browser.get(base)
        browser.add_cookie({"name":"huddle_session","value":alice.cookies.get("huddle_session"),
                            "path":"/","sameSite":"Strict"})
        browser.refresh()
        WebDriverWait(browser,12).until(lambda d:d.find_element(By.ID,"appScreen").is_displayed())
        assert browser.execute_async_script("""
          const done=arguments[arguments.length-1];
          openConversation(arguments[0]).then(()=>done(true)).catch(e=>done(e.message));
        """,cid) is True
        browser.find_element(By.ID,"mediaFileInput").send_keys(str(image_path))
        WebDriverWait(browser,10).until(lambda d:len(d.find_elements(By.ID,"hEditorViewOnce"))==1)
        box=browser.find_element(By.ID,"hEditorViewOnce")
        assert not box.is_selected()
        box.click()
        browser.find_element(By.ID,"hEditorSend").click()
        WebDriverWait(browser,12).until(lambda d:
          len(d.find_elements(By.CSS_SELECTOR,"#messages .h-once-card"))>=attempt)
        sender=browser.execute_script("""
          const c=[...document.querySelectorAll('.h-once-card')].at(-1);
          return {text:c?.innerText,inline:!!c?.querySelector('img,video'),
            button:!!c?.querySelector('[data-view-once]'),
            pageWidth:document.documentElement.scrollWidth,viewport:innerWidth};
        """)
        print("VIEW_ONCE_SENDER",width,sender,flush=True)
        assert not sender["inline"] and not sender["button"]
        assert sender["pageWidth"]<=sender["viewport"]+2
        aid=alice.get(base+f"/api/conversations/{cid}/messages").json()["messages"][-1]["attachments"][0]["id"]
        browser.get(base)
        browser.delete_all_cookies()
        browser.add_cookie({"name":"huddle_session","value":bob.cookies.get("huddle_session"),
                            "path":"/","sameSite":"Strict"})
        browser.refresh()
        WebDriverWait(browser,12).until(lambda d:d.find_element(By.ID,"appScreen").is_displayed())
        browser.execute_async_script("""
          const done=arguments[arguments.length-1];
          openConversation(arguments[0]).then(()=>done(true)).catch(e=>done(e.message));
        """,cid)
        WebDriverWait(browser,8).until(lambda d:len(d.find_elements(By.CSS_SELECTOR,
              "button[data-view-once='"+aid+"']"))==1)
        browser.find_element(By.CSS_SELECTOR,"button[data-view-once='"+aid+"']").click()
        WebDriverWait(browser,8).until(lambda d:d.find_element(By.ID,"hViewOnceViewer").is_displayed())
        bounds=browser.execute_script("""
          const v=document.getElementById('hViewOnceViewer'),r=v.getBoundingClientRect();
          return {src:v.querySelector('img,video')?.src,top:r.top,bottom:r.bottom,height:innerHeight,
            pageWidth:document.documentElement.scrollWidth,viewport:innerWidth};
        """)
        print("VIEW_ONCE_OPEN",width,bounds,flush=True)
        assert bounds["src"].startswith("blob:")
        assert bounds["bottom"]<=bounds["height"]+2
        assert bounds["pageWidth"]<=bounds["viewport"]+2
        browser.find_element(By.CSS_SELECTOR,"#hViewOnceViewer .h-once-viewer-head button").click()
        assert not browser.find_elements(By.ID,"hViewOnceViewer")
        assert not browser.find_elements(By.CSS_SELECTOR,"button[data-view-once='"+aid+"']")
        assert "Opened" in browser.find_element(By.CSS_SELECTOR,
            ".h-once-card[data-h-once-card='"+aid+"']").text
        assert bob.post(base+f"/api/media/{aid}/view-once").status_code==410
        assert bob.get(base+f"/api/media/{aid}").status_code==404
      print("VIEW_ONCE_BROWSER_PASS",flush=True)
    finally:
      browser.quit()
      server.should_exit=True

if __name__=="__main__":
  main()
