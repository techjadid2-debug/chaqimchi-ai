"""FastAPI dependency provayderlari.

Har bir provayder `app.state.container` dan o'qiydi, shuning uchun testda
`app.dependency_overrides[get_engine] = lambda: fake` ishlaydi — bungacha
handlerlar `get_db()` ni to'g'ridan-to'g'ri chaqirgani uchun bu imkonsiz edi.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fastapi import Depends, Header, Request

from chaqimchi_ai.audit import AuditLog
from chaqimchi_ai.auth import verify_access, verify_api_key
from chaqimchi_ai.database import FaceDatabase
from chaqimchi_ai.events import EventLog
from chaqimchi_ai.rate_limit import check_rate_limit
from chaqimchi_ai.runtime.container import AppContainer
from chaqimchi_ai.settings import AppSettings

if TYPE_CHECKING:  # pragma: no cover
    from chaqimchi_ai.face_engine import FaceEngine


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def get_settings(container: AppContainer = Depends(get_container)) -> AppSettings:
    return container.settings


def get_engine(container: AppContainer = Depends(get_container)) -> "FaceEngine":
    return container.engine


def get_db(container: AppContainer = Depends(get_container)) -> FaceDatabase:
    return container.db


def get_events(container: AppContainer = Depends(get_container)) -> EventLog:
    return container.events


def get_audit(container: AppContainer = Depends(get_container)) -> AuditLog:
    return container.audit


# ── Autentifikatsiya ─────────────────────────────────────────────────────
#
# Diqqat: hozir bu ikkitasi bir-biridan farq qiladi va bu farq ataylab emas —
# `require_api_key` JWT'ni qabul qilmaydi va rate limit qo'llamaydi.
# Faza 1 da ikkalasi bitta `require_auth` ga birlashadi (deny-by-default).


def require_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    settings: AppSettings = Depends(get_settings),
) -> Optional[str]:
    verify_api_key(x_api_key, security=settings.security)
    return x_api_key


def require_protected(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
    settings: AppSettings = Depends(get_settings),
) -> str:
    """Rate limit + (JWT yoki API kalit). Audit uchun aktor satrini qaytaradi."""
    check_rate_limit(request, settings.rate_limit)
    return verify_access(
        security=settings.security,
        x_api_key=x_api_key,
        authorization=authorization,
    )
