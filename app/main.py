"""Huddle: single-process FastAPI + SQLite + native WebSocket chat.

No cloud account, paid provider, or JavaScript build chain required.
Run: uvicorn app.main:app --reload
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import hmac
import time
import os
import re
import secrets
import sqlite3
import uuid
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from fastapi import Cookie, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .extras import mail_ready, text_ready, image_ready, google_ready, verify_google_credential, firebase_ready, firebase_web_config, verify_firebase_credential, send_verification_email, ask_ai, generate_ai_image
from .security import encrypt_text, decrypt_text
from .extensions import install_extensions

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
PH = PasswordHasher(time_cost=2, memory_cost=32768, parallelism=2)
COOKIE = "huddle_session"
TTL = timedelta(days=7)
HANDLES = re.compile(r"^[a-z0-9_]{3,22}$")
EMOJIS = {"❤️", "🔥", "😂", "👏", "👍", "🎉", "💡", "🚀"}


def escape_like(value: str) -> str:
    """Treat search text literally, not as SQL LIKE wildcard patterns."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def new_id():
    return uuid.uuid4().hex


def fail(code: int, message: str):
    raise HTTPException(code, message)


class RegisterBody(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    handle: str = Field(min_length=3, max_length=22)
    password: str = Field(min_length=8, max_length=128)
    email: str | None = Field(default=None, max_length=254)


class VerifyBody(BaseModel):
    ticket: str = Field(min_length=32, max_length=40)
    code: str = Field(pattern=r"^[0-9]{6}$")


class TicketBody(BaseModel):
    ticket: str = Field(min_length=32, max_length=40)


class AIRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2500)


class GoogleCredentialBody(BaseModel):
    credential: str = Field(min_length=30, max_length=9000)


class GoogleDiagnosticBody(BaseModel):
    stage: str = Field(min_length=2, max_length=32)
    code: str = Field(min_length=3, max_length=80)
    reason: str = Field(default="unknown", min_length=3, max_length=36)


class LoginBody(BaseModel):
    handle: str
    password: str


