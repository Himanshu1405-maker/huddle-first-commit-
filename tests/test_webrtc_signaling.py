"""Regression for authorized, room-scoped WebRTC signaling, no call media stored."""
from fastapi.testclient import TestClient
from app.main import create_app


def register(client,handle):
    response=client.post("/api/auth/register",json={
      "name":handle.title(),"handle":handle,"password":"TestPassword123!"})
    assert response.status_code==201,response.text
    return response.json()["user"]


def take(ws,expected):
    for _ in range(8):
        msg=ws.receive_json()
        if msg.get("type")==expected:return msg
    raise AssertionError("Expected WebRTC signal not received")


def test_webrtc_signaling_membership_and_no_group_fanout(tmp_path):
    app=create_app(str(tmp_path/"rtc.db"))
    with TestClient(app) as alice,TestClient(app) as bob,TestClient(app) as eve:
        a=register(alice,"alice");b=register(bob,"bobby");e=register(eve,"evelyn")
        cid=alice.post("/api/conversations/direct",json={"user_id":b["id"]}).json()["conversation"]["id"]
        group=alice.post("/api/conversations/group",json={
            "name":"Circle 1","member_ids":[b["id"]]}).json()["conversation"]["id"]
        before=alice.get(f"/api/conversations/{cid}/messages").json()["messages"]
        with alice.websocket_connect("/ws") as first, bob.websocket_connect("/ws") as second:
            hello=take(first,"hello");assert hello["user_id"]==a["id"]
            take(second,"hello")
            first.send_json({"type":"call:signal","conversation_id":cid,
                "recipient_id":b["id"],"action":"offer",
                "payload":{"type":"offer","sdp":"v=0\r\n","video":False}})
            delivered=take(second,"call:signal")
            assert delivered["from_user_id"]==a["id"]
            assert delivered["conversation_id"]==cid and delivered["action"]=="offer"
            second.send_json({"type":"call:signal","conversation_id":cid,
                "recipient_id":a["id"],"action":"reject","payload":{}})
            rejected=take(first,"call:signal")
            assert rejected["action"]=="reject" and rejected["from_user_id"]==b["id"]
            first.send_json({"type":"call:signal","conversation_id":group,
                "recipient_id":b["id"],"action":"offer",
                "payload":{"type":"offer","sdp":"v=0\r\n"}})
            error=take(first,"error")
            assert "direct chats" in error["detail"]
            first.send_json({"type":"call:signal","conversation_id":cid,
                "recipient_id":e["id"],"action":"offer",
                "payload":{"type":"offer","sdp":"v=0\r\n"}})
            forbidden=take(first,"error")
            assert forbidden["detail"]=="Conversation not found"
        after=alice.get(f"/api/conversations/{cid}/messages").json()["messages"]
        assert after==before
