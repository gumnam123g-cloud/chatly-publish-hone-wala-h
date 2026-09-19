"""Status / Stories feature. Users post text, photo (base64) or video (object
storage). Statuses auto-expire after 24h. Visible to the author and their
mutual contacts only."""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from db import db
from security import get_current_user, get_user_id_from_token
from ws_manager import manager
from storage_service import put_object, get_object, build_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["status"])

STATUS_TTL_HOURS = 24  # retained for backward-compat only; statuses are now permanent
MAX_IMG_B64 = 8_000_000          # ~8 MB base64 (≈6 MB image)
MAX_VIDEO = 200 * 1024 * 1024    # 200 MB (large-video support)


def _now():
    return datetime.now(timezone.utc)


def _pub(u: dict) -> dict:
    return {
        "user_id": u["user_id"], "name": u.get("name", "User"),
        "avatar": u.get("avatar"), "username": u.get("username"),
    }


def _clean(st: dict, me: str) -> dict:
    return {
        "id": st["id"], "user_id": st["user_id"], "kind": st["kind"],
        "text": st.get("text", ""), "bg": st.get("bg"),
        "media_b64": st.get("media_b64"), "media_path": st.get("media_path"),
        "mime": st.get("mime"), "created_at": st["created_at"],
        "expires_at": st["expires_at"], "seen": me in st.get("views", []),
        "views_count": len(st.get("views", [])),
    }


async def _active_statuses(user_id: str):
    # Statuses are permanent (no 24h expiry). Newest last for viewer ordering.
    cursor = db.statuses.find({"user_id": user_id}, {"_id": 0}).sort("created_at", 1)
    return [s async for s in cursor]


async def _contact_ids(user_id: str) -> list[str]:
    cursor = db.contacts.find({"user_id": user_id}, {"_id": 0, "contact_id": 1})
    return [c["contact_id"] async for c in cursor]


class StatusBody(BaseModel):
    kind: str = Field(pattern="^(text|image)$")
    text: str | None = Field(default=None, max_length=700)
    bg: str | None = None
    media_b64: str | None = None  # full data URI for image statuses


@router.post("/status")
async def create_status(body: StatusBody, user: dict = Depends(get_current_user)):
    if body.kind == "text":
        if not (body.text or "").strip():
            raise HTTPException(status_code=400, detail="Status text is required.")
    else:  # image
        if not body.media_b64 or not body.media_b64.startswith("data:"):
            raise HTTPException(status_code=400, detail="A valid image is required.")
        if len(body.media_b64) > MAX_IMG_B64:
            raise HTTPException(status_code=413, detail="Image is too large. Please pick a smaller one.")
    now = _now()
    doc = {
        "id": str(uuid.uuid4()), "user_id": user["user_id"], "kind": body.kind,
        "text": (body.text or "").strip(), "bg": body.bg,
        "media_b64": body.media_b64 if body.kind == "image" else None,
        "media_path": None, "mime": None,
        "created_at": now.isoformat(),
        "expires_at": None,  # permanent status
        "views": [],
    }
    await db.statuses.insert_one(dict(doc))
    return {"status": _clean(doc, user["user_id"])}


@router.post("/status/video")
async def create_video_status(file: UploadFile = File(...), caption: str = Form(""),
                              user: dict = Depends(get_current_user)):
    data = await file.read()
    if not data or len(data) > MAX_VIDEO:
        raise HTTPException(status_code=413, detail="Video must be non-empty and under 25 MB.")
    fname = file.filename or "status.mp4"
    ext = ("." + fname.rsplit(".", 1)[-1].lower()) if "." in fname else ".mp4"
    path = build_path(user["user_id"], ext, str(uuid.uuid4()))
    try:
        await put_object(path, data, file.content_type or "video/mp4")
    except Exception as e:
        logger.error(f"Status video upload failed: {e}")
        raise HTTPException(status_code=502, detail="Upload failed. Please retry.")
    now = _now()
    doc = {
        "id": str(uuid.uuid4()), "user_id": user["user_id"], "kind": "video",
        "text": (caption or "").strip(), "bg": None, "media_b64": None,
        "media_path": path, "mime": file.content_type or "video/mp4",
        "created_at": now.isoformat(),
        "expires_at": None,  # permanent status
        "views": [],
    }
    await db.statuses.insert_one(dict(doc))
    return {"status": _clean(doc, user["user_id"])}


@router.get("/status/feed")
async def status_feed(user: dict = Depends(get_current_user)):
    me = user["user_id"]
    mine = [_clean(s, me) for s in await _active_statuses(me)]
    groups = []
    for cid in await _contact_ids(me):
        sts = await _active_statuses(cid)
        if not sts:
            continue
        u = await db.users.find_one({"user_id": cid, "deleted_at": None}, {"_id": 0})
        if not u:
            continue
        cleaned = [_clean(s, me) for s in sts]
        groups.append({
            "user": _pub(u),
            "statuses": cleaned,
            "has_unseen": any(not c["seen"] for c in cleaned),
            "last_ts": cleaned[-1]["created_at"],
        })
    groups.sort(key=lambda g: (not g["has_unseen"], ), reverse=False)
    return {"mine": mine, "mine_user": _pub(user), "others": groups}


@router.get("/status/media/{path:path}")
async def status_media(path: str, token: str = Query(None)):
    uid = await get_user_id_from_token(token) if token else None
    if not uid:
        raise HTTPException(status_code=401, detail="Unauthorized")
    st = await db.statuses.find_one({"media_path": path}, {"_id": 0})
    if not st:
        raise HTTPException(status_code=404, detail="Status not found.")
    if st["user_id"] != uid:
        allowed = await db.contacts.find_one({"user_id": uid, "contact_id": st["user_id"]})
        if not allowed:
            raise HTTPException(status_code=403, detail="Not authorized.")
    try:
        content, ctype = await get_object(path)
    except Exception:
        raise HTTPException(status_code=404, detail="Media unavailable.")
    return Response(content=content, media_type=ctype)


@router.post("/status/{sid}/view")
async def view_status(sid: str, user: dict = Depends(get_current_user)):
    await db.statuses.update_one({"id": sid}, {"$addToSet": {"views": user["user_id"]}})
    return {"ok": True}


@router.delete("/status/{sid}")
async def delete_status(sid: str, user: dict = Depends(get_current_user)):
    st = await db.statuses.find_one({"id": sid, "user_id": user["user_id"]})
    if not st:
        raise HTTPException(status_code=404, detail="Status not found.")
    await db.statuses.delete_one({"id": sid})
    return {"status": "deleted"}
