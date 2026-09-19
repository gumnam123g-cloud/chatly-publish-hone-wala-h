import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from db import db
from security import get_current_user
from ai_service import ai_complete, ai_json, tavily_search, AIServiceError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["ai"])

CHATLY_SYSTEM = (
    "You are Chatly, an AI-native communication assistant living inside the Chatly messaging app. "
    "You are intelligent, fast, helpful, warm and professional. You understand English, Hindi and Hinglish "
    "and reply in the user's language. Be concise and practical. Never fabricate messages, files, people, "
    "dates or sources. Clearly separate facts from suggestions. Do not use emojis."
)


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _authorized(user_id: str) -> bool:
    p = await db.privacy.find_one({"user_id": user_id}, {"_id": 0})
    return bool(p and p.get("messages", True))


async def _chat_transcript(chat_id: str, user_id: str, limit: int = 200) -> tuple[str, dict]:
    chat = await db.chats.find_one({"chat_id": chat_id, "participants": user_id})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    names = {}
    for pid in chat["participants"]:
        u = await db.users.find_one({"user_id": pid}, {"_id": 0})
        names[pid] = ("You" if pid == user_id else (u["name"] if u else "Unknown"))
    cursor = db.messages.find({"chat_id": chat_id, "deleted": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).limit(limit)
    msgs = [m async for m in cursor]
    msgs.reverse()
    lines = []
    for m in msgs:
        ts = m["created_at"][:16].replace("T", " ")
        lines.append(f"[{ts}] {names.get(m['sender_id'],'Unknown')}: {m['text']}")
    return "\n".join(lines), chat


# ---------------- Chatly Assistant ----------------
class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None


@router.post("/chat")
async def chatly_chat(body: ChatBody, user: dict = Depends(get_current_user)):
    conv_id = body.conversation_id
    if not conv_id:
        conv_id = str(uuid.uuid4())
        await db.ai_conversations.insert_one({
            "conversation_id": conv_id, "user_id": user["user_id"],
            "title": body.message[:48], "created_at": _now(), "updated_at": _now(),
        })
    history = db.ai_messages.find({"conversation_id": conv_id}, {"_id": 0}).sort("created_at", 1).limit(20)
    msgs = [{"role": "system", "content": CHATLY_SYSTEM}]
    async for m in history:
        msgs.append({"role": m["role"], "content": m["text"]})
    msgs.append({"role": "user", "content": body.message})

    await db.ai_messages.insert_one({
        "message_id": str(uuid.uuid4()), "conversation_id": conv_id, "user_id": user["user_id"],
        "role": "user", "text": body.message, "created_at": _now(),
    })
    reply = await ai_complete(CHATLY_SYSTEM,
                              "\n".join([f"{m['role']}: {m['content']}" for m in msgs if m["role"] != "system"]),
                              temperature=0.6, max_tokens=1400)
    await db.ai_messages.insert_one({
        "message_id": str(uuid.uuid4()), "conversation_id": conv_id, "user_id": user["user_id"],
        "role": "assistant", "text": reply, "created_at": _now(),
    })
    await db.ai_conversations.update_one({"conversation_id": conv_id}, {"$set": {"updated_at": _now()}})
    return {"conversation_id": conv_id, "reply": reply}


@router.get("/conversations")
async def list_conversations(user: dict = Depends(get_current_user)):
    cursor = db.ai_conversations.find({"user_id": user["user_id"]}, {"_id": 0}).sort("updated_at", -1).limit(50)
    return {"conversations": [c async for c in cursor]}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, user: dict = Depends(get_current_user)):
    cursor = db.ai_messages.find({"conversation_id": conversation_id, "user_id": user["user_id"]},
                                 {"_id": 0}).sort("created_at", 1)
    return {"messages": [m async for m in cursor]}


# ---------------- Smart Reply ----------------
class SmartReplyBody(BaseModel):
    chat_id: str


@router.post("/smart-reply")
async def smart_reply(body: SmartReplyBody, user: dict = Depends(get_current_user)):
    transcript, _ = await _chat_transcript(body.chat_id, user["user_id"], limit=12)
    data = await ai_json(
        "You generate 3 short, natural reply suggestions the user could send next in this chat. "
        "Match the language (English/Hindi/Hinglish) and tone of the conversation.",
        f"Conversation:\n{transcript}\n\nReturn JSON: {{\"replies\": [\"...\", \"...\", \"...\"]}}",
        max_tokens=400,
    )
    replies = data.get("replies", []) if isinstance(data, dict) else []
    return {"replies": replies[:3]}


