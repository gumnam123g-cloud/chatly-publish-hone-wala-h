"""
Firebase Admin SDK layer for Chatly (server-side, privileged).

The service-account JSON lives ONLY on the backend (never shipped to the client),
which satisfies the security requirement. This module exposes safe helpers for:
  - verifying Firebase ID tokens (Google Sign-In bridge)
  - Firestore access (server-side mirror / privileged reads-writes)
  - Storage bucket access (privileged cleanup)
  - Cloud Messaging (FCM) push send
  - account deletion in Firebase Auth

Everything is lazy-initialised and fails soft so a Firebase misconfiguration can
never crash the FastAPI process — callers get a clear FirebaseUnavailable error.
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logger = logging.getLogger(__name__)

_CRED_PATH = os.environ.get("FIREBASE_CREDENTIALS", str(ROOT_DIR / "firebase-admin.json"))
_BUCKET = os.environ.get("FIREBASE_STORAGE_BUCKET", "chatlyai-12478.firebasestorage.app")

_app = None
_db = None
_ready = False
_init_error = None


class FirebaseUnavailable(Exception):
    """Raised when a Firebase operation is attempted but Admin SDK is not initialised."""


def init_firebase():
    """Initialise the Admin SDK once (singleton). Safe to call repeatedly."""
    global _app, _db, _ready, _init_error
    if _ready:
        return True
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not os.path.exists(_CRED_PATH):
            raise FileNotFoundError(f"Service account not found at {_CRED_PATH}")

        if not firebase_admin._apps:
            cred = credentials.Certificate(_CRED_PATH)
            _app = firebase_admin.initialize_app(cred, {"storageBucket": _BUCKET})
        else:
            _app = firebase_admin.get_app()
        _db = firestore.client()
        _ready = True
        _init_error = None
        logger.info("Firebase Admin initialised (project bucket=%s)", _BUCKET)
        return True
    except Exception as e:  # pragma: no cover - depends on live creds
        _init_error = str(e)
        _ready = False
        logger.warning("Firebase Admin init failed: %s", e)
        return False


def is_ready() -> bool:
    return _ready or init_firebase()


def status() -> dict:
    ok = is_ready()
    return {"ready": ok, "bucket": _BUCKET, "error": None if ok else _init_error}


def get_db():
    if not is_ready():
        raise FirebaseUnavailable(_init_error or "Firebase not initialised")
    return _db


def get_bucket():
    if not is_ready():
        raise FirebaseUnavailable(_init_error or "Firebase not initialised")
    from firebase_admin import storage
    return storage.bucket()


# ---------------- Auth ----------------

def verify_id_token(id_token: str) -> dict:
    """Verify a Firebase ID token (from client Google/Email sign-in). Returns decoded claims."""
    if not is_ready():
        raise FirebaseUnavailable(_init_error or "Firebase not initialised")
    from firebase_admin import auth as fb_auth
    return fb_auth.verify_id_token(id_token)


def delete_auth_user(uid: str | None = None, email: str | None = None) -> bool:
    """Delete a Firebase Auth user by uid or email. Returns True if a user was deleted.
    Never raises for 'user not found' — those users simply never used Firebase Auth."""
    if not is_ready():
        return False
    from firebase_admin import auth as fb_auth
    try:
        if not uid and email:
            try:
                rec = fb_auth.get_user_by_email(email)
                uid = rec.uid
            except Exception:
                return False
        if uid:
            fb_auth.delete_user(uid)
            return True
    except fb_auth.UserNotFoundError:
        return False
    except Exception as e:
        logger.warning("delete_auth_user error: %s", e)
    return False


# ---------------- FCM ----------------

def send_push(tokens: list[str], title: str, body: str, data: dict | None = None) -> dict:
    """Send an FCM notification to one or more device tokens.
    Returns {sent, failed, invalid_tokens}. Invalid tokens should be pruned by caller."""
    tokens = [t for t in (tokens or []) if t]
    if not tokens:
        return {"sent": 0, "failed": 0, "invalid_tokens": []}
    if not is_ready():
        raise FirebaseUnavailable(_init_error or "Firebase not initialised")
    from firebase_admin import messaging

    # Data payload must be all-strings for FCM
    str_data = {k: str(v) for k, v in (data or {}).items()}
    invalid: list[str] = []
    sent = 0
    failed = 0
    for tok in tokens:
        msg = messaging.Message(
            token=tok,
            notification=messaging.Notification(title=title, body=body),
            data=str_data,
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id=str_data.get("channel_id", "messages"),
                    sound="default",
                ),
            ),
        )
        try:
            messaging.send(msg)
            sent += 1
        except messaging.UnregisteredError:
            invalid.append(tok)
            failed += 1
        except Exception as e:
            logger.warning("FCM send failed: %s", e)
            failed += 1
    return {"sent": sent, "failed": failed, "invalid_tokens": invalid}


# ---------------- Storage cleanup ----------------

def delete_storage_prefix(prefix: str) -> int:
    """Delete all objects under a prefix (e.g. a user's media). Returns count deleted."""
    if not is_ready():
        return 0
    try:
        bucket = get_bucket()
        blobs = list(bucket.list_blobs(prefix=prefix))
        for b in blobs:
            try:
                b.delete()
            except Exception:
                pass
        return len(blobs)
    except Exception as e:
        logger.warning("delete_storage_prefix error: %s", e)
        return 0


# ---------------- Firestore user mirror ----------------

def mirror_user(user: dict):
    """Mirror the public profile to Firestore `users/{user_id}` so the client can do
    Firestore-native reads (search, QR resolution) with security rules. Best-effort."""
    if not is_ready():
        return
    try:
        db = get_db()
        db.collection("users").document(user["user_id"]).set({
            "user_id": user["user_id"],
            "name": user.get("name"),
            "username": user.get("username"),
            "username_lower": (user.get("username") or "").lower(),
            "name_lower": (user.get("name") or "").lower(),
            "avatar": user.get("avatar"),
            "bio": user.get("bio", ""),
            "qr_token": user.get("qr_token"),
            "is_bot": user.get("is_bot", False),
        }, merge=True)
    except Exception as e:
        logger.warning("mirror_user error: %s", e)


def delete_user_mirror(user_id: str):
    if not is_ready():
        return
    try:
        get_db().collection("users").document(user_id).delete()
    except Exception:
        pass
