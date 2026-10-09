from fastapi.testclient import TestClient
from app.main import create_app

def register(client, handle):
    r = client.post("/api/auth/register", json={
        "name": handle.title(), "handle": handle, "password": "ExamplePass123!"})
    assert r.status_code == 201, r.text
    return r.json()["user"]

def test_video_shared_with_conversation_members_only(tmp_path):
    with TestClient(create_app(str(tmp_path / "app.sqlite"))) as alice, TestClient(create_app(str(tmp_path / "app.sqlite"))) as bob, TestClient(create_app(str(tmp_path / "app.sqlite"))) as stranger:
        register(alice, "alice")
        recipient = register(bob, "bobby")
        register(stranger, "charlie")
        chat = alice.post("/api/conversations/direct", json={"user_id": recipient["id"]})
        assert chat.status_code == 200, chat.text
        cid = chat.json()["conversation"]["id"]
        upload = f"/api/conversations/{cid}/attachments"
        mp4 = bytes([0,0,0,20]) + b"ftypisom" + bytes([0]*128)
        headers = {"content-type": "video/mp4", "x-huddle-filename": "campus.mp4"}
        assert stranger.post(upload, content=mp4, headers=headers).status_code == 404
        response = alice.post(upload, content=mp4, headers=headers)
        assert response.status_code == 201, response.text
        message = response.json()["message"]
        attachment = message["attachments"][0]
        assert attachment["content_type"] == "video/mp4"
        assert attachment["filename"] == "campus.mp4"
        url = "/api/media/" + attachment["id"]
        playback = bob.get(url)
        assert playback.status_code == 200
        assert playback.content == mp4
        assert playback.headers["content-type"].startswith("video/mp4")
        assert stranger.get(url).status_code == 404
        assert bob.get(f"/api/conversations/{cid}/messages").json()["messages"][0]["attachments"][0]["id"] == attachment["id"]
        assert alice.delete("/api/messages/" + message["id"]).status_code == 200
        assert bob.get(url).status_code == 404

def test_video_type_size_safety(tmp_path):
    with TestClient(create_app(str(tmp_path / "app.sqlite"))) as client:
        user = register(client, "alice")
        partner = register(TestClient(create_app(str(tmp_path / "app.sqlite"))), "bobby")
        chat = client.post("/api/conversations/direct", json={"user_id": partner["id"]})
        assert chat.status_code == 200
        url = f"/api/conversations/{chat.json()['conversation']['id']}/attachments"
        rejected = client.post(url, content=b"123", headers={"content-type": "video/mp4", "x-huddle-filename": "empty.mp4"})
        assert rejected.status_code == 422
        wrong_extension = client.post(url, content=b"x" * 32, headers={"content-type": "video/mp4", "x-huddle-filename": "fake.exe"})
        assert wrong_extension.status_code == 422
