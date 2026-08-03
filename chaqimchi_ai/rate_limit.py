"""Oddiy IP asosidagi tezlik cheklovi."""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import DefaultDict, List

from fastapi import HTTPException, Request

from chaqimchi_ai.settings import RateLimitSettings


class RateLimiter:
    def __init__(self, requests_per_minute: int) -> None:
        self.limit = max(1, requests_per_minute)
        self.window_sec = 60.0
        self._hits: DefaultDict[str, List[float]] = defaultdict(list)
        self._lock = Lock()

    def check(self, client_id: str) -> None:
        now = time.time()
        cutoff = now - self.window_sec
        with self._lock:
            bucket = [t for t in self._hits[client_id] if t >= cutoff]
            if len(bucket) >= self.limit:
                raise HTTPException(
                    status_code=429,
                    detail=f"Juda ko‘p so‘rov. Limit: {self.limit}/daq",
                )
            bucket.append(now)
            self._hits[client_id] = bucket


_limiter: RateLimiter | None = None


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def check_rate_limit(request: Request, settings: RateLimitSettings) -> None:
    global _limiter
    if not settings.enabled:
        return
    if _limiter is None or _limiter.limit != settings.requests_per_minute:
        _limiter = RateLimiter(settings.requests_per_minute)
    _limiter.check(client_ip(request))
