import uuid
import secrets
import logging
import os
import httpx
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field

from db import db
from security import hash_password, verify_password, create_token, get_current_user
from email_service import send_email, otp_email_html, reset_email_html

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

OTP_TTL_MIN = 10
RESEND_COOLDOWN_SEC = 45
MAX_OTP_ATTEMPTS = 5


def _now():
    return datetime.now(timezone.utc)


def _gen_otp() -> str:
    return f"{secrets.randbelow(1000000):06d}"


async def _issue_otp(user_id: str, email: str, name: str, purpose: str):
    """Invalidate previous OTP, create + email a new one. Enforces resend cooldown."""
    existing = await db.otps.find_one({"user_id": user_id, "purpose": purpose})
    if existing:
        last = existing.get("last_sent")
        if last:
            last_dt = datetime.fromisoformat(last)
            elapsed = (_now() - last_dt).total_seconds()
            if elapsed < RESEND_COOLDOWN_SEC:
                raise HTTPException(
                    status_code=429,
                    detail=f"Please wait {int(RESEND_COOLDOWN_SEC - elapsed)}s before requesting a new code.",
                )
    code = _gen_otp()
    html = otp_email_html(name, code) if purpose == "verify" else reset_email_html(name, code)
    subject = "Your Chatly verification code" if purpose == "verify" else "Your Chatly password reset code"
    # Dev/QA only: when OTP_DEBUG=1 log the code server-side so automated end-to-end
    # tests can complete the verify/reset flow (the provider blocks fake test inboxes and
    # codes are hashed at rest). Never enable in production; the code is never returned to the client.
    if os.environ.get("OTP_DEBUG") == "1":
        logger.info(f"[OTP_DEBUG] purpose={purpose} email={email} code={code}")
    await send_email(to=email, subject=subject, html=html)
    await db.otps.delete_many({"user_id": user_id, "purpose": purpose})
    await db.otps.insert_one({
        "user_id": user_id,
        "purpose": purpose,
        "otp_hash": hash_password(code),
        "expires_at": (_now() + timedelta(minutes=OTP_TTL_MIN)).isoformat(),
        "attempts": 0,
        "last_sent": _now().isoformat(),
        "created_at": _now().isoformat(),
    })
    return code


def _dev(code: str | None) -> dict:
    """Dev/QA only: surface the OTP in the API response when OTP_DEBUG=1 so curl-based
    tests can complete flows. Empty in production; the frontend never reads this field."""
    if code and os.environ.get("OTP_DEBUG") == "1":
        return {"dev_code": code}
    return {}


async def _verify_otp(user_id: str, purpose: str, code: str) -> bool:
    rec = await db.otps.find_one({"user_id": user_id, "purpose": purpose})
    if not rec:
        raise HTTPException(status_code=400, detail="No code found. Please request a new code.")
    if datetime.fromisoformat(rec["expires_at"]) < _now():
        await db.otps.delete_many({"user_id": user_id, "purpose": purpose})
        raise HTTPException(status_code=400, detail="Code expired. Please request a new code.")
    if rec.get("attempts", 0) >= MAX_OTP_ATTEMPTS:
        await db.otps.delete_many({"user_id": user_id, "purpose": purpose})
        raise HTTPException(status_code=429, detail="Too many attempts. Please request a new code.")
    if not verify_password(code, rec["otp_hash"]):
        await db.otps.update_one({"_id": rec["_id"]}, {"$inc": {"attempts": 1}})
        remaining = MAX_OTP_ATTEMPTS - (rec.get("attempts", 0) + 1)
        raise HTTPException(status_code=400, detail=f"Incorrect code. {max(remaining,0)} attempts left.")
    await db.otps.delete_many({"user_id": user_id, "purpose": purpose})
    return True


def _public_user(u: dict) -> dict:
    return {
        "user_id": u["user_id"],
        "name": u["name"],
        "email": u["email"],
        "username": u.get("username"),
        "bio": u.get("bio", ""),
        "avatar": u.get("avatar"),
        "email_verified": u.get("email_verified", False),
    }


class SignupBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class VerifyBody(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class EmailBody(BaseModel):
    email: EmailStr


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class ResetBody(BaseModel):
    email: EmailStr
    code: str
    new_password: str = Field(min_length=6, max_length=128)


@router.post("/signup")
async def signup(body: SignupBody):
    email = body.email.lower()
    existing = await db.users.find_one({"email": email, "deleted_at": None})
    if existing:
        if existing.get("email_verified"):
            raise HTTPException(status_code=409, detail="An account with this email already exists.")
        # unverified — resend code
        code = await _issue_otp(existing["user_id"], email, existing["name"], "verify")
        return {"status": "otp_sent", "email": email, **_dev(code)}

    user_id = str(uuid.uuid4())
    username = email.split("@")[0] + secrets.token_hex(2)
    await db.users.insert_one({
        "user_id": user_id,
        "name": body.name.strip(),
        "email": email,
        "username": username,
        "bio": "",
        "avatar": None,
        "password": hash_password(body.password),
        "email_verified": False,
        "online": False,
        "last_seen": _now().isoformat(),
        "created_at": _now().isoformat(),
        "deleted_at": None,
    })
    # default privacy settings
    await db.privacy.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {
            "user_id": user_id,
            "messages": True, "files": True, "memory": True, "contacts": True,
            "location": False, "calendar": True, "web_search": True, "calls": False,
            "images": True, "documents": True,
        }},
        upsert=True,
    )
    code = await _issue_otp(user_id, email, body.name.strip(), "verify")
    return {"status": "otp_sent", "email": email, **_dev(code)}


@router.post("/verify-otp")
async def verify_otp(body: VerifyBody):
    email = body.email.lower()
    user = await db.users.find_one({"email": email, "deleted_at": None})
    if not user:
        raise HTTPException(status_code=404, detail="Account not found.")
    await _verify_otp(user["user_id"], "verify", body.code)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"email_verified": True}})
    token = create_token(user["user_id"])
    user["email_verified"] = True
    return {"token": token, "user": _public_user(user)}


@router.post("/resend-otp")
async def resend_otp(body: EmailBody):
    email = body.email.lower()
    user = await db.users.find_one({"email": email, "deleted_at": None})
    if not user:
        raise HTTPException(status_code=404, detail="Account not found.")
    if user.get("email_verified"):
        raise HTTPException(status_code=400, detail="Email already verified.")
    code = await _issue_otp(user["user_id"], email, user["name"], "verify")
    return {"status": "otp_sent", "email": email, **_dev(code)}


@router.post("/login")
async def login(body: LoginBody):
    email = body.email.lower()
    user = await db.users.find_one({"email": email, "deleted_at": None})
    if not user or not verify_password(body.password, user["password"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    if not user.get("email_verified"):
        # Best-effort resend of a fresh verification code. If the email provider is
        # momentarily unavailable/rate-limited, we still return the actionable 403 so
        # the user is directed to the verify screen (where they can tap Resend) rather
        # than seeing a generic server error.
        try:
            await _issue_otp(user["user_id"], email, user["name"], "verify")
        except HTTPException:
            pass
        raise HTTPException(status_code=403, detail="Please verify your email first. We sent you a new code.")
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"last_seen": _now().isoformat()}})
    token = create_token(user["user_id"])
    return {"token": token, "user": _public_user(user)}


@router.post("/forgot-password")
async def forgot_password(body: EmailBody):
    email = body.email.lower()
    user = await db.users.find_one({"email": email, "deleted_at": None})
    # Do not reveal whether the account exists, but still issue if it does.
    if user:
        try:
            code = await _issue_otp(user["user_id"], email, user["name"], "reset")
            return {"status": "reset_sent", "email": email, **_dev(code)}
        except HTTPException as e:
            if e.status_code == 429:
                raise
    return {"status": "reset_sent", "email": email}


@router.post("/reset-password")
async def reset_password(body: ResetBody):
    email = body.email.lower()
    user = await db.users.find_one({"email": email, "deleted_at": None})
    if not user:
        raise HTTPException(status_code=404, detail="Account not found.")
    await _verify_otp(user["user_id"], "reset", body.code)
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"password": hash_password(body.new_password)}},
    )
    return {"status": "password_updated"}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return {"user": _public_user(user)}


