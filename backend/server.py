import logging
from datetime import datetime, timezone
from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from db import db, client
from security import get_user_id_from_token, hash_password
from ws_manager import manager
from ai_service import AIServiceError
import auth
import chat_routes
import ai_routes
import productivity_routes
import social_routes
import groups_routes
import files_routes
import calls_routes
import status_routes
import firebase_routes
import firebase_service
from storage_service import init_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Chatly AI Messenger API")

health = APIRouter(prefix="/api")


@health.get("/")
async def root():
    return {"message": "Chatly AI Messenger API", "status": "ok"}


app.include_router(health)


@app.exception_handler(AIServiceError)
async def ai_service_error_handler(request: Request, exc: AIServiceError):
    """Global AI/search error boundary: predictable JSON, user-safe message only.
    503 signals a transient/provider condition the client can retry."""
    logger.warning(f"[AI] handled AIServiceError provider={exc.provider} "
                   f"category={exc.category} status={exc.status} path={request.url.path}")
    return JSONResponse(
        status_code=503,
        content={
            "detail": exc.message,
            "error": {"type": "ai_error", "category": exc.category,
                      "provider": exc.provider, "retryable": exc.category in ("exhausted", "circuit_open", "rate_limited")},
        },
    )
app.include_router(auth.router)
app.include_router(chat_routes.router)
app.include_router(ai_routes.router)
app.include_router(productivity_routes.router)
app.include_router(social_routes.router)
app.include_router(groups_routes.router)
app.include_router(files_routes.router)
app.include_router(calls_routes.router)
app.include_router(status_routes.router)
app.include_router(firebase_routes.router)


@app.websocket("/api/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(...)):
    user_id = await get_user_id_from_token(token)
    if not user_id:
        await ws.close(code=4401)
        return
    await manager.connect(user_id, ws)
    await db.users.update_one({"user_id": user_id}, {"$set": {"online": True}})
    try:
        while True:
            data = await ws.receive_json()
            t = data.get("type")
            if t == "ping":
                await ws.send_json({"type": "pong"})
            elif t in ("call_offer", "call_answer", "call_ice", "call_hangup", "call_ringing"):
                # Relay WebRTC signaling to the target participant(s). The backend
                # never trusts client participant IDs beyond routing; call authorization
                # is enforced by the REST /api/calls endpoints and the DB session.
                to = data.get("to")
                if to:
                    await manager.send_to_user(to, {**data, "from": user_id})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WS error: {e}")
    finally:
        await manager.disconnect(user_id, ws)
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"online": False, "last_seen": datetime.now(timezone.utc).isoformat()}},
        )


DEMO_CONTACTS = [
    {"name": "Rahul Sharma", "persona": "a busy project manager who talks about work, deadlines, meetings and files. Mixes Hindi and English (Hinglish).",
     "avatar": "https://images.unsplash.com/photo-1543132220-3ec99c6094dc?crop=entropy&cs=srgb&fm=jpg&w=200&q=80",
     "seed": ["Bro, project ki requirements aa gayi hain. Can you review by tomorrow?",
              "Also meeting 5 PM par hai kal, client ke saath.",
              "Please send the presentation by Friday, it's important."]},
    {"name": "Priya Verma", "persona": "a friendly designer who discusses creative work, feedback and casual plans.",
     "avatar": "https://images.unsplash.com/photo-1506863530036-1efeddceb993?crop=entropy&cs=srgb&fm=jpg&w=200&q=80",
     "seed": ["Hey! I shared the new design mockups in the drive.",
              "Let me know your thoughts when you get a chance.",
              "Are we still on for coffee this weekend?"]},
    {"name": "Aman Gupta", "persona": "a college friend who talks about payments, invoices, and shared expenses.",
     "avatar": "https://images.unsplash.com/photo-1604904612715-47bf9d9bc670?crop=entropy&cs=srgb&fm=jpg&w=200&q=80",
     "seed": ["Yaar, invoice ka payment pending hai. ₹48,500 due hai.",
              "Can you confirm the amount from your side?",
              "Deadline for the payment is end of this month."]},
]


async def _seed_demo_contacts():
    for c in DEMO_CONTACTS:
        email = c["name"].lower().replace(" ", ".") + "@chatly.demo"
        existing = await db.users.find_one({"email": email})
        if existing:
            continue
        uid = "bot_" + email.split("@")[0].replace(".", "_")
        await db.users.insert_one({
            "user_id": uid, "name": c["name"], "email": email,
            "username": email.split("@")[0], "bio": c["persona"][:60],
            "avatar": c["avatar"], "password": hash_password("demo_bot_no_login"),
            "email_verified": True, "is_bot": True, "persona": c["persona"],
            "online": True, "last_seen": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(), "deleted_at": None,
            "seed_messages": c["seed"],
        })
        logger.info(f"Seeded demo contact {c['name']}")


async def _seed_test_user():
    """A pre-verified account for QA / demo so the full app can be exercised
    without email OTP. Real users sign up with their real email (OTP works)."""
    accounts = [
        {"email": "demo@chatly.app", "uid": "user_demo_chatly", "name": "Demo User", "username": "demouser"},
        {"email": "demo2@chatly.app", "uid": "user_demo2_chatly", "name": "Aria Nair", "username": "arianair"},
    ]
    for a in accounts:
        existing = await db.users.find_one({"email": a["email"]})
        if existing:
            continue
        await db.users.insert_one({
            "user_id": a["uid"], "name": a["name"], "email": a["email"],
            "username": a["username"], "bio": "Exploring Chatly AI", "avatar": None,
            "password": hash_password("Demo1234"), "email_verified": True,
            "online": False, "last_seen": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(), "deleted_at": None,
        })
        await db.privacy.update_one({"user_id": a["uid"]}, {"$setOnInsert": {
            "user_id": a["uid"], "messages": True, "files": True, "memory": True, "contacts": True,
            "location": False, "calendar": True, "web_search": True, "calls": False,
            "images": True, "documents": True}}, upsert=True)
        logger.info(f"Seeded demo login user {a['email']}")


async def _backfill_qr_tokens():
    """Ensure every existing user has a permanent unique QR token."""
    import secrets
    cursor = db.users.find({"$or": [{"qr_token": {"$exists": False}}, {"qr_token": None}]}, {"_id": 0, "user_id": 1})
    async for u in cursor:
        token = "CHATLY-" + secrets.token_urlsafe(9)
        await db.users.update_one({"user_id": u["user_id"]}, {"$set": {"qr_token": token}})


@app.on_event("startup")
async def on_startup():
    await _seed_demo_contacts()
    await _seed_test_user()
    await _backfill_qr_tokens()
    try:
        firebase_service.init_firebase()
        logger.info("Firebase Admin status: %s", firebase_service.status())
    except Exception as e:
        logger.warning(f"Firebase init deferred: {e}")
    try:
        await init_storage()
        logger.info("Object storage initialized")
    except Exception as e:
        logger.warning(f"Storage init deferred: {e}")
    logger.info("Chatly backend started")


@app.on_event("shutdown")
async def on_shutdown():
    client.close()


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
