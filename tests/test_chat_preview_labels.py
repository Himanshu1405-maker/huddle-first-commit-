"""Semantic inbox labels: never display attachment filenames or raw location emojis."""
import io
import wave

from PIL import Image
from fastapi.testclient import TestClient
from app.main import create_app


def register(client,handle):
    r=client.post("/api/auth/register",json={
        "handle":handle,"name":handle.title(),"password":"TestPassword123!"})
    assert r.status_code==201,r.text
    return r.json()["user"]


def latest(client,conversation_id):
    res=client.get("/api/conversations")
    assert res.status_code==200,res.text
    return next(c["last_message"] for c in res.json()["conversations"]
                if c["id"]==conversation_id)


def test_media_inbox_labels_are_structured_and_private(tmp_path):
    app=create_app(str(tmp_path/"previews.db"))
    with TestClient(app) as alice,TestClient(app) as bob,TestClient(app) as outsider:
        register(alice,"alice")
        friend=register(bob,"bobby")
        register(outsider,"carol")
        cid=alice.post("/api/conversations/direct",json={"user_id":friend["id"]}).json()["conversation"]["id"]
        endpoint=f"/api/conversations/{cid}/attachments"
        data=io.BytesIO()
        Image.new("RGB",(28,28),"blue").save(data,format="JPEG")
        sent=alice.post(endpoint,content=data.getvalue(),headers={
            "Content-Type":"image/jpeg",
            "X-Huddle-Filename":"IMG-20261011-edited.jpg",
            "X-Huddle-Caption":"After the workshop"})
        assert sent.status_code==201,sent.text
        info=latest(bob,cid)
        assert info["preview_kind"]=="photo"
        assert info["preview_label"]=="Edited photo"
        assert info["preview_caption"]=="After the workshop"
        assert "IMG-" in info["body"]  # Existing message is not modified.
        assert "IMG-" not in info["preview_label"]
        assert outsider.get("/api/conversations").json()["conversations"]==[]
        view_once=alice.post(endpoint,content=data.getvalue(),headers={
            "Content-Type":"image/jpeg",
            "X-Huddle-Filename":"secret.jpg",
            "X-Huddle-View-Once":"1"})
        assert view_once.status_code==201,view_once.text
        info=latest(bob,cid)
        assert info["preview_kind"]=="photo"
        assert info["preview_label"]=="View once photo"
        assert not info["preview_caption"]
        video=b"\x00\x00\x00\x18ftypisom"+b"\x00"*80
        sent=alice.post(endpoint,content=video,headers={
            "Content-Type":"video/mp4","X-Huddle-Filename":"trip.mp4"})
        assert sent.status_code==201,sent.text
        assert latest(bob,cid)["preview_label"]=="Video"
        wav=io.BytesIO()
        with wave.open(wav,"wb") as audio:
            audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000)
            audio.writeframes(b"\x00\x00"*160)
        sent=alice.post(endpoint,content=wav.getvalue(),headers={
            "Content-Type":"audio/wav","X-Huddle-Filename":"sound.wav"})
        assert sent.status_code==201,sent.text
        assert latest(bob,cid)["preview_kind"]=="voice"
        assert latest(bob,cid)["preview_label"]=="Voice message"
        sent=alice.post(endpoint,content=b"%PDF-1.4\n1 0 obj <<>> endobj\n%%EOF",headers={
            "Content-Type":"application/pdf","X-Huddle-Filename":"notes.pdf"})
        assert sent.status_code==201,sent.text
        assert latest(bob,cid)["preview_label"]=="Document"
        location=alice.post(f"/api/conversations/{cid}/locations",json={
            "mode":"pin","latitude":31.77,"longitude":76.98})
        assert location.status_code==201,location.text
        info=latest(bob,cid)
        assert info["preview_kind"]=="location"
        assert info["preview_label"]=="Location"
        assert "latitude" not in str(info)
        live=alice.post(f"/api/conversations/{cid}/locations",json={
            "mode":"live","latitude":31.77,"longitude":76.98,"duration_minutes":15})
        assert live.status_code==201,live.text
        assert latest(bob,cid)["preview_label"]=="Live location"
        assert alice.post(f"/api/locations/{live.json()['message']['id']}/stop").status_code==200
        assert latest(bob,cid)["preview_label"]=="Location"
        text=alice.post(f"/api/conversations/{cid}/messages",json={
            "body":"🖼️ this is just an emoji I typed, not an attachment"})
        assert text.status_code==201,text.text
        info=latest(bob,cid)
        assert info["preview_kind"]=="text"
        assert info["body"].startswith("🖼️")
        assert info["preview_label"]==""
        deleted=alice.delete("/api/messages/"+text.json()["message"]["id"])
        assert deleted.status_code==200,deleted.text
        info=latest(bob,cid)
        assert info["preview_kind"]=="text"
        assert info["body"]=="Message deleted"