class SessionBody(BaseModel):
    session_id: str


@router.post("/session")
async def google_session(body: SessionBody):
    """Exchange an Emergent Google OAuth session_id for a Chatly JWT.
    Upserts by email so the same Google account never creates a duplicate."""
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": body.session_id},
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Google sign-in failed. Please try again.")
        data = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google session exchange failed: {e}")
        raise HTTPException(status_code=502, detail="Could not reach Google sign-in service.")

    email = (data.get("email") or "").lower()
    if not email:
        raise HTTPException(status_code=401, detail="Google account has no email.")
    name = data.get("name") or email.split("@")[0]
    picture = data.get("picture")

    user = await db.users.find_one({"email": email, "deleted_at": None})
    if user:
        updates = {"email_verified": True, "last_seen": _now()}
        if picture and not user.get("avatar"):
            updates["avatar"] = picture
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": updates})
        user = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    else:
        user_id = str(uuid.uuid4())
        username = email.split("@")[0] + secrets.token_hex(2)
        user = {
            "user_id": user_id, "name": name, "email": email, "username": username,
            "bio": "", "avatar": picture, "password": None, "email_verified": True,
            "auth_provider": "google", "online": False, "last_seen": _now(),
            "created_at": _now(), "deleted_at": None,
        }
        await db.users.insert_one(dict(user))
        await db.privacy.update_one({"user_id": user_id}, {"$setOnInsert": {
            "user_id": user_id, "messages": True, "files": True, "memory": True, "contacts": True,
            "location": False, "calendar": True, "web_search": True, "calls": False,
            "images": True, "documents": True}}, upsert=True)
    token = create_token(user["user_id"])
    return {"token": token, "user": _public_user(user)}


class ProfileBody(BaseModel):
    name: str | None = None
    bio: str | None = None
    username: str | None = None
    avatar: str | None = None


@router.put("/me")
async def update_me(body: ProfileBody, user: dict = Depends(get_current_user)):
    import re
    updates = {k: v for k, v in body.model_dump().items() if v is not None}

    # Username validation + global uniqueness (case-insensitive)
    if "username" in updates:
        uname = (updates["username"] or "").strip().lstrip("@")
        reserved = {"admin", "chatly", "support", "root", "system", "me", "null", "undefined"}
        if not re.fullmatch(r"[a-zA-Z0-9_.]{3,20}", uname):
            raise HTTPException(status_code=400,
                                detail="Username must be 3-20 characters: letters, numbers, _ or .")
        if uname.lower() in reserved:
            raise HTTPException(status_code=400, detail="That username is reserved.")
        clash = await db.users.find_one({
            "username": {"$regex": f"^{re.escape(uname)}$", "$options": "i"},
            "user_id": {"$ne": user["user_id"]}, "deleted_at": None,
        })
        if clash:
            raise HTTPException(status_code=409, detail="That username is already taken.")
        updates["username"] = uname

    if "name" in updates:
        nm = (updates["name"] or "").strip()
        if not nm:
            raise HTTPException(status_code=400, detail="Name cannot be empty.")
        updates["name"] = nm[:60]
    if "bio" in updates:
        updates["bio"] = (updates["bio"] or "")[:200]

    if updates:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": updates})
    fresh = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    try:
        import firebase_service as fb
        fb.mirror_user(fresh)
    except Exception:
        pass
    return {"user": _public_user(fresh)}


@router.get("/username-available")
async def username_available(u: str, user: dict = Depends(get_current_user)):
    import re
    uname = (u or "").strip().lstrip("@")
    if not re.fullmatch(r"[a-zA-Z0-9_.]{3,20}", uname):
        return {"available": False, "reason": "invalid"}
    clash = await db.users.find_one({
        "username": {"$regex": f"^{re.escape(uname)}$", "$options": "i"},
        "user_id": {"$ne": user["user_id"]}, "deleted_at": None,
    })
    return {"available": not clash}


@router.delete("/me")
async def delete_me(user: dict = Depends(get_current_user)):
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"deleted_at": _now().isoformat(), "email_verified": False}},
    )
    return {"status": "deleted"}
