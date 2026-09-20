"""Phase 2 — all remaining features consolidated (backend).

Endpoints:
- Group Task Manager  (/groups/{chat_id}/tasks)
- Group Meeting Planner (/groups/{chat_id}/meeting)
- Smart Contact Groups (/contact-groups)
- AI Meeting Mode (/ai/meeting-mode)
- AI Negotiation Assistant (/ai/negotiate)
- AI Voice Reply — polish transcript (/ai/voice-reply)
- Voice Commands interpret (/ai/interpret-command)
- Vision helpers (/ai/vision — screenshot/receipt/business-card assistants share this)
- Chat → export (PDF/DOC/PPT/Invoice/Form/Spreadsheet) (/exports/{fmt})
- Message Vault (/vault)
- Temporary Chat TTL (/chats/{id}/ttl)

All AI goes through Sarvam. Consequential actions never fire without the client
explicitly calling a "confirm" endpoint or providing an explicit user token/id.
"""
from __future__ import annotations

import io
import uuid
import base64
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query
from pydantic import BaseModel, Field

from db import db
from security import get_current_user
from ai_service import ai_complete, ai_json
from media_service import transcribe_audio, image_qa

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["phase2"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _require_group(chat_id: str, uid: str) -> dict:
    chat = await db.chats.find_one({"chat_id": chat_id, "participants": uid, "type": "group"}, {"_id": 0})
    if not chat:
        raise HTTPException(status_code=404, detail="Group not found.")
    return chat


async def _require_chat(chat_id: str, uid: str) -> dict:
    chat = await db.chats.find_one({"chat_id": chat_id, "participants": uid}, {"_id": 0})
    if not chat:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return chat


async def _chat_transcript(chat_id: str, uid: str, limit: int = 200) -> str:
    chat = await _require_chat(chat_id, uid)
    names: dict[str, str] = {}
    async for u in db.users.find({"user_id": {"$in": chat["participants"]}}, {"_id": 0, "user_id": 1, "name": 1}):
        names[u["user_id"]] = "You" if u["user_id"] == uid else u.get("name", "User")
    cur = db.messages.find({"chat_id": chat_id, "deleted": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).limit(limit)
    rows = [m async for m in cur]
    rows.reverse()
    return "\n".join(f"[{(m.get('created_at','')[:16]).replace('T',' ')}] {names.get(m.get('sender_id'),'User')}: {m.get('text','')}" for m in rows)


# ============================================================================
# 1. GROUP TASK MANAGER
class GroupTaskBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    assignee_id: str | None = None
    due_at: str | None = None          # ISO
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")
    notes: str | None = Field(default=None, max_length=1000)


class GroupTaskPatch(BaseModel):
    title: str | None = None
    assignee_id: str | None = None
    due_at: str | None = None
    status: str | None = Field(default=None, pattern="^(open|in_progress|done)$")
    priority: str | None = Field(default=None, pattern="^(low|normal|high)$")
    notes: str | None = None


@router.post("/groups/{chat_id}/tasks")
async def create_group_task(chat_id: str, body: GroupTaskBody, user: dict = Depends(get_current_user)):
    chat = await _require_group(chat_id, user["user_id"])
    if body.assignee_id and body.assignee_id not in chat["participants"]:
        raise HTTPException(status_code=400, detail="Assignee must be a group member.")
    doc = {"id": str(uuid.uuid4()), "chat_id": chat_id, "created_by": user["user_id"],
           "title": body.title.strip(), "assignee_id": body.assignee_id, "due_at": body.due_at,
           "priority": body.priority, "notes": (body.notes or "").strip(), "status": "open",
           "created_at": _now(), "updated_at": _now()}
    await db.group_tasks.insert_one(dict(doc))
    return doc


@router.get("/groups/{chat_id}/tasks")
async def list_group_tasks(chat_id: str, user: dict = Depends(get_current_user)):
    await _require_group(chat_id, user["user_id"])
    cur = db.group_tasks.find({"chat_id": chat_id}, {"_id": 0}).sort("created_at", -1)
    return {"tasks": [t async for t in cur]}


@router.patch("/groups/{chat_id}/tasks/{task_id}")
async def update_group_task(chat_id: str, task_id: str, body: GroupTaskPatch, user: dict = Depends(get_current_user)):
    await _require_group(chat_id, user["user_id"])
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")
    updates["updated_at"] = _now()
    res = await db.group_tasks.update_one({"id": task_id, "chat_id": chat_id}, {"$set": updates})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Task not found.")
    return await db.group_tasks.find_one({"id": task_id}, {"_id": 0})


@router.delete("/groups/{chat_id}/tasks/{task_id}")
async def delete_group_task(chat_id: str, task_id: str, user: dict = Depends(get_current_user)):
    await _require_group(chat_id, user["user_id"])
    await db.group_tasks.delete_one({"id": task_id, "chat_id": chat_id})
    return {"status": "deleted"}


# ============================================================================
# 2. GROUP MEETING PLANNER
class SlotBody(BaseModel):
    slots: list[str] = Field(min_length=1, max_length=30)  # ISO datetimes


@router.post("/groups/{chat_id}/meeting/availability")
async def submit_availability(chat_id: str, body: SlotBody, user: dict = Depends(get_current_user)):
    await _require_group(chat_id, user["user_id"])
    doc = {"chat_id": chat_id, "user_id": user["user_id"], "slots": body.slots, "updated_at": _now()}
    await db.meeting_availability.update_one(
        {"chat_id": chat_id, "user_id": user["user_id"]}, {"$set": doc}, upsert=True,
    )
    return {"status": "saved", "slots": body.slots}


@router.get("/groups/{chat_id}/meeting/common")
async def common_slots(chat_id: str, user: dict = Depends(get_current_user)):
    chat = await _require_group(chat_id, user["user_id"])
    docs = [d async for d in db.meeting_availability.find({"chat_id": chat_id}, {"_id": 0})]
    counter: dict[str, list[str]] = {}
    for d in docs:
        for s in d.get("slots", []):
            counter.setdefault(s, []).append(d["user_id"])
    total = len(chat["participants"])
    # slots ranked by how many of the group are available
    ranked = sorted(counter.items(), key=lambda x: (-len(x[1]), x[0]))
    return {"total_members": total,
            "suggestions": [{"slot": s, "available": u, "coverage": round(len(u) / max(total, 1), 2)} for s, u in ranked[:12]]}


class ConfirmMeetingBody(BaseModel):
    slot: str
    title: str = "Team meeting"
    location: str | None = None


@router.post("/groups/{chat_id}/meeting/confirm")
async def confirm_meeting(chat_id: str, body: ConfirmMeetingBody, user: dict = Depends(get_current_user)):
    """Explicit user confirmation creates the calendar event for the caller and posts a
    system message in the group so everyone sees the plan."""
    chat = await _require_group(chat_id, user["user_id"])
    doc = {"id": str(uuid.uuid4()), "user_id": user["user_id"], "title": body.title.strip(),
           "when": body.slot, "location": body.location, "source_chat_id": chat_id, "created_at": _now()}
    await db.calendar_events.insert_one(dict(doc))
    # System message in group
    await db.messages.insert_one({
        "message_id": str(uuid.uuid4()), "chat_id": chat_id, "sender_id": "system",
        "text": f"Meeting scheduled: {body.title} on {body.slot}" + (f" at {body.location}" if body.location else ""),
        "type": "system", "status": "sent", "reactions": {}, "starred_by": [],
        "read_by": [], "edited": False, "deleted": False, "created_at": _now(),
    })
    doc.pop("_id", None)
    return {"status": "confirmed", "event": doc, "participants": chat["participants"]}


# ============================================================================
# 3. SMART CONTACT GROUPS (labels on contact edge)
class ContactLabelBody(BaseModel):
    contact_id: str
    labels: list[str] = Field(default_factory=list, max_length=8)  # e.g. ["family","work"]


@router.get("/contact-groups")
async def list_contact_groups(user: dict = Depends(get_current_user)):
    cur = db.contacts.find({"user_id": user["user_id"]}, {"_id": 0})
    labels: dict[str, list[str]] = {}
    async for c in cur:
        for l in c.get("labels", []) or []:
            labels.setdefault(l, []).append(c["contact_id"])
    presets = ["family", "friends", "work", "college"]
    for p in presets:
        labels.setdefault(p, [])
    return {"groups": [{"label": k, "contact_ids": v, "count": len(v)} for k, v in labels.items()]}


@router.put("/contact-groups")
async def set_contact_labels(body: ContactLabelBody, user: dict = Depends(get_current_user)):
    clean = list({(l or "").strip().lower() for l in body.labels if (l or "").strip()})
    await db.contacts.update_one(
        {"user_id": user["user_id"], "contact_id": body.contact_id},
        {"$set": {"labels": clean, "updated_at": _now()}},
        upsert=True,
    )
    return {"contact_id": body.contact_id, "labels": clean}


# ============================================================================
# 4-6. Vision assistants (screenshot / receipt / business card)
#     Shared endpoint — the "kind" changes the prompt/schema, image goes to Sarvam Vision.

class VisionMode(BaseModel):
    kind: str = Field(pattern="^(screenshot|receipt|business_card|generic)$")
    prompt: str | None = None


@router.post("/ai/vision")
async def ai_vision(file: UploadFile = File(...), kind: str = Form("generic"),
                    prompt: str | None = Form(None), user: dict = Depends(get_current_user)):
    kind = kind if kind in ("screenshot", "receipt", "business_card", "generic") else "generic"
    data = await file.read()
    if not data or len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image must be under 20 MB.")

    kind_prompts = {
        "screenshot": (
            "Read the screenshot precisely. Return JSON with keys: title, summary, extracted_text, "
            "actions[]. Actions are short suggested next steps for the user (e.g. 'Reply to this message', "
            "'Save the phone number 9876543210'). Never invent numbers or names."
        ),
        "receipt": (
            "This is a receipt or invoice. Extract JSON: merchant, date (ISO if possible), currency, total, tax, "
            "items[] (each: name, qty, unit_price, amount). Any unknown field must be null. Do NOT invent."
        ),
        "business_card": (
            "This is a business card. Extract JSON: name, company, title, phone (E.164 if possible), email, "
            "website, address. Any unknown field must be null. Do NOT invent."
        ),
        "generic": prompt or "Describe what you see in this image faithfully. Never invent facts.",
    }
    q = kind_prompts[kind]
    text = await image_qa(data, file.content_type or "image/jpeg", q)
    # Try JSON-parse the vision output when appropriate; keep raw string otherwise.
    parsed: Any = None
    if kind in ("screenshot", "receipt", "business_card"):
        try:
            import json as _json
            start = min([i for i in [text.find("{"), text.find("[")] if i != -1] or [0])
            end = max(text.rfind("}"), text.rfind("]"))
            parsed = _json.loads(text[start:end + 1]) if end != -1 else None
        except Exception:
            parsed = None
    return {"kind": kind, "data": parsed, "text": text}


# ============================================================================
# 7. DOCUMENT SCANNER — client uploads pre-processed images, backend stores as
#    multi-page "scan" attachment. Uses existing /files object storage.
class ScanPagesBody(BaseModel):
    pages: list[str]                          # storage_paths (already uploaded)
    name: str = Field(default="Scanned Document", max_length=120)
    chat_id: str | None = None


@router.post("/ai/document-scan/save")
async def save_document_scan(body: ScanPagesBody, user: dict = Depends(get_current_user)):
    doc = {"id": str(uuid.uuid4()), "user_id": user["user_id"], "name": body.name.strip() or "Scanned Document",
           "pages": body.pages, "chat_id": body.chat_id, "created_at": _now()}
    await db.document_scans.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("/ai/document-scan")
async def list_document_scans(user: dict = Depends(get_current_user)):
    cur = db.document_scans.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).limit(80)
    return {"scans": [s async for s in cur]}


@router.delete("/ai/document-scan/{sid}")
async def delete_document_scan(sid: str, user: dict = Depends(get_current_user)):
    await db.document_scans.delete_one({"id": sid, "user_id": user["user_id"]})
    return {"status": "deleted"}


# ============================================================================
# 8. VOICE COMMANDS interpret
class InterpretBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/ai/interpret-command")
async def interpret_command(body: InterpretBody, user: dict = Depends(get_current_user)):
    data = await ai_json(
        "Classify the spoken user command. Return strict JSON with intent (one of: "
        "reminder|task|message_draft|unread_summary|meeting_mode|search|other), "
        "params (title, when, person, chat, text) and a friendly confirmation. Never send/create anything.",
        f"Command: {body.text}\n\nReturn JSON: {{\"intent\": \"...\", \"params\": {{}}, \"confirmation\": \"...\", \"requires_confirmation\": true}}",
        max_tokens=500,
    )
    if not isinstance(data, dict):
        data = {"intent": "other", "params": {}, "confirmation": "Sorry, I didn't understand."}
    data["requires_confirmation"] = True
    return data


# ============================================================================
# 9. AI VOICE REPLY — client uploads audio, we transcribe (Sarvam) + polish, return
#    a draft the user can edit and send. Never sends automatically.
@router.post("/ai/voice-reply")
async def voice_reply(file: UploadFile = File(...), tone: str = Form("friendly"),
                       out_lang: str = Form(""), user: dict = Depends(get_current_user)):
    audio = await file.read()
    if not audio or len(audio) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Voice clip must be under 15 MB.")
    try:
        raw = await transcribe_audio(audio, file.filename or "voice.m4a", "auto")
    except Exception as e:
        logger.error("voice_reply STT failed: %s", e)
        raise HTTPException(status_code=502, detail="Could not transcribe your voice note.")
    if not raw.strip():
        return {"transcript": "", "draft": "", "requires_confirmation": True}
    lang_clause = f" Write the polished output in {out_lang}." if out_lang.strip() else ""
    draft = await ai_complete(
        "You polish a transcribed voice note into a natural message the user can send. Never invent facts.",
        f"Polish this transcript into a {tone} message.{lang_clause}\n\nTranscript:\n{raw}\n\nReturn only the message text.",
        temperature=0.4, max_tokens=600,
    )
    return {"transcript": raw, "draft": draft.strip(), "requires_confirmation": True}


# ============================================================================
# 10. AI MEETING MODE — extract structured decisions/action items from a chat range
class MeetingModeBody(BaseModel):
    chat_id: str
    hours: int = Field(default=24, ge=1, le=24 * 14)


@router.post("/ai/meeting-mode")
async def meeting_mode(body: MeetingModeBody, user: dict = Depends(get_current_user)):
    await _require_chat(body.chat_id, user["user_id"])
    since = (datetime.now(timezone.utc) - timedelta(hours=body.hours)).isoformat()
    cur = db.messages.find({"chat_id": body.chat_id, "created_at": {"$gte": since}, "deleted": {"$ne": True}}, {"_id": 0}).sort("created_at", 1)
    rows = [m async for m in cur]
    if not rows:
        return {"summary": "", "participants": [], "decisions": [], "action_items": [], "deadlines": [], "open_questions": []}
    names: dict[str, str] = {}
    async for u in db.users.find({"user_id": {"$in": list({m["sender_id"] for m in rows})}}, {"_id": 0, "user_id": 1, "name": 1}):
        names[u["user_id"]] = u.get("name", "User")
    transcript = "\n".join(f"[{m['created_at'][:16].replace('T',' ')}] {names.get(m['sender_id'],'User')}: {m['text']}" for m in rows)
    data = await ai_json(
        "You analyze a meeting/conversation transcript faithfully. Return JSON: summary, participants[], "
        "decisions[], action_items[{owner,title,due}], deadlines[], open_questions[]. Never invent.",
        transcript, max_tokens=1800,
    )
    return data if isinstance(data, dict) else {}


# ============================================================================
# 11. AI NEGOTIATION ASSISTANT — multiple reply approaches, never sends.
class NegotiateBody(BaseModel):
    chat_id: str
    goal: str = Field(min_length=1, max_length=500)


@router.post("/ai/negotiate")
async def negotiate(body: NegotiateBody, user: dict = Depends(get_current_user)):
    transcript = await _chat_transcript(body.chat_id, user["user_id"], 80)
    data = await ai_json(
        "You are a negotiation coach. Return strict JSON with 3 reply approaches: collaborative, firm, and "
        "creative_alternative. Each: {name, message, why_it_works, risks}. Only propose — never send.",
        f"User's goal: {body.goal}\n\nConversation so far:\n{transcript}",
        max_tokens=1400,
    )
    if not isinstance(data, dict):
        data = {"approaches": []}
    data["requires_confirmation"] = True
    return data


# ============================================================================
# 12. CHAT → EXPORTS (PDF / DOC / PPT-like markdown / Invoice / Form / Spreadsheet)
class ExportBody(BaseModel):
    chat_id: str
    kind: str = Field(pattern="^(pdf|doc|pptx|invoice|form|spreadsheet)$")
    prompt: str | None = None


@router.post("/exports")
async def export_chat(body: ExportBody, user: dict = Depends(get_current_user)):
    """Turn a conversation into a structured deliverable. Never sends/finalizes;
    returns editable content the user can review + share."""
    transcript = await _chat_transcript(body.chat_id, user["user_id"], 200)
    if not transcript.strip():
        raise HTTPException(status_code=400, detail="This conversation has no messages to export.")
    kind = body.kind
    goal = (body.prompt or "").strip()

    if kind == "pptx":
        data = await ai_json(
            "Convert the conversation into a presentation outline. Return JSON: title, subtitle, slides[] "
            "each with heading, bullets[], notes. Never invent numbers/dates.",
            f"{goal}\n\nConversation:\n{transcript}", max_tokens=2000,
        )
        return {"kind": "pptx", "editable": True, "content": data}

    if kind == "spreadsheet":
        data = await ai_json(
            "Convert the conversation into a spreadsheet. Return JSON: title, columns[], rows[[...]], summary. "
            "Never invent values.",
            f"{goal}\n\nConversation:\n{transcript}", max_tokens=2000,
        )
        return {"kind": "spreadsheet", "editable": True, "content": data}

    if kind == "invoice":
        data = await ai_json(
            "Draft an invoice/quotation from the conversation. Return JSON: title, from, to, date, due_date, "
            "currency, items[{description,qty,unit_price,amount}], subtotal, tax, total, notes. Do NOT finalize or send.",
            f"{goal}\n\nConversation:\n{transcript}", max_tokens=1600,
        )
        return {"kind": "invoice", "editable": True, "content": data}

    if kind == "form":
        data = await ai_json(
            "Design a structured form from the conversation. Return JSON: title, description, "
            "fields[{label,name,type(text|number|date|email|choice),required,options[]}]. Never invent.",
            f"{goal}\n\nConversation:\n{transcript}", max_tokens=1200,
        )
        return {"kind": "form", "editable": True, "content": data}

    # doc / pdf: markdown-first (client can render to PDF locally or share text)
    md = await ai_complete(
        "You convert conversations into a clean document. Use markdown headings. Never invent.",
        f"Goal: {goal or 'Turn this conversation into a well-structured document.'}\n\nConversation:\n{transcript}",
        temperature=0.3, max_tokens=1800,
    )
    return {"kind": kind, "editable": True, "content": {"markdown": md.strip(),
             "hint": "Client can render markdown to PDF/DOC using expo-print or share as text."}}


# ============================================================================
# 13. MESSAGE VAULT (protected local secrets — server keeps only ciphertext blobs)
class VaultBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="note", pattern="^(note|file|password|other)$")
    ciphertext: str = Field(min_length=1, max_length=200_000)   # base64 or opaque string
    iv: str | None = None
    meta: dict[str, Any] | None = None


