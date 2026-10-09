"""Puter user-owned hosted AI history is isolated from normal Huddle messages."""
from fastapi.testclient import TestClient
from app.main import create_app

def _user(client, handle):
    r=client.post("/api/auth/register",json={"name":handle.title(),"handle":handle,"password":"SufficientlyStrong123!"})
    assert r.status_code==201,r.text
    return r.json()["user"]

def test_hosted_result_requires_login_and_is_personal(tmp_path, monkeypatch):
    for key in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "HUDDLE_AI_PROVIDER"):
        monkeypatch.delenv(key,raising=False)
    app=create_app(str(tmp_path/"puter.sqlite"))
    with TestClient(app) as alice, TestClient(app) as bob, TestClient(app) as outsider:
        item={"prompt":"Explain Newton's first law","answer":"An object stays at rest or keeps moving unless a force changes its motion."}
        assert outsider.post("/api/ai/client-result",json=item).status_code==401
        _user(alice,"alice")
        _user(bob,"bobby")
        config=alice.get("/api/config").json()
        assert config["ai_chat"] is False
        assert config["ai_local"] is False
        result=alice.post("/api/ai/client-result",json=item)
        assert result.status_code==200,result.text
        assert result.json()["reply"]["body"]==item["answer"]
        own=alice.get("/api/ai/history").json()["messages"]
        assert [v["role"] for v in own]==["user","assistant"]
        assert bob.get("/api/ai/history").json()["messages"]==[]
        assert alice.get("/api/conversations").json()["conversations"]==[]
        invalid=alice.post("/api/ai/client-result",json={"prompt":"a","answer":""})
        assert invalid.status_code==422
