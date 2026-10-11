"""Huddle optional chat extensions: private media, reports, moderation, recaps.
No untrusted attachment may be executed or displayed as HTML.
This is a single-worker/small-campus implementation, not a malware-scanning service.
"""
from __future__ import annotations
import io
import os
import re
import zipfile
from pathlib import Path
from urllib.parse import unquote
from fastapi import Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from .security import encrypt_bytes, decrypt_bytes, decrypt_text

MAX_UPLOAD = 25 * 1024 * 1024
MAX_VIDEO_UPLOAD = 50 * 1024 * 1024
SAFE_IMAGE_TYPES = {
    "image/png": (".png",),
    "image/jpeg": (".jpg", ".jpeg"),
    "image/webp": (".webp",),
}
SAFE_AUDIO_TYPES = {
    "audio/webm": (".webm",),
    "audio/ogg": (".ogg",),
    "audio/mp4": (".m4a", ".mp4"),
    "audio/mpeg": (".mp3",),
    "audio/wav": (".wav",),
}
SAFE_VIDEO_TYPES = {"video/mp4": (".mp4",), "video/webm": (".webm",), "video/quicktime": (".mov",)}
SAFE_DOCUMENT_TYPES = {
    "application/pdf": (".pdf",),
    "text/plain": (".txt", ".md"),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (".docx",)
}
ALLOW = {**SAFE_IMAGE_TYPES, **SAFE_AUDIO_TYPES, **SAFE_VIDEO_TYPES, **SAFE_DOCUMENT_TYPES}


class ReportBody(BaseModel):
    reason: str = Field(min_length=5, max_length=400)


class RemoveMemberBody(BaseModel):
    user_id: str = Field(min_length=1, max_length=60)


class ReviewReportBody(BaseModel):
    report_id: str = Field(min_length=32, max_length=40)
    status: str = Field(pattern=r"^(reviewed|dismissed)$")