@router.get("/vault")
async def list_vault(user: dict = Depends(get_current_user)):
    cur = db.vault.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1)
    return {"items": [v async for v in cur]}


@router.post("/vault")
async def add_vault(body: VaultBody, user: dict = Depends(get_current_user)):
    doc = {"id": str(uuid.uuid4()), "user_id": user["user_id"], "title": body.title.strip(),
           "kind": body.kind, "ciphertext": body.ciphertext, "iv": body.iv, "meta": body.meta or {},
           "created_at": _now(), "updated_at": _now()}
    await db.vault.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.delete("/vault/{vid}")
async def delete_vault(vid: str, user: dict = Depends(get_current_user)):
    await db.vault.delete_one({"id": vid, "user_id": user["user_id"]})
    return {"status": "deleted"}


# ============================================================================
# 14. TEMPORARY CHAT — per-chat message TTL default that new sends auto-inherit.
class ChatTTLBody(BaseModel):
    seconds: int | None = Field(default=None, ge=60, le=60 * 60 * 24 * 30)  # None disables


@router.post("/chats/{chat_id}/ttl")
async def set_chat_ttl(chat_id: str, body: ChatTTLBody, user: dict = Depends(get_current_user)):
    await _require_chat(chat_id, user["user_id"])
    if body.seconds is None:
        await db.chats.update_one({"chat_id": chat_id}, {"$unset": {f"ttl.{user['user_id']}": ""}})
        return {"ttl_seconds": None}
    await db.chats.update_one({"chat_id": chat_id}, {"$set": {f"ttl.{user['user_id']}": int(body.seconds)}})
    return {"ttl_seconds": int(body.seconds)}


@router.get("/chats/{chat_id}/ttl")
async def get_chat_ttl(chat_id: str, user: dict = Depends(get_current_user)):
    chat = await _require_chat(chat_id, user["user_id"])
    return {"ttl_seconds": (chat.get("ttl") or {}).get(user["user_id"])}
