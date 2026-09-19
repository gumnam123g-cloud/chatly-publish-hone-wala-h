"""User feedback + lightweight product analytics event log.

Both endpoints require auth. Feedback is stored in Mongo (`feedback` collection)
and mirrored to logs so operators can triage without opening the DB. Analytics
events are stored in `analytics_events` (capped-style TTL is caller's job) and
never contain raw message contents or credentials — the client sends only
event names plus small labelled properties.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import db
from security import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["feedback"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Feedback

class FeedbackBody(BaseModel):
    message: str = Field(min_length=3, max_length=4000)
    category: str | None = Field(default=None, max_length=40)
    app_version: str | None = Field(default=None, max_length=40)
    platform: str | None = Field(default=None, max_length=40)
    device: str | None = Field(default=None, max_length=120)


@router.post("/feedback")
async def submit_feedback(body: FeedbackBody, user: dict = Depends(get_current_user)):
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["user_id"],
        "email": user.get("email"),
        "name": user.get("name"),
        "message": body.message.strip(),
        "category": (body.category or "general").strip().lower()[:40],
        "app_version": body.app_version,
        "platform": body.platform,
        "device": body.device,
        "created_at": _now(),
    }
    try:
        await db.feedback.insert_one(dict(doc))
    except Exception as e:
        logger.error(f"feedback insert failed: {e}")
        raise HTTPException(status_code=500, detail="We couldn't save your feedback. Please try again.")
    logger.info(f"[feedback] user={user['user_id']} cat={doc['category']} len={len(doc['message'])}")
    return {"status": "received", "id": doc["id"]}


@router.get("/feedback/mine")
async def my_feedback(user: dict = Depends(get_current_user)):
    cur = db.feedback.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).limit(50)
    return {"items": [f async for f in cur]}


# ---------------------------------------------------------------------------
# Product analytics events (backend log — safe alternative to Firebase Analytics
# in Expo managed workflow). Real Firebase Analytics can be layered later via a
# custom dev-build; the same event names are emitted here.

# Explicit allow-list keeps the event surface auditable and lets us reject any
# accidental sensitive-payload send.
ALLOWED_EVENTS = {
    "app_open", "sign_up", "login", "google_sign_in", "logout",
    "message_sent", "message_received", "media_sent", "file_sent",
    "status_created", "status_viewed",
    "call_started", "call_answered", "call_ended", "call_rejected", "call_missed",
    "ai_action_started", "ai_action_completed", "ai_action_failed",
    "share_app", "feedback_submitted",
    "media_viewed_image", "media_viewed_video", "media_viewed_pdf",
    "screen_view",
}

# Property values are truncated to keep the log small and to defensively block
# any accidental large-blob send (e.g. a raw message body).
def _sanitize_props(props: dict[str, Any] | None) -> dict[str, Any]:
    if not props:
        return {}
    out: dict[str, Any] = {}
    for k, v in list(props.items())[:16]:
        if not isinstance(k, str) or len(k) > 40:
            continue
        if isinstance(v, (int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, str):
            out[k] = v[:120]
        else:
            out[k] = str(v)[:120]
    return out


class AnalyticsEvent(BaseModel):
    event: str = Field(min_length=1, max_length=48)
    props: dict[str, Any] | None = None
    at: str | None = None  # client-side ISO timestamp (optional)


class AnalyticsBatch(BaseModel):
    events: list[AnalyticsEvent] = Field(min_length=1, max_length=50)


@router.post("/analytics/event")
async def track_event(payload: AnalyticsBatch, user: dict = Depends(get_current_user)):
    accepted: list[dict] = []
    for ev in payload.events:
        if ev.event not in ALLOWED_EVENTS:
            continue
        row = {
            "id": str(uuid.uuid4()),
            "user_id": user["user_id"],
            "event": ev.event,
            "props": _sanitize_props(ev.props),
            "client_at": ev.at,
            "server_at": _now(),
        }
        accepted.append(row)
    if accepted:
        try:
            await db.analytics_events.insert_many(accepted)
        except Exception as e:
            logger.error(f"analytics insert failed: {e}")
    return {"accepted": len(accepted), "rejected": len(payload.events) - len(accepted)}
