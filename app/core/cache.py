"""
AirRev Engine — Rate Limiting & In-Memory Cache
Protects the DDF API from hammering and speeds up repeated lookups.
Uses simple in-memory store — swap for Redis on Railway if needed.
"""

import time
import hashlib
import json
import logging
from typing import Any, Optional, Dict, Tuple
from collections import defaultdict
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# SIMPLE IN-MEMORY CACHE
# For production at scale, replace with:
#   from redis.asyncio import Redis
# ─────────────────────────────────────────

class MemoryCache:
    """
    TTL-based in-memory cache.
    Stores analysis results so repeated MLS lookups don't re-hit DDF.
    """

    def __init__(self):
        self._store: Dict[str, Tuple[Any, float]] = {}  # key → (value, expires_at)

    def _key(self, *parts: str) -> str:
        raw = ":".join(str(p) for p in parts)
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, *key_parts: str) -> Optional[Any]:
        key = self._key(*key_parts)
        entry = self._store.get(key)
        if not entry:
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, *key_parts: str, value: Any, ttl_seconds: int = 3600):
        key = self._key(*key_parts)
        self._store[key] = (value, time.time() + ttl_seconds)

    def delete(self, *key_parts: str):
        key = self._key(*key_parts)
        self._store.pop(key, None)

    def clear_expired(self):
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if exp < now]
        for k in expired:
            del self._store[k]
        return len(expired)

    @property
    def size(self) -> int:
        return len(self._store)


# ─────────────────────────────────────────
# RATE LIMITER
# Per-IP sliding window
# ─────────────────────────────────────────

class RateLimiter:
    """
    Simple sliding window rate limiter.
    Default: 30 requests per minute per IP.
    """

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: Dict[str, list] = defaultdict(list)

    def is_allowed(self, identifier: str) -> Tuple[bool, int]:
        """
        Returns (allowed: bool, retry_after_seconds: int)
        """
        now = time.time()
        window_start = now - self.window

        # Clean old entries
        self._buckets[identifier] = [
            t for t in self._buckets[identifier] if t > window_start
        ]

        count = len(self._buckets[identifier])

        if count >= self.max_requests:
            oldest = self._buckets[identifier][0]
            retry_after = int(oldest + self.window - now) + 1
            return False, retry_after

        self._buckets[identifier].append(now)
        return True, 0

    def get_remaining(self, identifier: str) -> int:
        now = time.time()
        window_start = now - self.window
        recent = [t for t in self._buckets[identifier] if t > window_start]
        return max(0, self.max_requests - len(recent))


async def rate_limit_check(request: Request, limiter: "RateLimiter"):
    """
    FastAPI dependency for rate limiting.
    Gets client IP from X-Forwarded-For (Railway sets this) or direct.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else (
        request.client.host if request.client else "unknown"
    )

    allowed, retry_after = limiter.is_allowed(client_ip)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    return client_ip


# Singletons
cache = MemoryCache()

# Tiered limits
analyze_limiter = RateLimiter(max_requests=20, window_seconds=60)   # 20/min for analysis
calc_limiter = RateLimiter(max_requests=60, window_seconds=60)       # 60/min for calculators
