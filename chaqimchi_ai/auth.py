"""API kalit va JWT tekshiruvi."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import HTTPException

from chaqimchi_ai.jwt_auth import JwtError, decode_access_token
from chaqimchi_ai.settings import SecuritySettings


def resolve_api_key(security: SecuritySettings) -> Optional[str]:
    env_key = os.environ.get("CHAQIMCHI_API_KEY", "").strip()
    if env_key:
        return env_key
    if security.api_key:
        return security.api_key.strip()
    return None


def verify_api_key(
    x_api_key: Optional[str],
    *,
    security: SecuritySettings,
) -> None:
    if not security.api_key_enabled:
        return
    expected = resolve_api_key(security)
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="API kalit yoqilgan, lekin CHAQIMCHI_API_KEY yoki config.security.api_key berilmagan",
        )
    if not x_api_key or x_api_key.strip() != expected:
        raise HTTPException(status_code=401, detail="Noto‘g‘ri yoki yo‘q API kalit (X-API-Key)")


def verify_access(
    *,
    security: SecuritySettings,
    x_api_key: Optional[str] = None,
    authorization: Optional[str] = None,
) -> str:
    """
    JWT (Bearer) yoki API kalit. Qaytadi: actor identifikatori (audit uchun).
    """
    jwt_cfg = security.jwt
    if jwt_cfg.enabled and authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            try:
                payload = decode_access_token(parts[1], cfg=jwt_cfg)
                sub = str(payload.get("sub", "jwt-user"))
                return f"jwt:{sub}"
            except JwtError as e:
                raise HTTPException(status_code=401, detail=str(e)) from e
            except Exception as e:
                raise HTTPException(status_code=401, detail="JWT yaroqsiz") from e

    verify_api_key(x_api_key, security=security)
    if x_api_key:
        return f"apikey:{x_api_key[:6]}..."
    return "local"
