import uuid
import re
from datetime import datetime, timezone, timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from db import db
from security import get_current_user
from ai_service import ai_json, ai_complete

router = APIRouter(prefix="/api", tags=["smart-inbox"])

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

async def require_chat(chat_id: str, uid: str) -> dict:
    chat = await db.chats.find_one({"chat_id": chat_id, "participants": uid}, {"_id": 0})
    if not chat:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return chat

async def transcript(chat_id: str, uid: str, limit: int = 160) -> str:
    chat = await require_chat(chat_id, uid)
    users = {}
    async for u in db.users.find({"user_id": {"$in": chat.get("participants", [])}}, {"_id": 0, "user_id": 1, "name": 1}):
        users[u["user_id"]] = u.get("name", "User")
    cur = db.messages.find({"chat_id": chat_id, "deleted": {"$ne": True}, "deleted_for": {"$ne": uid}}, {"_id": 0}).sort("created_at", -1).limit(limit)
    rows = [m async for m in cur]
    rows.reverse()
    return "\n".join(f"[{m.get('created_at','')[:16]}] {('You' if m.get('sender_id') == uid else users.get(m.get('sender_id'), 'User'))}: {m.get('text','')}" for m in rows)

class PriorityBody(BaseModel):
    priority: str = Field(pattern="^(important|normal|low|action_required|follow_up_required)$")
    source: str = Field(default="manual", pattern="^(manual|ai)$")

@router.patch("/messages/{message_id}/priority")
async def set_priority(message_id: str, body: PriorityBody, user: dict = Depends(get_current_user)):
    msg = await db.messages.find_one({"message_id": message_id}, {"_id": 0})
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found.")
    chat = await require_chat(msg["chat_id"], user["user_id"])
    await db.messages.update_one({"message_id": message_id}, {"$set": {"priority": body.priority, "priority_source": body.source, "priority_at": now_iso()}})
    return {"message_id": message_id, "priority": body.priority, "source": body.source}

