"""Regression tests for private encrypted video/audio byte-range delivery."""
import io
import sqlite3
import wave
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from PIL import Image
from app.main import create_app


def _signup(client, name):
    result = client.post("/api/auth/register", json={
        "handle": name, "name": name.title(), "password": "MediaTestPass123!"})
    assert result.status_code == 201, result.text
    return result.json()["user"]


def test_two_accounts_share_encrypted_photo_document_voice_and_video(tmp_path, monkeypatch):
    monkeypatch.setenv("HUDDLE_MESSAGE_KEY", Fernet.generate_key().decode())
    db = tmp_path / "huddle.sqlite"
    app = create_app(str(db))
    with TestClient(app) as alice, TestClient(app) as bob, TestClient(app) as outsider:
        _signup(alice, "alice")
        recipient = _signup(bob, "bobby")
        _signup(outsider, "eve")
        resp = alice.post("/api/conversations/direct", json={"user_id": recipient["id"]})
        assert resp.status_code == 200
        cid = resp.json()["conversation"]["id"]
        endpoint = f"/api/conversations/{cid}/attachments"
        img = io.BytesIO()
        Image.new("RGB", (10, 10), "green").save(img, "PNG")
        voice = io.BytesIO()
        with wave.open(voice, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(8000)
            w.writeframes(b"\x00\x01" * 600)
        media = [
            ("picture.png", "image/png", img.getvalue()),
            ("notes.pdf", "application/pdf", b"%PDF-1.4\n1 0 obj <<>> endobj\n%%EOF"),
            ("memo.txt", "text/plain", b"Hi from another account!"),
            ("voice.wav", "audio/wav", voice.getvalue()),
            ("campus.mp4", "video/mp4", b"\x00\x00\x00\x18ftypisom" + b"\0" * 120),
        ]
        for filename, content_type, data in media:
            headers = {"Content-Type": content_type, "X-Huddle-Filename": filename}
            assert outsider.post(endpoint, content=data, headers=headers).status_code == 404
            up = alice.post(endpoint, content=data, headers=headers)
            assert up.status_code == 201, (filename, up.text)
            attachment = up.json()["message"]["attachments"][0]
            assert attachment["filename"] == filename
            url = "/api/media/" + attachment["id"]
            assert outsider.get(url).status_code == 404
            download = bob.get(url)
            assert download.status_code == 200
            assert download.content == data
            assert "no-store" in download.headers["cache-control"]
            encrypted = (tmp_path / "media" / attachment["id"]).read_bytes()
            assert encrypted.startswith(b"HUDDLE_MEDIA_V1:")
            assert data not in encrypted
            if content_type.startswith(("audio/", "video/")):
                partial = bob.get(url, headers={"Range": "bytes=0-15"})
                assert partial.status_code == 206
                assert partial.content == data[:16]
                assert partial.headers["content-range"] == f"bytes 0-15/{len(data)}"
                assert partial.headers["accept-ranges"] == "bytes"
                assert bob.get(url, headers={"Range": "bytes=-5"}).content == data[-5:]
                assert bob.get(url, headers={"Range": "bytes=999999-"}).status_code == 416
                assert bob.get(url, headers={"Range": "bytes=0-1,3-4"}).status_code == 416
            assert any(m["attachments"] and m["attachments"][0]["id"] == attachment["id"]
                       for m in bob.get(f"/api/conversations/{cid}/messages").json()["messages"])
        with sqlite3.connect(db) as sql:
            assert sql.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == len(media)
            assert all(row[0].startswith("huddle.enc.v1:") for row in
                       sql.execute("SELECT body FROM messages").fetchall())


def test_reject_invalid_video_signatures(tmp_path):
    with TestClient(create_app(str(tmp_path / "app.db"))) as alice, TestClient(create_app(str(tmp_path / "app.db"))) as bob:
        _signup(alice, "alice")
        recipient = _signup(bob, "bobby")
        cid = alice.post("/api/conversations/direct", json={"user_id": recipient["id"]}).json()["conversation"]["id"]
        endpoint = f"/api/conversations/{cid}/attachments"
        for filename, mime in [("fake.mp4", "video/mp4"), ("fake.webm", "video/webm"), ("fake.mov", "video/quicktime")]:
            result = alice.post(endpoint, content=b"not a media file!" * 4,
                                headers={"Content-Type": mime, "X-Huddle-Filename": filename})
            assert result.status_code == 422, (filename, result.text)
