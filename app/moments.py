"""Huddle Moments: private, expiring stories shared with existing chat contacts.

Moments are visible only to their authors or users sharing a conversation with
the author. Every feed, image/video request and view event checks this rule.
"""
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, Field

PALETTES={"iris","lagoon","sunrise","midnight","peach","mint"}
MEDIA_LIMIT=12*1024*1024
TTL=timedelta(hours=24)

class MomentText(BaseModel):
    text: str=Field(min_length=1,max_length=320)
    palette: str="iris"

def media_format(data, declared):
    if data.startswith(b"\xff\xd8\xff") and declared=="image/jpeg":
        return "image/jpeg","image"
    if data.startswith(b"\x89PNG\r\n\x1a\n") and declared=="image/png":
        return "image/png","image"
    if data.startswith(b"RIFF") and data[8:12]==b"WEBP" and declared=="image/webp":
        return "image/webp","image"
    if len(data)>12 and data[4:8]==b"ftyp" and declared=="video/mp4":
        return "video/mp4","video"
    if data.startswith(b"\x1a\x45\xdf\xa3") and declared=="video/webm":
        return "video/webm","video"
    raise HTTPException(422,"Use a JPG, PNG, WebP, MP4 or WebM file")

def install_moments(app,db,require_user,now,new_id):
    with db.connection() as cx:
        cx.executescript("""
          CREATE TABLE IF NOT EXISTS moments (
              id TEXT PRIMARY KEY,
              author_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              kind TEXT NOT NULL CHECK(kind IN ('text','image','video')),
              body TEXT NOT NULL DEFAULT '',
              palette TEXT NOT NULL DEFAULT 'iris',
              media BLOB,
              media_type TEXT,
              created_at TEXT NOT NULL,
              expires_at TEXT NOT NULL
          );
          CREATE INDEX IF NOT EXISTS idx_moments_expiry ON moments(expires_at);
          CREATE INDEX IF NOT EXISTS idx_moments_author ON moments(author_id,created_at DESC);
          CREATE TABLE IF NOT EXISTS moment_views (
              moment_id TEXT NOT NULL REFERENCES moments(id) ON DELETE CASCADE,
              user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              seen_at TEXT NOT NULL,
              PRIMARY KEY(moment_id,user_id)
          );
          CREATE TABLE IF NOT EXISTS moment_hearts (
              moment_id TEXT NOT NULL REFERENCES moments(id) ON DELETE CASCADE,
              user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              created_at TEXT NOT NULL,
              PRIMARY KEY(moment_id,user_id)
          );
        """)

    def timestamp():
        return datetime.now(timezone.utc).isoformat(timespec="microseconds")

    def cleanup(cx):
        cx.execute("DELETE FROM moments WHERE expires_at<=?",(timestamp(),))

    def allowed(cx,author,viewer):
        if author==viewer:return True
        return cx.execute("""
            SELECT 1 FROM members m JOIN members other
              ON other.conversation_id=m.conversation_id
            WHERE m.user_id=? AND other.user_id=? LIMIT 1
        """,(viewer,author)).fetchone() is not None

    def authorized(cx,id,user_id,own=False):
        row=cx.execute("SELECT * FROM moments WHERE id=? AND expires_at>?",
                       (id,timestamp())).fetchone()
        if not row or (own and row["author_id"]!=user_id) or not allowed(cx,row["author_id"],user_id):
            raise HTTPException(404,"Moment not found")
        return row

    def serialize(cx,row,user_id):
        seen=cx.execute("SELECT 1 FROM moment_views WHERE moment_id=? AND user_id=?",
                        (row["id"],user_id)).fetchone()
        heart=cx.execute("SELECT 1 FROM moment_hearts WHERE moment_id=? AND user_id=?",
                         (row["id"],user_id)).fetchone()
        views=cx.execute("SELECT COUNT(*) n FROM moment_views WHERE moment_id=?",
                         (row["id"],)).fetchone()["n"] if row["author_id"]==user_id else None
        hearts=cx.execute("SELECT COUNT(*) n FROM moment_hearts WHERE moment_id=?",
                          (row["id"],)).fetchone()["n"]
        return {"id":row["id"],"author_id":row["author_id"],"author_name":row["name"],
            "author_handle":row["handle"],"kind":row["kind"],"text":row["body"],
            "palette":row["palette"],"created_at":row["created_at"],
            "expires_at":row["expires_at"],"mine":row["author_id"]==user_id,
            "seen":bool(seen),"hearted":bool(heart),"views":views,
            "hearts":hearts,"has_media":row["kind"]!="text"}

    def rate_guard(cx,user_id):
        count=cx.execute("SELECT COUNT(*) n FROM moments WHERE author_id=? AND expires_at>?",
                         (user_id,timestamp())).fetchone()["n"]
        if count>=24:raise HTTPException(429,"You have reached 24 active Moments")
        since=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(timespec="microseconds")
        frequent=cx.execute("SELECT COUNT(*) n FROM moments WHERE author_id=? AND created_at>?",
                            (user_id,since)).fetchone()["n"]
        if frequent>=12:raise HTTPException(429,"Too many Moments this hour")

    def add(cx,user_id,kind,text,palette,media=None,mime=None):
        rate_guard(cx,user_id)
        stamp=timestamp();expires=(datetime.now(timezone.utc)+TTL).isoformat(timespec="microseconds")
        id=new_id()
        cx.execute("""INSERT INTO moments(id,author_id,kind,body,palette,media,media_type,created_at,expires_at)
                      VALUES(?,?,?,?,?,?,?,?,?)""",
                   (id,user_id,kind,text,palette,media,mime,stamp,expires))
        return {"id":id,"expires_at":expires}

    @app.get("/api/moments")
    async def list_moments(request:Request):
        me=require_user(request)
        with db.connection() as cx:
            cleanup(cx)
            rows=cx.execute("""
                SELECT m.id,m.author_id,m.kind,m.body,m.palette,m.created_at,m.expires_at,
                       u.name,u.handle
                FROM moments m JOIN users u ON u.id=m.author_id
                WHERE m.expires_at>? AND (
                    m.author_id=? OR EXISTS(
                      SELECT 1 FROM members mine JOIN members theirs
                        ON theirs.conversation_id=mine.conversation_id
                      WHERE mine.user_id=? AND theirs.user_id=m.author_id))
                ORDER BY m.created_at DESC LIMIT 350
            """,(timestamp(),me["id"],me["id"])).fetchall()
            return {"moments":[serialize(cx,row,me["id"]) for row in rows]}

    @app.post("/api/moments",status_code=201)
    async def create_text(payload:MomentText,request:Request):
        me=require_user(request)
        if payload.palette not in PALETTES:raise HTTPException(422,"Unsupported color theme")
        text=payload.text.strip()
        if not text:raise HTTPException(422,"Write something to share")
        with db.connection() as cx:
            cleanup(cx)
            return add(cx,me["id"],"text",text,payload.palette)

    @app.post("/api/moments/media",status_code=201)
    async def create_media(request:Request):
        me=require_user(request)
        declared=request.headers.get("content-type","").split(";",1)[0].strip().lower()
        allowed_types={"image/jpeg","image/png","image/webp","video/mp4","video/webm"}
        if declared not in allowed_types:raise HTTPException(422,"Unsupported media format")
        length=request.headers.get("content-length","")
        if length.isdigit() and int(length)>MEDIA_LIMIT:raise HTTPException(413,"Moment file is too large (12 MB max)")
        # Stream to avoid unbounded in-memory reads of a malicious upload.
        buffer=bytearray()
        async for chunk in request.stream():
            buffer.extend(chunk)
            if len(buffer)>MEDIA_LIMIT:raise HTTPException(413,"Moment file is too large (12 MB max)")
        if len(buffer)<16:raise HTTPException(422,"The file is empty or invalid")
        mime,kind=media_format(bytes(buffer[:24]),declared)
        with db.connection() as cx:
            cleanup(cx)
            return add(cx,me["id"],kind,"","iris",bytes(buffer),mime)

    @app.get("/api/moments/{moment_id}/media")
    async def moment_media(moment_id:str,request:Request):
        me=require_user(request)
        with db.connection() as cx:
            row=authorized(cx,moment_id,me["id"])
            if not row["media"] or not row["media_type"]:
                raise HTTPException(404,"Media unavailable")
            return Response(content=row["media"],media_type=row["media_type"],
                headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})

    @app.post("/api/moments/{moment_id}/view")
    async def mark_view(moment_id:str,request:Request):
        me=require_user(request)
        with db.connection() as cx:
            row=authorized(cx,moment_id,me["id"])
            if row["author_id"]!=me["id"]:
                cx.execute("""INSERT OR IGNORE INTO moment_views(moment_id,user_id,seen_at)
                              VALUES(?,?,?)""",(moment_id,me["id"],timestamp()))
        return {"ok":True}

    @app.put("/api/moments/{moment_id}/heart")
    async def add_heart(moment_id:str,request:Request):
        me=require_user(request)
        with db.connection() as cx:
            authorized(cx,moment_id,me["id"])
            cx.execute("""INSERT OR IGNORE INTO moment_hearts(moment_id,user_id,created_at)
                          VALUES(?,?,?)""",(moment_id,me["id"],timestamp()))
        return {"hearted":True}

    @app.delete("/api/moments/{moment_id}/heart")
    async def remove_heart(moment_id:str,request:Request):
        me=require_user(request)
        with db.connection() as cx:
            authorized(cx,moment_id,me["id"])
            cx.execute("DELETE FROM moment_hearts WHERE moment_id=? AND user_id=?",
                       (moment_id,me["id"]))
        return {"hearted":False}

    @app.delete("/api/moments/{moment_id}")
    async def delete_moment(moment_id:str,request:Request):
        me=require_user(request)
        with db.connection() as cx:
            authorized(cx,moment_id,me["id"],own=True)
            cx.execute("DELETE FROM moments WHERE id=?",(moment_id,))
        return {"deleted":True}
