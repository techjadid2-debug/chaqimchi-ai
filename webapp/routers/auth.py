"""JWT chiqarish va audit jurnali."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from chaqimchi_ai.audit import AuditLog
from chaqimchi_ai.auth import verify_api_key
from chaqimchi_ai.jwt_auth import JwtError, create_access_token
from chaqimchi_ai.rate_limit import check_rate_limit
from chaqimchi_ai.settings import AppSettings
from webapp.deps import get_audit, get_settings, require_protected

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/token")
async def issue_token(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    settings: AppSettings = Depends(get_settings),
):
    """API kalit bilan JWT olish (security.jwt.enabled=true)."""
    if not settings.security.jwt.enabled:
        return JSONResponse({"ok": False, "error": "JWT o‘chirilgan"}, status_code=400)
    if not settings.security.api_key_enabled:
        return JSONResponse({"ok": False, "error": "API key o'chirilgan"}, status_code=503)
    check_rate_limit(request, settings.rate_limit)
    verify_api_key(x_api_key, security=settings.security)
    try:
        token = create_access_token("api-client", cfg=settings.security.jwt)
    except JwtError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=503)
    return {
        "ok": True,
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.security.jwt.expire_hours * 3600,
    }


@router.get("/audit")
async def list_audit(
    limit: int = 50,
    audit: AuditLog = Depends(get_audit),
    _actor: str = Depends(require_protected),
):
    return audit.recent(limit)
