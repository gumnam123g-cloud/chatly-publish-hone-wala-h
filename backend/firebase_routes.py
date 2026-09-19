"""
Firebase-backed routes for Chatly:
  - Firebase status/health
  - FCM device-token registry (register/unregister) + server-side push helper
  - Firebase ID-token -> Chatly JWT bridge (Google / Email sign-in via Firebase Auth; NO anonymous)
  - Full account deletion (Firebase Auth user + all Mongo data + Storage media + Firestore mirror)

These endpoints keep the existing JWT/session working while adding the real Firebase layer.
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from db import db
from security import get_current_user, create_token
import firebase_service as fb

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["firebase"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------- Firebase status ----------------

@router.get("/firebase/status")
async def firebase_status():
    """Non-secret health signal for diagnostics (no keys exposed)."""
    return fb.status()


# ---------------- FCM device tokens ----------------

class FcmTokenBody(BaseModel):
    token: str
    platform: str | None = "android"


@router.post("/fcm/register")
async def register_fcm(body: FcmTokenBody, user: dict = Depends(get_current_user)):
    token = (body.token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Missing device token.")
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$addToSet": {"fcm_tokens": token}},
    )
    # Keep a reverse index so we can prune/lookup quickly
    await db.fcm_tokens.update_one(
        {"token": token},
        {"$set": {"token": token, "user_id": user["user_id"],
                  "platform": body.platform or "android", "updated_at": _now()}},
        upsert=True,
    )
    return {"status": "registered"}


@router.post("/fcm/unregister")
async def unregister_fcm(body: FcmTokenBody, user: dict = Depends(get_current_user)):
    token = (body.token or "").strip()
    await db.users.update_one({"user_id": user["user_id"]}, {"$pull": {"fcm_tokens": token}})
    await db.fcm_tokens.delete_one({"token": token})
    return {"status": "unregistered"}


async def push_to_user(user_id: str, title: str, body: str, data: dict | None = None):
    """Server-side helper: send an FCM push to all of a user's devices and prune dead tokens.
    Best-effort — never raises to the caller."""
    try:
        u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "fcm_tokens": 1})
        tokens = (u or {}).get("fcm_tokens", [])
        if not tokens:
            return
        res = fb.send_push(tokens, title, body, data or {})
        for bad in res.get("invalid_tokens", []):
            await db.users.update_one({"user_id": user_id}, {"$pull": {"fcm_tokens": bad}})
            await db.fcm_tokens.delete_one({"token": bad})
    except fb.FirebaseUnavailable:
        logger.info("push_to_user skipped: Firebase not ready")
    except Exception as e:
        logger.warning("push_to_user error: %s", e)


@router.get("/auth/firebase-token")
async def firebase_custom_token(user: dict = Depends(get_current_user)):
    """Mint a Firebase custom token for the already-JWT-authenticated user so the client
    can sign into Firebase Auth (signInWithCustomToken) and access Firestore/Storage under
    the security rules (request.auth.uid == user_id). No anonymous auth involved."""
    if not fb.is_ready():
        raise HTTPException(status_code=503, detail="Firebase is temporarily unavailable.")
    try:
        from firebase_admin import auth as fb_auth
        claims = {"name": user.get("name"), "username": user.get("username")}
        token = fb_auth.create_custom_token(user["user_id"], claims)
        # ensure the public mirror exists for search/QR
        fb.mirror_user(user)
        return {"firebase_token": token.decode("utf-8") if isinstance(token, bytes) else token,
                "uid": user["user_id"]}
    except Exception as e:
        logger.warning("custom token error: %s", e)
        raise HTTPException(status_code=503, detail="Could not initialise secure sync.")


# ---------------- Firebase Auth bridge (Google / Email via Firebase) ----------------

class FirebaseAuthBody(BaseModel):
    id_token: str


@router.post("/auth/firebase")
async def firebase_auth_bridge(body: FirebaseAuthBody):
    """Verify a Firebase ID token and issue a Chatly JWT. Upserts by email (no duplicates).
    Rejects anonymous Firebase users (guest mode is not supported)."""
    try:
        decoded = fb.verify_id_token(body.id_token)
    except fb.FirebaseUnavailable:
        raise HTTPException(status_code=503, detail="Sign-in is temporarily unavailable.")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid sign-in. Please try again.")

    provider = (decoded.get("firebase", {}) or {}).get("sign_in_provider")
    if provider == "anonymous":
        raise HTTPException(status_code=403, detail="Guest sign-in is not allowed.")

    email = (decoded.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(status_code=400, detail="An email is required to sign in.")
    name = decoded.get("name") or email.split("@")[0]
    avatar = decoded.get("picture")
    fb_uid = decoded.get("uid")

    user = await db.users.find_one({"email": email, "deleted_at": None})
    if not user:
        base_username = email.split("@")[0].replace(".", "")[:20] or "user"
        username = base_username
        i = 0
        while await db.users.find_one({"username": username}):
            i += 1
            username = f"{base_username}{i}"
        uid = "user_" + (fb_uid or username)
        user = {
            "user_id": uid, "name": name, "email": email, "username": username,
            "bio": "", "avatar": avatar, "email_verified": True,
            "firebase_uid": fb_uid, "auth_provider": provider or "firebase",
            "online": False, "last_seen": _now(), "created_at": _now(), "deleted_at": None,
        }
        await db.users.insert_one(dict(user))
    else:
        await db.users.update_one({"user_id": user["user_id"]},
                                  {"$set": {"firebase_uid": fb_uid, "email_verified": True}})

    fb.mirror_user(user)
    token = create_token(user["user_id"])
    return {"token": token, "user": {
        "user_id": user["user_id"], "name": user["name"], "email": user["email"],
        "username": user.get("username"), "avatar": user.get("avatar"),
        "bio": user.get("bio", ""), "email_verified": True}}


# ---------------- Full account deletion ----------------

_PURGE_COLLECTIONS_BY_USER = [
    ("contacts", "user_id"), ("privacy", "user_id"), ("tasks", "user_id"),
    ("reminders", "user_id"), ("ai_conversations", "user_id"), ("ai_messages", "user_id"),
    ("ai_memories", "user_id"), ("ai_creations", "user_id"), ("ai_search_history", "user_id"),
    ("research_history", "user_id"), ("calendar_events", "user_id"),
    ("important_messages", "user_id"), ("statuses", "user_id"), ("otps", "user_id"),
    ("fcm_tokens", "user_id"),
]


@router.delete("/account")
async def delete_account(user: dict = Depends(get_current_user)):
    """Permanently delete the user's account: Firebase Auth user + all Mongo data +
    Storage media + Firestore mirror. Idempotent and safe."""
    uid = user["user_id"]
    email = user.get("email")

    # 1) Firebase Auth user (if they ever used Firebase sign-in) — never fatal
    try:
        fb.delete_auth_user(uid=user.get("firebase_uid"), email=email)
    except Exception as e:
        logger.warning("account delete: auth cleanup issue: %s", e)

    # 2) Mongo data owned by the user
    for coll, field in _PURGE_COLLECTIONS_BY_USER:
        try:
            await db[coll].delete_many({field: uid})
        except Exception as e:
            logger.warning("purge %s failed: %s", coll, e)

    # contact requests either direction
    await db.contact_requests.delete_many({"$or": [{"from_id": uid}, {"to_id": uid}]})
    # remove me from everyone else's contacts / blocks
    await db.contacts.delete_many({"contact_id": uid})
    await db.users.update_many({"blocked": uid}, {"$pull": {"blocked": uid}})

    # chats + messages where the user is a participant
    try:
        chat_ids = [c["chat_id"] async for c in db.chats.find({"participants": uid}, {"_id": 0, "chat_id": 1})]
        if chat_ids:
            await db.messages.delete_many({"chat_id": {"$in": chat_ids}})
            await db.chats.delete_many({"chat_id": {"$in": chat_ids}})
    except Exception as e:
        logger.warning("chat purge failed: %s", e)

    # calls involving the user
    try:
        await db.calls.delete_many({"$or": [{"caller_id": uid}, {"callee_id": uid},
                                            {"from_id": uid}, {"to_id": uid},
                                            {"participants": uid}]})
    except Exception:
        pass

    # 3) Storage media under the user's prefix
    try:
        fb.delete_storage_prefix(f"users/{uid}/")
        fb.delete_storage_prefix(f"status/{uid}/")
    except Exception:
        pass

    # 4) Firestore mirror
    fb.delete_user_mirror(uid)

    # 5) Finally remove the user document (hard delete)
    await db.users.delete_one({"user_id": uid})

    return {"status": "account_deleted"}
