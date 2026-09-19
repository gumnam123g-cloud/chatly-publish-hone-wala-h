import uuid
import asyncio
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from db import db
from security import get_current_user
from ws_manager import manager
from ai_service import ai_complete

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _user_public(uid: str) -> dict:
    u = await db.users.find_one({"user_id": uid}, {"_id": 0, "password": 0})
    if not u:
        return {"user_id": uid, "name": "Unknown", "avatar": None}
    return {
        "user_id": u["user_id"], "name": u["name"], "avatar": u.get("avatar"),
        "username": u.get("username"), "bio": u.get("bio", ""),
        "is_bot": u.get("is_bot", False), "persona": u.get("persona"),
        "online": manager.is_online(uid) or u.get("is_bot", False),
        "last_seen": u.get("last_seen"),
    }


async def ensure_seed_chats(user_id: str):
    """Give a new user demo conversations (with seeded content) so the full
    messaging + AI-intelligence loop is experienceable on a single account."""
    bots = db.users.find({"is_bot": True}, {"_id": 0})
    async for bot in bots:
        chat_id = _dm_id(user_id, bot["user_id"])
        # ensure the bot is a saved contact both ways so the contacts list is populated
        for x, y in ((user_id, bot["user_id"]), (bot["user_id"], user_id)):
            await db.contacts.update_one({"user_id": x, "contact_id": y},
                                         {"$setOnInsert": {"user_id": x, "contact_id": y, "created_at": _now()}}, upsert=True)
        if await db.chats.find_one({"chat_id": chat_id}):
            continue
        now = _now()
        await db.chats.insert_one({
            "chat_id": chat_id, "type": "dm",
            "participants": sorted([user_id, bot["user_id"]]),
            "ai_enabled": True, "created_at": now, "last_message": None,
            "last_ts": now, "muted_by": [], "pinned_by": [], "archived_by": [],
        })
        last = None
        for text in bot.get("seed_messages", []):
            await db.messages.insert_one({
                "message_id": str(uuid.uuid4()), "chat_id": chat_id,
                "sender_id": bot["user_id"], "text": text, "type": "text",
                "status": "delivered", "reply_to": None, "reactions": {},
                "starred_by": [], "read_by": [bot["user_id"]], "edited": False,
                "deleted": False, "created_at": _now(),
            })
            last = text
        if last:
            await db.chats.update_one({"chat_id": chat_id},
                                      {"$set": {"last_message": last[:120], "last_ts": now}})


@router.get("/contacts")
async def list_contacts(user: dict = Depends(get_current_user)):
    cursor = db.users.find(
        {"user_id": {"$ne": user["user_id"]}, "deleted_at": None},
        {"_id": 0, "password": 0},
    ).sort("is_bot", -1)
    out = []
    async for u in cursor:
        out.append({
            "user_id": u["user_id"], "name": u["name"], "avatar": u.get("avatar"),
            "username": u.get("username"), "bio": u.get("bio", ""),
            "is_bot": u.get("is_bot", False), "persona": u.get("persona"),
            "online": manager.is_online(u["user_id"]) or u.get("is_bot", False),
        })
    return {"contacts": out}


def _dm_id(a: str, b: str) -> str:
    return "dm_" + "_".join(sorted([a, b]))


class CreateChatBody(BaseModel):
    contact_id: str


@router.post("/chats")
async def create_chat(body: CreateChatBody, user: dict = Depends(get_current_user)):
    other = await db.users.find_one({"user_id": body.contact_id, "deleted_at": None})
    if not other:
        raise HTTPException(status_code=404, detail="Contact not found.")
    chat_id = _dm_id(user["user_id"], body.contact_id)
    existing = await db.chats.find_one({"chat_id": chat_id}, {"_id": 0})
    if not existing:
        await db.chats.insert_one({
            "chat_id": chat_id,
            "type": "dm",
            "participants": sorted([user["user_id"], body.contact_id]),
            "ai_enabled": True,
            "created_at": _now(),
            "last_message": None,
            "last_ts": _now(),
            "muted_by": [],
            "pinned_by": [],
            "archived_by": [],
        })
    return {"chat_id": chat_id}


