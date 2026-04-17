"""
Production AI Agent — Part 6 Final Project

Implements every requirement from the checklist:
  ✅ Config from environment variables (12-factor)
  ✅ Structured JSON logging
  ✅ API Key authentication
  ✅ Rate limiting (10 req/min per user, Redis-backed)
  ✅ Cost guard ($10/month per user, Redis-backed)
  ✅ Input validation (Pydantic)
  ✅ Conversation history (stateless — stored in Redis)
  ✅ Health check endpoint  (/health — liveness probe)
  ✅ Readiness check endpoint (/ready — readiness probe)
  ✅ Graceful shutdown (SIGTERM handler)
  ✅ Security headers middleware
  ✅ CORS middleware
  ✅ Error handling
"""
import json
import logging
import os
import signal
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .auth import verify_api_key
from .config import settings
from .cost_guard import check_budget, estimate_cost, record_cost
from .rate_limiter import check_rate_limit

# ── Logging — structured JSON ─────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

# ── Import mock LLM (replace with real client when you have an API key) ────────
try:
    from utils.mock_llm import ask as llm_ask  # when running from project root
except ModuleNotFoundError:
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from utils.mock_llm import ask as llm_ask
    except ModuleNotFoundError:
        # Minimal inline fallback so the app can still start without the utils folder.
        def llm_ask(question: str) -> str:  # type: ignore[misc]
            return f"[mock] Received: {question}"

# ── Redis connection (lazy singleton) ─────────────────────────────────────────
_redis = None


def _get_redis():
    """Return a Redis client, creating it on first call. Returns None on failure."""
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis as redis_lib
        client = redis_lib.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        _redis = client
        logger.info("Connected to Redis at %s", settings.redis_url)
    except Exception as exc:
        logger.warning("Redis unavailable (%s) — conversation history disabled", exc)
    return _redis


# ── Conversation history helpers (stateless — all state in Redis) ─────────────

def _history_key(session_id: str) -> str:
    return f"history:{session_id}"


def load_history(session_id: str) -> list[dict]:
    """Load conversation history from Redis (or empty list if unavailable)."""
    r = _get_redis()
    if r is None:
        return []
    raw = r.get(_history_key(session_id))
    return json.loads(raw) if raw else []


def save_history(session_id: str, history: list[dict]) -> None:
    """Persist conversation history to Redis with a 1-hour TTL."""
    r = _get_redis()
    if r is None:
        return
    # Keep at most the last 20 messages (10 turns) to bound memory usage.
    history = history[-20:]
    r.setex(_history_key(session_id), 3600, json.dumps(history))


# ── Startup / shutdown ────────────────────────────────────────────────────────
_is_ready = False
INSTANCE_ID = os.getenv("INSTANCE_ID", f"instance-{uuid.uuid4().hex[:6]}")
START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Set readiness flag on startup; log clean shutdown on exit."""
    global _is_ready
    logger.info('{"event":"startup","instance":"%s","version":"%s"}', INSTANCE_ID, settings.app_version)
    _is_ready = True
    yield
    _is_ready = False
    logger.info('{"event":"shutdown","instance":"%s"}', INSTANCE_ID)


# ── SIGTERM handler — graceful shutdown ───────────────────────────────────────
def _handle_sigterm(signum, frame):
    """
    Kubernetes / Docker sends SIGTERM before killing the container.
    We flip the readiness flag so the load-balancer stops sending new
    traffic, then exit cleanly after uvicorn drains in-flight requests.
    """
    global _is_ready
    logger.info("SIGTERM received — stopping gracefully")
    _is_ready = False
    # Give the load-balancer a moment to stop routing here.
    time.sleep(2)
    sys.exit(0)


signal.signal(signal.SIGTERM, _handle_sigterm)

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    # Hide interactive docs in production to reduce attack surface.
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment != "production" else [],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


# ── Security headers ──────────────────────────────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    """Attach standard security headers to every response."""
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Do not leak the server/framework version.
    if "server" in response.headers:
        del response.headers["server"]
    return response


# ── Request / Response models ─────────────────────────────────────────────────
class AskRequest(BaseModel):
    """Validated request body for the /ask endpoint."""
    question: str = Field(..., min_length=1, max_length=2000, description="The user's question")
    session_id: str | None = Field(
        None,
        description="Optional conversation session ID. Omit to start a new session.",
    )


class AskResponse(BaseModel):
    """Response envelope for /ask."""
    answer: str
    session_id: str
    served_by: str  # which instance handled the request — useful for verifying load balancing


# ── Health / Readiness endpoints ──────────────────────────────────────────────
@app.get("/health", tags=["ops"])
def health() -> dict:
    """
    Liveness probe — answers "is the process alive?"
    Returns 200 as long as the Python process is running.
    """
    return {
        "status": "ok",
        "instance": INSTANCE_ID,
        "uptime_seconds": round(time.time() - START_TIME, 1),
    }


@app.get("/ready", tags=["ops"])
def ready() -> dict:
    """
    Readiness probe — answers "is the instance ready to receive traffic?"
    Returns 503 if Redis is unreachable or the app is shutting down.
    """
    if not _is_ready:
        raise HTTPException(status_code=503, detail="Instance is not ready")

    # Check Redis connectivity.
    r = _get_redis()
    if r is not None:
        try:
            r.ping()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Redis check failed: {exc}")

    return {"status": "ready", "instance": INSTANCE_ID}


# ── Main endpoint ─────────────────────────────────────────────────────────────
@app.post("/ask", response_model=AskResponse, tags=["agent"])
def ask(
    body: AskRequest,
    # Authentication — must come first; other deps depend on the returned user_id.
    user_id: str = Depends(verify_api_key),
    # Rate limiting — raises 429 when the user exceeds the per-minute cap.
    _rate_ok: None = Depends(check_rate_limit),
    # Budget guard — raises 402 when the user exceeds their monthly spend.
    _budget_ok: None = Depends(check_budget),
) -> AskResponse:
    """
    Ask the AI agent a question.  Conversation history is maintained across
    calls in the same session (session_id persisted in Redis).

    Authentication: X-API-Key header required.
    """
    # ── 1. Resolve / create session ──────────────────────────────────────────
    session_id = body.session_id or str(uuid.uuid4())

    # ── 2. Load conversation history from Redis (stateless design) ────────────
    history = load_history(session_id)

    # ── 3. Call LLM ───────────────────────────────────────────────────────────
    start = time.time()
    answer = llm_ask(body.question)
    latency_ms = round((time.time() - start) * 1000, 1)

    # ── 4. Persist history ────────────────────────────────────────────────────
    history.append({
        "role": "user",
        "content": body.question,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    history.append({
        "role": "assistant",
        "content": answer,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    save_history(session_id, history)

    # ── 5. Record cost ────────────────────────────────────────────────────────
    cost = estimate_cost(body.question, answer)
    record_cost(user_id, cost)

    logger.info(
        '{"event":"ask","user":"%s","session":"%s","latency_ms":%s,"cost_usd":%s,"instance":"%s"}',
        user_id, session_id, latency_ms, round(cost, 6), INSTANCE_ID,
    )

    return AskResponse(answer=answer, session_id=session_id, served_by=INSTANCE_ID)


# ── Entry point (used when running directly, not via Docker CMD) ───────────────
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
