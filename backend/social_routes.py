import uuid
import secrets
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from db import db
from security import get_current_user
from ws_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["social"])


def _now():
    return datetime.now(timezone.utc).isoformat()


def _pub(u: dict, viewer: str) -> dict:
    return {
        "user_id": u["user_id"], "name": u["name"], "avatar": u.get("avatar"),
        "username": u.get("username"), "bio": u.get("bio", ""),
        "is_bot": u.get("is_bot", False),
        "online": manager.is_online(u["user_id"]) or u.get("is_bot", False),
    }


@router.get("/users/search")
async def search_users(q: str, user: dict = Depends(get_current_user)):
    q = (q or "").strip()
    if len(q) < 2:
        return {"users": []}
    blocked = set(user.get("blocked", []))
    regex = {"$regex": q, "$options": "i"}
    cursor = db.users.find(
        {"$and": [
            {"user_id": {"$ne": user["user_id"]}, "deleted_at": None},
            {"$or": [{"name": regex}, {"username": regex}, {"email": q.lower()}]},
        ]}, {"_id": 0, "password": 0}).limit(25)
    out = []
    async for u in cursor:
        if u["user_id"] in blocked:
            continue
        rel = await db.contacts.find_one({"user_id": user["user_id"], "contact_id": u["user_id"]}, {"_id": 0})
        pending = await db.contact_requests.find_one(
            {"from_id": user["user_id"], "to_id": u["user_id"], "status": "pending"}, {"_id": 0})
        item = _pub(u, user["user_id"])
        item["is_contact"] = bool(rel)
        item["request_sent"] = bool(pending)
        out.append(item)
    return {"users": out}


class RequestBody(BaseModel):
    to_id: str


@router.post("/contacts/request")
async def send_request(body: RequestBody, user: dict = Depends(get_current_user)):
    if body.to_id == user["user_id"]:
        raise HTTPException(status_code=400, detail="You cannot add yourself.")
    target = await db.users.find_one({"user_id": body.to_id, "deleted_at": None})
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    # already contacts?
    if await db.contacts.find_one({"user_id": user["user_id"], "contact_id": body.to_id}):
        return {"status": "already_contacts"}
    # reverse pending -> auto accept
    reverse = await db.contact_requests.find_one({"from_id": body.to_id, "to_id": user["user_id"], "status": "pending"})
    if reverse:
        return await _accept(reverse, user)
    existing = await db.contact_requests.find_one({"from_id": user["user_id"], "to_id": body.to_id, "status": "pending"})
    if existing:
        return {"status": "pending"}
    req = {"id": str(uuid.uuid4()), "from_id": user["user_id"], "to_id": body.to_id,
           "status": "pending", "created_at": _now()}
    await db.contact_requests.insert_one(dict(req))
    await manager.send_to_user(body.to_id, {"type": "contact_request", "from": _pub(user, body.to_id)})
    return {"status": "pending"}


@router.get("/contacts/requests")
async def list_requests(user: dict = Depends(get_current_user)):
    cursor = db.contact_requests.find({"to_id": user["user_id"], "status": "pending"}, {"_id": 0}).sort("created_at", -1)
    out = []
    async for r in cursor:
        u = await db.users.find_one({"user_id": r["from_id"]}, {"_id": 0})
        if u:
            item = _pub(u, user["user_id"])
            item["request_id"] = r["id"]
            out.append(item)
    return {"requests": out}


async def _accept(req: dict, user: dict) -> dict:
    a, b = req["from_id"], req["to_id"]
    for x, y in ((a, b), (b, a)):
        await db.contacts.update_one({"user_id": x, "contact_id": y},
                                     {"$setOnInsert": {"user_id": x, "contact_id": y, "created_at": _now()}}, upsert=True)
    await db.contact_requests.update_many(
        {"$or": [{"from_id": a, "to_id": b}, {"from_id": b, "to_id": a}], "status": "pending"},
        {"$set": {"status": "accepted"}})
    await manager.send_to_user(req["from_id"], {"type": "contact_accepted", "user": _pub(user, req["from_id"])})
    return {"status": "accepted"}


class RespondBody(BaseModel):
    request_id: str
    accept: bool


@router.post("/contacts/respond")
async def respond_request(body: RespondBody, user: dict = Depends(get_current_user)):
    req = await db.contact_requests.find_one({"id": body.request_id, "to_id": user["user_id"], "status": "pending"})
    if not req:
        raise HTTPException(status_code=404, detail="Request not found.")
    if not body.accept:
        await db.contact_requests.update_one({"id": body.request_id}, {"$set": {"status": "rejected"}})
        return {"status": "rejected"}
    return await _accept(req, user)


