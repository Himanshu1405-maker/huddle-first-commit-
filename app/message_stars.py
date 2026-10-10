"""Private WhatsApp-style message bookmarks.

Bookmarks belong to one authenticated member, never broadcast to another
member and never appear in someone else's message serialization.
"""
from fastapi import Request, HTTPException


def install_message_stars(app, db, require_user, ensure_membership, serialize_message, now):
    with db.connection() as cx:
        cx.executescript("""
            CREATE TABLE IF NOT EXISTS message_stars (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                PRIMARY KEY(user_id,message_id)
            );
            CREATE INDEX IF NOT EXISTS idx_stars_user_recent
                ON message_stars(user_id,created_at DESC);
        """)

    def fetch_authorized(cx, message_id, user_id):
        msg=cx.execute("SELECT * FROM messages WHERE id=? AND deleted_at IS NULL",
                       (message_id,)).fetchone()
        if not msg:
            raise HTTPException(404,"Message not found")
        ensure_membership(cx,msg["conversation_id"],user_id)
        return msg

    @app.put("/api/messages/{message_id}/star")
    async def star_message(message_id: str, request: Request):
        user=require_user(request)
        with db.connection() as cx:
            fetch_authorized(cx,message_id,user["id"])
            cx.execute("""INSERT OR IGNORE INTO message_stars(user_id,message_id,created_at)
                          VALUES(?,?,?)""",(user["id"],message_id,now()))
        return {"starred":True,"message_id":message_id}

    @app.delete("/api/messages/{message_id}/star")
    async def unstar_message(message_id: str, request: Request):
        user=require_user(request)
        with db.connection() as cx:
            fetch_authorized(cx,message_id,user["id"])
            cx.execute("DELETE FROM message_stars WHERE user_id=? AND message_id=?",
                       (user["id"],message_id))
        return {"starred":False,"message_id":message_id}

    @app.get("/api/messages/starred")
    async def list_starred_messages(request: Request):
        user=require_user(request)
        with db.connection() as cx:
            rows=cx.execute("""SELECT m.*,c.name AS conversation_name,c.kind AS conversation_kind,
                s.created_at AS starred_at
                FROM message_stars s JOIN messages m ON m.id=s.message_id
                JOIN conversations c ON c.id=m.conversation_id
                JOIN members member ON member.conversation_id=m.conversation_id
                                    AND member.user_id=s.user_id
                WHERE s.user_id=? AND m.deleted_at IS NULL
                ORDER BY s.created_at DESC,m.id DESC LIMIT 300""",
                (user["id"],)).fetchall()
            # Saved by current user only; sender details remain inside authorized chats.
            result=[{"message":serialize_message(cx,row),
                     "conversation_name":row["conversation_name"],
                     "conversation_kind":row["conversation_kind"],
                     "starred_at":row["starred_at"]} for row in rows]
        return {"items":result}
