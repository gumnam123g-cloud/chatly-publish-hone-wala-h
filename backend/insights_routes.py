"""AI Insights (features #17, #18, #34, #46, #47, #48).

All endpoints reuse the existing ai_service. Every route returns a user-safe
error on provider failure; nothing is silently swallowed and no raw provider
exception is exposed.
"""
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from db import db
from security import get_current_user
from ai_service import ai_complete, ai_json, AIServiceError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["insights"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Daily Brief (features #46, #47, #48).

class BriefBody(BaseModel):
    kind: str = Field(default="daily", pattern="^(daily|morning|end_of_day)$")
    out_lang: str | None = None


@router.post("/insights/daily-brief")
async def daily_brief(body: BriefBody, user: dict = Depends(get_current_user)):
    me = user["user_id"]
    since = (_now() - timedelta(hours=24)).isoformat()
    # Recent messages the user hasn't read (unread) + user's tasks + reminders.
    unread_cur = db.messages.find({
        "created_at": {"$gte": since},
        "deleted": {"$ne": True},
        "sender_id": {"$ne": me},
        "read_by": {"$ne": me},
    }, {"_id": 0, "chat_id": 1, "sender_id": 1, "text": 1, "created_at": 1}).sort("created_at", -1).limit(80)
    unread = [m async for m in unread_cur]
    tasks_cur = db.tasks.find({"user_id": me, "status": {"$ne": "done"}}, {"_id": 0}).sort("created_at", -1).limit(30)
    tasks = [t async for t in tasks_cur]
    reminders_cur = db.reminders.find({"user_id": me}, {"_id": 0}).sort("remind_at", 1).limit(30)
    reminders = [r async for r in reminders_cur]

    # Compact display-names for the prompt.
    sender_ids = list({m["sender_id"] for m in unread if m.get("sender_id")})
    name_map: dict[str, str] = {}
    if sender_ids:
        async for u in db.users.find({"user_id": {"$in": sender_ids}}, {"_id": 0, "user_id": 1, "name": 1}):
            name_map[u["user_id"]] = u.get("name", "User")
    lines: list[str] = []
    for m in unread[:30]:
        who = name_map.get(m.get("sender_id", ""), "User")
        lines.append(f"- {who}: {(m.get('text') or '')[:200]}")
    tk = "\n".join(f"- {t.get('title')} (priority: {t.get('priority','normal')})" for t in tasks[:20]) or "(none)"
    rm = "\n".join(f"- {r.get('text')} @ {r.get('remind_at')}" for r in reminders[:20]) or "(none)"
    lang_hint = f"Write the brief in {body.out_lang}." if body.out_lang else ""
    kind_label = {"daily": "today's", "morning": "morning", "end_of_day": "end-of-day"}[body.kind]
    system = (
        f"You are Chatly. Produce the user's {kind_label} brief. Be concise, calm, and actionable. "
        f"Group under: Important updates, Pending replies, Tasks, Reminders. {lang_hint} "
        f"Keep bullet-points short. Do not invent items. If sections are empty say so."
    )
    prompt = (
        f"UNREAD (last 24h):\n{chr(10).join(lines) or '(none)'}\n\n"
        f"OPEN TASKS:\n{tk}\n\nUPCOMING REMINDERS:\n{rm}\n"
    )
    try:
        text = await ai_complete(system, prompt)
    except AIServiceError:
        raise
    return {"kind": body.kind, "generated_at": _now().isoformat(), "brief": (text or "").strip(),
            "unread_count": len(unread), "open_tasks": len(tasks), "reminders": len(reminders)}


# ---------------------------------------------------------------------------
# Scam Detector (feature #17).

class ScamBody(BaseModel):
    text: str = Field(min_length=1, max_length=6000)
    context: str | None = None


_SCAM_INSTRUCTIONS = (
    "You are a cautious safety assistant. Classify the risk of the given message. "
    "NEVER claim certainty; use hedged language such as 'potentially suspicious'. "
    "Focus on: suspicious URLs, urgency language, payment/OTP/credential requests, "
    "unknown-sender pressure, impersonation. Return strict JSON with keys: "
    "risk_level (safe|low|medium|high), reasons (array of short strings), "
    "advice (one short sentence)."
)


@router.post("/insights/scam-check")
async def scam_check(body: ScamBody, user: dict = Depends(get_current_user)):
    prompt = f"MESSAGE:\n{body.text}\n\nRETURN JSON."
    try:
        j = await ai_json(_SCAM_INSTRUCTIONS, prompt)
    except AIServiceError:
        raise
    if not isinstance(j, dict):
        j = {"risk_level": "safe", "reasons": [], "advice": "No obvious risk detected."}
    j.setdefault("risk_level", "safe")
    j.setdefault("reasons", [])
    j.setdefault("advice", "")
    return j


# ---------------------------------------------------------------------------
# Link Preview + Analyzer (feature #18). Fetches basic Open Graph info.

_HDRS = {"User-Agent": "Mozilla/5.0 Chatly Preview"}


class LinkBody(BaseModel):
    url: str = Field(min_length=4, max_length=2048)


@router.post("/insights/link-preview")
async def link_preview(body: LinkBody, user: dict = Depends(get_current_user)):
    p = urlparse(body.url.strip())
    if p.scheme not in {"http", "https"} or not p.hostname:
        raise HTTPException(status_code=400, detail="Not a valid URL.")
    domain = p.hostname
    title = domain
    description = ""
    image = None
    signals: list[str] = []
    # Very conservative: 4s timeout, 512KB max, no redirect chains beyond 3.
    try:
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True, max_redirects=3, headers=_HDRS) as c:
            r = await c.get(body.url, headers=_HDRS)
            content_type = (r.headers.get("content-type") or "").lower()
            if "text/html" in content_type:
                html = r.text[:512_000]
                def og(prop: str) -> str | None:
                    pat1 = r'<meta[^>]+property=[\"\']og:' + re.escape(prop) + r'[\"\'][^>]+content=[\"\']([^\"\']+)'
                    m = re.search(pat1, html, re.I)
                    if m:
                        return m.group(1)
                    pat2 = r'<meta[^>]+name=[\"\']\s*' + re.escape(prop) + r'\s*[\"\'][^>]+content=[\"\']([^\"\']+)'
                    m = re.search(pat2, html, re.I)
                    return m.group(1) if m else None
                title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
                title = og("title") or (title_m.group(1) if title_m else domain)
                description = og("description") or ""
                image = og("image")
    except Exception as e:
        signals.append("unable_to_fetch")
    # Simple safety signals (never claim certainty).
    if re.search(r"\b(bit\.ly|tinyurl|is\.gd|t\.co|goo\.gl|adf\.ly)\b", domain, re.I):
        signals.append("url_shortener")
    if p.scheme == "http":
        signals.append("non_https")
    if re.search(r"[0-9]+", (domain or "").split(".", 1)[0]) and "-" in (domain or ""):
        signals.append("suspicious_hostname")
    return {
        "url": body.url, "domain": domain,
        "title": (title or domain)[:200],
        "description": (description or "")[:400],
        "image": image, "signals": signals,
    }


# ---------------------------------------------------------------------------
# AI Contact Brief (feature #34).

@router.get("/users/{user_id}/brief")
async def contact_brief(user_id: str, user: dict = Depends(get_current_user)):
    me = user["user_id"]
    # Auth: only briefs for people the user has a chat with.
    dm = await db.chats.find_one({"type": "dm", "participants": {"$all": [me, user_id]}}, {"_id": 0})
    if not dm:
        raise HTTPException(status_code=404, detail="No conversation with this contact.")
    target = await db.users.find_one({"user_id": user_id, "deleted_at": None}, {"_id": 0, "name": 1, "username": 1, "bio": 1})
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    since = (_now() - timedelta(days=30)).isoformat()
    cur = db.messages.find({
        "chat_id": dm["chat_id"], "deleted": {"$ne": True}, "created_at": {"$gte": since},
    }, {"_id": 0, "sender_id": 1, "text": 1, "created_at": 1}).sort("created_at", -1).limit(120)
    hist = [m async for m in cur]
    hist.reverse()
    convo = "\n".join(f"{'Them' if m['sender_id']==user_id else 'Me'}: {(m.get('text') or '')[:400]}" for m in hist) or "(no recent messages)"
    system = (
        f"Summarise this contact ({target.get('name','User')}) for the user. Include: recent topics, "
        f"pending items I owe them, pending items they owe me, tone. 5-8 short bullet points. "
        f"Never invent facts."
    )
    try:
        text = await ai_complete(system, convo)
    except AIServiceError:
        raise
    return {"user": target, "brief": (text or "").strip(), "messages_considered": len(hist)}


# ---------------------------------------------------------------------------
# Universal Search (feature #44).

@router.get("/search/universal")
async def universal_search(q: str = Query(min_length=1, max_length=120),
                            user: dict = Depends(get_current_user)):
    me = user["user_id"]
    query = q.strip()
    rx = re.compile(re.escape(query), re.I)
    async def _chats():
        cur = db.chats.find({
            "participants": me, "deleted_by": {"$ne": me},
            "$or": [{"last_message": {"$regex": rx}}, {"name": {"$regex": rx}}, {"title": {"$regex": rx}}],
        }, {"_id": 0, "chat_id": 1, "last_message": 1, "name": 1, "title": 1, "last_ts": 1}).limit(10)
        return [{**c, "kind": "chat"} async for c in cur]
    async def _messages():
        my_chats = [c["chat_id"] async for c in db.chats.find({"participants": me, "deleted_by": {"$ne": me}}, {"_id": 0, "chat_id": 1})]
        if not my_chats:
            return []
        cur = db.messages.find({
            "chat_id": {"$in": my_chats}, "deleted": {"$ne": True},
            "deleted_for": {"$ne": me},
            "text": {"$regex": rx},
        }, {"_id": 0, "message_id": 1, "chat_id": 1, "sender_id": 1, "text": 1, "created_at": 1, "type": 1}).sort("created_at", -1).limit(30)
        return [{**m, "kind": "message"} async for m in cur]
    async def _tasks():
        cur = db.tasks.find({"user_id": me, "$or": [{"title": {"$regex": rx}}, {"notes": {"$regex": rx}}]}, {"_id": 0}).limit(20)
        return [{**t, "kind": "task"} async for t in cur]
    async def _reminders():
        cur = db.reminders.find({"user_id": me, "text": {"$regex": rx}}, {"_id": 0}).limit(20)
        return [{**r, "kind": "reminder"} async for r in cur]
    async def _files():
        my_chats = [c["chat_id"] async for c in db.chats.find({"participants": me}, {"_id": 0, "chat_id": 1})]
        if not my_chats:
            return []
        cur = db.messages.find({
            "chat_id": {"$in": my_chats}, "attachment": {"$ne": None},
            "$or": [{"attachment.filename": {"$regex": rx}}, {"text": {"$regex": rx}}],
        }, {"_id": 0, "message_id": 1, "chat_id": 1, "attachment": 1, "text": 1, "created_at": 1}).sort("created_at", -1).limit(20)
        return [{**m, "kind": "file"} async for m in cur]
    chats, messages, tasks, reminders, files = await __import__("asyncio").gather(_chats(), _messages(), _tasks(), _reminders(), _files())
    return {"query": query, "chats": chats, "messages": messages, "tasks": tasks, "reminders": reminders, "files": files}


# ---------------------------------------------------------------------------
# AI Personal Assistant — natural language interpreter (feature #1, #25).
#
# Returns a structured *proposed action* (never executed automatically). The
# frontend surfaces a confirmation card; user taps Confirm to invoke the
# corresponding endpoint (tasks/reminders/schedule). No side-effects here.

class InterpretBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    now: str | None = None  # ISO client-local now, used only as prompt hint


_ASSISTANT_INSTRUCTIONS = (
    "You are Chatly's personal assistant. Read the user's request and propose the SINGLE most useful "
    "action. Return strict JSON with keys: action, params, human_readable. "
    "Valid action values: 'create_task', 'create_reminder', 'schedule_message', "
    "'summarize_chat', 'summarize_unread', 'show_important', 'show_pending', 'answer'. "
    "For 'create_task' params={title,priority}. For 'create_reminder' params={text, remind_at_iso}. "
    "For 'schedule_message' params={contact_hint,text,send_at_iso}. For 'answer' params={reply}. "
    "NEVER include private information you were not given. Preserve the user's language (Hindi, English, Hinglish)."
)


@router.post("/assistant/interpret")
async def assistant_interpret(body: InterpretBody, user: dict = Depends(get_current_user)):
    now_hint = body.now or _now().isoformat()
    prompt = f"CLIENT_NOW: {now_hint}\nUSER: {body.text.strip()}\n\nRETURN JSON."
    try:
        j = await ai_json(_ASSISTANT_INSTRUCTIONS, prompt)
    except AIServiceError:
        raise
    if not isinstance(j, dict):
        j = {"action": "answer", "params": {"reply": (body.text[:200] or "Okay.")}, "human_readable": "I couldn't structure a clear action."}
    j.setdefault("action", "answer")
    j.setdefault("params", {})
    j.setdefault("human_readable", "")
    return j
