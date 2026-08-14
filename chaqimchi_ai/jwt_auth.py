"""JWT (HS256) — API kalit bilan birga ixtiyoriy."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from chaqimchi_ai.settings import JwtSettings

try:
    import jwt as pyjwt
except ImportError:  # pragma: no cover
    pyjwt = None  # type: ignore


class JwtError(Exception):
    pass


def resolve_jwt_secret(cfg: JwtSettings) -> Optional[str]:
    env = os.environ.get("CHAQIMCHI_JWT_SECRET", "").strip()
    if env:
        return env
    if cfg.secret:
        return cfg.secret.strip()
    return None


def create_access_token(
    subject: str,
    *,
    cfg: JwtSettings,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    if pyjwt is None:
        raise JwtError("PyJWT o‘rnatilmagan: pip install PyJWT")
    secret = resolve_jwt_secret(cfg)
    if not secret:
        raise JwtError("CHAQIMCHI_JWT_SECRET yoki config.security.jwt_secret kerak")

    now = int(time.time())
    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + cfg.expire_hours * 3600,
    }
    if extra:
        payload.update(extra)
    return pyjwt.encode(payload, secret, algorithm=cfg.algorithm)


def decode_access_token(token: str, *, cfg: JwtSettings) -> Dict[str, Any]:
    if pyjwt is None:
        raise JwtError("PyJWT o‘rnatilmagan")
    secret = resolve_jwt_secret(cfg)
    if not secret:
        raise JwtError("JWT secret sozlanmagan")
    try:
        return pyjwt.decode(
            token,
            secret,
            algorithms=[cfg.algorithm],
        )
    except pyjwt.PyJWTError as exc:
        raise JwtError("JWT yaroqsiz yoki muddati tugagan") from exc
