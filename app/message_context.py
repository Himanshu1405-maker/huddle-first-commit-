"""Secure reply references and forwarding for Huddle conversations.

Only chat members can reply or forward. Forwarded location data is deliberately
blocked; forwarded media gets a new attachment ID and a copy of the encrypted
original blob instead of sharing its old conversation's media URL.
"""
from __future__ import annotations
from pathlib import Path
import shutil

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field
from .security import decrypt_text


class ContextMessage(BaseModel):
    action: str = Field(pattern="^(reply|forward)$")
    source_message_id: str = Field(min_length=32,max_length=36)
    body: str | None = Field(default=None,max_length=4000)
    client_nonce: str | None = Field(default=None,max_length=64)


def serialize_context(cx, msg):
    info=cx.execute("""SELECT action,source_message_id FROM message_context
        WHERE message_id=?""",(msg["id"],)).fetchone()
    if not info:
        return {"reply_to":None,"forwarded":False}
    if info["action"]=="forward":
        return {"reply_to":None,"forwarded":True}
    src=cx.execute("""SELECT m.id,m.body,m.sender_id,m.deleted_at,u.name
        FROM messages m JOIN users u ON u.id=m.sender_id
        WHERE m.id=? AND m.conversation_id=?""",
        (info["source_message_id"],msg["conversation_id"])).fetchone()
    if not src:
        return {"reply_to":{"id":info["source_message_id"],"name":"Unknown",
                            "preview":"Message unavailable"},"forwarded":False}
    if src["deleted_at"]:
        snippet="This message was deleted"
    else:
        attachment=cx.execute("SELECT filename,content_type FROM attachments WHERE message_id=?",
                              (src["id"],)).fetchone()
        if attachment:
            content=attachment["content_type"]
            snippet=("📷 Photo" if content.startswith("image/") else
                     "🎥 Video" if content.startswith("video/") else
                     "🎙 Voice message" if content.startswith("audio/") else
                     "📎 File")+(": "+attachment["filename"][:80])
        else:
            snippet=decrypt_text(src["body"])[:160]
            if snippet.startswith("[[huddle-sticker:"):
                snippet="✨ Animated sticker"
            if cx.execute("SELECT 1 FROM location_shares WHERE message_id=?",
                          (src["id"],)).fetchone():
                snippet="📍 Location"
    return {"reply_to":{"id":src["id"],"name":src["name"],
                         "preview":snippet},"forwarded":False}


def install_message_context(app,db,hub,require_user,serialize_message,send_message,
                            member_ids,ensure_membership,now,new_id):
    with db.connection() as cx:
        cx.executescript("""
            CREATE TABLE IF NOT EXISTS message_context(
                message_id TEXT PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
                source_message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE RESTRICT,
                action TEXT NOT NULL CHECK(action IN ('reply','forward'))
            );
        """)

    @app.post("/api/conversations/{conversation_id}/messages/context",status_code=201)
    async def send_context_message(conversation_id: str,payload: ContextMessage,request: Request):
        user=require_user(request)
        if payload.action=="reply" and not (payload.body and payload.body.strip()):
            raise HTTPException(422,"Write a reply before sending")
        # Verify source and destination independently. Never leak another chat's data.
        with db.connection() as cx:
            ensure_membership(cx,conversation_id,user["id"])
            source=cx.execute("SELECT * FROM messages WHERE id=?",
                              (payload.source_message_id,)).fetchone()
            if not source or source["deleted_at"]:
                raise HTTPException(404,"Message not available")
            ensure_membership(cx,source["conversation_id"],user["id"])
            if payload.action=="reply" and source["conversation_id"]!=conversation_id:
                raise HTTPException(422,"Replies must stay in the same conversation")
            if payload.action=="forward" and cx.execute(
                "SELECT 1 FROM location_shares WHERE message_id=?",
                (source["id"],)).fetchone():
                raise HTTPException(422,"Location sharing cannot be forwarded")
            attachment=None
            if payload.action=="forward":
                attachment=cx.execute("SELECT * FROM attachments WHERE message_id=?",
                                      (source["id"],)).fetchone()
            text=decrypt_text(source["body"]) if payload.action=="forward" else payload.body.strip()
        # Forwarding text is a server-side copy; ignore untrusted client-provided text.
        # Keep the existing rate limit, nonce deduplication and encryption via send_message.
        result,created=send_message(conversation_id,user["id"],text,payload.client_nonce)
        if not created:
            return {"message":result,"created":False}
        copied_path=None
        try:
            with db.connection() as cx:
                if attachment:
                    storage=(Path(db.path).resolve().parent/"media" if db.path!=":memory:"
                             else Path("/tmp/huddle-media"))
                    storage.mkdir(parents=True,exist_ok=True,mode=0o700)
                    origin=storage/attachment["storage_name"]
                    if not origin.is_file():
                        raise HTTPException(404,"Source media no longer available")
                    aid=new_id()
                    copied_path=storage/aid
                    shutil.copyfile(origin,copied_path)
                    cx.execute("""INSERT INTO attachments
                        (id,message_id,filename,content_type,byte_size,storage_name,created_at)
                        VALUES(?,?,?,?,?,?,?)""",
                        (aid,result["id"],attachment["filename"],attachment["content_type"],
                         attachment["byte_size"],aid,now()))
                cx.execute("""INSERT INTO message_context(message_id,source_message_id,action)
                              VALUES(?,?,?)""",
                           (result["id"],payload.source_message_id,payload.action))
                message=serialize_message(cx,cx.execute(
                    "SELECT * FROM messages WHERE id=?",(result["id"],)).fetchone())
        except Exception:
            if copied_path:copied_path.unlink(missing_ok=True)
            with db.connection() as cx:
                cx.execute("DELETE FROM messages WHERE id=? AND sender_id=?",
                           (result["id"],user["id"]))
            raise
        await hub.notify(member_ids(conversation_id),{"type":"message:new","message":message})
        return {"message":message,"created":True}
