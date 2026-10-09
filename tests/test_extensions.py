import io
import sqlite3
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from PIL import Image
from app.main import create_app

def register(c, handle):
    r=c.post("/api/auth/register",json={"name":handle.title(),"handle":handle,"password":"StrongPass123!"})
    assert r.status_code==201,r.text
    return r.json()["user"]

def test_media_validation_privacy_and_message_integrity(tmp_path):
    app=create_app(str(tmp_path/"db.sqlite"))
    with TestClient(app) as a,TestClient(app) as b,TestClient(app) as third:
        u,v,w=register(a,"alice"),register(b,"bobby"),register(third,"carla")
        cid=a.post("/api/conversations/direct",json={"user_id":v["id"]}).json()["conversation"]["id"]
        stream=io.BytesIO();Image.new("RGB",(20,20),"blue").save(stream,"PNG");data=stream.getvalue()
        url=f"/api/conversations/{cid}/attachments"
        h={"Content-Type":"image/png","X-Huddle-Filename":"campus%20photo.png"}
        assert third.post(url,content=data,headers=h).status_code==404
        resp=a.post(url,content=data,headers=h)
        assert resp.status_code==201,resp.text
        msg=resp.json()["message"]; att=msg["attachments"][0]
        assert att["filename"]=="campus photo.png"
        assert third.get("/api/media/"+att["id"]).status_code==404
        assert b.get("/api/media/"+att["id"]).content==data
        assert b.get(f"/api/conversations/{cid}/messages").json()["messages"][0]["attachments"][0]["id"]==att["id"]
        assert a.post(url,content=b"MZgarbage",headers=h).status_code==422
        assert a.post(url,content=b"%PDF-1.4\n/JavaScript",headers={"Content-Type":"application/pdf","X-Huddle-Filename":"bad.pdf"}).status_code==422
        assert a.post(url,content=b"<html>",headers={"Content-Type":"text/html","X-Huddle-Filename":"bad.html"}).status_code==422
        assert a.post(url,content=b"hello!",headers={"Content-Type":"text/plain","X-Huddle-Filename":"notes.txt"}).status_code==201
        assert a.post(url,content=b"x"*(6*1024*1024+1),headers={"Content-Type":"text/plain","X-Huddle-Filename":"huge.txt"}).status_code==413
        audio=b"RIFF"+(36).to_bytes(4,"little")+b"WAVEfmt "+bytes(30)
        assert a.post(url,content=audio,headers={"Content-Type":"audio/wav","X-Huddle-Filename":"note.wav"}).status_code==201
        assert a.delete("/api/messages/"+msg["id"]).status_code==200
        assert b.get("/api/media/"+att["id"]).status_code==404

def test_reports_and_admin_permissions(tmp_path):
    app=create_app(str(tmp_path/"db.sqlite"))
    with TestClient(app) as a,TestClient(app) as b,TestClient(app) as c:
        alice,bob,charlie=register(a,"alice"),register(b,"bobby"),register(c,"carla")
        r=a.post("/api/conversations/group",json={"name":"Study Group","member_ids":[bob["id"]]})
        assert r.status_code==201,r.text
        cid=r.json()["conversation"]["id"]
        msg=a.post(f"/api/conversations/{cid}/messages",json={"body":"Remember chapter five"}).json()["message"]
        mid=msg["id"]
        assert c.get(f"/api/conversations/{cid}/recap").status_code==404
        recap=b.get(f"/api/conversations/{cid}/recap").json()
        assert recap["method"]=="recent_messages" and recap["items"][0]["speaker"]=="Alice"
        assert a.post(f"/api/messages/{mid}/report",json={"reason":"Spam content"}).status_code==422
        assert c.post(f"/api/messages/{mid}/report",json={"reason":"Unsafe message"}).status_code==404
        assert b.post(f"/api/messages/{mid}/report",json={"reason":"Unkind content"}).status_code==201
        assert b.get(f"/api/conversations/{cid}/moderation/reports").status_code==403
        reports=a.get(f"/api/conversations/{cid}/moderation/reports").json()["reports"]
        assert len(reports)==1
        assert a.post(f"/api/conversations/{cid}/moderation/review",json={"report_id":reports[0]["id"],"status":"reviewed"}).status_code==200
        assert a.post(f"/api/conversations/{cid}/moderation/remove",json={"user_id":bob["id"]}).status_code==200
        assert b.get(f"/api/conversations/{cid}/messages").status_code==404

def test_server_side_message_encryption_and_migration(tmp_path,monkeypatch):
    db=tmp_path/"db.sqlite";monkeypatch.delenv("HUDDLE_MESSAGE_KEY",raising=False)
    with TestClient(create_app(str(db))) as a,TestClient(create_app(str(db))) as b:
        alice,bob=register(a,"alice"),register(b,"bobby")
        cid=a.post("/api/conversations/direct",json={"user_id":bob["id"]}).json()["conversation"]["id"]
        assert a.post(f"/api/conversations/{cid}/messages",json={"body":"Chapter nine algebra notes"}).status_code==201
    monkeypatch.setenv("HUDDLE_MESSAGE_KEY",Fernet.generate_key().decode())
    with TestClient(create_app(str(db))) as client:
        assert client.post("/api/auth/login",json={"handle":"alice","password":"StrongPass123!"}).status_code==200
        assert client.get(f"/api/conversations/{cid}/messages").json()["messages"][0]["body"]=="Chapter nine algebra notes"
        assert len(client.get("/api/search/messages?q=algebra").json()["results"])==1
        assert client.post(f"/api/conversations/{cid}/messages",json={"body":"Hidden algebra secret"}).status_code==201
    with sqlite3.connect(db) as sql:
        rows=sql.execute("SELECT body FROM messages").fetchall()
        assert len(rows)==2 and all(x[0].startswith("huddle.enc.v1:") for x in rows)
        assert all("algebra" not in x[0] for x in rows)