class ProfileBody(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    bio: str = Field(default="", max_length=160)


class DirectBody(BaseModel):
    user_id: str


class GroupBody(BaseModel):
    name: str = Field(min_length=3, max_length=64)
    description: str = Field(default="", max_length=200)
    member_ids: list[str] = Field(min_length=1, max_length=30)


class AddMembersBody(BaseModel):
    member_ids: list[str] = Field(min_length=1, max_length=30)


class MessageBody(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    client_nonce: str | None = Field(default=None, max_length=64)


class EditBody(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ReactionBody(BaseModel):
    emoji: str


class Database:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.init()

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=20000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def init(self):
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, handle TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL, bio TEXT NOT NULL DEFAULT '',
                password_hash TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('dm','group')),
                name TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
                dm_key TEXT UNIQUE, created_by TEXT NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS members (
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL DEFAULT 'member', joined_at TEXT NOT NULL,
                last_read_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(conversation_id,user_id)
            );
            CREATE INDEX IF NOT EXISTS idx_members_user ON members(user_id);
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                sender_id TEXT NOT NULL REFERENCES users(id), body TEXT NOT NULL,
                client_nonce TEXT, created_at TEXT NOT NULL, edited_at TEXT, deleted_at TEXT,
                UNIQUE(sender_id, client_nonce)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_conv_time ON messages(conversation_id,created_at DESC);
            CREATE TABLE IF NOT EXISTS reactions (
                message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                emoji TEXT NOT NULL, PRIMARY KEY(message_id,user_id,emoji)
            );
            """)
            db.executescript("""
            CREATE TABLE IF NOT EXISTS verified_emails (
                user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                email TEXT NOT NULL UNIQUE, verified_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pending_signups (
                ticket TEXT PRIMARY KEY, email TEXT NOT NULL, handle TEXT NOT NULL,
                name TEXT NOT NULL, password_hash TEXT NOT NULL,
                code_hash TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL, sent_at INTEGER NOT NULL, expires_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_pending_email ON pending_signups(email);
            CREATE TABLE IF NOT EXISTS google_accounts (
                google_sub TEXT PRIMARY KEY,
                user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                email TEXT NOT NULL, linked_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ai_messages (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                kind TEXT NOT NULL CHECK(kind IN ('text','image')),
                body TEXT NOT NULL, image_id TEXT, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ai_user_time ON ai_messages(user_id,created_at);
            """)
            db.execute("DELETE FROM pending_signups WHERE expires_at < ?", (int(time.time()),))
            db.execute("DELETE FROM sessions WHERE expires_at < ?", (now(),))


class Hub:
    def __init__(self):
        self.sockets: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, user_id: str, socket: WebSocket):
        await socket.accept()
        self.sockets[user_id].add(socket)

    def disconnect(self, user_id: str, socket: WebSocket):
        connections = self.sockets.get(user_id)
        if connections:
            connections.discard(socket)
            if not connections:
                self.sockets.pop(user_id, None)

    async def notify(self, user_ids, event: dict):
        for user_id in set(user_ids):
            for socket in list(self.sockets.get(user_id, ())):
                try:
                    await socket.send_json(event)
                except Exception:
                    self.disconnect(user_id, socket)

    async def close_all(self, user_id):
        for socket in list(self.sockets.get(user_id, ())):
            try:
                await socket.close(code=4401)
            except Exception:
                pass
            self.disconnect(user_id, socket)

    def online(self, user_id):
        return bool(self.sockets.get(user_id))


def create_app(database_path: str | None = None):
    db = Database(database_path or os.getenv("HUDDLE_DB", "./huddle.db"))
    hub = Hub()
    app = FastAPI(title="Huddle | Real-time campus chat", version="1.0.0", docs_url=None, redoc_url=None)
    app.state.db = db
    app.state.hub = hub
    app.mount("/assets", StaticFiles(directory=str(WEB)), name="assets")
    login_attempts: dict[str, deque] = defaultdict(deque)
    google_diagnostic_attempts: dict[str, deque] = defaultdict(deque)
    registration_attempts: dict[str, deque] = defaultdict(deque)
    message_attempts: dict[str, deque] = defaultdict(deque)
    ai_attempts: dict[str, deque] = defaultdict(deque)
    image_attempts: dict[str, deque] = defaultdict(deque)
    email_attempts: dict[str, deque] = defaultdict(deque)

    def normalize_email(email: str) -> str:
        email = (email or "").strip().lower()
        if len(email) > 254 or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+", email):
            fail(422, "Enter a valid email address")
        return email

    def otp_digest(ticket: str, code: str) -> str:
        return hashlib.sha256((ticket + ":" + code).encode()).hexdigest()


    def client_ip(request: Request) -> str:
        # Railway sets X-Real-IP at its edge. Avoid trusting a forged header in local mode.
        if os.getenv("RAILWAY_ENVIRONMENT"):
            address = request.headers.get("x-real-ip", "")
            if re.fullmatch(r"[0-9a-fA-F:.]{3,64}", address):
                return address
        return request.client.host if request.client else "unknown"

    def enforce_rate_limit(store: dict, key: str, max_events: int, window_seconds: int):
        """Low-overhead abuse protection for the deliberately single-worker pilot."""
        timestamp = datetime.now(timezone.utc).timestamp()
        events = store[key]
        while events and events[0] < timestamp - window_seconds:
            events.popleft()
        if len(events) >= max_events:
            fail(429, "Too many requests. Please try again later")
        events.append(timestamp)

    def public_user(row):
        if row is None:
            return None
        return {"id": row["id"], "handle": row["handle"], "name": row["name"], "bio": row["bio"]}

    def session_user(raw: str | None):
        if not raw:
            return None
        hashed = hashlib.sha256(raw.encode()).hexdigest()
        with db.connection() as cx:
            return cx.execute("""SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id
                WHERE s.token_hash=? AND s.expires_at>?""", (hashed, now())).fetchone()

    def require_user(request: Request):
        user = session_user(request.cookies.get(COOKIE))
        if not user:
            fail(401, "Please sign in to continue")
        return user

    def ensure_membership(cx, conversation_id: str, user_id: str):
        row = cx.execute("SELECT 1 FROM members WHERE conversation_id=? AND user_id=?", (conversation_id, user_id)).fetchone()
        if not row:
            fail(404, "Conversation not found")

    def member_ids(conversation_id):
        with db.connection() as cx:
            return [r["user_id"] for r in cx.execute("SELECT user_id FROM members WHERE conversation_id=?", (conversation_id,))]

    def serialize_message(cx, msg):
        attachment = cx.execute("""SELECT id,filename,content_type,byte_size FROM attachments WHERE message_id=?""",(msg["id"],)).fetchone()
        reactions = cx.execute("""SELECT emoji, COUNT(*) AS count, GROUP_CONCAT(user_id) AS users
              FROM reactions WHERE message_id=? GROUP BY emoji ORDER BY emoji""", (msg["id"],)).fetchall()
        readers = cx.execute("""SELECT user_id FROM members
            WHERE conversation_id=? AND user_id<>? AND last_read_at>=?""", (msg["conversation_id"], msg["sender_id"], msg["created_at"])).fetchall()
        return {
            "id": msg["id"], "conversation_id": msg["conversation_id"],
            "sender_id": msg["sender_id"], "body": "" if msg["deleted_at"] else decrypt_text(msg["body"]),
            "created_at": msg["created_at"], "edited_at": msg["edited_at"],
            "deleted_at": msg["deleted_at"], "seen_by": [r["user_id"] for r in readers],
            "attachments": [dict(attachment)] if attachment and not msg["deleted_at"] else [],
            "reactions": [{"emoji": r["emoji"], "count": r["count"], "users": r["users"].split(",")} for r in reactions]
        }

    def message_preview(body):
        """Short friendly previews for typed Huddle animated stickers."""
        if body.startswith("[[huddle-sticker:") and body.endswith("]]"):
            return "🎉 Animated sticker"
        return body

    def serialize_conversation(cx, conv, user_id):
        members = cx.execute("""SELECT u.id,u.handle,u.name,u.bio,m.role,m.last_read_at
            FROM members m JOIN users u ON u.id=m.user_id WHERE m.conversation_id=? ORDER BY u.name""", (conv["id"],)).fetchall()
        me = next((m for m in members if m["id"] == user_id), None)
        other = next((m for m in members if m["id"] != user_id), None)
        latest = cx.execute("""SELECT id,body,created_at,sender_id,deleted_at FROM messages
            WHERE conversation_id=? ORDER BY created_at DESC LIMIT 1""", (conv["id"],)).fetchone()
        unread = cx.execute("""SELECT COUNT(*) FROM messages WHERE conversation_id=? AND sender_id<>?
            AND created_at>? AND deleted_at IS NULL""", (conv["id"], user_id, me["last_read_at"] if me else "")).fetchone()[0]
        return {
            "id": conv["id"], "kind": conv["kind"],
            "name": other["name"] if conv["kind"] == "dm" and other else conv["name"],
            "description": conv["description"],
            "handle": other["handle"] if other and conv["kind"] == "dm" else "",
            "members": [{**public_user(m), "role": m["role"], "online": hub.online(m["id"])} for m in members],
            "unread": unread, "updated_at": conv["updated_at"],
            "last_message": ({"body": "Message deleted" if latest["deleted_at"] else message_preview(decrypt_text(latest["body"])),
                              "created_at": latest["created_at"], "sender_id": latest["sender_id"]} if latest else None)
        }

    async def send_conversation_update(conversation_id):
        for uid in member_ids(conversation_id):
            await hub.notify([uid], {"type": "conversation:refresh", "conversation_id": conversation_id})

    def create_session(response: Response, user_id: str):
        raw = secrets.token_urlsafe(36)
        expires = (datetime.now(timezone.utc) + TTL).isoformat(timespec="microseconds")
        with db.connection() as cx:
            cx.execute("INSERT INTO sessions VALUES(?,?,?)", (hashlib.sha256(raw.encode()).hexdigest(), user_id, expires))
        response.set_cookie(COOKIE, raw, max_age=int(TTL.total_seconds()), httponly=True,
                            secure=os.getenv("SECURE_COOKIES", "0") == "1", samesite="strict", path="/")

    def send_message(conv_id, user_id, body, nonce=None):
        body = body.strip()
        if not body or len(body) > 4000:
            fail(422, "Message must be 1–4000 characters")
        if nonce is not None and (len(nonce) > 64 or not nonce):
            fail(422, "Invalid client nonce")
        with db.connection() as cx:
            ensure_membership(cx, conv_id, user_id)
            if nonce:
                duplicate = cx.execute("SELECT * FROM messages WHERE sender_id=? AND client_nonce=?", (user_id, nonce)).fetchone()
                if duplicate:
                    if duplicate["conversation_id"] != conv_id:
                        fail(409, "Message token already used")
                    return serialize_message(cx, duplicate), False
            enforce_rate_limit(message_attempts, user_id, 30, 60)
            msg_id, ts = new_id(), now()
            cx.execute("INSERT INTO messages(id,conversation_id,sender_id,body,client_nonce,created_at) VALUES(?,?,?,?,?,?)",
                       (msg_id, conv_id, user_id, encrypt_text(body), nonce, ts))
            cx.execute("UPDATE conversations SET updated_at=? WHERE id=?", (ts, conv_id))
            msg = cx.execute("SELECT * FROM messages WHERE id=?", (msg_id,)).fetchone()
            return serialize_message(cx, msg), True

    @app.middleware("http")
    async def protection(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin:
                # Browsers sending cross-site cookies must not mutate state.
                target = urlparse(origin)
                if target.netloc.lower() != request.headers.get("host", "").lower():
                    return JSONResponse({"detail": "Cross-origin request blocked"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; object-src 'none'; "
            "frame-ancestors 'none'; form-action 'self'; "
            "script-src 'self' 'wasm-unsafe-eval' https://accounts.google.com https://www.gstatic.com https://apis.google.com https://cdn.jsdelivr.net; "
            "worker-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://accounts.google.com https://fonts.googleapis.com; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "frame-src https://accounts.google.com https://*.firebaseapp.com; "
            "img-src 'self' data: blob: https://accounts.google.com https://*.googleusercontent.com https://*.gstatic.com; "
            "media-src 'self' blob:; "
            "connect-src 'self' ws: wss: https://accounts.google.com https://apis.google.com https://identitytoolkit.googleapis.com https://securetoken.googleapis.com https://*.googleapis.com https://*.firebaseapp.com https://cdn.jsdelivr.net https://huggingface.co https://*.huggingface.co https://*.hf.co https://*.xethub.hf.co https://*.xethub.huggingface.co"
        )
        return response

    @app.get("/health")
    async def health():
        return {"ok": True, "service": "huddle"}

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(WEB / "index.html")

    @app.get("/api/config")
    async def public_config():
        return {"email_otp": mail_ready(), "ai_chat": text_ready(), "ai_image": image_ready(), "ai_local": True,
                "google_login": google_ready() or firebase_ready(),
                "google_client_id": os.environ.get("GOOGLE_CLIENT_ID", "").strip() if google_ready() else "",
                "firebase_config": firebase_web_config()}

    @app.post("/api/auth/register", status_code=201)
    async def register(payload: RegisterBody, response: Response, request: Request):
        enforce_rate_limit(registration_attempts,
                           client_ip(request), 30, 900)
        handle = payload.handle.strip().lower()
        name = payload.name.strip()
        if not HANDLES.fullmatch(handle):
            fail(422, "Username must use 3–22 letters (a-z), digits (0-9), or underscores (_), without spaces or @ signs.")
        if len(name) < 2:
            fail(422, "Display name must have at least 2 characters.")
        if mail_ready():
            if not payload.email:
                fail(422, "Email address is required for verification")
            email = normalize_email(payload.email)
            enforce_rate_limit(email_attempts, "signup:" + email, 4, 3600)
            ticket, code, ts = new_id(), f"{secrets.randbelow(1000000):06d}", int(time.time())
            with db.connection() as cx:
                if cx.execute("SELECT 1 FROM users WHERE handle=?", (handle,)).fetchone():
                    fail(409, "That username is already taken")
                if cx.execute("SELECT 1 FROM verified_emails WHERE email=?", (email,)).fetchone():
                    fail(409, "This email is already registered")
                cx.execute("DELETE FROM pending_signups WHERE email=? OR handle=?", (email, handle))
                cx.execute("""INSERT INTO pending_signups(ticket,email,handle,name,password_hash,code_hash,created_at,sent_at,expires_at)
                    VALUES(?,?,?,?,?,?,?,?,?)""", (ticket,email,handle,name,PH.hash(payload.password),otp_digest(ticket,code),ts,ts,ts+600))
            try:
                await send_verification_email(email, code)
            except Exception:
                with db.connection() as cx:
                    cx.execute("DELETE FROM pending_signups WHERE ticket=?", (ticket,))
                fail(503, "Verification email could not be sent. Try again later")
            response.status_code = 202
            return {"requires_verification": True, "ticket":ticket, "email_hint":email[:2]+"***@"+email.split("@")[-1]}
        uid = new_id()
        try:
            with db.connection() as cx:
                cx.execute("INSERT INTO users(id,handle,name,password_hash,created_at) VALUES(?,?,?,?,?)",
                           (uid, handle, name, PH.hash(payload.password), now()))
        except sqlite3.IntegrityError:
            fail(409, "That username is already taken. Please choose another one.")
        create_session(response, uid)
        with db.connection() as cx:
            return {"user": public_user(cx.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())}

    @app.post("/api/auth/verify")
    async def verify_otp(payload: VerifyBody, response: Response, request: Request):
        enforce_rate_limit(email_attempts, "verify-ip:" + (client_ip(request)), 25, 900)
        with db.connection() as cx:
            row = cx.execute("SELECT * FROM pending_signups WHERE ticket=?", (payload.ticket,)).fetchone()
            if not row or row["expires_at"] < int(time.time()):
                fail(410, "Verification code expired. Please register again")
            if row["attempts"] >= 5:
                fail(429, "Too many incorrect codes. Register again")
            correct = hmac.compare_digest(row["code_hash"], otp_digest(payload.ticket, payload.code))
            if not correct:
                cx.execute("UPDATE pending_signups SET attempts=attempts+1 WHERE ticket=?", (payload.ticket,))
        if not correct:
            fail(422, "Incorrect verification code")
        with db.connection() as cx:
            # Re-check after the failed-attempt counter is committed, even for concurrent requests.
            row = cx.execute("SELECT * FROM pending_signups WHERE ticket=?", (payload.ticket,)).fetchone()
            if not row or row["expires_at"]<int(time.time()) or row["attempts"]>=5:
                fail(410,"Verification has expired or too many attempts")
            uid = new_id()
            try:
                cx.execute("INSERT INTO users(id,handle,name,password_hash,created_at) VALUES(?,?,?,?,?)",
                           (uid,row["handle"],row["name"],row["password_hash"],now()))
                cx.execute("INSERT INTO verified_emails(user_id,email,verified_at) VALUES(?,?,?)",(uid,row["email"],now()))
            except sqlite3.IntegrityError:
                fail(409, "Account or email already registered. Please sign in or use another address")
            cx.execute("DELETE FROM pending_signups WHERE ticket=?", (payload.ticket,))
        create_session(response,uid)
        with db.connection() as cx:
            return {"user":public_user(cx.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone())}

    @app.post("/api/auth/resend")
    async def resend_otp(payload: TicketBody, request: Request):
        if not mail_ready():
            fail(503, "Email verification is not configured")
        enforce_rate_limit(email_attempts, "resend-ip:" + (client_ip(request)), 15, 3600)
        ts, code = int(time.time()),f"{secrets.randbelow(1000000):06d}"
        with db.connection() as cx:
            row = cx.execute("SELECT * FROM pending_signups WHERE ticket=?",(payload.ticket,)).fetchone()
            if not row or row["expires_at"]<ts:
                fail(410, "Code expired. Register again")
            if ts-row["sent_at"]<60:
                fail(429, "Wait 60 seconds before requesting another code")
            cx.execute("UPDATE pending_signups SET code_hash=?,sent_at=?,expires_at=?,attempts=0 WHERE ticket=?",
                       (otp_digest(payload.ticket,code),ts,ts+600,payload.ticket))
        try:
            await send_verification_email(row["email"],code)
        except Exception:
            fail(503, "Email service unavailable. Try again later")
        return {"ok":True}

    async def google_identity(credential: str, request: Request):
        if not (firebase_ready() or google_ready()):
            fail(503, "Google sign-in is not configured yet")
        # Popup credential stays in our own first-party JavaScript. Cross-origin
        # forms cannot set this custom header; do not accept a GIS redirect POST.
        if request.headers.get("x-huddle-client") != "web":
            fail(403, "Google sign-in requires the Huddle website")
        enforce_rate_limit(login_attempts, "google:" + client_ip(request), 25, 900)
        try:
            verifier = verify_google_credential if google_ready() else verify_firebase_credential
            info = await asyncio.to_thread(verifier, credential)
        except Exception:
            fail(401, "Google couldn't verify this sign-in. Please try again")
        return info

    @app.post("/api/diagnostics/google")
    async def google_diagnostics(payload: GoogleDiagnosticBody, request: Request):
        # Accept only standardized error codes; never log identities, tokens or emails.
        enforce_rate_limit(google_diagnostic_attempts, client_ip(request), 8, 600)
        if (not re.fullmatch(r"[a-z0-9_-]{2,32}", payload.stage)
            or not re.fullmatch(r"auth/[a-z0-9-]{3,74}", payload.code)
            or not re.fullmatch(r"[a-z_]{3,36}", payload.reason)):
            fail(422, "Invalid diagnostic event")
        logging.getLogger("uvicorn.error").warning(
            "Huddle Google sign-in stage=%s error_code=%s reason=%s",
            payload.stage, payload.code, payload.reason)
        return {"ok": True}

    @app.post("/api/auth/google")
    async def google_login(payload: GoogleCredentialBody, response: Response, request: Request):
        identity = await google_identity(payload.credential, request)
        with db.connection() as cx:
            linked = cx.execute("SELECT user_id FROM google_accounts WHERE google_sub=?", (identity["sub"],)).fetchone()
            if linked:
                user = cx.execute("SELECT * FROM users WHERE id=?", (linked["user_id"],)).fetchone()
                if user is None:
                    fail(409, "Linked user is unavailable")
            else:
                # Never take over an existing local account merely because its email
                # resembles the claim. Existing members can link from their profile.
                owner = cx.execute("SELECT user_id FROM verified_emails WHERE email=?", (identity["email"],)).fetchone()
                if owner:
                    fail(409, "This email already belongs to a Huddle account. Sign in with your password and link Google under Profile.")
                handle_base = re.sub(r"[^a-z0-9_]", "_", identity["email"].split("@")[0])[:16].strip("_")
                if len(handle_base) < 3:
                    handle_base = "google_user"
                handle = handle_base
                while cx.execute("SELECT 1 FROM users WHERE handle=?", (handle,)).fetchone():
                    handle = handle_base + "_" + secrets.token_hex(3)
                uid = new_id()
                cx.execute("INSERT INTO users(id,handle,name,password_hash,created_at) VALUES(?,?,?,?,?)",
                           (uid,handle,identity["name"],PH.hash(secrets.token_urlsafe(48)),now()))
                cx.execute("INSERT INTO verified_emails(user_id,email,verified_at) VALUES(?,?,?)", (uid,identity["email"],now()))
                cx.execute("INSERT INTO google_accounts(google_sub,user_id,email,linked_at) VALUES(?,?,?,?)",
                           (identity["sub"],uid,identity["email"],now()))
                user = cx.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        create_session(response, user["id"])
        return {"user":public_user(user)}

    @app.post("/api/auth/google/link")
    async def google_link(payload: GoogleCredentialBody, request: Request):
        user = require_user(request)
        identity = await google_identity(payload.credential, request)
        with db.connection() as cx:
            existing = cx.execute("SELECT user_id FROM google_accounts WHERE google_sub=?", (identity["sub"],)).fetchone()
            if existing:
                if existing["user_id"] == user["id"]:
                    return {"ok":True,"already_linked":True}
                fail(409, "That Google account is already linked to another Huddle account")
            already = cx.execute("SELECT google_sub FROM google_accounts WHERE user_id=?", (user["id"],)).fetchone()
            if already:
                fail(409, "Your Huddle account already has a linked Google account")
            owner = cx.execute("SELECT user_id FROM verified_emails WHERE email=?", (identity["email"],)).fetchone()
            if owner and owner["user_id"] != user["id"]:
                fail(409, "That email belongs to another account")
            cx.execute("INSERT INTO google_accounts(google_sub,user_id,email,linked_at) VALUES(?,?,?,?)",
                       (identity["sub"],user["id"],identity["email"],now()))
            if not owner:
                # If the user already had a verified email, do not overwrite it.
                existing_email = cx.execute("SELECT email FROM verified_emails WHERE user_id=?", (user["id"],)).fetchone()
                if not existing_email:
                    cx.execute("INSERT INTO verified_emails(user_id,email,verified_at) VALUES(?,?,?)",
                               (user["id"],identity["email"],now()))
        return {"ok":True,"already_linked":False}

    @app.post("/api/auth/login")
    async def login(payload: LoginBody, response: Response, request: Request):
        ip = client_ip(request)
        attempts = login_attempts[ip]
        timestamp = datetime.now(timezone.utc).timestamp()
        while attempts and attempts[0] < timestamp - 300:
            attempts.popleft()
        if len(attempts) >= 20:
            fail(429, "Too many sign-in attempts. Try again later")
        with db.connection() as cx:
            user = cx.execute("SELECT * FROM users WHERE handle=?", (payload.handle.strip().lower(),)).fetchone()
        try:
            valid = bool(user) and PH.verify(user["password_hash"], payload.password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            valid = False
        if not valid:
            attempts.append(timestamp)
            fail(401, "Invalid handle or password")
        attempts.clear()
        create_session(response, user["id"])
        return {"user": public_user(user)}

    @app.post("/api/auth/logout")
    async def logout(request: Request, response: Response):
        raw = request.cookies.get(COOKIE)
        user = session_user(raw)
        if raw:
            with db.connection() as cx:
                cx.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(raw.encode()).hexdigest(),))
        response.delete_cookie(COOKIE, path="/")
        if user:
            await hub.close_all(user["id"])
        return {"ok": True}

    @app.get("/api/me")
    async def me(request: Request):
        return {"user": public_user(require_user(request))}

    @app.patch("/api/me")
    async def profile(payload: ProfileBody, request: Request):
        user = require_user(request)
        name = payload.name.strip()
        if len(name) < 2:
            fail(422, "Name must be at least 2 characters")
        with db.connection() as cx:
            cx.execute("UPDATE users SET name=?,bio=? WHERE id=?", (name, payload.bio.strip(), user["id"]))
            updated = public_user(cx.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone())
        await hub.notify(list(hub.sockets), {"type": "user:refresh", "user_id": user["id"]})
        return {"user": updated}

    @app.get("/api/users")
    async def users(request: Request, search: str = ""):
        user = require_user(request)
        search = search.strip().lower()[:60]
        with db.connection() as cx:
            needle = f"%{escape_like(search)}%"
            found = cx.execute("""SELECT * FROM users WHERE id<>? AND
                (LOWER(name) LIKE ? ESCAPE '\\' OR handle LIKE ? ESCAPE '\\')
                ORDER BY name LIMIT 40""", (user["id"], needle, needle)).fetchall()
        return {"users": [{**public_user(u), "online": hub.online(u["id"])} for u in found]}

    @app.get("/api/conversations")
    async def conversations(request: Request):
        user = require_user(request)
        with db.connection() as cx:
            rows = cx.execute("""SELECT c.* FROM conversations c JOIN members m ON m.conversation_id=c.id
                WHERE m.user_id=? ORDER BY c.updated_at DESC""", (user["id"],)).fetchall()
            return {"conversations": [serialize_conversation(cx, row, user["id"]) for row in rows]}

    @app.post("/api/conversations/direct")
    async def direct(payload: DirectBody, request: Request):
        user = require_user(request)
        if payload.user_id == user["id"]:
            fail(422, "You cannot start a conversation with yourself")
        a, b = sorted([user["id"], payload.user_id])
        key = f"{a}:{b}"
        created = False
        with db.connection() as cx:
            other = cx.execute("SELECT id FROM users WHERE id=?", (payload.user_id,)).fetchone()
            if not other:
                fail(404, "User not found")
            conv = cx.execute("SELECT * FROM conversations WHERE dm_key=?", (key,)).fetchone()
            if conv is None:
                ts, cid = now(), new_id()
                try:
                    cx.execute("""INSERT INTO conversations(id,kind,dm_key,created_by,created_at,updated_at)
                        VALUES(?,'dm',?,?,?,?)""", (cid, key, user["id"], ts, ts))
                    cx.executemany("INSERT INTO members(conversation_id,user_id,joined_at) VALUES(?,?,?)",
                                   [(cid, uid, ts) for uid in (a, b)])
                    created = True
                except sqlite3.IntegrityError:
                    pass
                conv = cx.execute("SELECT * FROM conversations WHERE dm_key=?", (key,)).fetchone()
            result = serialize_conversation(cx, conv, user["id"])
        if created:
            await send_conversation_update(result["id"])
        return {"conversation": result}

    @app.post("/api/conversations/group", status_code=201)
    async def group(payload: GroupBody, request: Request):
        user = require_user(request)
        name = payload.name.strip()
        if len(name) < 3:
            fail(422, "Circle name must be at least 3 characters")
        selected = set(payload.member_ids) - {user["id"]}
        if not selected or len(selected) > 30:
            fail(422, "Select 1–30 other members")
        with db.connection() as cx:
            valid = cx.execute(f"SELECT id FROM users WHERE id IN ({','.join('?' for _ in selected)})", tuple(selected)).fetchall()
            if len(valid) != len(selected):
                fail(422, "One or more users do not exist")
            cid, ts = new_id(), now()
            cx.execute("""INSERT INTO conversations(id,kind,name,description,created_by,created_at,updated_at)
                VALUES(?,'group',?,?,?,?,?)""", (cid, name, payload.description.strip(), user["id"], ts, ts))
            cx.executemany("INSERT INTO members(conversation_id,user_id,role,joined_at) VALUES(?,?,?,?)",
                           [(cid, uid, "admin" if uid == user["id"] else "member", ts) for uid in selected | {user["id"]}])
            result = serialize_conversation(cx, cx.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone(), user["id"])
        await send_conversation_update(cid)
        return {"conversation": result}

    @app.post("/api/conversations/{conversation_id}/members")
    async def invite_members(conversation_id: str, payload: AddMembersBody, request: Request):
        user = require_user(request)
        selected = set(payload.member_ids) - {user["id"]}
        if not selected:
            fail(422, "Select at least one person")
        with db.connection() as cx:
            conv = cx.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
            if not conv or conv["kind"] != "group":
                fail(404, "Circle not found")
            role = cx.execute("SELECT role FROM members WHERE conversation_id=? AND user_id=?",
                              (conversation_id, user["id"])).fetchone()
            if not role or role["role"] != "admin":
                fail(403, "Only circle administrators can invite members")
            existing = {r["user_id"] for r in cx.execute("SELECT user_id FROM members WHERE conversation_id=?", (conversation_id,))}
            additions = selected - existing
            if len(existing) + len(additions) > 31:
                fail(422, "A circle supports up to 31 members")
            if additions:
                valid = cx.execute(f"SELECT id FROM users WHERE id IN ({','.join('?' for _ in additions)})", tuple(additions)).fetchall()
                if len(valid) != len(additions):
                    fail(422, "One or more users do not exist")
                ts = now()
                cx.executemany("INSERT INTO members(conversation_id,user_id,joined_at) VALUES(?,?,?)",
                               [(conversation_id, uid, ts) for uid in additions])
                cx.execute("UPDATE conversations SET updated_at=? WHERE id=?", (ts, conversation_id))
        await send_conversation_update(conversation_id)
        return {"ok": True, "added": len(additions)}

    @app.get("/api/conversations/{conversation_id}/messages")
    async def get_messages(conversation_id: str, request: Request, before: str | None = None):
        user = require_user(request)
        with db.connection() as cx:
            ensure_membership(cx, conversation_id, user["id"])
            args = [conversation_id]
            cond = ""
            if before:
                anchor = cx.execute("SELECT created_at, id FROM messages WHERE id=? AND conversation_id=?", (before, conversation_id)).fetchone()
                if not anchor:
                    fail(404, "Message cursor not found")
                cond = "AND (created_at < ? OR (created_at = ? AND id < ?))"
                args.extend([anchor["created_at"], anchor["created_at"], anchor["id"]])
            # Fetch one extra message to determine accurately whether an older page exists.
            rows = cx.execute(f"""SELECT * FROM messages WHERE conversation_id=? {cond}
                ORDER BY created_at DESC, id DESC LIMIT 61""", args).fetchall()
            has_more = len(rows) > 60
            items = [serialize_message(cx, row) for row in reversed(rows[:60])]
            return {"messages": items, "has_more": has_more}

    @app.post("/api/conversations/{conversation_id}/messages", status_code=201)
    async def post_message(conversation_id: str, payload: MessageBody, request: Request):
        user = require_user(request)
        result, created = send_message(conversation_id, user["id"], payload.body, payload.client_nonce)
        if created:
            await hub.notify(member_ids(conversation_id), {"type": "message:new", "message": result})
        return {"message": result, "created": created}

    @app.post("/api/conversations/{conversation_id}/read")
    async def mark_read(conversation_id: str, request: Request):
        user = require_user(request)
        with db.connection() as cx:
            ensure_membership(cx, conversation_id, user["id"])
            timestamp = now()
            cx.execute("UPDATE members SET last_read_at=? WHERE conversation_id=? AND user_id=?",
                       (timestamp, conversation_id, user["id"]))
        await hub.notify(member_ids(conversation_id), {"type": "read:update", "conversation_id": conversation_id,
                                                        "user_id": user["id"], "read_at": timestamp})
        return {"ok": True}

    @app.patch("/api/messages/{message_id}")
    async def edit_message(message_id: str, payload: EditBody, request: Request):
        user = require_user(request)
        content = payload.body.strip()
        if not content:
            fail(422, "Message cannot be empty")
        with db.connection() as cx:
            msg = cx.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
            if not msg or msg["sender_id"] != user["id"] or msg["deleted_at"]:
                fail(404, "Your message was not found")
            cx.execute("UPDATE messages SET body=?, edited_at=? WHERE id=?", (encrypt_text(content), now(), message_id))
            new_msg = serialize_message(cx, cx.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone())
        await hub.notify(member_ids(new_msg["conversation_id"]), {"type": "message:update", "message": new_msg})
        return {"message": new_msg}

    @app.delete("/api/messages/{message_id}")
    async def delete_message(message_id: str, request: Request):
        user = require_user(request)
        with db.connection() as cx:
            msg = cx.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
            if not msg or msg["sender_id"] != user["id"]:
                fail(404, "Your message was not found")
            cx.execute("UPDATE messages SET body='',deleted_at=COALESCE(deleted_at,?) WHERE id=?", (now(), message_id))
            cx.execute("DELETE FROM reactions WHERE message_id=?", (message_id,))
            updated = serialize_message(cx, cx.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone())
        await hub.notify(member_ids(updated["conversation_id"]), {"type": "message:update", "message": updated})
        return {"message": updated}

    @app.post("/api/messages/{message_id}/reactions")
    async def toggle_reaction(message_id: str, payload: ReactionBody, request: Request):
        user = require_user(request)
        if payload.emoji not in EMOJIS:
            fail(422, "Unsupported reaction")
        with db.connection() as cx:
            msg = cx.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
            if not msg or msg["deleted_at"]:
                fail(404, "Message not found")
            ensure_membership(cx, msg["conversation_id"], user["id"])
            exists = cx.execute("SELECT 1 FROM reactions WHERE message_id=? AND user_id=? AND emoji=?",
                                (message_id, user["id"], payload.emoji)).fetchone()
            if exists:
                cx.execute("DELETE FROM reactions WHERE message_id=? AND user_id=? AND emoji=?", (message_id, user["id"], payload.emoji))
            else:
                cx.execute("INSERT INTO reactions VALUES(?,?,?)", (message_id, user["id"], payload.emoji))
            updated = serialize_message(cx, msg)
        await hub.notify(member_ids(msg["conversation_id"]), {"type": "message:update", "message": updated})
        return {"message": updated}

    @app.get("/api/search/messages")
    async def search_messages(request: Request, q: str = "", conversation_id: str | None = None):
        user = require_user(request)
        q = q.strip()[:100]
        if len(q) < 2:
            return {"results": []}
        with db.connection() as cx:
            cond = ""
            args = [user["id"]]
            if conversation_id:
                ensure_membership(cx, conversation_id, user["id"])
                cond = " AND ms.conversation_id=?"
                args.append(conversation_id)
            # Search a bounded recent history after decryption; SQL LIKE cannot
            # match Fernet ciphertext. Membership is enforced in the JOIN.
            rows = cx.execute(f"""SELECT ms.id,ms.conversation_id,ms.body,ms.created_at,
                u.name AS sender_name, c.kind,c.name AS group_name
                FROM messages ms JOIN members mem ON mem.conversation_id=ms.conversation_id
                JOIN users u ON u.id=ms.sender_id JOIN conversations c ON c.id=ms.conversation_id
                WHERE mem.user_id=? AND ms.deleted_at IS NULL {cond}
                ORDER BY ms.created_at DESC LIMIT 5000""", args).fetchall()
        matches = []
        for row in rows:
            body = decrypt_text(row["body"])
            if q.casefold() in body.casefold():
                entry = dict(row)
                entry["body"] = body
                matches.append(entry)
                if len(matches) >= 30: break
        return {"results": matches}

    @app.get("/api/ai/history")
    async def ai_history(request: Request):
        user = require_user(request)
        with db.connection() as cx:
            rows = cx.execute("SELECT id,role,kind,body,image_id,created_at FROM ai_messages WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT 60", (user["id"],)).fetchall()
        return {"messages": [dict(r) for r in reversed(rows)], "enabled":text_ready(), "images_enabled":image_ready()}

    def ai_save(user_id, role, kind, body, image_id=None):
        mid = new_id()
        with db.connection() as cx:
            cx.execute("INSERT INTO ai_messages(id,user_id,role,kind,body,image_id,created_at) VALUES(?,?,?,?,?,?,?)", (mid,user_id,role,kind,body,image_id,now()))
            cx.execute("""DELETE FROM ai_messages WHERE user_id=? AND id NOT IN
              (SELECT id FROM ai_messages WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT 150)""",(user_id,user_id))
        return {"id":mid,"role":role,"kind":kind,"body":body,"image_id":image_id}

    @app.post("/api/ai/chat")
    async def ai_chat(payload: AIRequest, request: Request):
        user = require_user(request)
        if not text_ready():
            fail(503, "AI chat is not configured yet. The site owner needs to connect a text AI provider")
        enforce_rate_limit(ai_attempts,user["id"],20,3600)
        prompt = payload.prompt.strip()
        if len(prompt)<2: fail(422,"Please write a longer question")
        with db.connection() as cx:
            history = list(reversed([dict(r) for r in cx.execute("SELECT role,body FROM ai_messages WHERE user_id=? AND kind='text' ORDER BY created_at DESC,id DESC LIMIT 10", (user["id"],)).fetchall()]))
        try:
            answer = await ask_ai(history + [{"role":"user","body":prompt}])
        except Exception:
            fail(503, "AI is currently unavailable or its free limit has been reached")
        ai_save(user["id"],"user","text",prompt)
        reply = ai_save(user["id"],"assistant","text",answer)
        return {"reply":reply}

    @app.post("/api/ai/image")
    async def ai_image(payload: AIRequest, request: Request):
        user = require_user(request)
        if not image_ready():
            fail(503, "Image generation is unavailable until an image provider is configured")
        enforce_rate_limit(image_attempts,user["id"],2,86400)
        with db.connection() as cx:
            today=now()[:10]
            if cx.execute("SELECT COUNT(*) FROM ai_messages WHERE user_id=? AND kind='image' AND created_at>=?",(user["id"],today)).fetchone()[0]>=2:
                fail(429,"Daily image limit reached to protect free credits")
        prompt = payload.prompt.strip()
        if len(prompt)<5:fail(422,"Describe the image in a little more detail")
        try:
            data = await generate_ai_image(prompt)
        except Exception:
            fail(503,"Image provider unavailable or free credits exhausted")
        if not data or len(data)>4_000_000:fail(503,"Image provider returned an unsupported result")
        image_id=new_id()
        image_dir=Path(os.getenv("HUDDLE_DB", "/data/huddle.db")).resolve().parent / "ai_images"
        image_dir.mkdir(parents=True,exist_ok=True)
        (image_dir / (image_id+".jpg")).write_bytes(data)
        ai_save(user["id"],"user","text","Generate an image: "+prompt)
        reply=ai_save(user["id"],"assistant","image",prompt,image_id)
        return {"reply":reply}

    @app.get("/api/ai/image/{image_id}")
    async def ai_get_image(image_id: str, request: Request):
        user=require_user(request)
        if not re.fullmatch(r"[a-f0-9]{32}",image_id):fail(404,"Image not found")
        with db.connection() as cx:
            row=cx.execute("SELECT 1 FROM ai_messages WHERE user_id=? AND image_id=?",(user["id"],image_id)).fetchone()
        if not row:fail(404,"Image not found")
        path=Path(os.getenv("HUDDLE_DB", "/data/huddle.db")).resolve().parent / "ai_images" / (image_id+".jpg")
        if not path.exists():fail(404,"Image not found")
        return FileResponse(path,media_type="image/jpeg",headers={"Cache-Control":"private, max-age=3600"})

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        origin = ws.headers.get("origin")
        if origin and urlparse(origin).netloc.lower() != ws.headers.get("host", "").lower():
            await ws.close(code=4403)
            return
        user = session_user(ws.cookies.get(COOKIE))
        if not user:
            await ws.close(code=4401)
            return
        uid = user["id"]
        session_token = ws.cookies.get(COOKIE)
        was_online = hub.online(uid)
        await hub.connect(uid, ws)
        await ws.send_json({"type": "hello", "user_id": uid})
        if not was_online:
            await hub.notify(list(hub.sockets), {"type": "presence:update", "user_id": uid, "online": True})
        try:
            while True:
                data = await ws.receive_json()
                if not session_user(session_token):
                    await ws.close(code=4401)
                    break
                kind = data.get("type") if isinstance(data, dict) else None
                if kind == "ping":
                    await ws.send_json({"type": "pong"})
                elif kind == "typing":
                    cid = str(data.get("conversation_id", ""))
                    with db.connection() as cx:
                        allowed = cx.execute("SELECT 1 FROM members WHERE user_id=? AND conversation_id=?", (uid, cid)).fetchone()
                    if allowed:
                        await hub.notify([x for x in member_ids(cid) if x != uid],
                                         {"type": "typing:update", "conversation_id": cid, "user_id": uid,
                                          "typing": data.get("typing") is True})
                elif kind == "message:send":
                    try:
                        cid = str(data.get("conversation_id", ""))
                        result, created = send_message(cid, uid, str(data.get("body", "")), data.get("nonce"))
                        if created:
                            await hub.notify(member_ids(cid), {"type": "message:new", "message": result})
                        await ws.send_json({"type": "message:ack", "nonce": data.get("nonce"), "message_id": result["id"]})
                    except HTTPException as exc:
                        await ws.send_json({"type": "error", "detail": exc.detail, "nonce": data.get("nonce")})
                else:
                    await ws.send_json({"type": "error", "detail": "Unknown event"})
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            hub.disconnect(uid, ws)
            if not hub.online(uid):
                await hub.notify(list(hub.sockets), {"type": "presence:update", "user_id": uid, "online": False})

    install_extensions(app, db, hub, require_user, serialize_message, send_message, member_ids, ensure_membership, now, new_id)
    # Lazy migration of legacy plaintext message records after installing a stable
    # Fernet key. Existing conversation text remains readable; new writes encrypt.
    if os.getenv("HUDDLE_MESSAGE_KEY"):
        with db.connection() as cx:
            legacy=cx.execute("SELECT id,body FROM messages WHERE body<>'' AND body NOT LIKE 'huddle.enc.v1:%'").fetchall()
            for row in legacy:
                cx.execute("UPDATE messages SET body=? WHERE id=?",(encrypt_text(row["body"]),row["id"]))
    if os.getenv("SEED_DEMO", "0") == "1":
        seed_demo(db)
    return app


def seed_demo(db: Database):
    """Idempotent sample people + conversation, opt-in only."""
    sample = [
        ("aarya", "Aarya Sharma", "Design lead · campus creator"),
        ("kabir", "Kabir Mehta", "Building things that matter"),
        ("meera", "Meera Rao", "Always up for a brainstorm"),
    ]
    with db.connection() as cx:
        if cx.execute("SELECT 1 FROM users WHERE handle='aarya'").fetchone():
            return
        ids = {}
        for handle, name, bio in sample:
            uid = new_id()
            ids[handle] = uid
            cx.execute("INSERT INTO users(id,handle,name,bio,password_hash,created_at) VALUES(?,?,?,?,?,?)",
                       (uid, handle, name, bio, PH.hash("DemoPass123!"), now()))
        cid, ts = new_id(), now()
        cx.execute("INSERT INTO conversations(id,kind,name,description,created_by,created_at,updated_at) VALUES(?,'group',?,?,?,?,?)",
                   (cid, "First Commit Builders", "Hackathon ideas, late-night debugging & team wins", ids["aarya"], ts, ts))
        for uid in ids.values():
            cx.execute("INSERT INTO members(conversation_id,user_id,joined_at) VALUES(?,?,?)", (cid, uid, ts))
        for handle, body in [
            ("aarya", "Welcome to First Commit Builders! 🌱 Let's ship something great."),
            ("kabir", "WebSockets are connected, design is looking crisp ✨"),
            ("meera", "Anyone up for a quick brainstorming session? 🚀")
        ]:
            cx.execute("INSERT INTO messages(id,conversation_id,sender_id,body,created_at) VALUES(?,?,?,?,?)",
                       (new_id(), cid, ids[handle], body, now()))


app = create_app()
