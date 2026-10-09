"""Isolated real Chromium end-to-end checks for two-account Huddle media sharing.

Run ONLY against an in-memory/test temp database, never the production Railway DB.
Requires selenium, Chrome, requests, uvicorn and the project's dependencies.
"""
import io
import os
import tempfile
import threading
import time
from pathlib import Path

import requests
import uvicorn
from cryptography.fernet import Fernet
from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from app.main import create_app


def main():
    with tempfile.TemporaryDirectory(prefix="huddle_browser_media_") as folder:
        root = Path(folder)
        os.environ["HUDDLE_MESSAGE_KEY"] = Fernet.generate_key().decode()
        os.environ["SEED_DEMO"] = "0"
        app = create_app(str(root / "test.sqlite"))
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8899, log_level="warning"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        base = "http://127.0.0.1:8899"
        for _ in range(60):
            try:
                if requests.get(base + "/health", timeout=0.5).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError("Test server did not start")

        alice = requests.Session()
        bob = requests.Session()
        stranger = requests.Session()

        def create_user(session, handle):
            response = session.post(base + "/api/auth/register", json={
                "name": handle.title(), "handle": handle, "password": "BrowserTest123!"})
            assert response.status_code == 201, response.text
            return response.json()["user"]

        create_user(alice, "alice")
        b = create_user(bob, "bobby")
        create_user(stranger, "outsider")
        room = alice.post(base + "/api/conversations/direct", json={
            "user_id": b["id"]}).json()["conversation"]["id"]

        options = webdriver.ChromeOptions()
        for flag in ["--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                     "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
                     "--window-size=1120,850"]:
            options.add_argument(flag)
        options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
        clients = []
        try:
            def launch(session):
                chrome = webdriver.Chrome(options=options)
                clients.append(chrome)
                chrome.get(base)
                cookie = session.cookies.get("huddle_session")
                assert cookie, "Missing session cookie"
                chrome.add_cookie({"name": "huddle_session", "value": cookie,
                                   "path": "/", "sameSite": "Strict"})
                chrome.refresh()
                WebDriverWait(chrome, 15).until(lambda browser: browser.execute_script(
                    "return !document.querySelector('#appScreen').classList.contains('hidden')"))
                ready = chrome.execute_async_script(
                    "const done=arguments[arguments.length-1];"
                    "openConversation(arguments[0]).then(()=>done(true)).catch(e=>done(e.message));", room)
                assert ready is True, ready
                return chrome

            a = launch(alice)
            c = launch(bob)
            c.execute_script("document.querySelector('#messageInput').value='';")
            a.find_element(By.ID, "messageInput").send_keys("Hello from browser Alice")
            a.find_element(By.ID, "sendBtn").click()
            WebDriverWait(c, 12).until(lambda browser:
                "Hello from browser Alice" in browser.find_element(By.ID, "messages").text)

            assert a.execute_script("return getComputedStyle(document.querySelector('.message-actions')).display") == "none"
            a.find_element(By.ID, "emojiBtn").click()
            a.find_element(By.CSS_SELECTOR, '[data-emoji-tab="Stickers"]').click()
            a.find_element(By.CSS_SELECTOR, '[data-sticker="🚀"]').click()
            WebDriverWait(c, 12).until(lambda browser:
                len(browser.find_elements(By.CSS_SELECTOR, "#messages .h-animated-sticker")) >= 1)
            bubble=a.execute_script("return [...document.querySelectorAll('.mine .bubble')].find(e=>e.textContent.includes('Hello from browser Alice'))")
            assert bubble is not None
            a.execute_script("arguments[0].dispatchEvent(new MouseEvent('dblclick',{bubbles:true}))", bubble)
            WebDriverWait(a, 4).until(lambda browser:
                len(browser.find_elements(By.CSS_SELECTOR, ".h-message-menu [data-h-reaction]")) >= 5)
            a.find_element(By.CSS_SELECTOR, '[data-h-reaction="❤️"]').click()
            WebDriverWait(c, 10).until(lambda browser:
                len(browser.find_elements(By.CSS_SELECTOR, '#messages .reactions .reaction')) >= 1)

            png = root / "sample.png"
            Image.new("RGB", (60, 35), "orange").save(png)
            print("ENHANCEMENT_READY=", a.execute_script("return {editor:typeof openMediaEditor,emoji:typeof drawEmojiPicker, scripts:[...document.scripts].map(x=>x.src)}"), flush=True)
            print("EARLY_BROWSER_LOGS=", a.get_log("browser"), flush=True)
            a.find_element(By.ID, "mediaFileInput").send_keys(str(png))
            print("POST_UPLOAD_SELECT=", a.execute_script("return {editor:!!document.querySelector('.h-editor-overlay'), progress:document.querySelector('#mediaProgress')?.textContent, input:document.querySelector('#mediaFileInput')?.files?.length}"), flush=True)
            WebDriverWait(a, 10).until(lambda browser:
                bool(browser.find_elements(By.CSS_SELECTOR, '[data-photo-tool="square"]')))
            a.find_element(By.CSS_SELECTOR, '[data-photo-tool="square"]').click()
            a.find_element(By.ID, "hEditorCaption").send_keys("Picture from our campus")
            a.find_element(By.ID, "hEditorSend").click()
            WebDriverWait(c, 12).until(lambda browser:
                len(browser.find_elements(By.CSS_SELECTOR, "#messages .image-media img")) >= 1)
            assert "Picture from our campus" in c.find_element(By.ID, "messages").text
            assert "picture.png" not in c.find_element(By.ID, "messages").text

            pdf = root / "study-notes.pdf"
            pdf.write_bytes(b"%PDF-1.4\n1 0 obj <<>> endobj\n%%EOF")
            a.find_element(By.ID, "mediaFileInput").send_keys(str(pdf))
            WebDriverWait(a, 10).until(lambda browser:
                bool(browser.find_elements(By.ID, "hEditorSend")))
            a.find_element(By.ID, "hEditorSend").click()
            WebDriverWait(c, 12).until(lambda browser:
                len(browser.find_elements(By.CSS_SELECTOR, "#messages .file-media")) >= 1)

            a.find_element(By.ID, "voiceNoteBtn").click()
            WebDriverWait(a, 10).until(lambda browser: browser.execute_script(
                "return document.querySelector('#voiceNoteBtn').classList.contains('recording')"))
            time.sleep(1.8)
            a.find_element(By.ID, "voiceNoteBtn").click()
            WebDriverWait(c, 15).until(lambda browser:
                len(browser.find_elements(By.CSS_SELECTOR, "#messages .voice-media audio")) >= 1)

            # Create a genuine playable WebM using Chrome's canvas + MediaRecorder
            # and send it through the same signed-in upload endpoint as file sharing.
            result = a.execute_async_script("""
                const room=arguments[0], done=arguments[arguments.length-1];
                (async()=>{
                  try{
                    const canvas=document.createElement('canvas');
                    canvas.width=160;canvas.height=90;
                    const ctx=canvas.getContext('2d');
                    const stream=canvas.captureStream(8);
                    const type=MediaRecorder.isTypeSupported('video/webm;codecs=vp8')
                      ? 'video/webm;codecs=vp8' : 'video/webm';
                    const recorder=new MediaRecorder(stream,{mimeType:type});
                    const chunks=[];
                    recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
                    recorder.onstop=async()=>{
                      try{
                        stream.getTracks().forEach(t=>t.stop());
                        const blob=new Blob(chunks,{type:'video/webm'});
                        const response=await fetch('/api/conversations/'+room+'/attachments',{
                          method:'POST',credentials:'same-origin',
                          headers:{'Content-Type':'video/webm','X-Huddle-Filename':'campus-clip.webm'},
                          body:blob
                        });
                        done({ok:response.ok,size:blob.size,response:await response.json()});
                      }catch(err){done({error:String(err)})}
                    };
                    recorder.start(200);
                    let tick=0;
                    const drawing=setInterval(()=>{
                      ctx.fillStyle=tick++%2?'#174ea6':'#f59e0b';
                      ctx.fillRect(0,0,160,90);
                    },100);
                    setTimeout(()=>{clearInterval(drawing);recorder.stop()},1550);
                  }catch(err){done({error:String(err)})}
                })();
            """, room)
            assert result.get("ok") and result.get("size", 0) > 200, result
            media = result["response"]["message"]["attachments"][0]
            assert media["content_type"] == "video/webm"
            WebDriverWait(c, 15).until(lambda browser:
                len(browser.find_elements(By.CSS_SELECTOR, "#messages .video-media video")) >= 1)
            video = c.find_element(By.CSS_SELECTOR, "#messages .video-media video")
            assert "/api/media/" in video.get_attribute("src")
            WebDriverWait(c, 15).until(lambda browser:
                browser.execute_script("return document.querySelector('.video-media video').videoWidth") > 0)

            url = base + "/api/media/" + media["id"]
            data = bob.get(url)
            assert data.status_code == 200 and data.content.startswith(bytes((0x1a,0x45,0xdf,0xa3)))
            assert stranger.get(url).status_code == 404
            part = bob.get(url, headers={"Range": "bytes=0-19"})
            assert part.status_code == 206 and part.content == data.content[:20]
            encrypted = (root / "media" / media["id"]).read_bytes()
            assert encrypted.startswith(b"HUDDLE_MEDIA_V1:")
            assert data.content != encrypted

            a.execute_cdp_cmd("Browser.grantPermissions",
                              {"origin": base, "permissions": ["notifications"]})
            a.find_element(By.ID, "notificationsBtn").click()
            WebDriverWait(a, 8).until(lambda browser:
                browser.execute_script("return localStorage.getItem('huddle-notify-opt-in')") == "yes")
            assert a.execute_script("return document.documentElement.scrollWidth <= innerWidth+4")
            assert all(not any(v in entry["message"] for v in ["Uncaught SyntaxError", "ReferenceError"])
                       for browser in clients for entry in browser.get_log("browser"))
            print("BROWSER_MEDIA_PASS: 2 browser accounts; WebSocket; PNG/PDF/voice/WebM; video playback; private ranges; encrypted storage; notifications", flush=True)
        finally:
            for chrome in reversed(clients):
                chrome.quit()
            server.should_exit = True


if __name__ == "__main__":
    main()