# ---------------- Message actions ----------------
class MsgActionBody(BaseModel):
    text: str
    action: str  # rewrite/improve/grammar/translate/summarize/explain/shorten/expand/reply/smart_reply
    tone: str | None = None
    target_lang: str | None = None   # translation target
    out_lang: str | None = None      # per-action output language for summarize/explain/reply
    context: str | None = None       # recent conversation context for reply drafts


@router.post("/message-action")
async def message_action(body: MsgActionBody, user: dict = Depends(get_current_user)):
    a = (body.action or "").strip()
    out_lang = (body.out_lang or "").strip()
    tgt = (body.target_lang or body.out_lang or "English").strip() or "English"
    lang_clause = f" Write the output in {out_lang}." if out_lang else " Match the language of the input."

    instructions = {
        "rewrite": "Rewrite the following message to be clearer and better while keeping the meaning.",
        "improve": "Improve the wording and flow of the following message.",
        "grammar": "Fix grammar and spelling in the following message. Return only the corrected text.",
        "translate": (f"Detect the source language automatically, then translate the message to {tgt}. "
                      f"Preserve emojis, numbers, names, URLs and formatting exactly. "
                      f"Do NOT summarize, explain or add anything. Return ONLY the translated text."),
        "summarize": f"Summarize the following message in one short, faithful line.{lang_clause}",
        "explain": f"Explain what the following message means in simple, clear terms.{lang_clause}",
        "shorten": "Make the following message shorter and more direct.",
        "expand": "Expand the following message with a bit more detail and politeness.",
        "professional": "Rewrite the following message in a professional tone.",
        "friendly": "Rewrite the following message in a friendly, warm tone.",
        "casual": "Rewrite the following message in a casual tone.",
        "polite": "Rewrite the following message in a polite tone.",
        "firm": "Rewrite the following message in a firm, direct tone.",
        "apologetic": "Rewrite the following message in an apologetic tone.",
    }

    if a == "reply":
        tone = (body.tone or "friendly").strip()
        ctx = f"\n\nConversation context (most recent last):\n{body.context}" if body.context else ""
        instr = (f"Draft a natural reply to the incoming message below. Use a {tone} tone.{lang_clause} "
                 f"Base it on the conversation context if provided. Return ONLY the reply text, no quotes.{ctx}")
        result = await ai_complete(
            "You are a helpful reply-drafting assistant. Never invent facts. Return only the reply text.",
            f"{instr}\n\nIncoming message:\n{body.text}", temperature=0.6, max_tokens=600,
        )
        return {"result": result.strip(), "action": a, "out_lang": out_lang or None}

    instr = instructions.get(a, "Rewrite the following message.")
    if body.tone and a in ("rewrite", "improve"):
        instr += f" Use a {body.tone} tone."
    result = await ai_complete(
        "You are a writing assistant. Return only the result text, no preamble, no quotes.",
        f"{instr}\n\nMessage:\n{body.text}", temperature=0.4, max_tokens=1000,
    )
    return {"result": result.strip(), "action": a, "out_lang": (tgt if a == "translate" else out_lang) or None}


# ---------------- Chat Brain (summary / decisions / timeline) ----------------
class ChatBrainBody(BaseModel):
    chat_id: str
    kind: str = "summary"  # summary/decisions/timeline/important/pending/find
    query: str | None = None
    out_lang: str | None = None  # output language for the result


