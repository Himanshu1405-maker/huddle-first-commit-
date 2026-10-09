"""Cloud AI API, privacy and configuration regression tests (no real provider calls)."""
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app import extras


def register(client, handle):
    response = client.post("/api/auth/register", json={
        "handle": handle, "name": handle.title(), "password": "StrongPass123!"})
    assert response.status_code == 201, response.text
    return response.json()["user"]


def test_no_device_model_and_no_provider_keys(tmp_path, monkeypatch):
    for name in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY",
                 "OPENAI_API_KEY", "HUDDLE_AI_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    with TestClient(create_app(str(tmp_path / "blank.db"))) as user:
        public = user.get("/api/config")
        assert public.status_code == 200
        config = public.json()
        assert config["ai_local"] is False
        assert config["ai_chat"] is False
        assert config["ai_provider"] is None
        register(user, "alice")
        result = user.post("/api/ai/chat", json={"prompt": "Explain photosynthesis"})
        assert result.status_code == 503
        assert "administrator" in result.json()["detail"].lower()
        assert "api_key" not in str(config).lower()


@pytest.mark.parametrize("provider,key,host,model", [
    ("gemini", "GEMINI_API_KEY", "generativelanguage.googleapis.com", "gemini-3.5-flash"),
    ("groq", "GROQ_API_KEY", "api.groq.com", "openai/gpt-oss-120b"),
    ("openrouter", "OPENROUTER_API_KEY", "openrouter.ai", "openai/gpt-4.1"),
    ("openai", "OPENAI_API_KEY", "api.openai.com", "gpt-4.1"),
])
def test_cloud_provider_routing(monkeypatch, provider, key, host, model):
    for name in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY",
                 "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HUDDLE_AI_PROVIDER", provider)
    monkeypatch.setenv(key, "server-secret-not-for-browsers")
    calls = []
    def fake_post(url, payload, headers, timeout):
        calls.append((url, payload, headers))
        if provider == "gemini":
            return {"candidates": [{"content": {"parts": [{"text": "Helpful answer."}]}}]}
        return {"choices": [{"message": {"content": "Helpful answer."}}]}
    monkeypatch.setattr(extras, "_post_json", fake_post)
    import asyncio
    answer = asyncio.run(extras.ask_ai([{"role": "user", "body": "Why is the sky blue?"}]))
    assert answer == "Helpful answer."
    url, body, headers = calls[0]
    assert host in url
    assert model in (url if provider == "gemini" else body["model"])
    assert "server-secret" not in str(body)
    assert extras.ai_provider() == provider


def test_explicit_context_consent_and_membership(tmp_path, monkeypatch):
    monkeypatch.setenv("HUDDLE_AI_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "local-test-secret")
    captured = []
    def fake_post(url, payload, headers, timeout):
        captured.append(payload)
        return {"choices": [{"message": {"content": "Here is a useful explanation."}}]}
    monkeypatch.setattr(extras, "_post_json", fake_post)
    app = create_app(str(tmp_path / "context.db"))
    with TestClient(app) as alice, TestClient(app) as bob, TestClient(app) as eve:
        a, b, outsider = register(alice,"alice"), register(bob,"bobby"), register(eve,"eve")
        room = alice.post("/api/conversations/direct",json={"user_id":b["id"]}).json()["conversation"]["id"]
        alice.post(f"/api/conversations/{room}/messages",json={"body":"Private calculus class discussion"}).raise_for_status()
        assert eve.post("/api/ai/chat",json={
            "prompt":"Summarize the class chat", "use_context":True, "conversation_id":room
        }).status_code == 404
        plain = bob.post("/api/ai/chat",json={"prompt":"What is a derivative?"})
        assert plain.status_code == 200, plain.text
        assert "Private calculus" not in str(captured[-1])
        consented = bob.post("/api/ai/chat",json={
            "prompt":"Use my class discussion to explain derivatives",
            "use_context":True, "conversation_id":room
        })
        assert consented.status_code == 200, consented.text
        assert "Private calculus class discussion" in str(captured[-1])
        history = bob.get("/api/ai/history").json()
        assert history["provider"] == "groq"
        assert history["enabled"] is True
        assert len(history["messages"]) == 4
        assert a["id"] != outsider["id"]