def validate_media(data: bytes, filename: str, media_type: str):
    """Exact allowlist + format checks; this is *validation*, not antivirus."""
    media_type = media_type.split(";")[0].strip().lower()
    if media_type == "audio/x-wav": media_type = "audio/wav"
    if media_type == "audio/x-m4a": media_type = "audio/mp4"
    if media_type == "video/x-m4v": media_type = "video/mp4"
    if media_type in ("text/markdown", "text/x-markdown"): media_type = "text/plain"
    if media_type in ("application/octet-stream",""):
        # Browsers sometimes omit the MIME for non-executable safe formats.
        media_type = {
            ".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",
            ".webp":"image/webp",".pdf":"application/pdf",".txt":"text/plain",
            ".md":"text/plain",".docx":"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".mp3":"audio/mpeg",".wav":"audio/wav",".ogg":"audio/ogg",
            ".webm":"audio/webm",".m4a":"audio/mp4",".mp4":"video/mp4",".mov":"video/quicktime"
        }.get(Path(filename).suffix.lower(), "application/octet-stream")
    if media_type not in ALLOW:
        raise ValueError("Only images, short videos, voice notes, PDF/TXT and DOCX files are supported")
    limit = MAX_VIDEO_UPLOAD if media_type in SAFE_VIDEO_TYPES else MAX_UPLOAD
    if not data or len(data)>limit: raise ValueError("Video limit: 50 MB; other files: 25 MB")
    ext = Path(filename).suffix.lower()
    if ext not in ALLOW[media_type]:
        raise ValueError("File extension does not match its declared type")
    if media_type in SAFE_IMAGE_TYPES:
        from PIL import Image
        try:
            with Image.open(io.BytesIO(data)) as img:
                img.verify()
            with Image.open(io.BytesIO(data)) as img:
                if img.width * img.height > 20_000_000:
                    raise ValueError("Image dimensions are too large")
                expected={"image/png":"PNG","image/jpeg":"JPEG","image/webp":"WEBP"}[media_type]
                if img.format != expected: raise ValueError("Image format does not match its name")
        except Exception as exc:
            raise ValueError("Invalid or unsupported image") from exc
    elif media_type == "application/pdf":
        if not data.startswith(b"%PDF-"):
            raise ValueError("Invalid PDF file")
        # Disallow common PDF active-content entry points.
        if re.search(rb"/(?:JavaScript|JS|OpenAction|Launch)\b", data, flags=re.I):
            raise ValueError("PDF active scripts are not supported")
    elif media_type == "text/plain":
        try: data.decode("utf-8")
        except UnicodeDecodeError as exc: raise ValueError("Only UTF-8 text files are supported") from exc
        if b"\x00" in data: raise ValueError("Binary data is not a text file")
    elif media_type.endswith("wordprocessingml.document"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names=archive.namelist()
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise ValueError("Invalid DOCX structure")
                if len(names)>600 or sum(item.file_size for item in archive.infolist())>25*1024*1024:
                    raise ValueError("Document expands beyond safety limits")
                if any("vba" in x.lower() or x.endswith(".bin") or "embeddings/" in x.lower() for x in names):
                    raise ValueError("Macro or embedded executables are not permitted")
        except zipfile.BadZipFile as exc: raise ValueError("Invalid DOCX") from exc
    elif media_type == "audio/webm" and not data.startswith(b"\x1a\x45\xdf\xa3"):
        raise ValueError("Invalid WebM audio")
    elif media_type == "audio/ogg" and not data.startswith(b"OggS"):
        raise ValueError("Invalid Ogg audio")
    elif media_type == "audio/wav" and not (data.startswith(b"RIFF") and data[8:12] == b"WAVE"):
        raise ValueError("Invalid WAV audio")
    elif media_type == "audio/mpeg" and not (data.startswith(b"ID3") or (data[:1]==b"\xff" and data[1:2] and data[1]&0xE0==0xE0)):
        raise ValueError("Invalid MP3 audio")
    elif media_type == "audio/mp4" and data[4:8] != b"ftyp":
        raise ValueError("Invalid MP4/M4A audio")
    if media_type == "video/mp4" and data[4:8] != b"ftyp":
        raise ValueError("Invalid MP4 header")
    if media_type == "video/webm" and not data.startswith(bytes((0x1a, 0x45, 0xdf, 0xa3))):
        raise ValueError("Invalid WebM video")
    if media_type == "video/quicktime" and data[4:8] != b"ftyp":
        raise ValueError("Invalid MOV header")
    if media_type in SAFE_VIDEO_TYPES and len(data) < 16:
        raise ValueError("Video file is too small")
    return media_type


def install_extensions(app, db, hub, require_user, serialize_message, send_message, member_ids, ensure_membership, now, new_id):
    from fastapi import HTTPException

    def fail(code, text):
        raise HTTPException(status_code=code, detail=text)

    with db.connection() as cx:
        cx.executescript("""
            CREATE TABLE IF NOT EXISTS attachments(
                id TEXT PRIMARY KEY, message_id TEXT NOT NULL UNIQUE REFERENCES messages(id) ON DELETE CASCADE,
                filename TEXT NOT NULL, content_type TEXT NOT NULL, byte_size INTEGER NOT NULL,
                storage_name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_attach_msg ON attachments(message_id);
            CREATE TABLE IF NOT EXISTS message_reports(
                id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                reporter_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                reason TEXT NOT NULL, created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                UNIQUE(message_id,reporter_id)
            );
            CREATE INDEX IF NOT EXISTS idx_reports_status ON message_reports(status);
        """)
        # Add the optional millisecond duration to existing installations safely.
        cols={row["name"] for row in cx.execute("PRAGMA table_info(attachments)")}
        if "duration_ms" not in cols:
            cx.execute("ALTER TABLE attachments ADD COLUMN duration_ms INTEGER")
        # Additive migration: preserve previously sent media across deploys.
        if "view_once" not in cols:
            cx.execute("ALTER TABLE attachments ADD COLUMN view_once INTEGER NOT NULL DEFAULT 0")
        if "opened_at" not in cols:
            cx.execute("ALTER TABLE attachments ADD COLUMN opened_at TEXT")
        if "opened_by" not in cols:
            cx.execute("ALTER TABLE attachments ADD COLUMN opened_by TEXT")

    @app.post("/api/conversations/{conversation_id}/attachments", status_code=201)
    async def upload_attachment(conversation_id: str, request: Request):
        user=require_user(request)
        with db.connection() as cx: ensure_membership(cx,conversation_id,user["id"])
        filename=Path(unquote(request.headers.get("x-huddle-filename","attachment"))).name
        filename="".join(c for c in filename if c.isprintable() and c not in '<>:"/\\|?*')[:95] or "attachment"
        media_type=request.headers.get("content-type","").split(";",1)[0].strip().lower()
        video_upload=media_type.startswith("video/") or (media_type in ("application/octet-stream","") and Path(filename).suffix.lower() in (".mp4",".mov"))
        upload_limit=MAX_VIDEO_UPLOAD if video_upload else MAX_UPLOAD
        upload_label="50 MB for videos" if video_upload else "25 MB for other files"
        raw_size=request.headers.get("content-length","")
        if raw_size.isdigit() and int(raw_size)>upload_limit:fail(413,"File exceeds limit: "+upload_label)
        view_once=request.headers.get("x-huddle-view-once","").strip()=="1"
        if view_once:
            if not media_type.startswith(("image/","video/")):
                fail(422,"View Once is available only for photos and videos")
            with db.connection() as cx:
                conversation=cx.execute("SELECT kind FROM conversations WHERE id=?",(conversation_id,)).fetchone()
                if not conversation or conversation["kind"]!="dm":
                    fail(422,"View Once is currently supported in direct chats only")
        raw_duration=request.headers.get("x-huddle-duration-ms","")
        duration_ms=int(raw_duration) if raw_duration.isascii() and raw_duration.isdecimal() and len(raw_duration)<=8 else None
        if duration_ms is not None and not (100<=duration_ms<=3600000):
            duration_ms=None
        chunks=bytearray()
        async for piece in request.stream():
            if len(chunks)+len(piece)>upload_limit:
                fail(413,"File exceeds limit: "+upload_label)
            chunks.extend(piece)
        data=bytes(chunks)
        try: media_type=validate_media(data, filename, media_type)
        except ValueError as exc: fail(422,str(exc))
        if view_once and not media_type.startswith(("image/","video/")):
            fail(422,"View Once is available only for photos and videos")
        if not media_type.startswith("audio/"):
            duration_ms=None
        if media_type=="audio/wav":
            # WAV duration is determinable from bytes for uploaded legacy files.
            import wave
            from io import BytesIO
            try:
                with wave.open(BytesIO(data),"rb") as reader:
                    if reader.getframerate()>0:
                        duration_ms=max(100,round(reader.getnframes()/reader.getframerate()*1000))
            except (wave.Error,EOFError,ValueError):
                pass
        storage=Path(db.path).resolve().parent / "media" if db.path!=":memory:" else Path("/tmp/huddle-media")
        storage.mkdir(parents=True, exist_ok=True, mode=0o700)
        aid=new_id()
        binary=encrypt_bytes(data)
        path=storage / aid
        path.write_bytes(binary)
        try:
            category="image" if media_type.startswith("image/") else "video" if media_type.startswith("video/") else "voice" if media_type.startswith("audio/") else "file"
            marker={"image":"🖼️","video":"🎬","voice":"🎤","file":"📎"}[category]
            caption=unquote(request.headers.get("x-huddle-caption","")).strip()
            if len(caption)>500 or any(ord(c)<32 and c not in "\n\t" for c in caption):
                fail(422,"Caption cannot exceed 500 characters or contain control characters")
            text=f"{marker} {filename}"+("\n"+caption if caption else "")
            message,created=send_message(conversation_id,user["id"],text)
            with db.connection() as cx:
                cx.execute("""INSERT INTO attachments(
                    id,message_id,filename,content_type,byte_size,storage_name,created_at,duration_ms,view_once)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                   (aid,message["id"],filename,media_type,len(data),aid,now(),duration_ms,int(view_once)))
                fresh=cx.execute("SELECT * FROM messages WHERE id=?",(message["id"],)).fetchone()
                message=serialize_message(cx,fresh)
            await hub.notify(member_ids(conversation_id),{"type":"message:new","message":message})
            return {"message":message,"created":created}
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @app.post("/api/media/{attachment_id}/view-once")
    async def open_view_once(attachment_id: str, request: Request):
        """One atomic claim, one whole-file response; no thumbnail or range leak.

        Do not promise screenshot prevention: clients control what they display.
        """
        user=require_user(request)
        if not re.fullmatch(r"[a-f0-9]{32}",attachment_id):
            fail(404,"View Once attachment not found")
        storage=Path(db.path).resolve().parent / "media" if db.path!=":memory:" else Path("/tmp/huddle-media")
        with db.connection() as cx:
            item=cx.execute("""SELECT a.*,m.conversation_id,m.sender_id,m.deleted_at
                    FROM attachments a JOIN messages m ON m.id=a.message_id
                    WHERE a.id=?""",(attachment_id,)).fetchone()
            if not item or item["deleted_at"] or not item["view_once"] or item["opened_at"]:
                fail(410,"This View Once media has expired or was already opened")
            ensure_membership(cx,item["conversation_id"],user["id"])
            if item["sender_id"]==user["id"]:
                fail(403,"The sender cannot reopen View Once media")
            path=storage/item["storage_name"]
            if not path.is_file():
                fail(410,"This View Once media is no longer available")
            try: blob=decrypt_bytes(path.read_bytes())
            except Exception: fail(503,"Could not open this media")
            if not blob or len(blob)>MAX_VIDEO_UPLOAD:
                fail(503,"Media corrupted")
            # A conditional UPDATE permits only one successful redemption,
            # even when the recipient opens the same image in two browser tabs.
            changed=cx.execute("""UPDATE attachments SET opened_at=?,opened_by=?
                    WHERE id=? AND view_once=1 AND opened_at IS NULL""",
                    (now(),user["id"],attachment_id))
            if changed.rowcount!=1:fail(410,"This View Once media was already opened")
            updated_message=serialize_message(cx,cx.execute("SELECT * FROM messages WHERE id=?",
                (item["message_id"],)).fetchone())
        # Best-effort immediate erasure of the encrypted server-side file.
        # Metadata stays to display an 'Opened' placeholder in the chat.
        path.unlink(missing_ok=True)
        await hub.notify(member_ids(item["conversation_id"]),{
            "type":"message:update","message":updated_message})
        return Response(blob,media_type=item["content_type"],headers={
            "Cache-Control":"no-store, no-cache, max-age=0, must-revalidate",
            "Pragma":"no-cache","X-Content-Type-Options":"nosniff",
            "Content-Disposition":"inline"})

    @app.get("/api/media/{attachment_id}")
    async def download_attachment(attachment_id: str, request: Request):
        user=require_user(request)
        if not re.fullmatch("[a-f0-9]{32}", attachment_id):fail(404,"Media not found")
        with db.connection() as cx:
            item=cx.execute("""SELECT a.*,m.conversation_id,m.deleted_at FROM attachments a
                JOIN messages m ON m.id=a.message_id WHERE a.id=?""",(attachment_id,)).fetchone()
            if not item or item["deleted_at"] or item["view_once"]:
                fail(404,"Media not found")
            ensure_membership(cx,item["conversation_id"],user["id"])
        storage=Path(db.path).resolve().parent/"media" if db.path!=":memory:" else Path("/tmp/huddle-media")
        path=storage/item["storage_name"]
        if not path.is_file():fail(404,"Media file no longer available")
        try: blob=decrypt_bytes(path.read_bytes())
        except Exception:fail(503,"Media could not be read")
        if len(blob)>MAX_VIDEO_UPLOAD:fail(503,"Media corrupted")
        mime=item["content_type"]
        inline=mime.startswith(("image/","audio/","video/"))
        # PDF, DOCX and text always download, not inline in the Huddle origin.
        safe_name=re.sub(r'[^a-zA-Z0-9._ -]','_',item["filename"]).replace('"','_')
        disposition=("inline" if inline else "attachment")+f'; filename="{safe_name}"'
        headers={"Content-Disposition":disposition,"Cache-Control":"private, no-store",
                 "X-Content-Type-Options":"nosniff",
                 "Content-Security-Policy":"sandbox" if not inline else "default-src 'none'"}
        # Support byte-range media requests for video/audio seeking and playback.
        if mime.startswith(("video/","audio/")):
            headers["Accept-Ranges"]="bytes"
            requested=request.headers.get("range")
            if requested is not None:
                match=re.fullmatch(r"bytes=(\d*)-(\d*)", requested.strip())
                size=len(blob)
                if match and (match.group(1) or match.group(2)):
                    first,last=match.groups()
                    if first:
                        start=int(first)
                        end=int(last) if last else size-1
                    else:
                        count=int(last)
                        start=max(0,size-count)
                        end=size-1
                    if start<size and end>=start and (first or int(last)>0):
                        end=min(end,size-1)
                        headers["Content-Range"]=f"bytes {start}-{end}/{size}"
                        return Response(blob[start:end+1],status_code=206,
                                        media_type=mime,headers=headers)
                headers["Content-Range"]=f"bytes */{size}"
                return Response(status_code=416,headers=headers)
        return Response(blob, media_type=mime if inline else "application/octet-stream",
                        headers=headers)

    @app.post("/api/messages/{message_id}/report", status_code=201)
    async def report_message(message_id: str, payload: ReportBody, request: Request):
        user=require_user(request)
        with db.connection() as cx:
            msg=cx.execute("SELECT * FROM messages WHERE id=? AND deleted_at IS NULL",(message_id,)).fetchone()
            if not msg: fail(404,"Message not found")
            ensure_membership(cx,msg["conversation_id"],user["id"])
            if msg["sender_id"]==user["id"]:fail(422,"Cannot report your own message")
            cx.execute("""INSERT INTO message_reports(id,message_id,reporter_id,reason,created_at)
                VALUES(?,?,?,?,?) ON CONFLICT(message_id,reporter_id) DO UPDATE SET reason=excluded.reason""",
                (new_id(),message_id,user["id"],payload.reason.strip(),now()))
        return {"ok":True, "status":"pending","message":"Report submitted for moderator review"}

    @app.post("/api/conversations/{conversation_id}/moderation/remove")
    async def remove_group_member(conversation_id: str, payload: RemoveMemberBody, request: Request):
        user=require_user(request)
        with db.connection() as cx:
            conv=cx.execute("SELECT kind FROM conversations WHERE id=?",(conversation_id,)).fetchone()
            if not conv or conv["kind"]!="group":fail(404,"Group not found")
            mine=cx.execute("SELECT role FROM members WHERE conversation_id=? AND user_id=?",(conversation_id,user["id"])).fetchone()
            target=cx.execute("SELECT role FROM members WHERE conversation_id=? AND user_id=?",(conversation_id,payload.user_id)).fetchone()
            if not mine or mine["role"]!="admin":fail(403,"Only circle admins can remove members")
            if not target or target["role"]=="admin":fail(422,"Cannot remove a group administrator")
            cx.execute("DELETE FROM members WHERE conversation_id=? AND user_id=?",(conversation_id,payload.user_id))
        await hub.notify(member_ids(conversation_id)+[payload.user_id],
                         {"type":"conversation:refresh","conversation_id":conversation_id})
        return {"ok":True}

    @app.get("/api/conversations/{conversation_id}/moderation/reports")
    async def list_group_reports(conversation_id: str, request: Request):
        user=require_user(request)
        with db.connection() as cx:
            conv=cx.execute("SELECT kind FROM conversations WHERE id=?",(conversation_id,)).fetchone()
            mine=cx.execute("SELECT role FROM members WHERE conversation_id=? AND user_id=?",(conversation_id,user["id"])).fetchone()
            if not conv or conv["kind"]!="group" or not mine or mine["role"]!="admin":
                fail(403,"Only circle admins can review reports")
            rows=cx.execute("""SELECT r.id,r.reason,r.status,r.created_at,m.id AS message_id,
                     m.sender_id,u.name AS sender_name,m.body
                     FROM message_reports r
                     JOIN messages m ON m.id=r.message_id
                     JOIN users u ON u.id=m.sender_id
                     WHERE m.conversation_id=? ORDER BY r.created_at DESC LIMIT 80""",(conversation_id,)).fetchall()
        return {"reports":[{**dict(row),"body":decrypt_text(row["body"])[:300]} for row in rows]}

    @app.post("/api/conversations/{conversation_id}/moderation/review")
    async def review_group_report(conversation_id: str, payload: ReviewReportBody, request: Request):
        user=require_user(request)
        with db.connection() as cx:
            conv=cx.execute("SELECT kind FROM conversations WHERE id=?",(conversation_id,)).fetchone()
            mine=cx.execute("SELECT role FROM members WHERE conversation_id=? AND user_id=?",(conversation_id,user["id"])).fetchone()
            if not conv or conv["kind"]!="group" or not mine or mine["role"]!="admin":
                fail(403,"Only circle admins can review reports")
            report=cx.execute("""SELECT r.id FROM message_reports r JOIN messages m ON m.id=r.message_id
                     WHERE r.id=? AND m.conversation_id=?""",(payload.report_id,conversation_id)).fetchone()
            if not report:fail(404,"Report not found")
            cx.execute("UPDATE message_reports SET status=? WHERE id=?",(payload.status,payload.report_id))
        return {"ok":True,"status":payload.status}

    @app.get("/api/conversations/{conversation_id}/recap")
    async def conversation_recap(conversation_id: str, request: Request):
        user=require_user(request)
        with db.connection() as cx:
            ensure_membership(cx,conversation_id,user["id"])
            rows=cx.execute("""SELECT m.body,m.sender_id,u.name FROM messages m
                 JOIN users u ON u.id=m.sender_id
                 WHERE m.conversation_id=? AND m.deleted_at IS NULL ORDER BY m.created_at DESC LIMIT 25""",
                 (conversation_id,)).fetchall()
        items=[]
        for r in reversed(rows):
            body=decrypt_text(r["body"]).strip()
            if not body or body.startswith(("📎","🖼️","🎤")):continue
            items.append({"speaker":r["name"],"text":body[:170]})
        return {"items":items[-12:],"count":len(rows),
                "method":"recent_messages","note":"Recent conversation highlights, not an AI-generated summary. Only visible to participants."}
