import pytest
from fastapi import HTTPException

from chaqimchi_ai.auth import resolve_api_key, verify_api_key
from chaqimchi_ai.settings import SecuritySettings


def test_resolve_prefers_env(monkeypatch) -> None:
    monkeypatch.setenv("CHAQIMCHI_API_KEY", "from-env")
    sec = SecuritySettings(api_key_enabled=True, api_key="from-config")
    assert resolve_api_key(sec) == "from-env"


def test_verify_disabled_allows_empty() -> None:
    verify_api_key(None, security=SecuritySettings(api_key_enabled=False))


def test_verify_rejects_wrong_key() -> None:
    sec = SecuritySettings(api_key_enabled=True, api_key="secret")
    with pytest.raises(HTTPException) as exc:
        verify_api_key("wrong", security=sec)
    assert exc.value.status_code == 401
