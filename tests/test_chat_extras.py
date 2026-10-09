"""Attachment caption and animated sticker backwards-compatibility checks."""
from urllib.parse import quote
from fastapi.testclient import TestClient
from app.main import create_app


def test_attachment_caption_and_sticker_preview(tmp_path):
    app=create_app(str(tmp_path/"app.sqlite"))
    with TestClient(app) as alice, TestClient(app) as bob:
        for client,name in [(alice,"alice"),(bob,"bobby")]:
            result=client.post("/api/auth/register",json={"handle":name,"name":name.title(),"password":"MySecurePass123!"})
            assert result.status_code==201,result.text
        recipient=bob.get("/api/me").json()["user"]["id"]
        room=alice.post("/api/conversations/direct",json={"user_id":recipient}).json()["conversation"]["id"]
        caption="Working draft with thoughts ✨"
        upload=alice.post(
            f"/api/conversations/{room}/attachments",content=b"These are class notes.",
            headers={"Content-Type":"text/plain","X-Huddle-Filename":"draft.txt",
                     "X-Huddle-Caption":quote(caption,safe="")})
        assert upload.status_code==201,upload.text
        message=upload.json()["message"]
        assert message["body"]=="📎 draft.txt\n"+caption
        assert bob.get("/api/media/"+message["attachments"][0]["id"]).content==b"These are class notes."
        sent=alice.post(f"/api/conversations/{room}/messages",json={"body":"[[huddle-sticker:🚀]]"})
        assert sent.status_code==201,sent.text
        assert bob.get("/api/conversations").json()["conversations"][0]["last_message"]["body"]=="🎉 Animated sticker"
        history=bob.get(f"/api/conversations/{room}/messages").json()["messages"]
        assert history[-1]["body"]=="[[huddle-sticker:🚀]]"
        assert history[0]["body"]=="📎 draft.txt\n"+caption
        invalid=alice.post(f"/api/conversations/{room}/attachments",content=b"test",
            headers={"Content-Type":"text/plain","X-Huddle-Filename":"bad.txt",
                     "X-Huddle-Caption":quote("a"*501)})
        assert invalid.status_code==422
