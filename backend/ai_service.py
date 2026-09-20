"""Provider-agnostic AI layer. Sarvam AI is primary; Emergent universal LLM is fallback.
Also wraps Tavily web search. All secrets stay server-side only.

Reliability layer (P0):
- Up to 5 attempts with exponential backoff (0s, 1s, 2s, 4s, 8s) on TRANSIENT failures only.
- Per-provider circuit breaker so we stop hammering an unhealthy provider.
- Structured server-side logging (provider, request id, attempt, category, status, latency).
- AIServiceError carries only a user-safe message; API keys / raw errors never reach the client.
"""
import os
import json
import time
import uuid
import asyncio
import logging
import httpx

logger = logging.getLogger(__name__)

SARVAM_API_KEY = os.environ["SARVAM_API_KEY"]
SARVAM_MODEL = os.environ.get("SARVAM_MODEL", "sarvam-105b")
SARVAM_URL = "https://api.sarvam.ai/v1/chat/completions"
TAVILY_API_KEY = os.environ["TAVILY_API_KEY"]
TAVILY_URL = "https://api.tavily.com/search"
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")

# Retry policy: attempt 1 immediate, then 1s, 2s, 4s, 8s before attempts 2..5.
MAX_ATTEMPTS = 5
BACKOFF_DELAYS = [0, 1, 2, 4, 8]
SARVAM_TIMEOUT = 120
TAVILY_TIMEOUT = 60


class AIServiceError(Exception):
    """Raised when an AI/search provider cannot fulfil a request. `message` is
    always safe to show a user; `category`/`provider`/`status` are for logging."""

    def __init__(self, message: str, *, category: str = "ai_error",
                 provider: str | None = None, status: int | None = None):
        self.message = message
        self.category = category
        self.provider = provider
        self.status = status
        super().__init__(message)


class CircuitBreaker:
    """Simple per-provider breaker: closed -> open (after N consecutive request
    failures) -> half_open (after cooldown) -> closed on the next success."""

    def __init__(self, name: str, fail_threshold: int = 4, reset_timeout: float = 30.0):
        self.name = name
        self.fail_threshold = fail_threshold
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.state = "closed"  # closed | open | half_open
        self.opened_at = 0.0

    def allow(self) -> bool:
        if self.state == "open":
            if (time.monotonic() - self.opened_at) >= self.reset_timeout:
                self.state = "half_open"
                logger.info(f"[AI] circuit provider={self.name} state=half_open (trial)")
                return True
            return False
        return True

    def record_success(self):
        if self.state != "closed" or self.failures:
            logger.info(f"[AI] circuit provider={self.name} state=closed (recovered)")
        self.failures = 0
        self.state = "closed"

    def record_failure(self):
        self.failures += 1
        if self.state == "half_open" or self.failures >= self.fail_threshold:
            self.state = "open"
            self.opened_at = time.monotonic()
            logger.warning(f"[AI] circuit provider={self.name} state=open "
                           f"failures={self.failures} cooldown={self.reset_timeout}s")


_breakers = {"sarvam": CircuitBreaker("sarvam"), "tavily": CircuitBreaker("tavily")}


def _is_transient(exc: Exception) -> bool:
    """Only retry transient faults: network/timeouts, 429 and 5xx. 4xx (bad
    request / auth) are permanent and must not be retried."""
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError,
                        httpx.WriteError, httpx.RemoteProtocolError, httpx.PoolTimeout)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or 500 <= code < 600
    return False