async def _chat_view(chat: dict, me: str) -> dict:
    unread = await db.messages.count_documents({
        "chat_id": chat["chat_id"],
        "sender_id": {"$ne": me},
        "read_by": {"$ne": me},
        "deleted": {"$ne": True},
    })
    base = {
        "chat_id": chat["chat_id"],
        "type": chat["type"],
        "last_message": chat.get("last_message"),
        "last_ts": chat.get("last_ts"),
        "ai_enabled": chat.get("ai_enabled", True),
        "unread": unread,
        "pinned": me in chat.get("pinned_by", []),
        "muted": me in chat.get("muted_by", []),
        "archived": me in chat.get("archived_by", []),
    }
    if chat["type"] == "group":
        base["other"] = {"user_id": chat["chat_id"], "name": chat.get("name", "Group"),
                         "avatar": chat.get("avatar"), "is_group": True,
                         "member_count": len(chat.get("participants", []))}
    else:
        others = [p for p in chat["participants"] if p != me]
        other_id = others[0] if others else None
        base["other"] = await _user_public(other_id) if other_id else None
        if other_id:
            me_doc = await db.users.find_one({"user_id": me}, {"_id": 0, "blocked": 1})
            other_doc = await db.users.find_one({"user_id": other_id}, {"_id": 0, "blocked": 1})
            base["blocked_by_me"] = other_id in (me_doc or {}).get("blocked", [])
            base["blocked_me"] = me in (other_doc or {}).get("blocked", [])
    base["theme"] = chat.get("themes", {}).get(me)
    base["translation"] = chat.get("translation", {}).get(me)
    return base


@router.get("/chats")
async def list_chats(user: dict = Depends(get_current_user)):
    await ensure_seed_chats(user["user_id"])
    cursor = db.chats.find(
        {"participants": user["user_id"], "deleted_by": {"$ne": user["user_id"]}},
        {"_id": 0},
    ).sort("last_ts", -1)
    out = []
    async for chat in cursor:
        out.append(await _chat_view(chat, user["user_id"]))
    return {"chats": out}


@router.get("/chats/{chat_id}")
async def get_chat(chat_id: str, user: dict = Depends(get_current_user)):
    chat = await db.chats.find_one({"chat_id": chat_id, "participants": user["user_id"]}, {"_id": 0})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return await _chat_view(chat, user["user_id"])


@router.get("/chats/{chat_id}/messages")
async def get_messages(chat_id: str, user: dict = Depends(get_current_user),
                       limit: int = Query(80, le=200), before: str | None = None):
    chat = await db.chats.find_one({"chat_id": chat_id, "participants": user["user_id"]})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    q = {"chat_id": chat_id, "deleted_for": {"$ne": user["user_id"]}}
    if before:
        q["created_at"] = {"$lt": before}
    # Filter out messages whose per-message TTL (feature #43) has elapsed.
    # `expires_at` is stored as an ISO string; string comparison is safe for
    # UTC ISO-8601. We accept messages where expires_at is null OR still in the
    # future.
    _now_iso = _now()
    q["$or"] = [{"expires_at": None}, {"expires_at": {"$gt": _now_iso}}, {"expires_at": {"$exists": False}}]
    cursor = db.messages.find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
    msgs = [m async for m in cursor]
    msgs.reverse()
    # mark incoming as read
    await db.messages.update_many(
        {"chat_id": chat_id, "sender_id": {"$ne": user["user_id"]}, "read_by": {"$ne": user["user_id"]}},
        {"$addToSet": {"read_by": user["user_id"]}, "$set": {"status": "read"}},
    )
    return {"messages": msgs}


