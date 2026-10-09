"""Optional integrations. All provider keys live on the server, never in the browser."""
from __future__ import annotations
import asyncio
import json
import os
import urllib.error
import urllib.request


def mail_ready() -> bool:
    return bool(os.getenv("BREVO_API_KEY") and os.getenv("MAIL_FROM"))


def text_ready() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


def image_ready() -> bool:
    return bool(os.getenv("HF_TOKEN") and os.getenv("AI_IMAGES_ENABLED", "0") == "1")


def _post_json(url: str, payload: dict, headers: dict, timeout=20) -> dict:
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type":"application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return json.loads(resp.read(262144).decode())
    except urllib.error.HTTPError as error:
        # Deliberately don't expose provider errors or any credentials to visitors.
        raise RuntimeError(f"Provider returned HTTP {error.code}") from error
    except Exception as error:
        raise RuntimeError("Provider unavailable") from error


async def send_verification_email(email: str, code: str):
    if not mail_ready():
        raise RuntimeError("Email sender not configured")
    sender = os.environ["MAIL_FROM"]
    body = {
        "sender": {"name":"Huddle", "email":sender},
        "to": [{"email":email}],
        "subject": "Your Huddle verification code",
        "textContent": f"Your Huddle verification code is {code}. It expires in 10 minutes. Never share this code. If you did not request it, ignore this email.",
    }
    return await asyncio.to_thread(_post_json, "https://api.brevo.com/v3/smtp/email", body, {"api-key":os.environ["BREVO_API_KEY"]}, 18)


async def ask_ai(messages: list[dict]) -> str:
    if not text_ready():
        raise RuntimeError("AI text provider not configured")
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    payload = {
      "systemInstruction": {"parts": [{"text": "You are Huddle AI, an approachable learning assistant. Help with doubts, explanations, studying, writing, brainstorming and safe creative requests. Be concise, accurate and say when uncertain. Never imply you have read users' private chats. Avoid collecting personal information and follow age-appropriate safety norms."}]},
      "contents": [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text":m["body"][:2400]}]} for m in messages[-12:]],
      "generationConfig": {"maxOutputTokens": 950, "temperature": 0.65},
    }
    data = await asyncio.to_thread(_post_json, f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", payload, {"x-goog-api-key":os.environ["GEMINI_API_KEY"]}, 30)
    text = "\n".join(p.get("text","") for c in data.get("candidates", []) for p in c.get("content",{}).get("parts",[]) if p.get("text"))
    if not text:
        raise RuntimeError("AI could not produce a response")
    return text[:10000]


async def generate_ai_image(prompt: str) -> bytes:
    if not image_ready():
        raise RuntimeError("Image provider not configured")
    from huggingface_hub import InferenceClient
    from io import BytesIO
    from PIL import Image
    def _work():
        client = InferenceClient(api_key=os.environ["HF_TOKEN"], provider="fal-ai", timeout=55)
        img = client.text_to_image(prompt[:650], model=os.getenv("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell"), width=768, height=768)
        out = BytesIO()
        img.convert("RGB").save(out, format="JPEG", quality=84, optimize=True)
        return out.getvalue()
    return await asyncio.to_thread(_work)


def google_ready() -> bool:
    """Web OAuth client ID is safe to expose; no client secret is needed for GSI popup."""
    return bool(os.getenv("GOOGLE_CLIENT_ID", "").strip())


def verify_google_credential(credential: str) -> dict:
    """Cryptographically verify the JWT with Google's public signing keys.

    Do not accept a browser-supplied email, name, or subject independently.
    """
    if not google_ready():
        raise ValueError("Google sign-in is not configured")
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token
    claims = id_token.verify_oauth2_token(credential, Request(), os.environ["GOOGLE_CLIENT_ID"].strip())
    if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise ValueError("Invalid token issuer")
    if not claims.get("email_verified") or not claims.get("email") or not claims.get("sub"):
        raise ValueError("A verified Google email is required")
    if len(str(claims["sub"])) > 255:
        raise ValueError("Invalid account identifier")
    return {
        "sub": str(claims["sub"]),
        "email": str(claims["email"]).strip().lower(),
        "name": str(claims.get("name") or claims["email"].split("@")[0])[:60],
    }
