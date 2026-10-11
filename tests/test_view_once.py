"""View Once is enforced by the server, even with direct URLs and replay attempts."""
import io
from pathlib import Path
from fastapi.testclient import TestClient
from PIL import Image
from app.main import create_app


def signup(c, handle):
    response=c.post("/api/auth/register",json={
        "name":handle.capitalize(),"handle":handle,"password":"TestPassword123!"})
    assert response.status_code==201,response.text
    return response.json()["user"]


def photo():
    buffer=io.BytesIO()
    Image.new("RGB",(25,25),"purple").save(buffer,format="PNG")
    return buffer.getvalue()


def test_view_once_photo_is_private_atomic_consumed_and_deleted(tmp_path):
    app=create_app(str(tmp_path/"huddle.db"))
    with TestClient(app) as alice,TestClient(app) as bob,TestClient(app) as stranger:
        me=signup(alice,"alice");b=signup(bob,"bobby");signup(stranger,"carol")
        room=alice.post("/api/conversations/direct",json={"user_id":b["id"]})
        cid=room.json()["conversation"]["id"]
        payload=photo()
        route=f"/api/conversations/{cid}/attachments"
        upload=alice.post(route,content=payload,headers={
            "Content-Type":"image/png","X-Huddle-Filename":"private.png",
            "X-Huddle-View-Once":"1"})
        assert upload.status_code==201,upload.text
        message=upload.json()["message"]
        media=message["attachments"][0]
        assert media["view_once"]==1 and not media["opened_at"]
        url="/api/media/"+media["id"]
        open_url=url+"/view-once"
        assert alice.get(url).status_code==404
        assert bob.get(url).status_code==404
        assert stranger.get(url).status_code==404
        assert stranger.post(open_url).status_code==404
        assert alice.post(open_url).status_code==403
        assert (tmp_path/"media"/media["id"]).exists()
        first=bob.post(open_url)
        assert first.status_code==200,first.text
        assert first.content==payload and first.headers["content-type"].startswith("image/png")
        assert "no-store" in first.headers["cache-control"]
        assert bob.post(open_url).status_code==410
        assert stranger.post(open_url).status_code==404
        assert not (tmp_path/"media"/media["id"]).exists()
        for c in (alice,bob):
            latest=c.get(f"/api/conversations/{cid}/messages").json()["messages"]
            attachment=next(m for m in latest if m["id"]==message["id"])["attachments"][0]
            assert attachment["view_once"]==1 and attachment["opened_at"]
        # The original survives as a status card, not as a media URL.
        assert message["id"] in [m["id"] for m in alice.get(
            f"/api/conversations/{cid}/messages").json()["messages"]]


def test_view_once_video_not_forwarded_and_invalid_uploads_rejected(tmp_path):
    app=create_app(str(tmp_path/"huddle.db"))
    with TestClient(app) as alice,TestClient(app) as bob,TestClient(app) as outsider:
        me=signup(alice,"alice");friend=signup(bob,"bobby");other=signup(outsider,"carol")
        cid=alice.post("/api/conversations/direct",
                       json={"user_id":friend["id"]}).json()["conversation"]["id"]
        elsewhere=alice.post("/api/conversations/direct",
                            json={"user_id":other["id"]}).json()["conversation"]["id"]
        group=alice.post("/api/conversations/group",
                         json={"name":"Private friends","member_ids":[friend["id"]]}).json()["conversation"]["id"]
        mp4=b"\x00\x00\x00\x18ftypisom"+b"\x00"*32
        headers={"Content-Type":"video/mp4","X-Huddle-Filename":"secret.mp4","X-Huddle-View-Once":"1"}
        upload=alice.post(f"/api/conversations/{cid}/attachments",content=mp4,headers=headers)
        assert upload.status_code==201,upload.text
        item=upload.json()["message"]
        aid=item["attachments"][0]["id"]
        assert bob.get("/api/media/"+aid,headers={"Range":"bytes=0-4"}).status_code==404
        forward=alice.post(f"/api/conversations/{elsewhere}/messages/context",json={
            "action":"forward","source_message_id":item["id"]})
        assert forward.status_code==422,forward.text
        assert alice.post(f"/api/conversations/{group}/attachments",
                          content=mp4,headers=headers).status_code==422
        assert alice.post(f"/api/conversations/{cid}/attachments",
                          content=b"hello",headers={
                              "Content-Type":"text/plain","X-Huddle-Filename":"note.txt",
                              "X-Huddle-View-Once":"1"}).status_code==422
        opened=bob.post(f"/api/media/{aid}/view-once")
        assert opened.status_code==200 and opened.content==mp4
        assert bob.post(f"/api/media/{aid}/view-once").status_code==410
        regular=alice.post(f"/api/conversations/{cid}/attachments",
                           content=photo(),headers={
                               "Content-Type":"image/png","X-Huddle-Filename":"regular.png"})
        assert regular.status_code==201,regular.text
        normal=regular.json()["message"]["attachments"][0]
        assert normal["view_once"]==0
        assert bob.get("/api/media/"+normal["id"]).content==photo()
