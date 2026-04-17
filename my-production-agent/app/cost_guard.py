"""
Redis-Based Monthly Cost Guard

Purpose: Prevent surprise LLM bills by tracking estimated spend per user
and blocking requests once the monthly budget is exceeded.

Storage layout (Redis):
  cost:<user_id>:<YYYY-MM>  →  float (USD spent so far this month)
  TTL: 35 days (auto-clean after month rolls over)

Cost estimation:
  Rough token counts are derived from the question/answer length.
  Pricing constants mirror GPT-4o-mini rates; adjust as needed.

If Redis is unavailable, cost checking is skipped with a warning so
the service does not become unavailable just because of Redis downtime.
"""
import time
import logging

from fastapi import Depends, HTTPException

from .auth import verify_api_key
from .config import settings

logger = logging.getLogger(__name__)

# Approximate GPT-4o-mini pricing (USD per 1 000 tokens)
PRICE_PER_1K_INPUT = 0.00015
PRICE_PER_1K_OUTPUT = 0.00060

# ── Redis connection (shared lazy singleton) ──────────────────────────────────
_redis = None


def _get_redis():
    """Return a Redis client, creating it on first call."""
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis as redis_lib
        client = redis_lib.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        _redis = client
        logger.info("Cost guard connected to Redis")
    except Exception as exc:
        logger.warning("Cost guard: Redis unavailable (%s) — budget tracking disabled", exc)
    return _redis


def estimate_cost(question: str, answer: str) -> float:
    """
    Rough cost estimate based on character count.
    ~4 chars ≈ 1 token is a widely-used heuristic.
    """
    input_tokens = max(1, len(question) // 4)
    output_tokens = max(1, len(answer) // 4)
    return (input_tokens / 1000) * PRICE_PER_1K_INPUT + (output_tokens / 1000) * PRICE_PER_1K_OUTPUT


def record_cost(user_id: str, cost_usd: float) -> None:
    """Increment the user's monthly spend counter in Redis."""
    r = _get_redis()
    if r is None:
        return
    month_key = time.strftime("%Y-%m")
    key = f"cost:{user_id}:{month_key}"
    r.incrbyfloat(key, cost_usd)
    r.expire(key, 35 * 24 * 3600)  # auto-expire after 35 days


def check_budget(user_id: str = Depends(verify_api_key)) -> None:
    """
    FastAPI dependency — blocks the request if the user has exceeded their
    monthly budget.

    Raises:
        HTTPException 402: When the user's monthly spend >= MONTHLY_BUDGET_USD.
    """
    r = _get_redis()
    if r is None:
        # Fail open: if we can't check, allow the request (with a log warning).
        logger.warning("Cost guard skipped for user %s — Redis unavailable", user_id)
        return

    month_key = time.strftime("%Y-%m")
    key = f"cost:{user_id}:{month_key}"
    current_spend = float(r.get(key) or 0.0)
    budget = settings.monthly_budget_usd

    if current_spend >= budget:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Monthly budget exceeded",
                "budget_usd": budget,
                "spent_usd": round(current_spend, 4),
                "hint": "Your monthly allowance resets on the 1st of next month.",
            },
        )
