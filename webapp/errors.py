"""Xatolarni bir xil konvertga solish.

Bungacha javob shakli ikki xil edi: qo'lda yozilgan xatolar
`{"ok": false, "error": ...}`, autentifikatsiya va rate limit'dan kelgan
`HTTPException` esa FastAPI ning `{"detail": ...}` shakli. Frontend faqat
`res.error` ni o'qigani uchun har bir 401/429 ekranda "Xato: undefined"
bo'lib ko'rinardi.

Bu yerda hamma narsa `{"ok": false, "error": ...}` ga keltiriladi.
`detail` ham qoldiriladi — mavjud API klientlarini buzmaslik uchun.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from chaqimchi_ai.exceptions import (
    ChaqimchiError,
    ConfigurationError,
    ModelLoadError,
)
from chaqimchi_ai.metrics import get_metrics
from webapp.imaging import UploadTooLarge

logger = logging.getLogger(__name__)


def _fail(status: int, message: str, **extra) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": message, "detail": message, **extra},
        status_code=status,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(UploadTooLarge)
    async def _upload_too_large(request: Request, exc: UploadTooLarge) -> JSONResponse:
        return _fail(413, str(exc))

    @app.exception_handler(ModelLoadError)
    async def _model_load(request: Request, exc: ModelLoadError) -> JSONResponse:
        get_metrics().record_error()
        logger.error("Model yuklanmadi: %s", exc, exc_info=True)
        return _fail(503, f"Model yuklanmadi: {exc}")

    @app.exception_handler(ConfigurationError)
    async def _config(request: Request, exc: ConfigurationError) -> JSONResponse:
        get_metrics().record_error()
        logger.error("Konfiguratsiya xatosi: %s", exc, exc_info=True)
        return _fail(500, f"Konfiguratsiya xatosi: {exc}")

    @app.exception_handler(ChaqimchiError)
    async def _chaqimchi(request: Request, exc: ChaqimchiError) -> JSONResponse:
        get_metrics().record_error()
        logger.error("Ichki xato: %s", exc, exc_info=True)
        return _fail(500, str(exc))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code >= 500:
            get_metrics().record_error()
        return _fail(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # `jsonable_encoder` shart: pydantic v2 xato ob'ektlari `ctx` ichida
        # JSON'ga aylanmaydigan qiymatlar (masalan, istisno) olib yurishi mumkin.
        return _fail(422, "So'rov parametrlari noto'g'ri", errors=jsonable_encoder(exc.errors()))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Bungacha ushlanmagan istisno bare 500 berardi va `errors_total`
        # hech qachon oshmasdi — /metrics doim 0 ko'rsatardi.
        get_metrics().record_error()
        logger.exception("Ushlanmagan xato: %s %s", request.method, request.url.path)
        return _fail(500, "Ichki server xatosi")
