import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from security import get_current_user
from push_service import register_managed_push

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["push"])

class RegisterPushBody(BaseModel):
    user_id: str = Field(min_length=1, max_length=160)
    platform: str = Field(pattern="^(android|ios)$")
    device_token: str = Field(min_length=8, max_length=4096)

@router.post("/register-push", status_code=201)
async def register_push(body: RegisterPushBody, user: dict = Depends(get_current_user)):
    if body.user_id != user["user_id"]:
        raise HTTPException(status_code=403, detail="You can only register your own device.")
    try:
        await register_managed_push(body.user_id, body.platform, body.device_token)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        logger.exception("push registration failed")
        raise HTTPException(status_code=502, detail="Push registration failed. Please try again.")
    return {"status": "registered"}