class SendBody(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    type: str = "text"
    reply_to: str | None = None
    # Optional per-message expiry (feature #43). Sender sets a TTL in seconds
    # (1h=3600, 1d=86400, 7d=604800, or custom). Server converts to an absolute
    # ISO timestamp so the receiver's clock skew never matters. Expired messages
    # are filtered out of get_messages and tombstoned lazily.
    expires_in_seconds: int | None = Field(default=None, ge=60, le=60 * 60 * 24 * 30)


async def _persist_message(chat_id: str, sender_id: str, text: str, mtype: str = "text",
                           reply_to: str | None = None, expires_at: str | None = None) -> dict:
    msg = {
        "message_id": str(uuid.uuid4()),
        "chat_id": chat_id,
        "sender_id": sender_id,
        "text": text,
        "type": mtype,
        "status": "sent",
        "reply_to": reply_to,
        "reactions": {},
        "starred_by": [],
        "read_by": [sender_id],
        "edited": False,
        "deleted": False,
        "expires_at": expires_at,
        "created_at": _now(),
    }
    await db.messages.insert_one(dict(msg))
    await db.chats.update_one(
        {"chat_id": chat_id},
        {"$set": {"last_message": text[:120], "last_ts": msg["created_at"]},
         "$unset": {"deleted_by": ""}},
    )
    msg.pop("_id", None)
    return msg


async def _demo_reply(chat_id: str, bot_id: str, human_id: str):
    """A seeded persona contact replies using the AI, so a single account can
    experience the full messaging + intelligence loop. Clearly a simulated persona."""
    await asyncio.sleep(1.2)
    bot = await db.users.find_one({"user_id": bot_id})
    if not bot:
        return
    await manager.send_to_user(human_id, {"type": "typing", "chat_id": chat_id, "user_id": bot_id, "typing": True})
    history = db.messages.find({"chat_id": chat_id, "deleted": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).limit(12)
    hist = [m async for m in history]
    hist.reverse()
    lines = []
    for m in hist:
        who = bot["name"] if m["sender_id"] == bot_id else "User"
        lines.append(f"{who}: {m['text']}")
    persona = bot.get("persona", "a friendly colleague")
    system = (
        f"You are roleplaying as {bot['name']}, {persona}. You are texting on a messaging app. "
        "Reply naturally in 1-2 short sentences like a real person. You may reply in English, Hindi or Hinglish "
        "matching the user's language. Occasionally mention real-world things like tasks, deadlines, meetings, "
        "files or decisions to keep the conversation lively. Do not act like an AI assistant. No emojis."
    )
    try:
        reply = await ai_complete(system, "Conversation so far:\n" + "\n".join(lines) + f"\n\nReply as {bot['name']}:",
                                  temperature=0.8, max_tokens=180)
    except Exception:
        reply = "Got it, will get back to you shortly."
    await asyncio.sleep(0.6)
    msg = await _persist_message(chat_id, bot_id, reply.strip() or "Okay!")
    await manager.send_to_user(human_id, {"type": "typing", "chat_id": chat_id, "user_id": bot_id, "typing": False})
    await manager.send_to_users([human_id], {"type": "message", "chat_id": chat_id, "message": msg})


@router.post("/chats/{chat_id}/messages")
async def send_message(chat_id: str, body: SendBody, user: dict = Depends(get_current_user)):
    chat = await db.chats.find_one({"chat_id": chat_id, "participants": user["user_id"]})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    others = [p for p in chat["participants"] if p != user["user_id"]]
    # Block enforcement for direct chats
    if chat.get("type") == "dm" and others:
        oid = others[0]
        other_doc = await db.users.find_one({"user_id": oid}, {"_id": 0, "blocked": 1})
        if user["user_id"] in (other_doc or {}).get("blocked", []) or oid in user.get("blocked", []):
            raise HTTPException(status_code=403, detail="You can't send messages in this chat.")
    # Compute per-message expiry if requested.
    _expires_at = None
    if body.expires_in_seconds:
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        _expires_at = (_dt.now(_tz.utc) + _td(seconds=int(body.expires_in_seconds))).isoformat()
    msg = await _persist_message(chat_id, user["user_id"], body.text.strip(), body.type, body.reply_to, expires_at=_expires_at)
    await manager.send_to_users(others, {"type": "message", "chat_id": chat_id, "message": msg})
    # Real FCM push to recipients who are not muted and are not bots (skip the sender).
    try:
        from firebase_routes import push_to_user
        muted = set(chat.get("muted_by", []))
        preview = (body.text.strip()[:120]) if body.type == "text" else f"Sent a {body.type}"
        for oid in others:
            if oid in muted:
                continue
            odoc = await db.users.find_one({"user_id": oid}, {"_id": 0, "is_bot": 1})
            if odoc and odoc.get("is_bot"):
                continue
            asyncio.create_task(push_to_user(
                oid, user.get("name", "New message"), preview,
                {"type": "chat_message", "chat_id": chat_id, "message_id": msg["message_id"],
                 "sender_id": user["user_id"], "channel_id": "messages"}))
    except Exception as _e:
        pass
    # trigger persona reply for bot contacts
    for oid in others:
        other = await db.users.find_one({"user_id": oid})
        if other and other.get("is_bot"):
            asyncio.create_task(_demo_reply(chat_id, oid, user["user_id"]))
    return {"message": msg}


class ThemeBody(BaseModel):
    theme: dict | None = None


@router.post("/chats/{chat_id}/theme")
async def set_chat_theme(chat_id: str, body: ThemeBody, user: dict = Depends(get_current_user)):
    chat = await db.chats.find_one({"chat_id": chat_id, "participants": user["user_id"]})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    key = f"themes.{user['user_id']}"
    if body.theme is None:
        await db.chats.update_one({"chat_id": chat_id}, {"$unset": {key: ""}})
    else:
        await db.chats.update_one({"chat_id": chat_id}, {"$set": {key: body.theme}})
    return {"theme": body.theme}


# ---------------------------------------------------------------------------
# Two-Way Translation Mode (feature #38)
#
# When a chat has translation mode ON, incoming messages are auto-translated
# to `to_lang` and outgoing messages are auto-translated to `from_lang` before
# sending. Both original + translation are shown in the UI (never destroyed).
# Setting is per-user-per-chat so each side can pick their own preference.

class TranslationMode(BaseModel):
    enabled: bool = False
    to_lang: str = "English"     # translate incoming to this
    from_lang: str = "English"   # translate outgoing to this


@router.post("/chats/{chat_id}/translation-mode")
async def set_translation_mode(chat_id: str, body: TranslationMode, user: dict = Depends(get_current_user)):
    chat = await db.chats.find_one({"chat_id": chat_id, "participants": user["user_id"]})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    key = f"translation.{user['user_id']}"
    payload = {"enabled": body.enabled, "to_lang": body.to_lang, "from_lang": body.from_lang}
    if not body.enabled:
        await db.chats.update_one({"chat_id": chat_id}, {"$unset": {key: ""}})
        return {"translation": None}
    await db.chats.update_one({"chat_id": chat_id}, {"$set": {key: payload}})
    return {"translation": payload}


# ---------------------------------------------------------------------------
# Chat Export (feature #39)
#
# Exports the visible history of a chat as UTF-8 text or Markdown. Messages
# deleted-for-me are excluded; expired messages are excluded; system messages
# are labelled. Requires participation in the chat.

@router.post("/chats/{chat_id}/export")
async def export_chat(chat_id: str, fmt: str = Query("markdown", pattern="^(markdown|text)$"),
                      user: dict = Depends(get_current_user)):
    chat = await db.chats.find_one({"chat_id": chat_id, "participants": user["user_id"]})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    _now_iso = _now()
    q = {"chat_id": chat_id, "deleted_for": {"$ne": user["user_id"]},
         "$or": [{"expires_at": None}, {"expires_at": {"$gt": _now_iso}}, {"expires_at": {"$exists": False}}]}
    msgs = [m async for m in db.messages.find(q, {"_id": 0}).sort("created_at", 1)]
    # Build a display-name map for participants.
    users = {u["user_id"]: u.get("name", "User") async for u in db.users.find(
        {"user_id": {"$in": chat["participants"]}}, {"_id": 0, "user_id": 1, "name": 1})}
    title = chat.get("title") or ", ".join(users.get(p, "User") for p in chat["participants"])
    lines: list[str] = []
    if fmt == "markdown":
        lines.append(f"# {title}")
        lines.append(f"_Exported by Chatly on {_now_iso}_\n")
    else:
        lines.append(f"{title}")
        lines.append(f"Exported by Chatly on {_now_iso}\n")
    for m in msgs:
        who = users.get(m.get("sender_id"), "User")
        when = (m.get("created_at") or "")[:19].replace("T", " ")
        text = (m.get("text") or "").replace("\r\n", "\n")
        if m.get("deleted"):
            text = "(deleted)"
        if m.get("type") == "system":
            if fmt == "markdown":
                lines.append(f"> {text}")
            else:
                lines.append(f"[{when}] system: {text}")
            continue
        if fmt == "markdown":
            lines.append(f"**{who}** _{when}_  \n{text}\n")
        else:
            lines.append(f"[{when}] {who}: {text}")
    body = "\n".join(lines) + "\n"
    return {"filename": f"{chat_id}.{ 'md' if fmt=='markdown' else 'txt'}",
            "content": body, "message_count": len(msgs)}



@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, user: dict = Depends(get_current_user)):
    chat = await db.chats.find_one({"chat_id": chat_id, "participants": user["user_id"]})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    await db.chats.update_one({"chat_id": chat_id}, {"$addToSet": {"deleted_by": user["user_id"]}})
    return {"status": "deleted"}


class ReactBody(BaseModel):
    emoji: str


@router.post("/messages/{message_id}/react")
async def react(message_id: str, body: ReactBody, user: dict = Depends(get_current_user)):
    msg = await db.messages.find_one({"message_id": message_id}, {"_id": 0})
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found.")
    reactions = msg.get("reactions", {})
    if reactions.get(user["user_id"]) == body.emoji:
        reactions.pop(user["user_id"], None)
    else:
        reactions[user["user_id"]] = body.emoji
    await db.messages.update_one({"message_id": message_id}, {"$set": {"reactions": reactions}})
    chat = await db.chats.find_one({"chat_id": msg["chat_id"]})
    if chat:
        await manager.send_to_users(chat["participants"],
                                    {"type": "reaction", "chat_id": msg["chat_id"],
                                     "message_id": message_id, "reactions": reactions})
    return {"reactions": reactions}


@router.post("/messages/{message_id}/star")
async def star(message_id: str, user: dict = Depends(get_current_user)):
    msg = await db.messages.find_one({"message_id": message_id})
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found.")
    starred = msg.get("starred_by", [])
    if user["user_id"] in starred:
        await db.messages.update_one({"message_id": message_id}, {"$pull": {"starred_by": user["user_id"]}})
        return {"starred": False}
    await db.messages.update_one({"message_id": message_id}, {"$addToSet": {"starred_by": user["user_id"]}})
    return {"starred": True}


@router.delete("/messages/{message_id}")
async def delete_message(message_id: str, user: dict = Depends(get_current_user),
                         scope: str = Query("everyone")):
    """scope='me' hides the message only for the requesting user (delete for me).
    scope='everyone' tombstones it for all participants (sender only)."""
    msg = await db.messages.find_one({"message_id": message_id})
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found.")
    chat = await db.chats.find_one({"chat_id": msg["chat_id"], "participants": user["user_id"]})
    if not chat:
        raise HTTPException(status_code=403, detail="Not allowed.")

    if scope == "me":
        await db.messages.update_one({"message_id": message_id},
                                     {"$addToSet": {"deleted_for": user["user_id"]}})
        return {"status": "deleted", "scope": "me"}

    # delete for everyone -> only the original sender may do this
    if msg["sender_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="You can only delete your own messages for everyone.")
    await db.messages.update_one({"message_id": message_id},
                                 {"$set": {"deleted": True, "text": "This message was deleted"}})
    await manager.send_to_users(chat["participants"],
                                {"type": "deleted", "chat_id": msg["chat_id"], "message_id": message_id})
    return {"status": "deleted", "scope": "everyone"}


class EditBody(BaseModel):
    text: str = Field(min_length=1, max_length=6000)


@router.put("/messages/{message_id}")
async def edit_message(message_id: str, body: EditBody, user: dict = Depends(get_current_user)):
    msg = await db.messages.find_one({"message_id": message_id})
    if not msg or msg["sender_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="You can only edit your own messages.")
    await db.messages.update_one({"message_id": message_id},
                                 {"$set": {"text": body.text.strip(), "edited": True}})
    return {"status": "edited"}


@router.post("/chats/{chat_id}/pin")
async def pin_chat(chat_id: str, user: dict = Depends(get_current_user)):
    chat = await db.chats.find_one({"chat_id": chat_id, "participants": user["user_id"]})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    if user["user_id"] in chat.get("pinned_by", []):
        await db.chats.update_one({"chat_id": chat_id}, {"$pull": {"pinned_by": user["user_id"]}})
        return {"pinned": False}
    await db.chats.update_one({"chat_id": chat_id}, {"$addToSet": {"pinned_by": user["user_id"]}})
    return {"pinned": True}


@router.post("/chats/{chat_id}/mute")
async def mute_chat(chat_id: str, user: dict = Depends(get_current_user)):
    chat = await db.chats.find_one({"chat_id": chat_id, "participants": user["user_id"]})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    if user["user_id"] in chat.get("muted_by", []):
        await db.chats.update_one({"chat_id": chat_id}, {"$pull": {"muted_by": user["user_id"]}})
        return {"muted": False}
    await db.chats.update_one({"chat_id": chat_id}, {"$addToSet": {"muted_by": user["user_id"]}})
    return {"muted": True}


class TypingBody(BaseModel):
    typing: bool


@router.post("/chats/{chat_id}/typing")
async def typing(chat_id: str, body: TypingBody, user: dict = Depends(get_current_user)):
    chat = await db.chats.find_one({"chat_id": chat_id, "participants": user["user_id"]})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    others = [p for p in chat["participants"] if p != user["user_id"]]
    await manager.send_to_users(others, {"type": "typing", "chat_id": chat_id,
                                          "user_id": user["user_id"], "typing": body.typing})
    return {"ok": True}
