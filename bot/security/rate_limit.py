from __future__ import annotations

import threading
import time

import redis

from bot.config import load_settings

_redis_client: redis.Redis | None = None
_memory_hits: dict[str, tuple[int, float]] = {}
_memory_blocks: dict[str, float] = {}
_lock = threading.Lock()


def _get_redis_client() -> redis.Redis | None:
    global _redis_client
    settings = load_settings()
    if not settings.redis_url:
        return None
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def check_download_rate_limit(user_id: int, *, is_admin: bool = False) -> tuple[bool, int]:
    settings = load_settings()
    if is_admin or settings.rate_limit_requests_per_window <= 0:
        return True, 0

    key = f"download-rate-limit:{user_id}"
    blocked_key = f"{key}:blocked"
    client = _get_redis_client()
    if client is not None:
        blocked_ttl = client.ttl(blocked_key)
        if blocked_ttl and blocked_ttl > 0:
            return False, blocked_ttl

        current = client.incr(key)
        if current == 1:
            client.expire(key, settings.rate_limit_window_seconds)
        if current > settings.rate_limit_requests_per_window:
            client.setex(blocked_key, settings.rate_limit_block_seconds, "1")
            retry_after = client.ttl(key)
            return False, max(settings.rate_limit_block_seconds, retry_after, 1)
        return True, 0

    return _check_download_rate_limit_in_memory(
        key,
        limit=settings.rate_limit_requests_per_window,
        window_seconds=settings.rate_limit_window_seconds,
        block_seconds=settings.rate_limit_block_seconds,
    )


def _check_download_rate_limit_in_memory(key: str, *, limit: int, window_seconds: int, block_seconds: int) -> tuple[bool, int]:
    now = time.monotonic()
    with _lock:
        blocked_until = _memory_blocks.get(key)
        if blocked_until and blocked_until > now:
            return False, max(int(blocked_until - now), 1)
        if blocked_until and blocked_until <= now:
            _memory_blocks.pop(key, None)

        count, expires_at = _memory_hits.get(key, (0, 0.0))
        if expires_at <= now:
            count = 0
            expires_at = now + window_seconds

        count += 1
        _memory_hits[key] = (count, expires_at)
        if count > limit:
            blocked_until = now + block_seconds
            _memory_blocks[key] = blocked_until
            return False, max(int(blocked_until - now), 1)
        return True, 0
