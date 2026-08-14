"""Telegram OTP asosidagi owner/manager sessionlari."""

from __future__ import annotations

import os
from typing import Literal

from fastapi import Header, HTTPException
from pydantic import BaseModel

from chaqimchi_ai.jwt_auth import JwtError, create_access_token, decode_access_token
from chaqimchi_ai.settings import JwtSettings
from cloud.portal_auth import bearer_token, decode_portal_token


class OwnerPrincipal(BaseModel):
    member_id: str
    site_id: str
    telegram_id: str
    role: Literal["owner", "manager", "service_admin"]
    auth_kind: Literal["telegram", "password"] = "telegram"
    auth_version: int = 0


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
    try:
        token = bearer_token(authorization)
    except JwtError as exc:
        raise HTTPException(401, "Owner session talab qilinadi") from exc
    try:
        payload = decode_access_token(token, cfg=owner_jwt_config())
        if payload.get("kind") != "chaqimchi-owner":
            raise JwtError("Token turi noto'g'ri")
        return OwnerPrincipal(
            member_id=str(payload["sub"]),
            site_id=str(payload["site_id"]),
            telegram_id=str(payload["telegram_id"]),
            role=str(payload["role"]),
            auth_kind="telegram",
        )
    except (JwtError, KeyError, ValueError):
        # Xarid qilgan mijoz login/parol bilan ham ayni owner API'larini
        # ishlatadi. Telegram OTP avvalgi mijozlar uchun o'zgarishsiz qoladi.
        try:
            portal = decode_portal_token(token)
            if portal.role != "customer" or not portal.site_id:
                raise JwtError("Mijoz tokeni emas")
            return OwnerPrincipal(
                member_id=portal.account_id,
                site_id=portal.site_id,
                telegram_id="",
                role="owner",
                auth_kind="password",
                auth_version=portal.auth_version,
            )
        except (JwtError, ValueError) as exc:
            raise HTTPException(401, "Owner token yaroqsiz") from exc


def require_owner_role(principal: OwnerPrincipal, *roles: str) -> None:
    if principal.role not in roles:
        raise HTTPException(403, "Bu amal uchun ruxsat yetarli emas")
