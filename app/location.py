"""Opt-in, conversation-scoped location cards for Huddle.

Live shares update only while the sender's browser can provide GPS positions.
Location sharing is never enabled without an explicit user action.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import Request
from pydantic import BaseModel, Field

from .security import encrypt_text, decrypt_text


class LocationStart(BaseModel):
    mode: Literal["pin", "live"]
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    accuracy_m: float | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)
    duration_minutes: Literal[15, 60, 480] = 15


class LocationUpdate(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    accuracy_m: float | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)


def _coordinates(latitude: float, longitude: float) -> str:
    return encrypt_text(json.dumps([round(latitude, 6), round(longitude, 6)]))


def _expire(cx, timestamp: str):
    # Expired live locations must not remain in persistent storage.
    cx.execute("""UPDATE location_shares SET coordinates=NULL, accuracy_m=NULL,
        stopped_at=COALESCE(stopped_at, ?)
        WHERE mode='live' AND stopped_at IS NULL AND expires_at<=?""",
        (timestamp, timestamp))


def serialize_location(cx, message):
    if message["deleted_at"]:
        return None
    row = cx.execute("""SELECT mode,coordinates,accuracy_m,updated_at,expires_at,stopped_at
        FROM location_shares WHERE message_id=?""", (message["id"],)).fetchone()
    if not row:
        return None
    current_time = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    if row["mode"] == "live" and not row["stopped_at"] and row["expires_at"] <= current_time:
        cx.execute("""UPDATE location_shares SET coordinates=NULL,accuracy_m=NULL,stopped_at=?
            WHERE message_id=?""", (current_time, message["id"]))
        row = cx.execute("""SELECT mode,coordinates,accuracy_m,updated_at,expires_at,stopped_at
            FROM location_shares WHERE message_id=?""", (message["id"],)).fetchone()
    active = row["mode"] == "live" and not row["stopped_at"] and row["expires_at"] > current_time
    coords = json.loads(decrypt_text(row["coordinates"])) if row["coordinates"] else None
    return {
        "mode": row["mode"], "active": active,
        "latitude": coords[0] if coords else None,
        "longitude": coords[1] if coords else None,
        "accuracy_m": row["accuracy_m"] if coords else None,
        "updated_at": row["updated_at"],
        "expires_at": row["expires_at"],
    }


def install_location(app, db, hub, require_user, serialize_message, member_ids,
                     ensure_membership, now, new_id):
    with db.connection() as cx:
        cx.executescript("""
            CREATE TABLE IF NOT EXISTS location_shares (
                message_id TEXT PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                sender_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                mode TEXT NOT NULL CHECK(mode IN ('pin','live')),
                coordinates TEXT, accuracy_m REAL,
                started_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                expires_at TEXT, stopped_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_location_expiry ON location_shares(mode,expires_at);
        """)

    @app.post("/api/conversations/{conversation_id}/locations", status_code=201)
    async def share_location(conversation_id: str, payload: LocationStart, request: Request):
        user = require_user(request)
        stamp = now()
        expires = (
            (datetime.now(timezone.utc) + timedelta(minutes=payload.duration_minutes))
            .isoformat(timespec="microseconds")
            if payload.mode == "live" else None
        )
        with db.connection() as cx:
            ensure_membership(cx, conversation_id, user["id"])
            _expire(cx, stamp)
            if payload.mode == "live":
                existing = cx.execute("""SELECT 1 FROM location_shares
                    WHERE sender_id=? AND mode='live' AND stopped_at IS NULL
                      AND expires_at>? LIMIT 1""", (user["id"], stamp)).fetchone()
                if existing:
                    raise_location_conflict()
            message_id = new_id()
            body = "🟢 Live location" if payload.mode == "live" else "📍 Shared location"
            cx.execute("""INSERT INTO messages(id,conversation_id,sender_id,body,created_at)
                VALUES(?,?,?,?,?)""",
                (message_id, conversation_id, user["id"], encrypt_text(body), stamp))
            cx.execute("""INSERT INTO location_shares(message_id,conversation_id,sender_id,
                mode,coordinates,accuracy_m,started_at,updated_at,expires_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (message_id, conversation_id, user["id"], payload.mode,
                 _coordinates(payload.latitude, payload.longitude), payload.accuracy_m,
                 stamp, stamp, expires))
            cx.execute("UPDATE conversations SET updated_at=? WHERE id=?", (stamp, conversation_id))
            message = serialize_message(cx, cx.execute(
                "SELECT * FROM messages WHERE id=?", (message_id,)).fetchone())
        await hub.notify(member_ids(conversation_id), {"type": "message:new", "message": message})
        return {"message": message}

    @app.patch("/api/locations/{message_id}")
    async def update_location(message_id: str, payload: LocationUpdate, request: Request):
        user = require_user(request)
        stamp = now()
        with db.connection() as cx:
            _expire(cx, stamp)
            row = cx.execute("""SELECT * FROM location_shares WHERE message_id=?
                AND sender_id=?""", (message_id, user["id"])).fetchone()
            if not row or row["mode"] != "live" or row["stopped_at"]:
                from fastapi import HTTPException
                raise HTTPException(404, "Active live location not found")
            ensure_membership(cx, row["conversation_id"], user["id"])
            msg = cx.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
            if not msg or msg["deleted_at"]:
                from fastapi import HTTPException
                raise HTTPException(404, "Active live location not found")
            if (datetime.fromisoformat(stamp) -
                    datetime.fromisoformat(row["updated_at"])).total_seconds() < 3:
                from fastapi import HTTPException
                raise HTTPException(429, "Please space location updates at least 3 seconds apart")
            cx.execute("""UPDATE location_shares
                SET coordinates=?,accuracy_m=?,updated_at=? WHERE message_id=?""",
                (_coordinates(payload.latitude, payload.longitude),
                 payload.accuracy_m, stamp, message_id))
            message = serialize_message(cx, msg)
        await hub.notify(member_ids(message["conversation_id"]),
                         {"type": "message:update", "message": message})
        return {"message": message}

    async def stop_location_impl(message_id: str, request: Request):
        user = require_user(request)
        stamp = now()
        with db.connection() as cx:
            row = cx.execute("""SELECT * FROM location_shares
                WHERE message_id=? AND sender_id=?""",
                (message_id, user["id"])).fetchone()
            if not row or row["mode"] != "live":
                from fastapi import HTTPException
                raise HTTPException(404, "Live location not found")
            ensure_membership(cx, row["conversation_id"], user["id"])
            cx.execute("""UPDATE location_shares SET coordinates=NULL,accuracy_m=NULL,
                stopped_at=COALESCE(stopped_at,?) WHERE message_id=?""",
                (stamp, message_id))
            message = serialize_message(cx, cx.execute(
                "SELECT * FROM messages WHERE id=?", (message_id,)).fetchone())
        await hub.notify(member_ids(message["conversation_id"]),
                         {"type": "message:update", "message": message})
        return {"message": message}

    @app.post("/api/locations/{message_id}/stop")
    async def stop_location(message_id: str, request: Request):
        # POST also permits best-effort stop via sendBeacon on tab close.
        return await stop_location_impl(message_id, request)

    @app.delete("/api/locations/{message_id}")
    async def delete_live_location(message_id: str, request: Request):
        return await stop_location_impl(message_id, request)


def raise_location_conflict():
    from fastapi import HTTPException
    raise HTTPException(409, "Stop your existing live location before starting another")