@router.post("/chat-brain")
async def chat_brain(body: ChatBrainBody, user: dict = Depends(get_current_user)):
    if not await _authorized(user["user_id"]):
        raise HTTPException(status_code=403, detail="Chat intelligence is disabled in your privacy settings.")
    transcript, chat = await _chat_transcript(body.chat_id, user["user_id"])
    if not transcript.strip():
        return {"kind": body.kind, "result": "There are no messages in this conversation yet."}
    kind = body.kind
    lang = (body.out_lang or "").strip()
    lang_clause = f" Write the entire response in {lang}." if lang else ""
    if kind == "summary":
        prompt = f"Summarize this conversation clearly in a few bullet points.{lang_clause}\n\n{transcript}"
    elif kind == "decisions":
        prompt = f"List the key decisions made in this conversation. If none, say so.{lang_clause}\n\n{transcript}"
    elif kind == "timeline":
        prompt = f"Build a short chronological timeline of key events (date - event).{lang_clause}\n\n{transcript}"
    elif kind == "important":
        prompt = f"List the most important messages/points from this conversation.{lang_clause}\n\n{transcript}"
    elif kind == "pending":
        prompt = f"List pending replies and open questions the user still needs to respond to.{lang_clause}\n\n{transcript}"
    elif kind == "find" and body.query:
        prompt = (f"Answer this question using ONLY the conversation below. Quote the relevant message and its "
                  f"timestamp as the source. If not found, say you couldn't find it.{lang_clause}\n\nQuestion: {body.query}\n\n{transcript}")
    else:
        prompt = f"Summarize this conversation.{lang_clause}\n\n{transcript}"
    result = await ai_complete(CHATLY_SYSTEM, prompt, temperature=0.4, max_tokens=1200)
    return {"kind": kind, "result": result.strip()}


# ---------------- Task / deadline extraction ----------------
class ExtractBody(BaseModel):
    chat_id: str | None = None
    text: str | None = None


@router.post("/extract")
async def extract_actions(body: ExtractBody, user: dict = Depends(get_current_user)):
    if body.chat_id:
        content, _ = await _chat_transcript(body.chat_id, user["user_id"], limit=60)
    else:
        content = body.text or ""
    if not content.strip():
        return {"items": []}
    data = await ai_json(
        "Extract actionable items from the text: tasks, deadlines, meetings and important commitments. "
        "Only extract what is actually present. Never invent.",
        f"Text:\n{content}\n\nReturn JSON: {{\"items\": [{{\"type\": \"task|deadline|meeting|followup\", "
        f"\"title\": \"...\", \"when\": \"natural language date/time or empty\", \"person\": \"name or empty\"}}]}}",
        max_tokens=900,
    )
    items = data.get("items", []) if isinstance(data, dict) else []
    return {"items": items, "source_chat": body.chat_id}


# ---------------- Ask Your Chats (cross-chat search + answer) ----------------
class AskChatsBody(BaseModel):
    query: str = Field(min_length=1)


