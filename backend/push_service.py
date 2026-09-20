import logging
import os
from typing import Any
import httpx

logger = logging.getLogger(__name__)
PUSH_BASE_URL = "https://integrations.emergentagent.com"
PUSH_KEY = os.environ.get("EMERGENT_PUSH_KEY", "placeholder")

async def register_managed_push(user_id: str, platform: str, device_token: str) -> None:
    payload = {"user_id": user_id, "platform": platform, "device_token": device_token}
    async with httpx.AsyncClient(base_url=PUSH_BASE_URL, headers={"X-Push-Key": PUSH_KEY}, timeout=10.0) as client:
        response = await client.post("/api/v1/push/users/register", json=payload)
    if response.status_code == 401:
        raise RuntimeError("Push provider credentials are not configured")
    if response.status_code >= 500:
        raise RuntimeError("Push provider unavailable")
    response.raise_for_status()

async def send_push(recipients: list[str], data: dict[str, Any], idempotency_key: str | None = None) -> None:
    if not recipients:
        return
    if len(recipients) > 100:
        raise ValueError("Push batches support at most 100 recipients")
    if not data.get("title") or not data.get("message"):
        raise ValueError("Push data requires title and message")
    payload: dict[str, Any] = {"recipients": recipients, "data": data}
    if idempotency_key:
        payload["$idempotency_key"] = idempotency_key
    async with httpx.AsyncClient(base_url=PUSH_BASE_URL, headers={"X-Push-Key": PUSH_KEY}, timeout=10.0) as client:
        response = await client.post("/api/v1/push/trigger", json=payload)
    if response.status_code == 401:
        raise RuntimeError("Push provider credentials are not configured")
    if response.status_code >= 500:
        raise RuntimeError("Push provider unavailable")
    response.raise_for_status()

async def safe_send_push(recipients: list[str], data: dict[str, Any], idempotency_key: str | None = None) -> None:
    try:
        await send_push(recipients, data, idempotency_key)
    except Exception as exc:
        logger.warning("managed push failed (non-blocking): %s", exc)