@router.get("/contacts/list")
async def my_contacts(user: dict = Depends(get_current_user)):
    cursor = db.contacts.find({"user_id": user["user_id"]}, {"_id": 0})
    ids = [c["contact_id"] async for c in cursor]
    out = []
    for cid in ids:
        u = await db.users.find_one({"user_id": cid, "deleted_at": None}, {"_id": 0})
        if u:
            out.append(_pub(u, user["user_id"]))
    return {"contacts": out}


class BlockBody(BaseModel):
    user_id: str


@router.post("/contacts/block")
async def block_user(body: BlockBody, user: dict = Depends(get_current_user)):
    if body.user_id in user.get("blocked", []):
        await db.users.update_one({"user_id": user["user_id"]}, {"$pull": {"blocked": body.user_id}})
        return {"blocked": False}
    await db.users.update_one({"user_id": user["user_id"]}, {"$addToSet": {"blocked": body.user_id}})
    return {"blocked": True}


# ---------------- Unique QR code + public profiles + relationship ----------------

async def ensure_qr_token(u: dict) -> str:
    """Every user gets one permanent, globally-unique QR token. Generated lazily
    and stored on the user document so it never changes for that account."""
    token = u.get("qr_token")
    if token:
        return token
    for _ in range(6):
        token = "CHATLY-" + secrets.token_urlsafe(9)
        if not await db.users.find_one({"qr_token": token}):
            break
    await db.users.update_one({"user_id": u["user_id"]}, {"$set": {"qr_token": token}})
    return token


async def _relationship(viewer_id: str, target: dict) -> dict:
    tid = target["user_id"]
    if tid == viewer_id:
        return {"status": "self"}
    if await db.contacts.find_one({"user_id": viewer_id, "contact_id": tid}):
        return {"status": "friends"}
    if await db.contact_requests.find_one({"from_id": viewer_id, "to_id": tid, "status": "pending"}):
        return {"status": "request_sent"}
    incoming = await db.contact_requests.find_one({"from_id": tid, "to_id": viewer_id, "status": "pending"})
    if incoming:
        return {"status": "request_incoming", "request_id": incoming["id"]}
    return {"status": "none"}


async def _profile_payload(target: dict, viewer: dict) -> dict:
    item = _pub(target, viewer["user_id"])
    item["relationship"] = await _relationship(viewer["user_id"], target)
    item["blocked_by_me"] = target["user_id"] in viewer.get("blocked", [])
    return item


@router.get("/me/qr")
async def my_qr(user: dict = Depends(get_current_user)):
    token = await ensure_qr_token(user)
    return {"qr_token": token, "payload": f"chatly://user/{token}", "user": _pub(user, user["user_id"])}


def _extract_qr_token(raw: str) -> str:
    """Normalise a scanned value into a bare CHATLY-token.
    Accepts: 'CHATLY-xxx', 'chatly://user/CHATLY-xxx', full deep links / URLs with the
    token in the path or a ?code= query, plus stray whitespace/encoding."""
    import urllib.parse
    code = urllib.parse.unquote((raw or "").strip())
    # If it's a deep link / URL, pull the last meaningful segment or ?code=
    if "code=" in code:
        try:
            q = urllib.parse.urlparse(code).query or code.split("?", 1)[-1]
            parsed = urllib.parse.parse_qs(q).get("code", [])
            if parsed:
                code = parsed[0]
        except Exception:
            pass
    if "chatly://user/" in code:
        code = code.split("chatly://user/")[-1]
    elif "/user/" in code:
        code = code.split("/user/")[-1]
    # keep only the token portion (strip any trailing path/query fragments)
    code = code.strip().strip("/").split("?")[0].split("/")[0].strip()
    return code


async def _resolve_qr(code: str, user: dict) -> dict:
    token = _extract_qr_token(code)
    if not token:
        raise HTTPException(status_code=400, detail="This QR code is not valid.")
    target = await db.users.find_one({"qr_token": token, "deleted_at": None}, {"_id": 0, "password": 0})
    if not target:
        raise HTTPException(status_code=404, detail="This QR code is not valid.")
    return {"user": await _profile_payload(target, user)}


@router.get("/users/by-qr")
async def user_by_qr_query(code: str, user: dict = Depends(get_current_user)):
    """Preferred QR lookup: token passed as a query param so deep-link URLs containing
    slashes never break FastAPI path routing (this was the real 'user not found' bug)."""
    return await _resolve_qr(code, user)


@router.get("/users/by-qr/{code:path}")
async def user_by_qr(code: str, user: dict = Depends(get_current_user)):
    """Backward-compatible path lookup. Uses {code:path} so a full 'chatly://user/...'
    deep link no longer breaks route matching on the '/' characters."""
    return await _resolve_qr(code, user)


@router.get("/users/{user_id}")
async def get_user_profile(user_id: str, user: dict = Depends(get_current_user)):
    target = await db.users.find_one({"user_id": user_id, "deleted_at": None}, {"_id": 0, "password": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"user": await _profile_payload(target, user)}