@router.post("/ask-chats")
async def ask_chats(body: AskChatsBody, user: dict = Depends(get_current_user)):
    if not await _authorized(user["user_id"]):
        raise HTTPException(status_code=403, detail="Chat intelligence is disabled in your privacy settings.")
    # naive keyword prefilter across authorized chats
    chats = db.chats.find({"participants": user["user_id"]}, {"_id": 0})
    chat_ids = [c["chat_id"] async for c in chats]
    terms = [t for t in body.query.lower().split() if len(t) > 2]
    matched = []
    async for m in db.messages.find({"chat_id": {"$in": chat_ids}, "deleted": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).limit(600):
        low = m["text"].lower()
        score = sum(1 for t in terms if t in low)
        if score:
            matched.append((score, m))
    matched.sort(key=lambda x: x[0], reverse=True)
    top = [m for _, m in matched[:25]]
    sources = []
    ctx_lines = []
    for m in top:
        u = await db.users.find_one({"user_id": m["sender_id"]}, {"_id": 0})
        chat = await db.chats.find_one({"chat_id": m["chat_id"]}, {"_id": 0})
        other_ids = [p for p in (chat["participants"] if chat else []) if p != user["user_id"]]
        ou = await db.users.find_one({"user_id": other_ids[0]}, {"_id": 0}) if other_ids else None
        sender = "You" if m["sender_id"] == user["user_id"] else (u["name"] if u else "Unknown")
        chat_name = ou["name"] if ou else "Chat"
        ts = m["created_at"][:16].replace("T", " ")
        ctx_lines.append(f"[{chat_name} | {ts}] {sender}: {m['text']}")
        sources.append({"chat_id": m["chat_id"], "message_id": m["message_id"],
                        "chat_name": chat_name, "sender": sender, "ts": m["created_at"], "text": m["text"]})
    await db.ai_search_history.insert_one({
        "id": str(uuid.uuid4()), "user_id": user["user_id"], "query": body.query,
        "created_at": _now(),
    })
    if not ctx_lines:
        return {"answer": "I couldn't find a matching result in your conversations.", "sources": []}
    answer = await ai_complete(
        CHATLY_SYSTEM + " Answer using ONLY the provided messages. Cite the chat and time. If unsure, say so.",
        f"Question: {body.query}\n\nRelevant messages:\n" + "\n".join(ctx_lines),
        temperature=0.3, max_tokens=900,
    )
    return {"answer": answer.strip(), "sources": sources[:6]}


# ---------------- Deep Research (Tavily + AI) ----------------
class ResearchBody(BaseModel):
    query: str = Field(min_length=1)


@router.post("/research")
async def deep_research(body: ResearchBody, user: dict = Depends(get_current_user)):
    p = await db.privacy.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if p and not p.get("web_search", True):
        raise HTTPException(status_code=403, detail="Web search is disabled in your privacy settings.")
    try:
        tav = await tavily_search(body.query, max_results=6)
    except AIServiceError:
        raise  # handled globally with a user-safe message + category
    except Exception as e:
        logger.error(f"Tavily error: {e}")
        raise HTTPException(status_code=502, detail="Web search failed. Please try again.")
    results = tav.get("results", [])
    sources = [{"title": r.get("title"), "url": r.get("url"),
                "content": (r.get("content") or "")[:500]} for r in results]
    src_text = "\n\n".join([f"[{i+1}] {s['title']} ({s['url']})\n{s['content']}" for i, s in enumerate(sources)])
    report = await ai_complete(
        CHATLY_SYSTEM + " Write a well-structured research report with clear sections and cite sources as [1], [2] "
        "matching the provided sources. Never invent sources.",
        f"Research question: {body.query}\n\nWeb sources:\n{src_text}\n\nWrite the report now.",
        temperature=0.4, max_tokens=1800,
    )
    rid = str(uuid.uuid4())
    doc = {"id": rid, "user_id": user["user_id"], "query": body.query, "report": report.strip(),
           "sources": [{"title": s["title"], "url": s["url"]} for s in sources], "created_at": _now()}
    await db.research_history.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("/research")
async def research_history(user: dict = Depends(get_current_user)):
    cursor = db.research_history.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).limit(50)
    return {"research": [r async for r in cursor]}


# ---------------- AI Creation Studio ----------------
class CreateBody(BaseModel):
    kind: str  # document/presentation/spreadsheet/notes/plan/checklist
    prompt: str = Field(min_length=1)
    chat_id: str | None = None


@router.post("/create")
async def ai_create(body: CreateBody, user: dict = Depends(get_current_user)):
    context = ""
    if body.chat_id:
        context, _ = await _chat_transcript(body.chat_id, user["user_id"], limit=80)
        context = f"\n\nUse this conversation as source material:\n{context}"
    kind = body.kind
    if kind == "presentation":
        data = await ai_json(
            "You create presentation outlines. Only use facts present in the prompt/context; never fabricate sources.",
            f"Create a presentation for: {body.prompt}{context}\n\nReturn JSON: {{\"title\": \"...\", "
            f"\"slides\": [{{\"heading\": \"...\", \"bullets\": [\"...\"], \"notes\": \"speaker notes\"}}]}}",
            max_tokens=2200,
        )
        title = data.get("title", body.prompt[:60]) if isinstance(data, dict) else body.prompt[:60]
        content = data
    elif kind == "spreadsheet":
        data = await ai_json(
            "You create spreadsheets. Only use data present in the prompt/context. Never invent numbers.",
            f"Create a spreadsheet for: {body.prompt}{context}\n\nReturn JSON: {{\"title\": \"...\", "
            f"\"columns\": [\"...\"], \"rows\": [[\"...\"]], \"summary\": \"...\"}}",
            max_tokens=2000,
        )
        title = data.get("title", body.prompt[:60]) if isinstance(data, dict) else body.prompt[:60]
        content = data
    else:
        text = await ai_complete(
            CHATLY_SYSTEM + f" You are creating a {kind}. Use clear markdown formatting with headings.",
            f"Create a {kind} for: {body.prompt}{context}", temperature=0.5, max_tokens=2000,
        )
        title = body.prompt[:60]
        content = {"markdown": text.strip()}
    cid = str(uuid.uuid4())
    doc = {"id": cid, "user_id": user["user_id"], "kind": kind, "title": title,
           "prompt": body.prompt, "content": content, "created_at": _now()}
    await db.ai_creations.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("/creations")
