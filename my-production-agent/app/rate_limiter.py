"""
Redis-Based Sliding Window Rate Limiter

Algorithm — Sliding Window using a Redis Sorted Set:
  • Each user gets a sorted-set key: ratelimit:<user_id>
  • Every request adds the current timestamp as a score.
  • Before adding, entries older than the window (60 s) are pruned.
  • If the remaining count >= limit → raise HTTP 429.
  • All operations are wrapped in a pipeline for atomicity.

Why Redis?
  Multiple agent instances share the same Redis, so the limit is enforced
  globally across the entire cluster (not per-instance).

If Redis is unavailable the limiter falls back to an in-memory deque so
the service degrades gracefully without crashing.
"""
import time
import logging
from collections import defaultdict, deque

from fastapi import Depends, HTTPException

from .auth import verify_api_key
from .config import settings

logger = logging.getLogger(__name__)

# ── Redis connection (lazy — only imported when actually available) ────────────
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
        logger.info("Rate limiter connected to Redis")
    except Exception as exc:
        logger.warning("Rate limiter: Redis unavailable (%s) — using in-memory fallback", exc)
    return _redis


# ── In-memory fallback (not scalable across multiple instances) ───────────────
_memory_windows: dict[str, deque] = defaultdict(deque)


def _check_redis(user_id: str, limit: int, window: int) -> int:
    """
    Sliding-window check via Redis sorted set.
    Returns the number of requests remaining after this one.
    """
    r = _get_redis()
    if r is None:
        raise RuntimeError("Redis not available")

    now = time.time()
    key = f"ratelimit:{user_id}"

    pipe = r.pipeline()
    # Remove timestamps outside the current window
    pipe.zremrangebyscore(key, 0, now - window)
    # Count how many remain
    pipe.zcard(key)
    # Add this request's timestamp
    pipe.zadd(key, {str(now): now})
    # Set TTL so keys auto-expire
    pipe.expire(key, window * 2)
    results = pipe.execute()

    current_count = results[1]  # count BEFORE adding this request
    remaining = limit - current_count - 1
    return current_count, remaining


def _check_memory(user_id: str, limit: int, window: int) -> tuple[int, int]:
    """In-memory fallback — single-instance only."""
    now = time.time()
    dq = _memory_windows[user_id]
    while dq and dq[0] < now - window:
        dq.popleft()
    current_count = len(dq)
    remaining = limit - current_count - 1
    dq.append(now)
    return current_count, remaining


def check_rate_limit(user_id: str = Depends(verify_api_key)) -> None:
    """
    FastAPI dependency — enforces per-user rate limiting.

    Raises:
        HTTPException 429: When the user exceeds the configured request rate.
    """
    limit = settings.rate_limit_per_minute
    window = 60  # seconds

    try:
        current_count, remaining = _check_redis(user_id, limit, window)
    except Exception:
        # Graceful fallback to in-memory store
        current_count, remaining = _check_memory(user_id, limit, window)

    if current_count >= limit:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "limit": limit,
                "window_seconds": window,
                "hint": f"You may send {limit} requests per minute.",
            },
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "Retry-After": str(window),
            },
        )
