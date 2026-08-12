"""Tezlik cheklovi: bitta buzuq mijoz cloud'ni yiqita olmasin."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from cloud import ratelimit
from cloud.ratelimit import RateLimiter


@pytest.fixture(autouse=True)
def clean_limiter():
    ratelimit.limiter().reset()
    yield
    ratelimit.limiter().reset()


def test_limit_allows_up_to_threshold_then_blocks() -> None:
    limiter = RateLimiter()
    assert all(limiter.hit("leads", "1.2.3.4", limit=3, window_sec=60) for _ in range(3))
    assert not limiter.hit("leads", "1.2.3.4", limit=3, window_sec=60)


def test_keys_and_buckets_are_independent() -> None:
    limiter = RateLimiter()
    for _ in range(3):
        limiter.hit("leads", "1.2.3.4", limit=3, window_sec=60)
    # Boshqa IP va boshqa bucket o'z hisobiga ega.
    assert limiter.hit("leads", "9.9.9.9", limit=3, window_sec=60)
    assert limiter.hit("otp", "1.2.3.4", limit=3, window_sec=60)


def test_window_expiry_restores_quota(monkeypatch) -> None:
    limiter = RateLimiter()
    clock = {"now": 1_000.0}
    monkeypatch.setattr("cloud.ratelimit.time.monotonic", lambda: clock["now"])

    assert limiter.hit("events", "dev-1", limit=1, window_sec=60)
    assert not limiter.hit("events", "dev-1", limit=1, window_sec=60)

    clock["now"] += 61
    assert limiter.hit("events", "dev-1", limit=1, window_sec=60)


def test_check_raises_429_with_retry_after() -> None:
    ratelimit.check("otp", "555", limit=1, window_sec=600, message="Kod juda ko'p so'raldi")
    with pytest.raises(HTTPException) as exc:
        ratelimit.check("otp", "555", limit=1, window_sec=600, message="Kod juda ko'p so'raldi")
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "600"
