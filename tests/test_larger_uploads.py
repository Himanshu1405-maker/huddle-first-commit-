"""Larger attachment limits with private access and early size rejection."""
from fastapi.testclient import TestClient
from app.main import create_app
from app.extensions import MAX_UPLOAD, MAX_VIDEO_UPLOAD
from app.moments import MEDIA_LIMIT


MiB=1024*1024


def create_user(client, handle):
    result=client.post("/api/auth/register",json={
        "name":handle.title(),"handle":handle,"password":"TestPass123456!"})
    assert result.status_code==201,result.text
    return result.json()["user"]


def test_larger_pdf_and_video_are_delivered_only_to_chat_members(tmp_path):
    assert MAX_UPLOAD==25*MiB
    assert MAX_VIDEO_UPLOAD==50*MiB
    app=create_app(str(tmp_path/"app.db"))
    with TestClient(app) as sender,TestClient(app) as friend,TestClient(app) as outsider:
        create_user(sender,"alice")
        recipient=create_user(friend,"bobby")
        create_user(outsider,"charlie")
        result=sender.post("/api/conversations/direct",json={"user_id":recipient["id"]})
        assert result.status_code==200,result.text
        cid=result.json()["conversation"]["id"]
        endpoint=f"/api/conversations/{cid}/attachments"
        # Cross the old 6 MB document and 20 MB video limits.
        samples=[
            ("study.pdf","application/pdf",b"%PDF-1.7\n"+b" "* (7*MiB)),
            ("event.mp4","video/mp4",b"\x00\x00\x00\x18ftypisom"+b"\x00"*(21*MiB)),
        ]
        for name,mime,payload in samples:
            headers={"Content-Type":mime,"X-Huddle-Filename":name}
            post=sender.post(endpoint,content=payload,headers=headers)
            assert post.status_code==201,(name,post.text)
            item=post.json()["message"]["attachments"][0]
            assert item["byte_size"]==len(payload)
            media_url="/api/media/"+item["id"]
            assert outsider.get(media_url).status_code==404
            assert friend.get(media_url,headers={"Range":"bytes=0-15"}).content[:16]==payload[:16] if mime.startswith("video/") else True
            download=friend.get(media_url)
            assert download.status_code==200,(name,download.status_code)
            assert download.content==payload
            assert "no-store" in download.headers["cache-control"]
        # Rejection checks are performed from Content-Length before reading large bodies.
        for mime,name,oversized in [
            ("application/pdf","too-large.pdf",25*MiB+1),
            ("video/mp4","too-large.mp4",50*MiB+1),
        ]:
            rejected=sender.post(endpoint,content=b"abc",headers={
                "Content-Type":mime,"X-Huddle-Filename":name,
                "Content-Length":str(oversized)})
            assert rejected.status_code==413,(name,rejected.status_code,rejected.text)


def test_larger_moment_media_is_private_and_limited(tmp_path):
    assert MEDIA_LIMIT==24*MiB
    app=create_app(str(tmp_path/"moments.db"))
    with TestClient(app) as sender,TestClient(app) as receiver,TestClient(app) as outsider:
        create_user(sender,"alice")
        bob=create_user(receiver,"bobby")
        create_user(outsider,"charlie")
        response=sender.post("/api/conversations/direct",json={"user_id":bob["id"]})
        assert response.status_code==200,response.text
        # Valid MP4 signature with a payload larger than the former 12 MB cap.
        video=b"\x00\x00\x00\x18ftypisom"+b"\x00"*(13*MiB)
        uploaded=sender.post("/api/moments/media",content=video,headers={"Content-Type":"video/mp4"})
        assert uploaded.status_code==201,uploaded.text
        media_url="/api/moments/"+uploaded.json()["id"]+"/media"
        assert outsider.get(media_url).status_code==404
        assert receiver.get(media_url).content==video
        rejected=sender.post("/api/moments/media",content=b"abc",headers={
            "Content-Type":"video/mp4","Content-Length":str(24*MiB+1)})
        assert rejected.status_code==413,rejected.text
