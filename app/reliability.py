"""Durable chat preferences, personal blocking and campus polls/events.

The existing Huddle room membership model remains the authorization boundary.
All mutations require a signed-in session; no cross-room data is exposed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
import sqlite3
import secrets

from fastapi import Request
from pydantic import BaseModel, Field


class Preferences(BaseModel):
    pinned: bool = False
    archived: bool = False
    muted: bool = False


class PollCreate(BaseModel):
    question: str = Field(min_length=4, max_length=180)
    options: list[str] = Field(min_length=2, max_length=8)


class PollVote(BaseModel):
    option_id: str = Field(min_length=20, max_length=40)


class EventCreate(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    starts_at: str = Field(min_length=15, max_length=48)
    details: str = Field(default="", max_length=500)


class EventRSVP(BaseModel):
    answer: Literal["going", "maybe", "not_going"]


def install_reliability(app, db, hub, require_user, ensure_membership, member_ids, now, new_id):
    from fastapi import HTTPException

    def fail(code, detail):
        raise HTTPException(code, detail)

    with db.connection() as cx:
        cx.executescript("""
        CREATE TABLE IF NOT EXISTS chat_preferences(
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            pinned INTEGER NOT NULL DEFAULT 0,
            archived INTEGER NOT NULL DEFAULT 0,
            muted INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,conversation_id)
        );
        CREATE TABLE IF NOT EXISTS user_blocks(
            blocker_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            blocked_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            PRIMARY KEY(blocker_id,blocked_id),
            CHECK(blocker_id<>blocked_id)
        );
        CREATE INDEX IF NOT EXISTS idx_blocks_blocked ON user_blocks(blocked_id);
        CREATE TABLE IF NOT EXISTS huddle_polls(
            id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            author_id TEXT NOT NULL REFERENCES users(id),
            question TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS huddle_poll_options(
            id TEXT PRIMARY KEY, poll_id TEXT NOT NULL REFERENCES huddle_polls(id) ON DELETE CASCADE,
            label TEXT NOT NULL, position INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS huddle_poll_votes(
            poll_id TEXT NOT NULL REFERENCES huddle_polls(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            option_id TEXT NOT NULL REFERENCES huddle_poll_options(id) ON DELETE CASCADE,
            PRIMARY KEY(poll_id,user_id)
        );
        CREATE TABLE IF NOT EXISTS huddle_events(
            id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            creator_id TEXT NOT NULL REFERENCES users(id),
            title TEXT NOT NULL, details TEXT NOT NULL,
            starts_at TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS huddle_event_rsvps(
            event_id TEXT NOT NULL REFERENCES huddle_events(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            answer TEXT NOT NULL CHECK(answer IN ('going','maybe','not_going')),
            PRIMARY KEY(event_id,user_id)
        );
        """)

    def blocked(cx, uid1, uid2):
        return cx.execute("""SELECT 1 FROM user_blocks
            WHERE (blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?)""",
            (uid1,uid2,uid2,uid1)).fetchone() is not None

    def serialize_poll(cx, row, user_id):
        items=cx.execute("""SELECT o.id,o.label,o.position,COUNT(v.user_id) AS count
            FROM huddle_poll_options o LEFT JOIN huddle_poll_votes v ON v.option_id=o.id
            WHERE o.poll_id=? GROUP BY o.id ORDER BY o.position""",(row["id"],)).fetchall()
        mine=cx.execute("SELECT option_id FROM huddle_poll_votes WHERE poll_id=? AND user_id=?",
                        (row["id"],user_id)).fetchone()
        return {"id":row["id"],"conversation_id":row["conversation_id"],
                "author_id":row["author_id"],"question":row["question"],
                "created_at":row["created_at"],"options":[dict(o) for o in items],
                "my_vote":mine["option_id"] if mine else None}

    def serialize_event(cx,row,user_id):
        counts={r["answer"]:r["count"] for r in cx.execute("""SELECT answer,COUNT(*) AS count
            FROM huddle_event_rsvps WHERE event_id=? GROUP BY answer""",(row["id"],))}
        mine=cx.execute("SELECT answer FROM huddle_event_rsvps WHERE event_id=? AND user_id=?",
                        (row["id"],user_id)).fetchone()
        return {"id":row["id"],"conversation_id":row["conversation_id"],
                "creator_id":row["creator_id"],"title":row["title"],"details":row["details"],
                "starts_at":row["starts_at"],"created_at":row["created_at"],
                "rsvps":counts,"my_rsvp":mine["answer"] if mine else None}

    @app.patch("/api/conversations/{conversation_id}/preferences")
    async def save_preferences(conversation_id:str,payload:Preferences,request:Request):
        user=require_user(request)
        with db.connection() as cx:
            ensure_membership(cx,conversation_id,user["id"])
            cx.execute("""INSERT INTO chat_preferences(user_id,conversation_id,pinned,archived,muted)
                VALUES(?,?,?,?,?) ON CONFLICT(user_id,conversation_id) DO UPDATE SET
                pinned=excluded.pinned,archived=excluded.archived,muted=excluded.muted""",
                (user["id"],conversation_id,int(payload.pinned),int(payload.archived),int(payload.muted)))
        return {"ok":True,"preferences":payload.model_dump()}

    @app.get("/api/me/blocked")
    async def blocked_users(request:Request):
        user=require_user(request)
        with db.connection() as cx:
            rows=cx.execute("""SELECT u.id,u.handle,u.name FROM users u JOIN user_blocks b ON b.blocked_id=u.id
                WHERE b.blocker_id=? ORDER BY u.name""",(user["id"],)).fetchall()
        return {"users":[dict(x) for x in rows]}

    @app.put("/api/users/{other_id}/block")
    async def block_user(other_id:str,request:Request):
        user=require_user(request)
        if other_id==user["id"]:fail(422,"You cannot block yourself")
        with db.connection() as cx:
            if not cx.execute("SELECT 1 FROM users WHERE id=?",(other_id,)).fetchone():
                fail(404,"User not found")
            cx.execute("""INSERT OR IGNORE INTO user_blocks VALUES(?,?,?)""",
                       (user["id"],other_id,now()))
        await hub.notify([other_id,user["id"]],{"type":"conversation:refresh"})
        return {"ok":True,"blocked":True}

    @app.delete("/api/users/{other_id}/block")
    async def unblock_user(other_id:str,request:Request):
        user=require_user(request)
        with db.connection() as cx:
            cx.execute("DELETE FROM user_blocks WHERE blocker_id=? AND blocked_id=?",
                       (user["id"],other_id))
        return {"ok":True,"blocked":False}

    @app.get("/api/conversations/{conversation_id}/polls")
    async def list_polls(conversation_id:str,request:Request):
        user=require_user(request)
        with db.connection() as cx:
            ensure_membership(cx,conversation_id,user["id"])
            rows=cx.execute("SELECT * FROM huddle_polls WHERE conversation_id=? ORDER BY created_at DESC LIMIT 30",
                            (conversation_id,)).fetchall()
            return {"polls":[serialize_poll(cx,row,user["id"]) for row in rows]}

    @app.post("/api/conversations/{conversation_id}/polls",status_code=201)
    async def create_poll(conversation_id:str,payload:PollCreate,request:Request):
        user=require_user(request)
        question=payload.question.strip()
        choices=[v.strip() for v in payload.options]
        if len(question)<4 or len(choices)<2 or any(len(s)<1 or len(s)>100 for s in choices):
            fail(422,"Question and choices must not be blank")
        if len({s.casefold() for s in choices})!=len(choices):fail(422,"Poll options must be different")
        with db.connection() as cx:
            ensure_membership(cx,conversation_id,user["id"])
            poll_id=new_id()
            cx.execute("INSERT INTO huddle_polls VALUES(?,?,?,?,?)",
                       (poll_id,conversation_id,user["id"],question,now()))
            for i,label in enumerate(choices):
                cx.execute("INSERT INTO huddle_poll_options VALUES(?,?,?,?)",
                           (new_id(),poll_id,label,i))
            result=serialize_poll(cx,cx.execute("SELECT * FROM huddle_polls WHERE id=?",
                                                (poll_id,)).fetchone(),user["id"])
        await hub.notify(member_ids(conversation_id),{"type":"huddle:planning","conversation_id":conversation_id})
        return {"poll":result}

    @app.put("/api/polls/{poll_id}/vote")
    async def vote_poll(poll_id:str,payload:PollVote,request:Request):
        user=require_user(request)
        with db.connection() as cx:
            row=cx.execute("SELECT * FROM huddle_polls WHERE id=?",(poll_id,)).fetchone()
            if not row:fail(404,"Poll not found")
            ensure_membership(cx,row["conversation_id"],user["id"])
            opt=cx.execute("SELECT 1 FROM huddle_poll_options WHERE poll_id=? AND id=?",
                           (poll_id,payload.option_id)).fetchone()
            if not opt:fail(422,"Invalid choice")
            cx.execute("""INSERT INTO huddle_poll_votes VALUES(?,?,?)
                ON CONFLICT(poll_id,user_id) DO UPDATE SET option_id=excluded.option_id""",
                (poll_id,user["id"],payload.option_id))
            result=serialize_poll(cx,row,user["id"])
        await hub.notify(member_ids(row["conversation_id"]),{
            "type":"huddle:planning","conversation_id":row["conversation_id"]})
        return {"poll":result}

    @app.get("/api/conversations/{conversation_id}/events")
    async def list_events(conversation_id:str,request:Request):
        user=require_user(request)
        with db.connection() as cx:
            ensure_membership(cx,conversation_id,user["id"])
            rows=cx.execute("""SELECT * FROM huddle_events WHERE conversation_id=?
                ORDER BY starts_at ASC LIMIT 40""",(conversation_id,)).fetchall()
            return {"events":[serialize_event(cx,row,user["id"]) for row in rows]}

    @app.post("/api/conversations/{conversation_id}/events",status_code=201)
    async def create_event(conversation_id:str,payload:EventCreate,request:Request):
        user=require_user(request)
        try:
            stamp=datetime.fromisoformat(payload.starts_at.replace("Z","+00:00"))
            if stamp.tzinfo is None:raise ValueError()
            when=stamp.astimezone(timezone.utc).isoformat()
        except ValueError:fail(422,"Use a date/time including its timezone")
        if stamp.astimezone(timezone.utc)<=datetime.now(timezone.utc):fail(422,"Event must be in the future")
        with db.connection() as cx:
            ensure_membership(cx,conversation_id,user["id"])
            eid=new_id()
            cx.execute("INSERT INTO huddle_events VALUES(?,?,?,?,?,?,?)",
                       (eid,conversation_id,user["id"],payload.title.strip(),
                        payload.details.strip(),when,now()))
            result=serialize_event(cx,cx.execute("SELECT * FROM huddle_events WHERE id=?",
                                                 (eid,)).fetchone(),user["id"])
        await hub.notify(member_ids(conversation_id),{
            "type":"huddle:planning","conversation_id":conversation_id})
        return {"event":result}

    @app.put("/api/events/{event_id}/rsvp")
    async def rsvp_event(event_id:str,payload:EventRSVP,request:Request):
        user=require_user(request)
        with db.connection() as cx:
            row=cx.execute("SELECT * FROM huddle_events WHERE id=?",(event_id,)).fetchone()
            if not row:fail(404,"Event not found")
            ensure_membership(cx,row["conversation_id"],user["id"])
            cx.execute("""INSERT INTO huddle_event_rsvps VALUES(?,?,?)
                ON CONFLICT(event_id,user_id) DO UPDATE SET answer=excluded.answer""",
                (event_id,user["id"],payload.answer))
            result=serialize_event(cx,row,user["id"])
        await hub.notify(member_ids(row["conversation_id"]),{
            "type":"huddle:planning","conversation_id":row["conversation_id"]})
        return {"event":result}
