"""Reusable message templates (feature #35) + Multi-message composer helper
(feature #36).

A template has a category, a title and a body that may contain simple merge
tokens like `{name}` / `{date}`. Rendering happens client-side.

`/api/templates/render` is an optional server-side helper that returns N
personalised drafts given a template + a list of `vars` (one row per recipient).
The user always reviews before sending; the API never sends anything itself.
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import db
from security import get_current_user

router = APIRouter(prefix="/api", tags=["templates"])

SEED = [
    ("work",     "Availability check",  "Hi {name}, do you have 15 minutes tomorrow to discuss {topic}?"),
    ("work",     "Send documents",      "Hi {name}, sharing the {doc_type} we discussed. Let me know if anything is missing."),
    ("followup", "Gentle follow-up",    "Hi {name}, just following up on {topic}. Any update?"),
    ("meeting",  "Meeting invite",      "Hey, are you free on {date} at {time} for a quick sync on {topic}?"),
    ("customer", "Order update",        "Hi {name}, your order {order_id} is on the way. Delivery expected by {date}."),
    ("college",  "Notes share",         "Hey {name}, sharing the notes for {subject}. Ping me if the file didn\u2019t open."),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ensure_seed(user_id: str):
    has = await db.templates.find_one({"user_id": user_id}, {"_id": 1})
    if has:
        return
    docs = [{
        "id": str(uuid.uuid4()), "user_id": user_id,
        "category": c, "title": t, "body": b,
        "is_seed": True, "created_at": _now(),
    } for (c, t, b) in SEED]
    if docs:
        await db.templates.insert_many(docs)


class TemplateBody(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=4000)
    category: str = Field(default="custom", max_length=40)


@router.get("/templates")
async def list_templates(user: dict = Depends(get_current_user)):
    await _ensure_seed(user["user_id"])
    cur = db.templates.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1)
    return {"items": [t async for t in cur]}


@router.post("/templates")
async def create_template(body: TemplateBody, user: dict = Depends(get_current_user)):
    doc = {
        "id": str(uuid.uuid4()), "user_id": user["user_id"],
        "title": body.title.strip(), "body": body.body.strip(),
        "category": body.category.strip().lower()[:40] or "custom",
        "is_seed": False, "created_at": _now(),
    }
    await db.templates.insert_one(dict(doc))
    doc.pop("_id", None)
    return {"template": doc}


@router.patch("/templates/{tid}")
async def update_template(tid: str, body: TemplateBody, user: dict = Depends(get_current_user)):
    doc = await db.templates.find_one({"id": tid, "user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found.")
    await db.templates.update_one({"id": tid}, {"$set": {
        "title": body.title.strip(), "body": body.body.strip(),
        "category": body.category.strip().lower()[:40] or "custom",
    }})
    return {"template": await db.templates.find_one({"id": tid}, {"_id": 0})}


@router.delete("/templates/{tid}")
async def delete_template(tid: str, user: dict = Depends(get_current_user)):
    r = await db.templates.delete_one({"id": tid, "user_id": user["user_id"]})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found.")
    return {"status": "deleted"}


class RenderBody(BaseModel):
    template_id: str
    rows: list[dict[str, Any]] = Field(default_factory=list, max_length=50)


@router.post("/templates/render")
async def render_template(body: RenderBody, user: dict = Depends(get_current_user)):
    """Render N drafts from a template + rows of merge variables.
    Never sends — the user reviews and dispatches manually."""
    doc = await db.templates.find_one({"id": body.template_id, "user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found.")
    body_text = doc["body"]
    drafts = []
    for row in body.rows[:50]:
        text = body_text
        for k, v in (row or {}).items():
            text = text.replace("{" + str(k) + "}", str(v))
        drafts.append({"vars": row or {}, "text": text})
    return {"template": doc, "drafts": drafts}
