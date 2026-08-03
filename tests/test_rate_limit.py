import pytest
from fastapi import HTTPException
from starlette.requests import Request

from chaqimchi_ai.rate_limit import RateLimiter, check_rate_limit
from chaqimchi_ai.settings import RateLimitSettings


def _fake_request(host: str = "127.0.0.1") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "client": (host, 1234),
    }
    return Request(scope)


def test_rate_limiter_blocks() -> None:
    rl = RateLimiter(2)
    rl.check("a")
    rl.check("a")
    with pytest.raises(HTTPException) as exc:
        rl.check("a")
    assert exc.value.status_code == 429


def test_rate_limit_disabled() -> None:
    check_rate_limit(_fake_request(), RateLimitSettings(enabled=False))