async def list_creations(user: dict = Depends(get_current_user)):
    cursor = db.ai_creations.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).limit(100)
    return {"creations": [c async for c in cursor]}


@router.delete("/creations/{cid}")
async def delete_creation(cid: str, user: dict = Depends(get_current_user)):
    await db.ai_creations.delete_one({"id": cid, "user_id": user["user_id"]})
    return {"status": "deleted"}


# ---------------- AI Memory ----------------
class MemoryBody(BaseModel):
    text: str = Field(min_length=1, max_length=500)


@router.post("/memory")
async def add_memory(body: MemoryBody, user: dict = Depends(get_current_user)):
    mid = str(uuid.uuid4())
    doc = {"id": mid, "user_id": user["user_id"], "text": body.text.strip(),
           "source": "user", "created_at": _now()}
    await db.ai_memories.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("/memory")
async def list_memory(user: dict = Depends(get_current_user)):
    cursor = db.ai_memories.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1)
    return {"memories": [m async for m in cursor]}


@router.delete("/memory/{mid}")
async def delete_memory(mid: str, user: dict = Depends(get_current_user)):
    await db.ai_memories.delete_one({"id": mid, "user_id": user["user_id"]})
    return {"status": "deleted"}


@router.delete("/memory")
async def clear_memory(user: dict = Depends(get_current_user)):
    await db.ai_memories.delete_many({"user_id": user["user_id"]})
    return {"status": "cleared"}


# ---------------- Insights (dashboard) ----------------
@router.get("/insights")
async def insights(user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    chats = db.chats.find({"participants": uid}, {"_id": 0})
    chat_ids = [c["chat_id"] async for c in chats]
    unread = await db.messages.count_documents({
        "chat_id": {"$in": chat_ids}, "sender_id": {"$ne": uid},
        "read_by": {"$ne": uid}, "deleted": {"$ne": True}})
    important = await db.important_messages.count_documents({"user_id": uid})
    pending_tasks = await db.tasks.count_documents({"user_id": uid, "status": {"$ne": "done"}, "deleted_at": None})
    reminders = await db.reminders.count_documents({"user_id": uid, "done": {"$ne": True}})
    creations = await db.ai_creations.count_documents({"user_id": uid})
    # pending replies: chats where last message is from someone else and unread
    pending_replies = await db.messages.count_documents({
        "chat_id": {"$in": chat_ids}, "sender_id": {"$ne": uid},
        "read_by": {"$ne": uid}, "deleted": {"$ne": True}})
    return {
        "unread": unread, "important": important, "pending_tasks": pending_tasks,
        "reminders": reminders, "creations": creations, "pending_replies": pending_replies,
    }


# ---------------- Privacy ----------------
class PrivacyBody(BaseModel):
    messages: bool | None = None
    files: bool | None = None
    memory: bool | None = None
    contacts: bool | None = None
    location: bool | None = None
    calendar: bool | None = None
    web_search: bool | None = None
    calls: bool | None = None
    images: bool | None = None
    documents: bool | None = None
    voice_messages: bool | None = None
    attachments: bool | None = None
    group_intelligence: bool | None = None
    call_intelligence: bool | None = None
    call_transcription: bool | None = None
    call_summary: bool | None = None
    call_memory: bool | None = None


@router.get("/privacy")
async def get_privacy(user: dict = Depends(get_current_user)):
    p = await db.privacy.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not p:
        p = {"user_id": user["user_id"]}
        await db.privacy.insert_one(dict(p))
        p.pop("_id", None)
    defaults = {"messages": True, "files": True, "memory": True, "contacts": True,
                "location": False, "calendar": True, "web_search": True, "calls": False,
                "images": True, "documents": True, "voice_messages": True,
                "attachments": True, "group_intelligence": True,
                "call_intelligence": True, "call_transcription": True,
                "call_summary": True, "call_memory": True}
    for k, v in defaults.items():
        p.setdefault(k, v)
    return {"privacy": p}


@router.put("/privacy")
async def update_privacy(body: PrivacyBody, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    await db.privacy.update_one({"user_id": user["user_id"]}, {"$set": updates}, upsert=True)
    p = await db.privacy.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return {"privacy": p}