@router.get("/inbox/smart")
async def smart_inbox(category: str = Query("all", pattern="^(all|important|normal|low|action_required|follow_up_required)$"), user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    chats = [c async for c in db.chats.find({"participants": uid, "deleted_by": {"$ne": uid}}, {"_id": 0, "chat_id": 1})]
    ids = [c["chat_id"] for c in chats]
    query: dict[str, Any] = {"chat_id": {"$in": ids}, "deleted": {"$ne": True}, "deleted_for": {"$ne": uid}}
    if category != "all":
        query["priority"] = category
    cur = db.messages.find(query, {"_id": 0}).sort("created_at", -1).limit(300)
    messages = [m async for m in cur]
    for m in messages:
        m["unread"] = m.get("sender_id") != uid and uid not in m.get("read_by", [])
    grouped = {k: [] for k in ("important", "normal", "low", "action_required", "follow_up_required")}
    for m in messages:
        grouped.setdefault(m.get("priority", "normal"), []).append(m)
    return {"category": category, "messages": messages, "groups": grouped}

class AutopilotRule(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    enabled: bool = True
    summary: bool = True
    suggest_priority: bool = True
    suggest_reminder: bool = True
    suggest_follow_up: bool = True
    chat_ids: list[str] = []

@router.get("/ai/autopilot/rules")
async def list_rules(user: dict = Depends(get_current_user)):
    return {"rules": [r async for r in db.autopilot_rules.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1)]}

@router.post("/ai/autopilot/rules")
async def create_rule(body: AutopilotRule, user: dict = Depends(get_current_user)):
    doc = {"id": str(uuid.uuid4()), "user_id": user["user_id"], **body.model_dump(), "created_at": now_iso(), "updated_at": now_iso()}
    await db.autopilot_rules.insert_one(dict(doc))
    return doc

@router.patch("/ai/autopilot/rules/{rule_id}")
async def update_rule(rule_id: str, body: AutopilotRule, user: dict = Depends(get_current_user)):
    res = await db.autopilot_rules.update_one({"id": rule_id, "user_id": user["user_id"]}, {"$set": {**body.model_dump(), "updated_at": now_iso()}})
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Autopilot rule not found.")
    return await db.autopilot_rules.find_one({"id": rule_id}, {"_id": 0})

@router.delete("/ai/autopilot/rules/{rule_id}")
async def delete_rule(rule_id: str, user: dict = Depends(get_current_user)):
    await db.autopilot_rules.delete_one({"id": rule_id, "user_id": user["user_id"]})
    return {"status": "deleted"}

class AnalyzeBody(BaseModel):
    chat_id: str
    message_ids: list[str] = []

@router.post("/ai/autopilot/analyze")
async def analyze_autopilot(body: AnalyzeBody, user: dict = Depends(get_current_user)):
    text = await transcript(body.chat_id, user["user_id"], 180)
    if not text.strip():
        return {"suggestions": []}
    prompt = ("Analyze only this authorized conversation. Return strict JSON with suggestions, never execute actions. "
              "Each suggestion must have type priority|reminder|follow_up|summary, message_id if known, "
              "title, reason, and params. Consequential actions are suggestions only.\n\n" + text)
    data = await ai_json("You are a cautious inbox automation analyst. Never invent facts or dates.", prompt, max_tokens=1500)
    suggestions = data.get("suggestions", []) if isinstance(data, dict) else []
    return {"suggestions": suggestions[:20], "requires_confirmation": True}

class ConfirmBody(BaseModel):
    suggestion_type: str = Field(pattern="^(priority|reminder|follow_up|summary)$")
    message_id: str | None = None
    title: str = Field(min_length=1, max_length=300)
    priority: str | None = Field(default=None, pattern="^(important|normal|low|action_required|follow_up_required)$")
    remind_at: str | None = None

@router.post("/ai/autopilot/confirm")
async def confirm_autopilot(body: ConfirmBody, user: dict = Depends(get_current_user)):
    if body.suggestion_type == "priority":
        if not body.message_id:
            raise HTTPException(status_code=400, detail="A message is required.")
        msg = await db.messages.find_one({"message_id": body.message_id}, {"_id": 0})
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found.")
        await require_chat(msg["chat_id"], user["user_id"])
        level = body.priority or "important"
        await db.messages.update_one({"message_id": body.message_id}, {"$set": {"priority": level, "priority_source": "ai", "priority_at": now_iso()}})
        return {"status": "priority_updated", "message_id": body.message_id, "priority": level}
    if body.suggestion_type in ("reminder", "follow_up"):
        doc = {"id": str(uuid.uuid4()), "user_id": user["user_id"], "title": body.title.strip(), "remind_at": body.remind_at, "source_message_id": body.message_id, "kind": body.suggestion_type, "done": False, "created_at": now_iso()}
        await db.reminders.insert_one(dict(doc))
        return {"status": "reminder_created", "reminder": doc}
    return {"status": "acknowledged"}

@router.get("/ai/unread-catchup")
async def unread_catchup(user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    cur = db.messages.find({"sender_id": {"$ne": uid}, "read_by": {"$ne": uid}, "deleted": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).limit(120)
    rows = [m async for m in cur]
    if not rows:
        return {"summary": "No unread conversations.", "items": [], "count": 0}
    context = "\n".join(f"[{m.get('message_id')}] {m.get('text','')}" for m in rows)
    data = await ai_json("Summarize unread messages faithfully. Return {summary, important_points, questions, action_items} arrays. Never invent.", context, max_tokens=1200)
    return {**(data if isinstance(data, dict) else {}), "items": rows, "count": len(rows)}

class DigestBody(BaseModel):
    period: str = Field(default="daily", pattern="^(daily|weekly)$")

@router.post("/ai/digest")
async def chat_digest(body: DigestBody, user: dict = Depends(get_current_user)):
    hours = 24 if body.period == "daily" else 168
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    cur = db.messages.find({"created_at": {"$gte": since}, "deleted": {"$ne": True}}, {"_id": 0, "chat_id": 1, "sender_id": 1, "text": 1, "created_at": 1}).sort("created_at", -1).limit(300)
    rows = [m async for m in cur]
    context = "\n".join(f"{m.get('chat_id')}: {m.get('text','')}" for m in rows) or "No messages in this period."
    digest = await ai_json("Create a faithful chat digest. Return {important_conversations, pending_replies, tasks, decisions, follow_ups}. Arrays only; no invented facts.", context, max_tokens=1600)
    return {"period": body.period, "from": since, "message_count": len(rows), "digest": digest}

@router.post("/ai/smart-reminder-suggest")
async def smart_reminder_suggest(body: AnalyzeBody, user: dict = Depends(get_current_user)):
    text = await transcript(body.chat_id, user["user_id"], 120)
    data = await ai_json("Find only messages that explicitly imply a future reminder or promised follow-up. Return {suggestions:[{message_id,title,remind_at,reason}]}. Never create a reminder.", text, max_tokens=900)
    return {"suggestions": (data.get("suggestions", []) if isinstance(data, dict) else []), "requires_confirmation": True}

@router.get("/follow-ups")
async def followups(user: dict = Depends(get_current_user)):
    cur = db.reminders.find({"user_id": user["user_id"], "kind": "follow_up", "done": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).limit(100)
    items = [r async for r in cur]
    return {"items": items}

@router.get("/groups/{chat_id}/assistant")
async def group_assistant(chat_id: str, user: dict = Depends(get_current_user)):
    chat = await require_chat(chat_id, user["user_id"])
    if chat.get("type") != "group":
        raise HTTPException(status_code=400, detail="This is not a group conversation.")
    text = await transcript(chat_id, user["user_id"], 240)
    data = await ai_json("Analyze this group conversation. Return {summary, decisions, action_items, questions, important_messages}. Cite message_id when possible and never invent.", text, max_tokens=1800)
    return {"chat_id": chat_id, "assistant": data}

@router.post("/groups/{chat_id}/decision-maker/analyze")
async def decision_analyze(chat_id: str, user: dict = Depends(get_current_user)):
    await require_chat(chat_id, user["user_id"])
    text = await transcript(chat_id, user["user_id"], 240)
    data = await ai_json("Detect an explicit decision question and options from this group conversation. Return {question, options:[{id,label}], evidence, final_decision:null}. Do not create a poll.", text, max_tokens=1200)
    return {"analysis": data, "requires_confirmation": True}

class PollBody(BaseModel):
    question: str = Field(min_length=1, max_length=400)
    options: list[str] = Field(min_length=2, max_length=10)
    source: str = "confirmed_by_user"

@router.post("/groups/{chat_id}/decision-maker/polls")
async def create_decision_poll(chat_id: str, body: PollBody, user: dict = Depends(get_current_user)):
    chat = await require_chat(chat_id, user["user_id"])
    poll = {"id": str(uuid.uuid4()), "chat_id": chat_id, "user_id": user["user_id"], "question": body.question.strip(), "options": [{"id": str(i), "label": x.strip(), "votes": []} for i, x in enumerate(body.options)], "status": "open", "created_at": now_iso(), "source": body.source}
    await db.group_polls.insert_one(dict(poll))
    return {"poll": poll, "status": "created"}

@router.get("/groups/{chat_id}/decision-maker/polls")
async def list_polls(chat_id: str, user: dict = Depends(get_current_user)):
    await require_chat(chat_id, user["user_id"])
    return {"polls": [p async for p in db.group_polls.find({"chat_id": chat_id}, {"_id": 0}).sort("created_at", -1).limit(30)]}

class VoteBody(BaseModel):
    option_id: str

@router.post("/groups/{chat_id}/decision-maker/polls/{poll_id}/vote")
async def vote_poll(chat_id: str, poll_id: str, body: VoteBody, user: dict = Depends(get_current_user)):
    await require_chat(chat_id, user["user_id"])
    poll = await db.group_polls.find_one({"id": poll_id, "chat_id": chat_id}, {"_id": 0})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found.")
    if not any(o.get("id") == body.option_id for o in poll.get("options", [])):
        raise HTTPException(status_code=400, detail="Option not found.")
    await db.group_polls.update_one({"id": poll_id}, {"$pull": {"options.$[].votes": user["user_id"]}})
    await db.group_polls.update_one({"id": poll_id, "options.id": body.option_id}, {"$addToSet": {"options.$.votes": user["user_id"]}})
    return {"status": "voted"}

@router.post("/groups/{chat_id}/decision-maker/polls/{poll_id}/close")
async def close_poll(chat_id: str, poll_id: str, user: dict = Depends(get_current_user)):
    await require_chat(chat_id, user["user_id"])
    poll = await db.group_polls.find_one({"id": poll_id, "chat_id": chat_id}, {"_id": 0})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found.")
    winner = max(poll.get("options", []), key=lambda x: len(x.get("votes", [])), default=None)
    await db.group_polls.update_one({"id": poll_id}, {"$set": {"status": "closed", "closed_at": now_iso(), "final_decision": winner}})
    return {"status": "closed", "final_decision": winner}
