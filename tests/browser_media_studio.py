"""Media Studio visual/control regression: all photo tools, View Once, video & documents.

Uses isolated temporary accounts and SQLite, not production account data.
"""
import tempfile
import threading
import time
from pathlib import Path

import requests
import uvicorn
from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from app.main import create_app


def main():
    with tempfile.TemporaryDirectory(prefix="huddle_editor_studio_") as folder:
        base="http://127.0.0.1:8897"
        server=uvicorn.Server(uvicorn.Config(create_app(str(Path(folder)/"chat.db")),
                             host="127.0.0.1",port=8897,log_level="warning"))
        threading.Thread(target=server.run,daemon=True).start()
        for _ in range(60):
            try:
                if requests.get(base+"/health",timeout=.5).status_code==200:
                    break
            except requests.RequestException:
                pass
            time.sleep(.2)
        else:
            raise AssertionError("Local Huddle app did not start")

        def register(handle):
            session=requests.Session()
            response=session.post(base+"/api/auth/register",json={
                "name":handle.title(),"handle":handle,"password":"TestPassword123!"})
            assert response.status_code==201,response.text
            return session,response.json()["user"]

        alice,_=register("alice")
        _,bob=register("bobby")
        room=alice.post(base+"/api/conversations/direct",
                        json={"user_id":bob["id"]}).json()["conversation"]["id"]
        photo=Path(folder)/"photo.png"
        Image.new("RGB",(420,650),"#36a6ad").save(photo)
        pdf=Path(folder)/"lecture.pdf"
        pdf.write_bytes(b"%PDF-1.4\n1 0 obj <<>> endobj\n%%EOF")
        video=Path(folder)/"clip.mp4"
        # Preview requires an HTML video element; actual codec playback is
        # already covered by the independent two-account browser tests.
        video.write_bytes(b"\x00\x00\x00\x18ftypisom"+b"\x00"*128)
        options=webdriver.ChromeOptions()
        for arg in ["--headless=new","--no-sandbox","--disable-dev-shm-usage",
                    "--window-size=1150,850"]:
            options.add_argument(arg)
        browser=webdriver.Chrome(options=options)
        try:
            for width,height in [(1150,850),(390,844),(345,740)]:
                browser.execute_cdp_cmd("Emulation.setDeviceMetricsOverride",{
                    "width":width,"height":height,"deviceScaleFactor":2,
                    "mobile":width<721})
                browser.get(base)
                if not browser.get_cookie("huddle_session"):
                    browser.add_cookie({"name":"huddle_session",
                       "value":alice.cookies.get("huddle_session"),
                       "path":"/","sameSite":"Strict"})
                    browser.refresh()
                WebDriverWait(browser,12).until(
                    lambda d:d.find_element(By.ID,"appScreen").is_displayed())
                result=browser.execute_async_script("""
                    const done=arguments[arguments.length-1];
                    openConversation(arguments[0]).then(()=>done(true)).catch(e=>done(e.message));
                """,room)
                assert result is True,result

                # Documents retain an actionable preview and caption.
                browser.find_element(By.ID,"mediaFileInput").send_keys(str(pdf))
                WebDriverWait(browser,8).until(
                    lambda d:d.find_element(By.CSS_SELECTOR,".h-document-preview").is_displayed())
                assert browser.find_element(By.ID,"hEditorTitle").text=="Preview file"
                assert browser.find_element(By.ID,"hEditorCaption").is_displayed()
                browser.find_element(By.ID,"hEditorCancel").click()
                WebDriverWait(browser,5).until(
                    lambda d:not d.find_elements(By.CSS_SELECTOR,".h-editor-overlay"))

                # Video still supports its native playback controls and View Once.
                browser.find_element(By.ID,"mediaFileInput").send_keys(str(video))
                WebDriverWait(browser,8).until(lambda d:d.find_element(
                    By.CSS_SELECTOR,".h-editor-video-summary").is_displayed())
                assert browser.find_element(By.CSS_SELECTOR,"#hEditorStage video").get_attribute("controls")
                assert browser.find_element(By.ID,"hEditorViewOnce").is_displayed()
                assert browser.find_element(By.ID,"hEditorTitle").text=="Preview video"
                browser.find_element(By.ID,"hEditorCancel").click()
                WebDriverWait(browser,5).until(
                    lambda d:not d.find_elements(By.CSS_SELECTOR,".h-editor-overlay"))

                # Image editing: crop, rotate, flip, zoom, draw, undo and caption
                # must remain present on both 345px and desktop viewports.
                browser.find_element(By.ID,"mediaFileInput").send_keys(str(photo))
                WebDriverWait(browser,8).until(
                    lambda d:bool(d.find_elements(By.CSS_SELECTOR,
                                                "#hEditorStage canvas")))
                layout=browser.execute_script("""
                  const panel=document.querySelector('.h-editor-panel').getBoundingClientRect();
                  const header=document.querySelector('.h-editor-head').getBoundingClientRect();
                  const stage=document.querySelector('.h-editor-stage').getBoundingClientRect();
                  const tools=document.querySelector('.h-editor-tools').getBoundingClientRect();
                  const bottom=document.querySelector('.h-editor-bottom').getBoundingClientRect();
                  const footer=document.querySelector('.h-editor-footer').getBoundingClientRect();
                  return {panelBottom:panel.bottom,headerBottom:header.bottom,
                    stageHeight:stage.height,toolsHeight:tools.height,
                    bottomHeight:bottom.height,footerBottom:footer.bottom,
                    width:document.documentElement.scrollWidth,viewport:innerWidth,
                    height:innerHeight,kind:document.getElementById('hEditorKind').innerText};
                """)
                print("MEDIA_STUDIO_LAYOUT",width,layout,flush=True)
                assert layout["panelBottom"]<=layout["height"]+3,layout
                assert layout["width"]<=layout["viewport"]+3,layout
                assert layout["stageHeight"]>=65,layout
                assert layout["toolsHeight"]>=80,layout
                assert layout["bottomHeight"]>=85,layout
                assert layout["footerBottom"]<=layout["height"]+3,layout
                assert layout["kind"]=="PHOTO"
                for tool in ("free","square","portrait","wide","rotate","flip","pen","undo"):
                    assert browser.find_element(By.CSS_SELECTOR,
                        '[data-photo-tool="'+tool+'"]')
                browser.execute_script("""
                    document.querySelector('[data-photo-tool="square"]').click();
                    document.querySelector('[data-photo-tool="rotate"]').click();
                    document.querySelector('[data-photo-tool="flip"]').click();
                    document.querySelector('[data-photo-tool="pen"]').click();
                    document.querySelector('[data-photo-tool="undo"]').click();
                    const zoom=document.getElementById('hEditorZoom');
                    zoom.value='125';zoom.dispatchEvent(new Event('input',{bubbles:true}));
                """)
                assert browser.find_element(By.ID,"hEditorZoomValue").text=="125%"
                assert browser.find_element(By.CSS_SELECTOR,
                    '[data-photo-tool="square"]').get_attribute("aria-pressed")=="true"
                browser.find_element(By.ID,"hEditorCaption").send_keys("Media Studio looks fresh")
                once=browser.find_element(By.ID,"hEditorViewOnce")
                assert not once.is_selected()
                if width==390:
                    browser.execute_script("document.getElementById('hEditorViewOnce').click()")
                    assert once.is_selected()
                browser.find_element(By.ID,"hEditorSend").click()
                WebDriverWait(browser,15).until(
                    lambda d:not d.find_elements(By.CSS_SELECTOR,".h-editor-overlay"))
                # The editor closes before the asynchronous XHR upload finishes.
                # Wait for the real server-side attachment instead of racing it.
                expected=1 if width==1150 else 2 if width==390 else 3
                def uploaded_images(_):
                    response=alice.get(base+f"/api/conversations/{room}/messages")
                    assert response.status_code==200,response.text
                    images=[m for m in response.json()["messages"]
                        if m.get("attachments") and
                           m["attachments"][0]["content_type"].startswith("image/")]
                    return images if len(images)>=expected else False
                images=WebDriverWait(browser,15,poll_frequency=.3).until(uploaded_images)
                recent=images[-1]
                assert "Media Studio looks fresh" in recent["body"]
                assert bool(recent["attachments"][0]["view_once"])==(width==390)
                print("MEDIA_STUDIO_SEND",width,len(images),flush=True)
            print("MEDIA_STUDIO_BROWSER_PASS",flush=True)
        finally:
            browser.quit()
            server.should_exit=True


if __name__=="__main__":
    main()
