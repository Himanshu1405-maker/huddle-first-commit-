"""Email-only password recovery with generic responses and single-use hashed tokens.

Requires BREVO_API_KEY + verified MAIL_FROM. Does not bypass Google authentication.
"""
import asyncio, hashlib, hmac, os, re, secrets, time
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field
from .extras import mail_ready, _post_json


class ResetStart(BaseModel):
    email: str = Field(min_length=4,max_length=254)

class ResetComplete(BaseModel):
    ticket: str = Field(min_length=32,max_length=80)
    code: str = Field(pattern=r"^[0-9]{8}$")
    password: str = Field(min_length=8,max_length=128)


def install_recovery(app,db,PH,now):
    with db.connection() as cx:
        cx.executescript("""
        CREATE TABLE IF NOT EXISTS password_resets(
            ticket TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pwresets_user ON password_resets(user_id);
        """)
    generic="If that address is linked to a Huddle account, a recovery code has been emailed."
    @app.post("/api/auth/recover")
    async def start_reset(payload:ResetStart, request:Request):
        if not mail_ready():
            raise HTTPException(503,"Password recovery requires a verified email sender. Contact the app owner.")
        email=payload.email.strip().lower()
        if not re.fullmatch(r"[^\s@]{1,100}@[^\s@]{1,130}\.[^\s@]{2,20}",email):
            raise HTTPException(422,"Enter a valid email address")
        # Throttle by email without disclosing whether the account exists.
        with db.connection() as cx:
            cx.execute("DELETE FROM password_resets WHERE expires_at<?",(now(),))
            found=cx.execute("""SELECT u.id FROM users u JOIN verified_emails ve ON ve.user_id=u.id
                WHERE ve.email=?""",(email,)).fetchone()
            if not found:return {"message":generic,"requires_code":True,"ticket":secrets.token_hex(24)}
            recent=cx.execute("""SELECT count(*) AS count FROM password_resets WHERE user_id=?
                AND created_at>?""",(found["id"],(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat())).fetchone()
            if recent["count"]>=4:return {"message":generic,"requires_code":True,"ticket":secrets.token_hex(24)}
            ticket=secrets.token_hex(24)
            code=f"{secrets.randbelow(100000000):08d}"
            digest=hashlib.sha256((ticket+':'+code).encode()).hexdigest()
            expires=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()
            cx.execute("""INSERT INTO password_resets(ticket,user_id,code_hash,expires_at,created_at)
                VALUES(?,?,?,?,?)""",(ticket,found["id"],digest,expires,now()))
        text="Your Huddle password reset code is "+code+". It expires in 10 minutes. If you did not request it, ignore this email."
        outgoing={"sender":{"name":"Huddle","email":os.environ["MAIL_FROM"]},
                  "to":[{"email":email}],"subject":"Your Huddle password reset code",
                  "textContent":text}
        try:
            await asyncio.to_thread(_post_json,"https://api.brevo.com/v3/smtp/email",
                                    outgoing,{"api-key":os.environ["BREVO_API_KEY"]},18)
        except Exception:
            with db.connection() as cx:
                cx.execute("DELETE FROM password_resets WHERE ticket=?",(ticket,))
            raise HTTPException(503,"Email delivery unavailable. Try again later.")
        return {"message":generic,"requires_code":True,"ticket":ticket}

    @app.post("/api/auth/recover/finish")
    async def finish_reset(payload:ResetComplete,request:Request):
        # Ticket is random and the code is hashed. No password hint or raw code in logs.
        with db.connection() as cx:
            row=cx.execute("SELECT * FROM password_resets WHERE ticket=?",(payload.ticket,)).fetchone()
            if not row or row["expires_at"]<=now() or row["attempts"]>=5:
                raise HTTPException(400,"Recovery code expired or unavailable")
            cx.execute("UPDATE password_resets SET attempts=attempts+1 WHERE ticket=?",(payload.ticket,))
            received=hashlib.sha256((payload.ticket+':'+payload.code).encode()).hexdigest()
            if not hmac.compare_digest(received,row["code_hash"]):
                raise HTTPException(400,"Incorrect code")
            cx.execute("UPDATE users SET password_hash=? WHERE id=?",
                       (PH.hash(payload.password),row["user_id"]))
            cx.execute("DELETE FROM sessions WHERE user_id=?",(row["user_id"],))
            cx.execute("DELETE FROM password_resets WHERE user_id=?",(row["user_id"],))
        return {"ok":True,"message":"Password updated. Sign in again on your devices."}
