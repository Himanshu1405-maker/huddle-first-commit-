"""Opt-in background Web Push, active only with operator-managed VAPID keys.

Browser subscriptions belong to the signed-in Huddle account. Payloads never
include private message content. Gracefully disables without valid config.
"""
import asyncio, json, os, re
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field


def ready():
    return bool(all(os.getenv(k,"").strip() for k in
       ("VAPID_PRIVATE_KEY","VAPID_PUBLIC_KEY","VAPID_CONTACT")))


class Subscription(BaseModel):
    endpoint: str = Field(min_length=20,max_length=1300)
    keys: dict[str,str]


def install_push(app,db,require_user,member_ids,now):
    with db.connection() as cx:
        cx.executescript("""
        CREATE TABLE IF NOT EXISTS web_push_subscriptions(
            endpoint TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            subscription TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_push_subs_user ON web_push_subscriptions(user_id);
        """)

    @app.get("/api/push/config")
    async def push_config(request:Request):
        require_user(request)
        return {"enabled":ready(),"public_key":os.getenv("VAPID_PUBLIC_KEY","") if ready() else ""}

    @app.post("/api/push/subscribe")
    async def subscribe(payload:Subscription,request:Request):
        user=require_user(request)
        if not ready():raise HTTPException(503,"Push notifications are not configured")
        if not payload.endpoint.startswith("https://") or not payload.keys.get("p256dh") or not payload.keys.get("auth"):
            raise HTTPException(422,"Invalid push subscription")
        info={"endpoint":payload.endpoint,"keys":{
            "p256dh":payload.keys["p256dh"],"auth":payload.keys["auth"]}}
        with db.connection() as cx:
            cx.execute("""INSERT INTO web_push_subscriptions(endpoint,user_id,subscription,created_at)
                VALUES(?,?,?,?) ON CONFLICT(endpoint) DO UPDATE SET
                user_id=excluded.user_id,subscription=excluded.subscription,
                created_at=excluded.created_at""",
                (payload.endpoint,user["id"],json.dumps(info),now()))
        return {"ok":True}

    @app.post("/api/push/unsubscribe")
    async def unsubscribe(payload:Subscription,request:Request):
        user=require_user(request)
        with db.connection() as cx:
            cx.execute("DELETE FROM web_push_subscriptions WHERE endpoint=? AND user_id=?",
                       (payload.endpoint,user["id"]))
        return {"ok":True}

    async def notify(conversation_id:str,sender_id:str):
        if not ready():return
        try:
            from pywebpush import webpush,WebPushException
        except ImportError:
            return
        with db.connection() as cx:
            entries=cx.execute("""SELECT s.endpoint,s.subscription FROM web_push_subscriptions s
                JOIN members m ON m.user_id=s.user_id
                LEFT JOIN chat_preferences p ON p.user_id=s.user_id AND p.conversation_id=m.conversation_id
                WHERE m.conversation_id=? AND m.user_id<>? AND COALESCE(p.muted,0)=0""",
                (conversation_id,sender_id)).fetchall()
        def send(entry):
            try:
                webpush(subscription_info=json.loads(entry["subscription"]),
                  data=json.dumps({"title":"Huddle","body":"You have a new message.","url":"/"}),
                  vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
                  vapid_claims={"sub":os.environ["VAPID_CONTACT"]},ttl=90,timeout=10)
            except Exception:
                # Invalid subscriptions can be pruned after provider failure.
                pass
        await asyncio.gather(*(asyncio.to_thread(send,e) for e in entries[:40]))
    return notify
