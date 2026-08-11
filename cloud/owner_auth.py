"""Telegram OTP asosidagi owner/manager sessionlari."""

from __future__ import annotations

import os
from typing import Literal

from fastapi import Header, HTTPException
from pydantic import BaseModel

from chaqimchi_ai.jwt_auth import JwtError, create_access_token, decode_access_token
from chaqimchi_ai.settings import JwtSettings


class OwnerPrincipal(BaseModel):
    member_id: str
    site_id: str
    telegram_id: str
    role: Literal["owner", "manager", "service_admin"]


def owner_jwt_config() -> JwtSettings:
    secret = os.environ.get("CHAQIMCHI_OWNER_JWT_SECRET", "").strip()
    return JwtSettings(enabled=True, secret=secret or None, expire_hours=12)


def issue_owner_token(member: dict) -> str:
    return create_access_token(
        str(member["id"]),
        cfg=owner_jwt_config(),
        extra={
            "site_id": str(member["site_id"]),
            "telegram_id": str(member["telegram_id"]),
            "role": str(member["role"]),
            "kind": "chaqimchi-owner",
        },
    )


def require_owner(authorization: str | None = Header(None)) -> OwnerPrincipal:
    if not authorization:
        raise HTTPException(401, "Owner session talab qilinadi")
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(401, "Bearer token talab qilinadi")
    try:
        payload = decode_access_token(parts[1], cfg=owner_jwt_config())
        if payload.get("kind") != "chaqimchi-owner":
            raise JwtError("Token turi noto'g'ri")
        return OwnerPrincipal(
            member_id=str(payload["sub"]),
            site_id=str(payload["site_id"]),
            telegram_id=str(payload["telegram_id"]),
            role=str(payload["role"]),
        )
    except (JwtError, KeyError, ValueError) as exc:
        raise HTTPException(401, "Owner token yaroqsiz") from exc


def require_owner_role(principal: OwnerPrincipal, *roles: str) -> None:
    if principal.role not in roles:
        raise HTTPException(403, "Bu amal uchun ruxsat yetarli emas")
