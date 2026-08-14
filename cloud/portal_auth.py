"""Login/parol uchun xavfsiz hashing va portal JWT yordamchilari.

Parol hech qachon ochiq holda saqlanmaydi. Scrypt parametrlari hash satrining
ichida turadi, shuning uchun keyinchalik kuchaytirish va eski hashlarni tekshirish
mumkin. JWT esa har so'rovda bazadagi ``auth_version`` bilan solishtiriladi:
parol yangilansa yoki akkaunt o'chirilsa eski token darhol ishlamaydi.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from typing import Literal, Optional

from pydantic import BaseModel

from chaqimchi_ai.jwt_auth import JwtError, create_access_token, decode_access_token
from chaqimchi_ai.settings import JwtSettings

PortalRole = Literal["admin", "installer", "customer"]
PortalStatus = Literal["pending", "active", "disabled"]

_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1


class PortalPrincipal(BaseModel):
    account_id: str
    username: str
    role: PortalRole
    status: PortalStatus
    site_id: Optional[str] = None
    auth_version: int = 1


def normalize_username(value: str) -> str:
    username = value.strip().lower()
    if not _USERNAME_RE.fullmatch(username):
        raise ValueError(
            "Login 3–64 belgi: kichik lotin harfi, raqam, nuqta, chiziq yoki pastki chiziq"
        )
    return username


def validate_password(password: str) -> None:
    if len(password) < 10 or len(password) > 128:
        raise ValueError("Parol 10–128 belgi bo'lishi kerak")
    if not any(char.isalpha() for char in password) or not any(char.isdigit() for char in password):
        raise ValueError("Parolda kamida bitta harf va bitta raqam bo'lishi kerak")


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
    )
    return "$".join(
        (
            "scrypt",
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_raw, digest_raw = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_raw.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_raw.encode("ascii"))
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def portal_jwt_config() -> JwtSettings:
    secret = os.environ.get("CHAQIMCHI_PORTAL_JWT_SECRET", "").strip()
    if not secret:
        secret = os.environ.get("CHAQIMCHI_OWNER_JWT_SECRET", "").strip()
    return JwtSettings(enabled=True, secret=secret or None, expire_hours=12)


def issue_portal_token(account: dict) -> str:
    return create_access_token(
        str(account["id"]),
        cfg=portal_jwt_config(),
        extra={
            "username": str(account["username"]),
            "role": str(account["role"]),
            "status": str(account["status"]),
            "site_id": account.get("site_id"),
            "auth_version": int(account.get("auth_version") or 1),
            "kind": "chaqimchi-portal",
        },
    )


def decode_portal_token(token: str) -> PortalPrincipal:
    try:
        payload = decode_access_token(token, cfg=portal_jwt_config())
        if payload.get("kind") != "chaqimchi-portal":
            raise JwtError("Token turi noto'g'ri")
        return PortalPrincipal(
            account_id=str(payload["sub"]),
            username=str(payload["username"]),
            role=str(payload["role"]),
            status=str(payload["status"]),
            site_id=str(payload["site_id"]) if payload.get("site_id") else None,
            auth_version=int(payload.get("auth_version") or 1),
        )
    except (JwtError, KeyError, ValueError) as exc:
        raise JwtError("Portal token yaroqsiz") from exc


def bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise JwtError("Bearer token talab qilinadi")
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise JwtError("Bearer token talab qilinadi")
    return parts[1].strip()
