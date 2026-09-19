"""Scheduled + Recurring Messages (features #9, #10).

A background asyncio task ticks every 15s and dispatches any due schedule
using the existing chat send-message path so downstream side-effects (WS
broadcast, FCM push, seen ledger) remain identical to a manual send.

Recurrence uses a compact custom spec (`freq` in {daily, weekly, custom}) plus
`interval_days`. On dispatch we recompute the next `send_at` (never delete the
row) so cancel/edit/pause remain first-class user actions.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from db import db
from security import get_current_user
from ws_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["schedule"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


class ScheduleBody(BaseModel):
    chat_id: str
    text: str = Field(min_length=1, max_length=20000)
    send_at: str  # ISO-8601 in UTC (frontend must convert local -> UTC first)
    recurrence: str | None = Field(default=None, pattern="^(daily|weekly|custom)$")
    interval_days: int | None = Field(default=None, ge=1, le=366)


class UpdateBody(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=20000)
    send_at: str | None = None
    recurrence: str | None = Field(default=None, pattern="^(daily|weekly|custom|off)$")
    interval_days: int | None = Field(default=None, ge=1, le=366)
    paused: bool | None = None


async def _require_chat(chat_id: str, user_id: str) -> dict:
    chat = await db.chats.find_one({"chat_id": chat_id, "participants": user_id})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return chat


def _next_run(current: datetime, spec: dict) -> datetime | None:
    freq = spec.get("recurrence")
    if not freq or freq == "off":
        return None
    if freq == "daily":
        return current + timedelta(days=1)
    if freq == "weekly":
        return current + timedelta(days=7)
    if freq == "custom":
        n = int(spec.get("interval_days") or 1)
        return current + timedelta(days=max(1, n))
    return None


@router.post("/messages/schedule")
async def create_schedule(body: ScheduleBody, user: dict = Depends(get_current_user)):
    await _require_chat(body.chat_id, user["user_id"])
    try:
        send_at_dt = datetime.fromisoformat(body.send_at.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid send_at (use ISO-8601).")
    if send_at_dt <= _now() - timedelta(minutes=1):
        raise HTTPException(status_code=400, detail="Please pick a future time.")
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["user_id"],
        "chat_id": body.chat_id,
        "text": body.text.strip(),
        "send_at": _iso(send_at_dt),
        "recurrence": body.recurrence,
        "interval_days": body.interval_days,
        "paused": False,
        "status": "scheduled",       # scheduled | sent | cancelled | failed
        "last_error": None,
        "created_at": _iso(_now()),
    }
    await db.scheduled_messages.insert_one(dict(doc))
    doc.pop("_id", None)
    return {"schedule": doc}


@router.get("/messages/schedule")
async def list_schedules(user: dict = Depends(get_current_user),
                         status: str = Query("active", pattern="^(active|all|past)$")):
    q: dict = {"user_id": user["user_id"]}
    if status == "active":
        q["status"] = "scheduled"
    elif status == "past":
        q["status"] = {"$in": ["sent", "cancelled", "failed"]}
    cur = db.scheduled_messages.find(q, {"_id": 0}).sort("send_at", 1).limit(200)
    return {"items": [s async for s in cur]}


@router.patch("/messages/schedule/{sid}")
async def update_schedule(sid: str, body: UpdateBody, user: dict = Depends(get_current_user)):
    doc = await db.scheduled_messages.find_one({"id": sid, "user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Scheduled message not found.")
    if doc.get("status") in {"sent", "cancelled"}:
        raise HTTPException(status_code=400, detail="This schedule can no longer be edited.")
    upd: dict = {}
    if body.text is not None:
        upd["text"] = body.text.strip()
    if body.send_at is not None:
        try:
            dt = datetime.fromisoformat(body.send_at.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid send_at.")
        if dt <= _now() - timedelta(minutes=1):
            raise HTTPException(status_code=400, detail="Please pick a future time.")
        upd["send_at"] = _iso(dt)
    if body.recurrence is not None:
        upd["recurrence"] = None if body.recurrence == "off" else body.recurrence
    if body.interval_days is not None:
        upd["interval_days"] = body.interval_days
    if body.paused is not None:
        upd["paused"] = bool(body.paused)
    if not upd:
        return {"schedule": doc}
    await db.scheduled_messages.update_one({"id": sid}, {"$set": upd})
    updated = await db.scheduled_messages.find_one({"id": sid}, {"_id": 0})
    return {"schedule": updated}


@router.delete("/messages/schedule/{sid}")
async def cancel_schedule(sid: str, user: dict = Depends(get_current_user)):
    doc = await db.scheduled_messages.find_one({"id": sid, "user_id": user["user_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Scheduled message not found.")
    if doc.get("status") == "sent":
        raise HTTPException(status_code=400, detail="This message has already been sent.")
    await db.scheduled_messages.update_one({"id": sid}, {"$set": {"status": "cancelled"}})
    return {"status": "cancelled"}


# ---------------------------------------------------------------------------
# Background dispatcher.

async def _dispatch_due():
    """Every tick: find schedules whose send_at is due, deliver via the standard
    _persist_message path, then either mark as `sent` (one-shot) or advance the
    `send_at` (recurring)."""
    from chat_routes import _persist_message  # local import to avoid circular
    from firebase_routes import push_to_user
    now_iso = _iso(_now())
    q = {"status": "scheduled", "paused": {"$ne": True}, "send_at": {"$lte": now_iso}}
    cur = db.scheduled_messages.find(q, {"_id": 0}).limit(50)
    due = [s async for s in cur]
    for s in due:
        try:
            chat = await db.chats.find_one({"chat_id": s["chat_id"], "participants": s["user_id"]})
            if not chat:
                await db.scheduled_messages.update_one({"id": s["id"]}, {"$set": {"status": "failed", "last_error": "chat_gone"}})
                continue
            msg = await _persist_message(s["chat_id"], s["user_id"], s["text"])
            others = [p for p in chat["participants"] if p != s["user_id"]]
            await manager.send_to_users(others, {"type": "message", "chat_id": s["chat_id"], "message": msg})
            muted = set(chat.get("muted_by", []))
            sender = await db.users.find_one({"user_id": s["user_id"]}, {"_id": 0, "name": 1})
            for oid in others:
                if oid in muted:
                    continue
                udoc = await db.users.find_one({"user_id": oid}, {"_id": 0, "is_bot": 1})
                if udoc and udoc.get("is_bot"):
                    continue
                asyncio.create_task(push_to_user(
                    oid, (sender or {}).get("name", "New message"), s["text"][:120],
                    {"type": "chat_message", "chat_id": s["chat_id"], "message_id": msg["message_id"]}))
            nxt = _next_run(datetime.fromisoformat(s["send_at"].replace("Z", "+00:00")), s)
            if nxt is None:
                await db.scheduled_messages.update_one({"id": s["id"]}, {"$set": {"status": "sent", "delivered_at": now_iso}})
            else:
                await db.scheduled_messages.update_one({"id": s["id"]}, {"$set": {"send_at": _iso(nxt), "last_run_at": now_iso}})
        except Exception as e:
            logger.error(f"schedule dispatch failed id={s.get('id')}: {e}")
            await db.scheduled_messages.update_one({"id": s["id"]}, {"$set": {"status": "failed", "last_error": str(e)[:200]}})


_TICK_TASK: asyncio.Task | None = None


async def _tick_loop():
    while True:
        try:
            await _dispatch_due()
        except Exception as e:
            logger.error(f"schedule tick error: {e}")
        await asyncio.sleep(15)


def start_scheduler():
    """Called at FastAPI startup from server.py."""
    global _TICK_TASK
    if _TICK_TASK is not None:
        return
    _TICK_TASK = asyncio.create_task(_tick_loop())
    logger.info("scheduled-messages dispatcher started (15s tick)")
