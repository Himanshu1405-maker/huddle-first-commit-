"""Real Chrome auth design QA using a private temporary Huddle database."""
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
    with tempfile.TemporaryDirectory(prefix="huddle_auth_") as directory:
        app = create_app(str(Path(directory) / "auth.db"))
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8898, log_level="warning"))
        threading.Thread(target=server.run, daemon=True).start()
        base = "http://127.0.0.1:8898/"
        for _ in range(50):
            try:
                if requests.get(base + "health", timeout=1).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(.2)
        else:
            raise RuntimeError("Huddle test app failed to start")
        options=webdriver.ChromeOptions()
        for arg in ["--headless=new","--no-sandbox","--disable-dev-shm-usage","--window-size=1400,950"]:
            options.add_argument(arg)
        browser=webdriver.Chrome(options=options)
        try:
            for width,height,mobile in [(1440,900,False),(390,844,True),(360,740,True)]:
                browser.execute_cdp_cmd("Emulation.setDeviceMetricsOverride",{
                    "width":width,"height":height,"deviceScaleFactor":2 if mobile else 1,"mobile":mobile})
                browser.get(base)
                WebDriverWait(browser,10).until(lambda b: b.find_element(By.ID,"authTitle").is_displayed())
                snap=browser.execute_script("""
                    const hero=document.querySelector('.auth-hero');
                    const card=document.querySelector('.auth-form-shell');
                    return {vw:innerWidth,doc:document.documentElement.scrollWidth,
                      title:document.querySelector('#authTitle').textContent,
                      hero:getComputedStyle(hero).display,cardWidth:card.getBoundingClientRect().width,
                      gradient:getComputedStyle(hero).backgroundImage.includes('linear-gradient'),
                      hasTheme:[...document.styleSheets].some(s=>s.href?.includes('auth-bloom.css'))};
                """)
                print("AUTH_LAYOUT",width,snap,flush=True)
                assert snap["doc"] <= snap["vw"] + 3, "Auth page overflows on width "+str(width)
                assert snap["hero"]!="none" and snap["gradient"] and snap["hasTheme"]
                assert "Huddle" in snap["title"] and snap["cardWidth"]>=min(width-36,325)
                browser.find_element(By.ID,"switchAuth").click()
                assert browser.find_element(By.ID,"registerNameField").is_displayed()
                assert "Huddle" in browser.find_element(By.ID,"authTitle").text
                assert "Create account" in browser.find_element(By.ID,"authSubmit").text
                browser.find_element(By.ID,"switchAuth").click()
                assert not browser.find_element(By.ID,"registerNameField").is_displayed()
                assert browser.find_element(By.ID,"authPassword").get_attribute("type")=="password"
                browser.find_element(By.ID,"togglePassword").click()
                assert browser.find_element(By.ID,"authPassword").get_attribute("type")=="text"
            print("AUTH_BLOOM_BROWSER_PASS",flush=True)
        finally:
            browser.quit()
            server.should_exit=True


if __name__=="__main__":
    main()