def _category(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 429:
            return "rate_limited"
        if code in (401, 403):
            return "auth"
        if 400 <= code < 500:
            return "bad_request"
        if code >= 500:
            return "server_error"
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
        return "connection"
    return "unknown"


def _safe_message(category: str, provider: str | None) -> str:
    label = "Web search" if provider == "tavily" else "Chatly AI"
    return {
        "auth": f"{label} is not configured correctly. Please contact support.",
        "bad_request": f"{label} could not process that request. Please rephrase and try again.",
        "rate_limited": f"{label} is busy right now. Please try again in a moment.",
        "circuit_open": f"{label} is temporarily unavailable. Please try again shortly.",
        "exhausted": f"{label} is busy right now. Please try again in a moment.",
    }.get(category, f"{label} is temporarily unavailable. Please try again.")


async def _run_with_retry(provider: str, do):
    """Run coroutine factory `do` with retry + backoff + circuit breaking.
    A single request records at most ONE breaker failure (on final exhaustion)."""
    breaker = _breakers[provider]
    req_id = uuid.uuid4().hex[:12]
    if not breaker.allow():
        logger.warning(f"[AI] provider={provider} req={req_id} outcome=circuit_open")
        raise AIServiceError(_safe_message("circuit_open", provider),
                             category="circuit_open", provider=provider)
    last_exc: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        delay = BACKOFF_DELAYS[attempt - 1]
        if delay:
            await asyncio.sleep(delay)
        start = time.monotonic()
        try:
            result = await do()
            latency = round((time.monotonic() - start) * 1000)
            breaker.record_success()
            logger.info(f"[AI] provider={provider} req={req_id} attempt={attempt} "
                        f"status=200 category=ok latency_ms={latency} outcome=success")
            return result
        except Exception as e:  # noqa: BLE001 - we classify below
            latency = round((time.monotonic() - start) * 1000)
            transient = _is_transient(e)
            status = e.response.status_code if isinstance(e, httpx.HTTPStatusError) else None
            category = _category(e)
            logger.warning(f"[AI] provider={provider} req={req_id} attempt={attempt} "
                           f"status={status} category={category} latency_ms={latency} "
                           f"transient={transient} outcome=error err={str(e)[:180]}")
            last_exc = e
            if not transient:
                # Permanent (4xx/auth/bad request): do NOT retry, do NOT open circuit.
                raise AIServiceError(_safe_message(category, provider),
                                     category=category, provider=provider, status=status) from e
            # transient -> loop and back off
    breaker.record_failure()
    logger.error(f"[AI] provider={provider} req={req_id} outcome=exhausted attempts={MAX_ATTEMPTS}")
    raise AIServiceError(_safe_message("exhausted", provider),
                         category="exhausted", provider=provider) from last_exc


async def _sarvam_chat(messages: list[dict], temperature: float = 0.5, max_tokens: int = 1200) -> str:
    # sarvam-105b is a reasoning model: reasoning_content consumes the token budget
    # before content is produced. Add generous headroom + low effort so `content`
    # is never truncated to empty (finish_reason="length").
    payload = {
        "model": SARVAM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens + 2500,
        "reasoning_effort": "low",
    }

    async def _do() -> str:
        async with httpx.AsyncClient(timeout=SARVAM_TIMEOUT) as c:
            resp = await c.post(
                SARVAM_URL,
                headers={"Content-Type": "application/json", "api-subscription-key": SARVAM_API_KEY},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return (data["choices"][0]["message"]["content"] or "").strip()

    return await _run_with_retry("sarvam", _do)


async def ai_chat(messages: list[dict], temperature: float = 0.5, max_tokens: int = 1200) -> str:
    """Sarvam AI only — no cross-provider fallback. Retries with headroom on empty completions."""
    out = await _sarvam_chat(messages, temperature, max_tokens)
    if not out:  # reasoning consumed budget — retry once with more headroom
        out = await _sarvam_chat(messages, temperature, max_tokens + 2000)
    if out:
        return out
    raise AIServiceError(
        "Chatly AI could not produce a response. Please try again.",
        category="empty_response", provider="sarvam",
    )


async def ai_complete(system: str, prompt: str, temperature: float = 0.5, max_tokens: int = 1200) -> str:
    return await ai_chat(
        [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        temperature,
        max_tokens,
    )


async def ai_json(system: str, prompt: str, max_tokens: int = 1500) -> dict | list:
    """Ask the model for strict JSON and parse it defensively."""
    sys = system + "\n\nRespond with ONLY valid JSON. No markdown, no code fences, no commentary."
    raw = await ai_chat(
        [{"role": "system", "content": sys}, {"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=max_tokens,
    )
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1] if "```" in raw else raw
        raw = raw.replace("json", "", 1).strip() if raw.lstrip().startswith("json") else raw
    # extract first { or [ ... to last } or ]
    start = min([i for i in [raw.find("{"), raw.find("[")] if i != -1] or [0])
    end = max(raw.rfind("}"), raw.rfind("]"))
    if end != -1:
        raw = raw[start:end + 1]
    try:
        return json.loads(raw)
    except Exception as e:
        logger.error(f"JSON parse failed: {e}; raw={raw[:400]}")
        return {}


async def tavily_search(query: str, max_results: int = 6) -> dict:
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "include_answer": True,
        "search_depth": "advanced",
    }

    async def _do() -> dict:
        async with httpx.AsyncClient(timeout=TAVILY_TIMEOUT) as c:
            resp = await c.post(TAVILY_URL, json=payload)
            resp.raise_for_status()
            return resp.json()

    return await _run_with_retry("tavily", _do)
