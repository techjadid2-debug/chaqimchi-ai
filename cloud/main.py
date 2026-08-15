"""
Chaqimchi Cloud — mijozlar, litsenziya, o‘rnatish juftlash.

Ishga tushirish: make run-cloud  (port 8750)
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import html
import io
import logging
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import date as date_type
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from chaqimchi_ai import __version__
from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.jwt_auth import JwtError
from chaqimchi_ai.licensing.plans import (
    PLANS,
    PlanTier,
    cheapest_plan_for,
    get_plan,
    usd_rate_uzs,
)
from chaqimchi_ai.pilot_acceptance import pilot_acceptance_status
from chaqimchi_ai.settings import SceneLineSettings, SceneZoneSettings
from chaqimchi_ai.sotqin_profile import (
    BUFFER_MAX_BYTES,
    BUFFER_RETENTION_DAYS,
    GUARANTEED_CAMERAS,
    MIN_FREE_BYTES,
    product_payload,
)
from cloud import ratelimit
from cloud.alerts import AlertService, test_message
from cloud.digest import DailyDigestService
from cloud.event_store import EventStore, event_store_from_env
from cloud.notify import build_alert, event_label
from cloud.owner_auth import (
    OwnerPrincipal,
    issue_owner_token,
    require_owner,
    require_owner_role,
)
from cloud.payments import PaymentStore, click_config, payme_config, public_url
from cloud.payments import click as click_api
from cloud.payments import payme as payme_api
from cloud.payments.store import billable_months
from cloud.portal_auth import (
    PortalPrincipal,
    bearer_token,
    decode_portal_token,
    issue_portal_token,
)
from cloud.snapshots import SnapshotStore, snapshot_store_from_env
from cloud.store import CloudStore, available_feature_codes

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(
    os.environ.get("CHAQIMCHI_CLOUD_DB", str(BASE_DIR / "data" / "cloud" / "cloud.db"))
)
STATIC_DIR = Path(__file__).resolve().parent / "static"

#: Bitta qurilma soatiga shuncha event batch yubora oladi.
#:
#: 600 x `batch_size` (50) = soatiga 30 000 hodisa — har qanday haqiqiy
#: do'kondan ancha yuqori, lekin nazoratdan chiqqan qurilmani hali ham
#: to'xtatadi.  Oldingi 120 chegarasi edge'ning 5 soniyalik sikli (soatiga
#: 720 so'rov) bilan birga ~10 daqiqada 429 berardi, edge esa 429 ni
#: tutmasdi va abadiy siklga tushardi.  Edge tarafi ham tuzatildi:
#: `chaqimchi_ai/cloud_sync.py` endi `Retry-After` ni hurmat qiladi va
#: navbat bo'sh bo'lganda oraliqni 60 soniyagacha ko'taradi.
EVENT_BATCH_HOURLY_LIMIT = 600

logger = logging.getLogger(__name__)

_store: Optional[CloudStore] = None
_payments: Optional[PaymentStore] = None
_alerts: Optional[AlertService] = None
_event_store: Optional[EventStore] = None
_snapshots: Optional[SnapshotStore] = None
_event_store_key: Optional[str] = None
_digest: Optional[DailyDigestService] = None
_digest_task: Optional[Any] = None
_maintenance_task: Optional[Any] = None
_lead_notification_task: Optional[Any] = None


def get_store() -> CloudStore:
    global _store
    if _store is None:
        _store = CloudStore(DB_PATH)
    return _store


def get_payments() -> PaymentStore:
    """To'lov saqlagichi. `_store` almashsa (testlarda) avtomatik qayta quriladi."""
    global _payments
    store = get_store()
    if _payments is None or _payments.cloud is not store:
        _payments = PaymentStore(store)
    return _payments


def get_event_store() -> EventStore:
    global _event_store, _event_store_key
    database_url = os.environ.get("DATABASE_URL", "").strip()
    sqlite_path = get_store().db_path.parent / "events.db"
    key = database_url or str(sqlite_path)
    if _event_store is None or _event_store_key != key:
        _event_store = (
            event_store_from_env(BASE_DIR) if database_url else EventStore(sqlite_path=sqlite_path)
        )
        _event_store_key = key
    return _event_store


def get_snapshot_store() -> SnapshotStore:
    global _snapshots
    if _snapshots is None:
        _snapshots = snapshot_store_from_env(BASE_DIR)
    return _snapshots


def require_admin(
    authorization: Optional[str] = Header(None),
    x_cloud_admin_key: Optional[str] = Header(None, alias="X-Cloud-Admin-Key"),
) -> Optional[PortalPrincipal]:
    expected = os.environ.get("CHAQIMCHI_CLOUD_ADMIN_KEY", "").strip()
    if (
        expected
        and x_cloud_admin_key
        and secrets.compare_digest(x_cloud_admin_key.strip(), expected)
    ):
        return None
    return _require_portal_principal(authorization, roles={"admin"})


def _require_portal_principal(
    authorization: Optional[str],
    *,
    roles: set[str],
    allow_pending: bool = False,
) -> PortalPrincipal:
    try:
        principal = decode_portal_token(bearer_token(authorization))
    except JwtError as exc:
        raise HTTPException(401, "Login talab qilinadi") from exc
    account = get_store().account_by_id(principal.account_id)
    if (
        not account
        or account["username"] != principal.username
        or account["role"] != principal.role
        or int(account["auth_version"]) != principal.auth_version
        or account["status"] == "disabled"
    ):
        raise HTTPException(401, "Session bekor qilingan")
    if principal.role not in roles:
        raise HTTPException(403, "Bu bo'lim uchun ruxsat yo'q")
    if account["status"] == "pending" and not allow_pending:
        raise HTTPException(403, "Akkaunt admin tasdig'ini kutmoqda")
    return PortalPrincipal(
        **{
            "account_id": account["id"],
            "username": account["username"],
            "role": account["role"],
            "status": account["status"],
            "site_id": account.get("site_id"),
            "auth_version": account["auth_version"],
        }
    )


def require_installer_account(
    authorization: Optional[str] = Header(None),
) -> PortalPrincipal:
    return _require_portal_principal(authorization, roles={"installer"}, allow_pending=True)


def require_portal_account(
    authorization: Optional[str] = Header(None),
) -> PortalPrincipal:
    return _require_portal_principal(
        authorization,
        roles={"admin", "installer", "customer"},
        allow_pending=True,
    )


def require_active_installer(
    authorization: Optional[str] = Header(None),
) -> PortalPrincipal:
    return _require_portal_principal(authorization, roles={"installer"})


class PortalLoginBody(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class InstallerRegisterBody(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=5, max_length=32)
    company: Optional[str] = Field(default=None, max_length=160)
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=128)
    consent: bool = False


class PortalAccountCreateBody(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=128)
    role: Literal["admin", "installer", "customer"]
    status: Literal["pending", "active", "disabled"] = "active"
    full_name: str = Field(min_length=2, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=32)
    company: Optional[str] = Field(default=None, max_length=160)
    site_id: Optional[str] = Field(default=None, max_length=64)


class PortalAccountUpdateBody(BaseModel):
    role: Optional[Literal["admin", "installer", "customer"]] = None
    status: Optional[Literal["pending", "active", "disabled"]] = None
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=32)
    company: Optional[str] = Field(default=None, max_length=160)
    site_id: Optional[str] = Field(default=None, max_length=64)


class PortalPasswordBody(BaseModel):
    current_password: Optional[str] = Field(default=None, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class InstallerAssignmentBody(BaseModel):
    installer_id: str = Field(min_length=1, max_length=64)
    site_id: str = Field(min_length=1, max_length=64)
    status: Literal["assigned", "in_progress", "ready", "completed", "cancelled"] = "assigned"
    notes: Optional[str] = Field(default=None, max_length=1000)


class InstallerAssignmentUpdateBody(BaseModel):
    status: Literal["assigned", "in_progress", "ready", "completed", "cancelled"]
    notes: Optional[str] = Field(default=None, max_length=1000)


class CreateSiteBody(BaseModel):
    name: str
    plan: PlanTier = "lite"
    subscription_months: int = Field(default=1, ge=1, le=60)
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    #: Davomat tariflarida shartnomadagi xodim soni — oylik to‘lov shunga bog‘liq.
    billable_persons: int = Field(default=0, ge=0, le=100_000)


class ClaimDeviceBody(BaseModel):
    pairing_code: str
    label: str = "sotqin-1"
    hardware_id: Optional[str] = None
    product_name: str = Field(default="Sotqin", max_length=64)
    hardware_model: Optional[str] = Field(default=None, max_length=120)
    hardware_revision: Optional[str] = Field(default="R1", max_length=32)
    serial_number: Optional[str] = Field(default=None, max_length=120)


class HeartbeatBody(BaseModel):
    active_cameras: int = 0
    app_version: str = __version__


class ExtendBody(BaseModel):
    months: int = Field(default=1, ge=1, le=36)


class StatusBody(BaseModel):
    status: Literal["active", "suspended"]


class CreateInvoiceBody(BaseModel):
    months: int = Field(default=1, ge=1, le=60)
    note: Optional[str] = None


class ManualPaymentBody(BaseModel):
    """Naqd yoki bank o'tkazmasi — admin qo'lda tasdiqlaydi."""

    provider: Literal["naqd", "bank", "manual"] = "naqd"
    reference: Optional[str] = None


class EventBatchBody(BaseModel):
    events: List[EdgeEvent] = Field(max_length=500)


class MemberBody(BaseModel):
    telegram_id: str = Field(min_length=1, max_length=32)
    role: Literal["owner", "manager", "service_admin"] = "manager"
    display_name: Optional[str] = Field(default=None, max_length=120)


class OtpRequestBody(BaseModel):
    telegram_id: str = Field(min_length=1, max_length=32)


class OtpVerifyBody(BaseModel):
    telegram_id: str = Field(min_length=1, max_length=32)
    site_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    code: str = Field(min_length=6, max_length=6)


class EdgeHeartbeatBody(BaseModel):
    cameras_active: int = Field(default=0, ge=0, le=64)
    temperature_c: Optional[float] = Field(default=None, ge=-40, le=150)
    disk_free_bytes: int = Field(default=0, ge=0)
    outbox_pending: int = Field(default=0, ge=0)
    outbox_bytes: int = Field(default=0, ge=0)
    outbox_critical_pending: int = Field(default=0, ge=0)
    app_version: str = Field(default="unknown", max_length=64)
    model_version: Optional[str] = Field(default=None, max_length=128)
    product_name: str = Field(default="Sotqin", max_length=64)
    hardware_model: Optional[str] = Field(default=None, max_length=120)
    hardware_revision: Optional[str] = Field(default=None, max_length=32)
    serial_number: Optional[str] = Field(default=None, max_length=120)
    config_revision: int = Field(default=0, ge=0)


class ConfigAckBody(BaseModel):
    revision: int = Field(ge=0)
    status: Literal["applied", "rejected"]
    error: Optional[str] = Field(default=None, max_length=500)


class SiteConfigBody(BaseModel):
    camera_labels: Dict[str, str] = Field(default_factory=dict)
    camera_roles: Dict[str, Literal["entrance", "checkout", "sales_floor", "storage"]] = Field(
        default_factory=dict
    )
    occupancy_limit: int = Field(default=20, ge=1, le=10000)
    loitering_sec: int = Field(default=60, ge=5, le=86400)
    queue_limit: int = Field(default=5, ge=1, le=1000)
    open_from: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    open_to: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    attendance_camera_ids: List[str] = Field(default_factory=list, max_length=2)
    attendance_camera_roles: Dict[str, Literal["arrival", "departure", "both"]] = Field(
        default_factory=dict
    )
    zones: List[SceneZoneSettings] = Field(default_factory=list, max_length=128)
    lines: List[SceneLineSettings] = Field(default_factory=list, max_length=32)


class EmployeeCreateBody(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    external_id: Optional[str] = Field(default=None, max_length=80)
    consent: bool
    consent_note: Optional[str] = Field(default=None, max_length=500)


class EmployeeUpdateBody(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=160)
    external_id: Optional[str] = Field(default=None, max_length=80)
    active: Optional[bool] = None


class EmployeeScheduleItem(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    grace_minutes: int = Field(default=5, ge=0, le=180)
    enabled: bool = True


class EmployeeScheduleBody(BaseModel):
    schedules: List[EmployeeScheduleItem] = Field(default_factory=list, max_length=7)


class EnrollmentStatusBody(BaseModel):
    status: Literal["enrolled", "failed", "removed"]


class FeatureSelectionBody(BaseModel):
    feature_code: str = Field(min_length=2, max_length=64)
    camera_count: int = Field(ge=1, le=GUARANTEED_CAMERAS)


class FeatureDraftBody(BaseModel):
    selections: List[FeatureSelectionBody] = Field(default_factory=list, max_length=24)


class PublicLeadBody(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=5, max_length=32)
    company: Optional[str] = Field(default=None, max_length=160)
    city: Optional[str] = Field(default=None, max_length=120)
    cameras: int = Field(default=1, ge=1, le=64)
    message: Optional[str] = Field(default=None, max_length=1_000)
    consent: bool = False
    website: str = Field(default="", max_length=200)  # spam honeypot


class LeadStatusBody(BaseModel):
    status: Literal["new", "contacted", "qualified", "converted", "closed"]
    note: Optional[str] = Field(default=None, max_length=1_000)


class ConvertLeadBody(BaseModel):
    subscription_months: int = Field(default=1, ge=1, le=12)


def require_device(
    x_site_id: str = Header(..., alias="X-Site-Id"),
    x_device_id: str = Header(..., alias="X-Device-Id"),
    x_device_token: str = Header(..., alias="X-Device-Token"),
) -> Dict[str, Any]:
    device = get_store().verify_device(x_site_id, x_device_token)
    if not device or not secrets.compare_digest(str(device["id"]), x_device_id):
        raise HTTPException(401, "Qurilma autentifikatsiyasi muvaffaqiyatsiz")
    return {
        "site_id": x_site_id,
        "device_id": x_device_id,
        "device_token": x_device_token,
    }


def require_active_owner(
    owner: OwnerPrincipal = Depends(require_owner),
) -> OwnerPrincipal:
    if owner.auth_kind == "password":
        account = get_store().account_by_id(owner.member_id)
        if (
            not account
            or account["role"] != "customer"
            or account["status"] != "active"
            or account.get("site_id") != owner.site_id
            or int(account["auth_version"]) != owner.auth_version
        ):
            raise HTTPException(401, "Mijoz sessioni bekor qilingan")
        return owner
    member = get_event_store().member_for_site(owner.site_id, owner.telegram_id)
    if not member or str(member["id"]) != owner.member_id or member["role"] != owner.role:
        raise HTTPException(401, "Owner session bekor qilingan")
    return owner


def _owner_secret() -> str:
    secret = os.environ.get("CHAQIMCHI_OWNER_JWT_SECRET", "").strip()
    if len(secret) < 32:
        raise HTTPException(503, "CHAQIMCHI_OWNER_JWT_SECRET sozlanmagan")
    return secret


def _attendance_enabled() -> bool:
    """Davomat tijoriy model yoki ataylab yoqilgan yopiq pilotda ishlaydi."""
    commercial = os.environ.get("CHAQIMCHI_FACE_MODEL_LICENSED", "").lower() in {
        "1",
        "true",
        "yes",
    }
    pilot = os.environ.get("CHAQIMCHI_ATTENDANCE_PILOT", "").lower() in {
        "1",
        "true",
        "yes",
    }
    return commercial or pilot or os.environ.get("CHAQIMCHI_ENV", "development") != "production"


def require_attendance() -> None:
    if not _attendance_enabled():
        raise HTTPException(
            403,
            "Davomat sotuvga ochilmagan: faqat yozma rozilikli yopiq pilot yoki "
            "tasdiqlangan tijoriy Face ID modeli bilan ishlaydi",
        )


async def _send_owner_telegram(
    chat_id: str,
    text: str,
    *,
    reply_markup: Optional[Dict[str, Any]] = None,
) -> None:
    import httpx

    token = (
        os.environ.get("CHAQIMCHI_OWNER_TELEGRAM_TOKEN", "").strip()
        or os.environ.get("CHAQIMCHI_CLOUD_TELEGRAM_TOKEN", "").strip()
    )
    if not token:
        raise HTTPException(503, "Owner Telegram bot tokeni sozlanmagan")
    async with httpx.AsyncClient(timeout=15) as client:
        payload: Dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        response = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload,
        )
        if response.status_code >= 400:
            raise HTTPException(502, "Telegram OTP yuborilmadi")


async def _notify_site_members(site_id: str, text: str) -> None:
    for member in get_event_store().list_members(site_id):
        try:
            await _send_owner_telegram(str(member["telegram_id"]), text)
        except Exception:
            # Event qabul qilinishi Telegramdagi vaqtinchalik xatoga bog'lanmasin.
            continue


def _purge_expired_events() -> int:
    """Har obyektni **o'z tarifi** muddati bo'yicha tozalaydi.

    Bungacha hammaga 30 kun qo'llanardi: 90 yoki 365 kunlik arxiv uchun
    to'lagan mijoz to'lagan narsasini olmasdi.
    """
    removed = 0
    for site in get_store().list_sites():
        try:
            retention = get_plan(str(site["plan"])).retention_days
        except ValueError:
            retention = 30
        for key in get_event_store().purge_site(str(site["id"]), retention_days=retention):
            get_snapshot_store().delete(key)
            removed += 1
    return removed


async def _maintenance_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(_purge_expired_events)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Cloud maintenance bajarilmadi")
        await asyncio.sleep(21_600)


async def _lead_notification_loop() -> None:
    while True:
        try:
            await _retry_lead_notifications()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Lead Telegram retry bajarilmadi")
        await asyncio.sleep(60)


def get_alerts() -> AlertService:
    """Aloqa ogohlantirishi xizmati. `_store` almashsa qayta quriladi."""
    global _alerts
    store = get_store()
    if _alerts is None or _alerts.store is not store:
        _alerts = AlertService(store)
    return _alerts


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _digest, _digest_task, _maintenance_task, _lead_notification_task
    if os.environ.get("CHAQIMCHI_ENV", "development") == "production":
        errors = []
        if not os.environ.get("DATABASE_URL", "").startswith("postgresql"):
            errors.append("DATABASE_URL PostgreSQL bo'lishi shart")
        if not os.environ.get("CHAQIMCHI_S3_ENDPOINT", "").strip():
            errors.append("MinIO/S3 endpoint sozlanishi shart")
        if not os.environ.get("CHAQIMCHI_SNAPSHOT_KEY", "").strip():
            errors.append("snapshot encryption key sozlanishi shart")
        if not os.environ.get("CHAQIMCHI_CAMERA_SECRET_KEY", "").strip():
            errors.append("camera credential encryption key sozlanishi shart")
        if len(os.environ.get("CHAQIMCHI_OWNER_JWT_SECRET", "")) < 32:
            errors.append("owner JWT secret kamida 32 belgi bo'lishi shart")
        if len(os.environ.get("CHAQIMCHI_PORTAL_JWT_SECRET", "")) < 32:
            errors.append("portal JWT secret kamida 32 belgi bo'lishi shart")
        if len(os.environ.get("CHAQIMCHI_CLOUD_ADMIN_KEY", "")) < 32:
            errors.append("cloud admin key kamida 32 belgi bo'lishi shart")
        try:
            usd_rate_uzs()
        except ValueError as exc:
            errors.append(str(exc))
        if errors:
            raise RuntimeError(
                "Cloud production konfiguratsiyasi xavfsiz emas: " + "; ".join(errors)
            )
    get_event_store()
    get_snapshot_store()
    get_payments()
    bootstrap_username = os.environ.get("CHAQIMCHI_BOOTSTRAP_ADMIN_USERNAME", "").strip()
    bootstrap_password = os.environ.get("CHAQIMCHI_BOOTSTRAP_ADMIN_PASSWORD", "")
    if bool(bootstrap_username) != bool(bootstrap_password):
        raise RuntimeError("Bootstrap admin login va paroli birga sozlanishi kerak")
    if bootstrap_username and bootstrap_password:
        get_store().ensure_bootstrap_admin(bootstrap_username, bootstrap_password)
    alerts = get_alerts()
    alerts.start()
    _digest = DailyDigestService(get_event_store(), get_store().list_sites, _send_owner_telegram)
    _digest_task = asyncio.create_task(_digest.run())
    _maintenance_task = asyncio.create_task(_maintenance_loop())
    _lead_notification_task = asyncio.create_task(_lead_notification_loop())
    try:
        yield
    finally:
        if _digest_task is not None:
            _digest_task.cancel()
            _digest_task = None
        if _maintenance_task is not None:
            _maintenance_task.cancel()
            _maintenance_task = None
        if _lead_notification_task is not None:
            _lead_notification_task.cancel()
            _lead_notification_task = None
        _digest = None
        await alerts.stop()


_cloud_production = os.environ.get("CHAQIMCHI_ENV", "development") == "production"
app = FastAPI(
    title="Chaqimchi Cloud",
    lifespan=lifespan,
    docs_url=None if _cloud_production else "/docs",
    redoc_url=None if _cloud_production else "/redoc",
    openapi_url=None if _cloud_production else "/openapi.json",
)


if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"ok": True, "service": "chaqimchi-cloud"}


def _static_page(name: str) -> FileResponse:
    page = STATIC_DIR / name
    if not page.is_file():
        raise HTTPException(404, "Sahifa topilmadi")
    return FileResponse(page)


@app.get("/", include_in_schema=False)
async def public_site(request: Request) -> HTMLResponse:
    page = STATIC_DIR / "site.html"
    if not page.is_file():
        raise HTTPException(404, "Sahifa topilmadi")
    origin = str(request.base_url).rstrip("/")
    bot_username = os.environ.get("CHAQIMCHI_TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    register_url = (
        f"https://t.me/{bot_username}?start=register"
        if re.fullmatch(r"[A-Za-z0-9_]{5,32}", bot_username)
        else f"{origin}/#pilot"
    )
    content = (
        page.read_text(encoding="utf-8")
        .replace("__PUBLIC_ORIGIN__", origin)
        .replace("__TELEGRAM_REGISTER_URL__", register_url)
    )
    return HTMLResponse(content)


@app.get("/connect", include_in_schema=False)
async def connect_page() -> FileResponse:
    return _static_page("connect.html")


@app.get("/install", include_in_schema=False)
async def install_page() -> FileResponse:
    """Mijozning mustaqil o'rnatish yo'riqnomasi."""
    return _static_page("install.html")


@app.get("/installer", include_in_schema=False)
async def installer_page() -> FileResponse:
    """O'rnatuvchi ro'yxatdan o'tishi, vazifalari va pairing paneli."""
    return _static_page("installer.html")


@app.get("/installer-guide", include_in_schema=False)
async def installer_guide_page() -> FileResponse:
    """Bo'sh mini-kompyuterdan mijozga topshirishgacha rasmli yo'riqnoma."""
    return _static_page("installer-guide.html")


@app.get("/downloads/sotqin-installer.sh", include_in_schema=False)
async def sotqin_bootstrap(request: Request) -> Response:
    """Rasmiy saytdan Sotqin first-install bootstrap.

    Release URL va SHA deploy paytida environmentga qo'yiladi; bo'sh bo'lsa
    noto'g'ri yoki eski paketni mijozga berish o'rniga endpoint yopiq turadi.
    """
    release_url = os.environ.get("CHAQIMCHI_SOTQIN_RELEASE_URL", "").strip()
    release_sha256 = os.environ.get("CHAQIMCHI_SOTQIN_RELEASE_SHA256", "").strip()
    if not release_url.startswith("https://") or len(release_sha256) != 64:
        raise HTTPException(503, "Sotqin release hali nashr qilinmagan")
    template = BASE_DIR / "deploy" / "bootstrap_sotqin.sh"
    if not template.is_file():
        raise HTTPException(404, "Installer template topilmadi")
    cloud_url = str(request.base_url).rstrip("/")
    script = (
        template.read_text(encoding="utf-8")
        .replace("__RELEASE_URL__", release_url)
        .replace("__RELEASE_SHA256__", release_sha256.lower())
        .replace("__CLOUD_URL__", cloud_url)
    )
    return Response(
        script,
        media_type="text/x-shellscript; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=sotqin-installer.sh"},
    )


@app.get("/releases/{release_name}", include_in_schema=False)
async def sotqin_release(release_name: str) -> FileResponse:
    """Serve only a named, locally published Sotqin release archive."""
    if Path(release_name).name != release_name or not release_name.endswith(".tar.gz"):
        raise HTTPException(404, "Release topilmadi")
    archive = BASE_DIR / "releases" / release_name
    if not archive.is_file():
        raise HTTPException(404, "Release topilmadi")
    return FileResponse(
        archive,
        media_type="application/gzip",
        filename=release_name,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@app.get("/privacy", include_in_schema=False)
async def privacy_page() -> FileResponse:
    return _static_page("privacy.html")


@app.get("/status", include_in_schema=False)
async def status_page() -> FileResponse:
    return _static_page("status.html")


@app.get("/admin", include_in_schema=False)
async def admin_panel() -> FileResponse:
    """Admin paneli. Kirish admin kalit bilan — brauzerda so‘raladi va API ga yuboriladi."""
    page = STATIC_DIR / "admin.html"
    if not page.is_file():
        raise HTTPException(404, "Admin paneli topilmadi")
    return FileResponse(page)


@app.get("/owner", include_in_schema=False)
async def owner_panel() -> FileResponse:
    page = STATIC_DIR / "owner.html"
    if not page.is_file():
        raise HTTPException(404, "Owner panel topilmadi")
    return FileResponse(page)


@app.get("/api/v1/plans")
async def list_plans() -> Dict[str, Any]:
    return {
        "plans": {
            k: {
                "max_cameras": v.max_cameras,
                "max_persons": v.max_persons,
                "retention_days": v.retention_days,
                "monthly_price_uzs": v.monthly_price(),
                "monthly_price_usd": v.monthly_price_usd,
                "install_price_uzs": v.install_price_uzs,
                "per_person_uzs": v.price_per_person_uzs,
                "billing": "per_person" if v.is_per_person else "flat",
            }
            for k, v in PLANS.items()
        }
    }


#: Yillik to'lovda nechа oy hisoblanadi (2 oy bepul). Sayt ham, hisob-faktura
#: ham shu bitta qoidani ishlatadi.
YEARLY_MONTHS_CHARGED = billable_months(12)

#: Baza obunaga kiradigan, AI inferens talab qilmaydigan imkoniyatlar.
BASE_PLAN_INCLUDES = (
    "Qurilma va kamera holati 24/7 nazorat",
    "Hodisa arxivi 30 kun",
    "Telegram ogohlantirishlari",
    "Mijoz paneli va kunlik hisobot",
    "Imzolangan dastur yangilanishlari",
)


@app.get("/api/v1/public/pricing")
async def public_pricing() -> Dict[str, Any]:
    """Rasmiy sayt narxni shu yerdan oladi.

    Bungacha narxlar `site.html` ichida qo'lda yozilgan edi — katalog
    o'zgarganda sayt eski narxni ko'rsatib turaverardi. Tannarx va marja bu
    javobga **chiqmaydi**: ular faqat admin endpointida qoladi.
    """
    catalog = get_store().list_feature_catalog()
    rate = usd_rate_uzs()
    base_cents = int(catalog["price_book"]["base_fee_usd_cents"])
    available = available_feature_codes()
    return {
        "currency_default": "uzs",
        "usd_rate_uzs": rate,
        "yearly_months_charged": YEARLY_MONTHS_CHARGED,
        "base": {
            "monthly_usd_cents": base_cents,
            "monthly_uzs": (base_cents * rate + 99) // 100,
            "includes": list(BASE_PLAN_INCLUDES),
        },
        "features": [
            {
                "code": item["code"],
                "name": item["name"],
                "category": item["category"],
                "queue_kind": item["queue_kind"],
                "monthly_usd_cents": int(item["monthly_usd_cents"]),
                "monthly_uzs": (int(item["monthly_usd_cents"]) * rate + 99) // 100,
                "available": item["code"] in available,
            }
            for item in catalog["features"]
            if item["active"]
        ],
        # 8 kamera apparat maksimumi, lekin public sotuv va'dasi 72 soatlik
        # soak-test tugamaguncha faqat 4 kamera.
        "max_cameras": GUARANTEED_CAMERAS,
    }


def _configured_lead_chat_ids() -> List[str]:
    """Environmentdagi qo'shimcha lead qabul qiluvchilarini qaytaradi."""
    raw = os.environ.get("CHAQIMCHI_TELEGRAM_LEAD_CHAT_IDS", "")
    return list(
        dict.fromkeys(
            chat_id.strip()
            for chat_id in raw.replace(";", ",").replace("\n", ",").split(",")
            if chat_id.strip()
        )
    )


def _lead_recipient_ids() -> List[str]:
    """Leadlar faqat maxsus statik shaxsiy qabul qiluvchilarga boradi."""
    return _configured_lead_chat_ids()


def _lead_notification_text(lead: Dict[str, Any], *, duplicate: bool = False) -> str:
    title = (
        "Takroriy Chaqimchi AI do'kon arizasi" if duplicate else "Yangi Chaqimchi AI do'kon arizasi"
    )
    return (
        f"📥 <b>{title}</b>\n"
        f"Ism: {html.escape(str(lead['full_name']))}\n"
        f"Telefon: {html.escape(str(lead['phone']))}\n"
        f"Tashkilot: {html.escape(str(lead.get('company') or '—'))}\n"
        f"Hudud: {html.escape(str(lead.get('city') or '—'))}\n"
        f"Kamera: {int(lead.get('cameras') or 1)} ta"
    )


async def _deliver_lead_notification(
    lead: Dict[str, Any], chat_id: str, *, duplicate: bool = False
) -> bool:
    try:
        sent = await get_alerts().sender.send_to(
            chat_id, _lead_notification_text(lead, duplicate=duplicate)
        )
    except Exception as exc:
        get_store().mark_lead_notification_delivery(
            str(lead["id"]), chat_id, sent=False, error=str(exc)
        )
        logger.warning("Lead %s Telegram %s ga yuborilmadi: %s", lead["id"], chat_id, exc)
        return False
    get_store().mark_lead_notification_delivery(
        str(lead["id"]),
        chat_id,
        sent=sent,
        error=None if sent else "Telegram API xabarni qabul qilmadi",
    )
    if not sent:
        logger.warning("Lead %s Telegram %s ga yuborilmadi", lead["id"], chat_id)
    return sent


async def _notify_new_lead(lead: Dict[str, Any], *, duplicate: bool = False) -> None:
    service = get_alerts()
    if not service.config.token:
        logger.warning("Lead %s saqlandi, lekin Telegram tokeni sozlanmagan", lead["id"])
        return
    recipients = _lead_recipient_ids()
    if not recipients:
        logger.warning("Lead %s saqlandi, lekin Telegram recipient sozlanmagan", lead["id"])
        return
    get_store().ensure_lead_notification_deliveries(str(lead["id"]), recipients, reset=duplicate)
    for chat_id in recipients:
        delivery = get_store().lead_notification_delivery(str(lead["id"]), chat_id)
        if delivery and delivery["state"] == "sent":
            continue
        await _deliver_lead_notification(lead, chat_id, duplicate=duplicate)


async def _retry_lead_notifications() -> None:
    if not get_alerts().config.token:
        return
    recipients = _lead_recipient_ids()
    if not recipients:
        return
    store = get_store()
    for lead in store.recent_leads_without_notifications(hours=24):
        store.ensure_lead_notification_deliveries(str(lead["id"]), recipients)
    for delivery in store.pending_lead_notification_deliveries(limit=100):
        lead = {**delivery, "id": delivery["lead_id"]}
        await _deliver_lead_notification(lead, str(delivery["chat_id"]))


@app.post("/api/v1/public/leads")
async def public_create_lead(
    body: PublicLeadBody,
    request: Request,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """Rasmiy saytdan pilot ariza; AI modeliga bog'liq emas."""
    if body.website:
        return {"ok": True, "message": "Arizangiz qabul qilindi"}
    ratelimit.check(
        "leads",
        request.client.host if request.client else "unknown",
        limit=5,
        window_sec=3_600,
        message="Juda ko'p ariza yuborildi. Bir soatdan keyin urinib ko'ring.",
    )
    if not body.consent:
        raise HTTPException(422, "Bog'lanish uchun rozilik talab qilinadi")
    full_name = " ".join(body.full_name.split())
    phone = " ".join(body.phone.split())
    if sum(char.isdigit() for char in phone) < 5:
        raise HTTPException(422, "Telefon raqami noto'g'ri")
    client_host = request.client.host if request.client else "unknown"
    source_hash = hashlib.sha256(client_host.encode("utf-8")).hexdigest()
    try:
        created = get_store().create_lead(
            full_name=full_name,
            phone=phone,
            company=" ".join(body.company.split()) if body.company else None,
            city=" ".join(body.city.split()) if body.city else None,
            cameras=body.cameras,
            message=body.message.strip() if body.message else None,
            source_hash=source_hash,
        )
    except ValueError as exc:
        raise HTTPException(429, str(exc)) from exc
    lead = get_store().get_lead(created["id"])
    if lead:
        background_tasks.add_task(
            _notify_new_lead,
            lead,
            duplicate=bool(created["duplicate"]),
        )
    return {
        "ok": True,
        "lead_id": created["id"],
        "duplicate": created["duplicate"],
        "message": "Arizangiz qabul qilindi. Jamoamiz siz bilan bog'lanadi.",
    }


# ── Login/parol portali: admin, o'rnatuvchi va xarid qilgan mijoz ───────


@app.post("/api/v1/auth/login")
async def portal_login(body: PortalLoginBody, request: Request) -> Dict[str, Any]:
    client_host = request.client.host if request.client else "unknown"
    ratelimit.check(
        "portal-login",
        f"{client_host}:{body.username.strip().lower()}",
        limit=8,
        window_sec=900,
        message="Juda ko'p kirish urinishi. 15 daqiqadan keyin urinib ko'ring.",
    )
    try:
        account = get_store().authenticate_account(body.username, body.password)
    except ValueError:
        account = None
    if not account or account["status"] == "disabled":
        raise HTTPException(401, "Login yoki parol noto'g'ri")
    try:
        token = issue_portal_token(account)
    except Exception as exc:
        raise HTTPException(503, "Login sessioni yaratilmadi") from exc
    redirect = {"admin": "/admin", "installer": "/installer", "customer": "/owner"}[account["role"]]
    return {
        "ok": True,
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 12 * 3600,
        "account": account,
        "redirect": redirect,
    }


@app.post("/api/v1/auth/installer/register")
async def installer_register(
    body: InstallerRegisterBody,
    request: Request,
) -> Dict[str, Any]:
    if not body.consent:
        raise HTTPException(422, "Shaxsiy ma'lumotlarni qayta ishlashga rozilik kerak")
    client_host = request.client.host if request.client else "unknown"
    ratelimit.check(
        "installer-register",
        client_host,
        limit=4,
        window_sec=3600,
        message="Ro'yxatdan o'tish limiti tugadi. Keyinroq urinib ko'ring.",
    )
    try:
        account = get_store().create_account(
            username=body.username,
            password=body.password,
            role="installer",
            status="pending",
            full_name=body.full_name,
            phone=body.phone,
            company=body.company,
        )
        token = issue_portal_token(account)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    get_store().audit_portal_action(
        "installer.register",
        actor_id=account["id"],
        target_type="account",
        target_id=account["id"],
    )
    return {
        "ok": True,
        "access_token": token,
        "token_type": "bearer",
        "account": account,
        "message": "Ro'yxatdan o'tdingiz. Buyurtmalar admin tasdig'idan keyin ochiladi.",
    }


@app.get("/api/v1/auth/me")
async def portal_me(
    principal: PortalPrincipal = Depends(require_portal_account),
) -> Dict[str, Any]:
    return {"account": get_store().account_by_id(principal.account_id)}


@app.post("/api/v1/auth/password")
async def portal_change_password(
    body: PortalPasswordBody,
    principal: PortalPrincipal = Depends(require_portal_account),
) -> Dict[str, Any]:
    if not body.current_password or not get_store().authenticate_account(
        principal.username, body.current_password
    ):
        raise HTTPException(401, "Joriy parol noto'g'ri")
    try:
        account = get_store().set_account_password(principal.account_id, body.new_password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    token = issue_portal_token(account)
    get_store().audit_portal_action(
        "account.password.changed",
        actor_id=principal.account_id,
        target_type="account",
        target_id=principal.account_id,
    )
    return {"ok": True, "access_token": token, "account": account}


@app.get("/api/v1/admin/accounts")
async def admin_accounts(
    role: Optional[Literal["admin", "installer", "customer"]] = None,
    status: Optional[Literal["pending", "active", "disabled"]] = None,
    _: Optional[PortalPrincipal] = Depends(require_admin),
) -> Dict[str, Any]:
    return {"accounts": get_store().list_accounts(role=role, status=status)}


@app.post("/api/v1/admin/accounts")
async def admin_create_account(
    body: PortalAccountCreateBody,
    admin: Optional[PortalPrincipal] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        account = get_store().create_account(
            **body.model_dump(),
            created_by=admin.account_id if admin else None,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    get_store().audit_portal_action(
        "account.created",
        actor_id=admin.account_id if admin else None,
        target_type="account",
        target_id=account["id"],
        detail={"role": account["role"], "status": account["status"]},
    )
    return account


@app.put("/api/v1/admin/accounts/{account_id}")
async def admin_update_account(
    account_id: str,
    body: PortalAccountUpdateBody,
    admin: Optional[PortalPrincipal] = Depends(require_admin),
) -> Dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    if admin and admin.account_id == account_id and changes.get("status") == "disabled":
        raise HTTPException(409, "O'zingizni bloklay olmaysiz")
    try:
        account = get_store().update_account(account_id, changes)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    get_store().audit_portal_action(
        "account.updated",
        actor_id=admin.account_id if admin else None,
        target_type="account",
        target_id=account_id,
        detail={key: value for key, value in changes.items() if key != "phone"},
    )
    return account


@app.post("/api/v1/admin/accounts/{account_id}/password")
async def admin_reset_account_password(
    account_id: str,
    body: PortalPasswordBody,
    admin: Optional[PortalPrincipal] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        account = get_store().set_account_password(account_id, body.new_password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    get_store().audit_portal_action(
        "account.password.reset",
        actor_id=admin.account_id if admin else None,
        target_type="account",
        target_id=account_id,
    )
    return {"ok": True, "account": account}


@app.get("/api/v1/admin/installer-assignments")
async def admin_installer_assignments(
    _: Optional[PortalPrincipal] = Depends(require_admin),
) -> Dict[str, Any]:
    return {"assignments": get_store().list_installer_assignments()}


@app.post("/api/v1/admin/installer-assignments")
async def admin_assign_installer(
    body: InstallerAssignmentBody,
    admin: Optional[PortalPrincipal] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        assignment = get_store().assign_installer(
            **body.model_dump(),
            created_by=admin.account_id if admin else None,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    get_store().audit_portal_action(
        "installer.assigned",
        actor_id=admin.account_id if admin else None,
        target_type="site",
        target_id=body.site_id,
        detail={"installer_id": body.installer_id, "status": body.status},
    )
    return assignment


@app.get("/api/v1/admin/portal-audit")
async def admin_portal_audit(
    limit: int = 200,
    _: Optional[PortalPrincipal] = Depends(require_admin),
) -> Dict[str, Any]:
    return {"events": get_store().list_portal_audit(limit=limit)}


@app.post("/api/v1/admin/sites")
async def admin_create_site(
    body: CreateSiteBody,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    return get_store().create_site(
        body.name,
        body.plan,
        subscription_months=body.subscription_months,
        contact_phone=body.contact_phone,
        address=body.address,
        billable_persons=body.billable_persons,
    )


@app.get("/api/v1/admin/sites")
async def admin_list_sites(_: None = Depends(require_admin)) -> List[Dict[str, Any]]:
    return get_store().list_sites()


@app.get("/api/v1/admin/features")
async def admin_feature_catalog(_: None = Depends(require_admin)) -> Dict[str, Any]:
    """Funksiya katalogi va amaldagi, versiyalangan narxlar."""
    return get_store().list_feature_catalog()


@app.get("/api/v1/admin/business-templates")
async def admin_business_templates(_: None = Depends(require_admin)) -> List[Dict[str, Any]]:
    return get_store().list_business_templates()


@app.post("/api/v1/admin/sites/{site_id}/features/quote")
async def admin_feature_quote(
    site_id: str,
    body: FeatureDraftBody,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    if not get_store().get_site(site_id):
        raise HTTPException(404, "Sayt topilmadi")
    try:
        return get_store().feature_quote([item.model_dump() for item in body.selections])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/admin/sites/{site_id}/features")
async def admin_site_features(site_id: str, _: None = Depends(require_admin)) -> Dict[str, Any]:
    try:
        return get_store().site_feature_summary(site_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.put("/api/v1/admin/sites/{site_id}/features/draft")
async def admin_save_feature_draft(
    site_id: str,
    body: FeatureDraftBody,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return get_store().replace_feature_draft(
            site_id, [item.model_dump() for item in body.selections]
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/v1/admin/sites/{site_id}/features/approve")
async def admin_approve_feature_draft(
    site_id: str,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    """Tasdiqlangandan keyin keyingi edge config revision faol funksiyalarni oladi."""
    try:
        summary = get_store().approve_feature_draft(site_id)
        # Edge polling revision orqali yangi vazifalarni ko'radi. Asosiy
        # konfiguratsiya owner sozlamalarini saqlagan holda faqat revision oladi.
        current = get_event_store().get_site_config(site_id)
        config = dict(current["config"])
        config["cloud_feature_revision"] = int(current["revision"]) + 1
        summary["edge_config"] = get_event_store().update_site_config(site_id, config)
        return summary
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/admin/stats")
async def admin_stats(_: None = Depends(require_admin)) -> Dict[str, Any]:
    return {
        **get_store().stats(),
        **get_store().lead_stats(),
        **get_payments().invoice_stats(),
    }


@app.get("/api/v1/admin/leads")
async def admin_list_leads(
    status: Optional[str] = None,
    limit: int = 200,
    _: None = Depends(require_admin),
) -> List[Dict[str, Any]]:
    return get_store().list_leads(status=status, limit=limit)


@app.post("/api/v1/admin/leads/{lead_id}/status")
async def admin_update_lead(
    lead_id: str,
    body: LeadStatusBody,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return get_store().update_lead(lead_id, status=body.status, admin_note=body.note)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/v1/admin/leads/{lead_id}/convert")
async def admin_convert_lead(
    lead_id: str,
    body: ConvertLeadBody,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    lead = get_store().get_lead(lead_id)
    if not lead:
        raise HTTPException(404, "Ariza topilmadi")
    if lead.get("site_id"):
        raise HTTPException(409, "Bu ariza allaqachon mijozga aylantirilgan")
    site = get_store().create_site(
        lead.get("company") or lead["full_name"],
        "lite",
        subscription_months=body.subscription_months,
        contact_phone=lead["phone"],
        address=lead.get("city"),
    )
    get_store().link_lead_site(lead_id, site["site_id"])
    return site


@app.get("/api/v1/admin/readiness")
async def admin_readiness(_: None = Depends(require_admin)) -> Dict[str, Any]:
    public = public_url()
    owner_token = os.environ.get("CHAQIMCHI_OWNER_TELEGRAM_TOKEN", "").strip()
    bot_username = os.environ.get("CHAQIMCHI_TELEGRAM_BOT_USERNAME", "").strip()
    webhook_secret = os.environ.get("CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET", "").strip()
    alert_status = get_alerts().status()
    lead_recipients = _lead_recipient_ids()
    n100_acceptance = pilot_acceptance_status()
    items = [
        {"key": "database", "label": "Mijoz va obuna bazasi", "ok": True, "required": True},
        {
            "key": "n100_acceptance",
            "label": "N100 4 kamera benchmark + 72 soat soak",
            "ok": bool(n100_acceptance["ok"]),
            "required": True,
            "reasons": n100_acceptance["reasons"],
        },
        {
            "key": "public_url",
            "label": "HTTPS rasmiy domen",
            "ok": public.startswith("https://"),
            "required": True,
        },
        {
            "key": "owner_bot",
            "label": "Mijoz Telegram boti",
            "ok": bool(owner_token and bot_username and webhook_secret),
            "required": True,
        },
        {
            "key": "portal_admin",
            "label": "Login/parolli portal administratori",
            "ok": bool(get_store().list_accounts(role="admin", status="active")),
            "required": True,
        },
        {
            "key": "lead_notifications",
            "label": "Sayt arizalari Telegram yetkazilishi",
            "ok": bool(get_alerts().config.token and lead_recipients),
            "required": True,
            "recipients": len(lead_recipients),
        },
        {
            "key": "service_alerts",
            "label": "Servis Telegram ogohlantirishi",
            "ok": bool(alert_status["enabled"]),
            "required": False,
        },
        {
            "key": "payments",
            "label": "Payme yoki Click",
            "ok": bool(payme_config().configured or click_config().configured),
            "required": False,
        },
    ]
    return {
        "ready": all(item["ok"] for item in items if item["required"]),
        "items": items,
    }


class PersonsBody(BaseModel):
    persons: int = Field(ge=0, le=100_000)


@app.post("/api/v1/admin/sites/{site_id}/persons")
async def admin_set_persons(
    site_id: str,
    body: PersonsBody,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    """Shartnomadagi xodim sonini o‘zgartirish (davomat tariflari)."""
    try:
        return get_store().set_billable_persons(site_id, body.persons)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/api/v1/quote")
async def price_quote(persons: int = 0) -> Dict[str, Any]:
    """Shu xodim soniga qaysi tarif arzon — sotuvchi qo‘lda hisoblamasin."""
    persons = max(0, min(100_000, persons))
    plan, monthly = cheapest_plan_for(persons)
    limits = PLANS[plan]
    return {
        "persons": persons,
        "plan": plan,
        "monthly_uzs": monthly,
        "yearly_uzs": monthly * 10,  # 2 oy tekin
        "install_uzs": limits.install_price_uzs,
        "first_payment_uzs": limits.install_price_uzs + monthly * 10,
        "options": {
            name: p.monthly_price(persons)
            for name, p in PLANS.items()
            if p.is_per_person and persons <= p.max_persons
        },
    }


class CamerasBody(BaseModel):
    expected: int = Field(ge=0, le=GUARANTEED_CAMERAS)


class CameraConfigBody(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    rtsp_url: str = Field(min_length=10, max_length=2_000)
    enabled: bool = True


class CameraProbeBody(BaseModel):
    camera_id: str = Field(pattern=r"^camera-\d{2}$")
    status: Literal["online", "offline", "pending"]
    error: Optional[str] = Field(default=None, max_length=500)
    codec: Optional[str] = Field(default=None, max_length=32)
    width: Optional[int] = Field(default=None, ge=1, le=16_384)
    height: Optional[int] = Field(default=None, ge=1, le=16_384)
    fps: Optional[float] = Field(default=None, ge=0.01, le=240)


@app.post("/api/v1/admin/sites/{site_id}/cameras")
async def admin_set_cameras(
    site_id: str,
    body: CamerasBody,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    """O‘rnatilgan kamera sonini belgilash (kamera ataylab olib tashlanganda)."""
    try:
        return get_store().set_cameras_expected(site_id, body.expected)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/api/v1/admin/sites/{site_id}/camera-inventory")
async def admin_list_camera_inventory(
    site_id: str, _: None = Depends(require_admin)
) -> Dict[str, Any]:
    """Admin RTSP secretini ko'rmaydi; u faqat qayta yozilishi mumkin."""
    try:
        return {"cameras": get_store().list_cameras(site_id)}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(404, str(exc)) from exc


@app.put("/api/v1/admin/sites/{site_id}/camera-inventory/{camera_id}")
async def admin_upsert_camera_inventory(
    site_id: str,
    camera_id: str,
    body: CameraConfigBody,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        camera = get_store().upsert_camera(
            site_id,
            camera_id,
            label=body.label,
            rtsp_url=body.rtsp_url,
            enabled=body.enabled,
        )
        # Sotqin keyingi poll'da yangi inventarni olishi uchun config revision oshadi.
        current = get_event_store().get_site_config(site_id)
        updated = get_event_store().update_site_config(site_id, current["config"])
        return {"camera": camera, "config_revision": updated["revision"]}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.delete("/api/v1/admin/sites/{site_id}/camera-inventory/{camera_id}")
async def admin_delete_camera_inventory(
    site_id: str, camera_id: str, _: None = Depends(require_admin)
) -> Dict[str, Any]:
    try:
        removed = get_store().delete_camera(site_id, camera_id)
        if not removed:
            raise HTTPException(404, "Kamera topilmadi")
        current = get_event_store().get_site_config(site_id)
        get_event_store().update_site_config(site_id, current["config"])
        return {"ok": True, "camera_id": camera_id}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


def _site_onboarding_payload(site_id: str) -> Dict[str, Any]:
    detail = get_store().site_detail(site_id)
    members = get_event_store().list_members(site_id)
    customer_accounts = [
        account
        for account in get_store().list_accounts(role="customer", status="active")
        if account.get("site_id") == site_id
    ]
    invoices = get_payments().list_invoices(site_id, limit=100)
    device_paired = bool(detail["devices"])
    cameras_configured = bool(get_store().list_cameras(site_id))
    cameras_seen = int(detail["cameras_expected"] or 0) > 0
    steps = [
        {"key": "customer", "label": "Mijoz ochildi", "done": True},
        {
            "key": "owner",
            "label": "Mijoz login yoki Telegram egasi qo'shildi",
            "done": bool(members or customer_accounts),
        },
        {"key": "cameras_config", "label": "RTSP kameralar kiritildi", "done": cameras_configured},
        {"key": "device", "label": "Sotqin cloudga juftlandi", "done": device_paired},
        {
            "key": "online",
            "label": "Qurilma cloud bilan aloqada",
            "done": detail["connection"] == "online",
        },
        {"key": "cameras", "label": "Kameralar online xabar berdi", "done": cameras_seen},
        {"key": "invoice", "label": "Hisob-faktura ochildi", "done": bool(invoices)},
        {
            "key": "payment",
            "label": "Birinchi to'lov qabul qilindi",
            "done": any(invoice["state"] == "paid" for invoice in invoices),
        },
    ]
    completed = sum(1 for step in steps if step["done"])
    active_code = detail["active_pairing_codes"][0] if detail["active_pairing_codes"] else None
    origin = public_url() or ""
    install_command = None
    if active_code and origin:
        install_command = (
            f"curl -fsSL {origin}/downloads/sotqin-installer.sh | "
            f"sudo bash -s -- --cloud {origin} --code {active_code['code']}"
        )
    return {
        "site_id": site_id,
        "site": detail,
        "completed": completed,
        "total": len(steps),
        "percent": round(completed * 100 / len(steps)),
        "steps": steps,
        "pairing": active_code,
        "connect_url": f"{origin}/connect",
        "install_command": install_command,
    }


def _require_installer_site(installer: PortalPrincipal, site_id: str) -> Dict[str, Any]:
    assignment = get_store().installer_assignment(installer.account_id, site_id)
    if not assignment or assignment["status"] == "cancelled":
        raise HTTPException(403, "Bu obyekt sizga biriktirilmagan")
    return assignment


@app.get("/api/v1/installer/assignments")
async def installer_assignments(
    installer: PortalPrincipal = Depends(require_active_installer),
) -> Dict[str, Any]:
    rows = get_store().list_installer_assignments(installer_id=installer.account_id)
    for row in rows:
        detail = get_store().site_detail(str(row["site_id"]))
        row["connection"] = detail["connection"]
        row["cameras_active"] = detail["cameras_active"]
        row["cameras_expected"] = detail["cameras_expected"]
    return {"assignments": rows}


@app.get("/api/v1/installer/sites/{site_id}/onboarding")
async def installer_site_onboarding(
    site_id: str,
    installer: PortalPrincipal = Depends(require_active_installer),
) -> Dict[str, Any]:
    _require_installer_site(installer, site_id)
    try:
        return _site_onboarding_payload(site_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/v1/installer/sites/{site_id}/pairing")
async def installer_new_pairing(
    site_id: str,
    installer: PortalPrincipal = Depends(require_active_installer),
) -> Dict[str, Any]:
    _require_installer_site(installer, site_id)
    try:
        pairing = get_store().new_pairing_code(site_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    get_store().audit_portal_action(
        "installer.pairing.created",
        actor_id=installer.account_id,
        target_type="site",
        target_id=site_id,
    )
    return {**pairing, "onboarding": _site_onboarding_payload(site_id)}


@app.get("/api/v1/installer/sites/{site_id}/cameras")
async def installer_list_cameras(
    site_id: str,
    installer: PortalPrincipal = Depends(require_active_installer),
) -> Dict[str, Any]:
    _require_installer_site(installer, site_id)
    try:
        return {"cameras": get_store().list_cameras(site_id)}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.put("/api/v1/installer/sites/{site_id}/cameras/{camera_id}")
async def installer_upsert_camera(
    site_id: str,
    camera_id: str,
    body: CameraConfigBody,
    installer: PortalPrincipal = Depends(require_active_installer),
) -> Dict[str, Any]:
    _require_installer_site(installer, site_id)
    try:
        camera = get_store().upsert_camera(
            site_id,
            camera_id,
            label=body.label,
            rtsp_url=body.rtsp_url,
            enabled=body.enabled,
        )
        current = get_event_store().get_site_config(site_id)
        updated = get_event_store().update_site_config(site_id, current["config"])
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    get_store().audit_portal_action(
        "installer.camera.saved",
        actor_id=installer.account_id,
        target_type="camera",
        target_id=f"{site_id}:{camera_id}",
        detail={"label": body.label, "enabled": body.enabled},
    )
    return {"camera": camera, "config_revision": updated["revision"]}


@app.delete("/api/v1/installer/sites/{site_id}/cameras/{camera_id}")
async def installer_delete_camera(
    site_id: str,
    camera_id: str,
    installer: PortalPrincipal = Depends(require_active_installer),
) -> Dict[str, Any]:
    _require_installer_site(installer, site_id)
    try:
        if not get_store().delete_camera(site_id, camera_id):
            raise HTTPException(404, "Kamera topilmadi")
        current = get_event_store().get_site_config(site_id)
        get_event_store().update_site_config(site_id, current["config"])
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    get_store().audit_portal_action(
        "installer.camera.deleted",
        actor_id=installer.account_id,
        target_type="camera",
        target_id=f"{site_id}:{camera_id}",
    )
    return {"ok": True, "camera_id": camera_id}


@app.put("/api/v1/installer/sites/{site_id}/status")
async def installer_update_assignment(
    site_id: str,
    body: InstallerAssignmentUpdateBody,
    installer: PortalPrincipal = Depends(require_active_installer),
) -> Dict[str, Any]:
    current = _require_installer_site(installer, site_id)
    if body.status not in {"in_progress", "ready", "completed"}:
        raise HTTPException(403, "O'rnatuvchi faqat ish jarayoni holatini yangilaydi")
    try:
        assignment = get_store().assign_installer(
            installer.account_id,
            site_id,
            status=body.status,
            notes=body.notes if body.notes is not None else current.get("notes"),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    get_store().audit_portal_action(
        "installer.assignment.status",
        actor_id=installer.account_id,
        target_type="site",
        target_id=site_id,
        detail={"status": body.status},
    )
    return assignment


@app.get("/api/v1/admin/alerts")
async def admin_alerts_status(_: None = Depends(require_admin)) -> Dict[str, Any]:
    """Ogohlantirish sozlamasi va oxirgi tekshiruv natijasi."""
    return get_alerts().status()


@app.post("/api/v1/admin/alerts/test")
async def admin_alerts_test(_: None = Depends(require_admin)) -> Dict[str, Any]:
    """Sinov xabari — token va chat_id to‘g‘ri sozlanganini tekshiradi."""
    service = get_alerts()
    if not service.config.enabled:
        raise HTTPException(
            400,
            "CHAQIMCHI_CLOUD_TELEGRAM_TOKEN va CHAQIMCHI_CLOUD_TELEGRAM_CHAT_ID sozlanmagan",
        )
    ok = await service.sender.send(test_message())
    if not ok:
        raise HTTPException(502, "Telegramga yuborilmadi — token yoki chat_id ni tekshiring")
    return {"ok": True, "message": "Sinov xabari yuborildi"}


@app.post("/api/v1/admin/alerts/check")
async def admin_alerts_check(_: None = Depends(require_admin)) -> Dict[str, Any]:
    """Tekshiruvni darhol ishga tushirish (fon vazifasini kutmasdan)."""
    run = await get_alerts().check_once()
    return {"ok": True, **run.to_dict()}


@app.get("/api/v1/admin/sites/{site_id}")
async def admin_site_detail(
    site_id: str,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return get_store().site_detail(site_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/api/v1/admin/sites/{site_id}/onboarding")
async def admin_site_onboarding(
    site_id: str,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    """Pilot obyektning modeldan mustaqil ulanish bosqichlari."""
    try:
        return _site_onboarding_payload(site_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/v1/admin/sites/{site_id}/extend")
async def admin_extend_subscription(
    site_id: str,
    body: ExtendBody,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return get_store().extend_subscription(site_id, body.months)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/api/v1/admin/sites/{site_id}/status")
async def admin_set_status(
    site_id: str,
    body: StatusBody,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    """To‘lov kechikkanda obunani to‘xtatish yoki to‘lovdan keyin qayta yoqish."""
    try:
        return get_store().set_status(site_id, body.status)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/api/v1/admin/sites/{site_id}/pairing")
async def admin_new_pairing_code(
    site_id: str,
    _: None = Depends(require_admin),
) -> Dict[str, str]:
    """Qurilma almashganda yoki kod muddati o‘tganda yangi juftlash kodi."""
    try:
        return get_store().new_pairing_code(site_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@app.post("/api/v1/devices/claim")
@app.post("/api/v1/sotqin/claim")
async def claim_device(body: ClaimDeviceBody) -> Dict[str, str]:
    try:
        return get_store().claim_device(
            body.pairing_code,
            hardware_id=body.hardware_id,
            label=body.label,
            product_name=body.product_name,
            hardware_model=body.hardware_model,
            hardware_revision=body.hardware_revision,
            serial_number=body.serial_number,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/v1/license/heartbeat")
async def license_heartbeat(
    body: HeartbeatBody,
    x_site_id: str = Header(..., alias="X-Site-Id"),
    x_device_token: str = Header(..., alias="X-Device-Token"),
) -> Dict[str, Any]:
    try:
        return get_store().heartbeat(
            x_site_id,
            x_device_token,
            active_cameras=body.active_cameras,
        )
    except ValueError as e:
        raise HTTPException(401, str(e)) from e


# ── Production event ingestion ───────────────────────────────────────────


@app.post("/api/v1/edge/events/batch")
async def ingest_event_batch(
    body: EventBatchBody,
    background_tasks: BackgroundTasks,
    device: Dict[str, Any] = Depends(require_device),
) -> Dict[str, Any]:
    ratelimit.check(
        "events",
        device["device_id"],
        limit=EVENT_BATCH_HOURLY_LIMIT,
        window_sec=3_600,
        message="Event yuborish chegarasi oshdi — keyinroq qayta yuboriladi",
    )
    event_store = get_event_store()
    existing = event_store.existing_event_ids(
        device["site_id"], [event.event_id for event in body.events]
    )
    accepted = event_store.ingest(device["site_id"], device["device_id"], body.events)
    new_events = [event for event in body.events if event.event_id not in existing]
    # Butun batch uchun **bitta** yig'ma xabar. Har event uchun alohida yuborish
    # 500 talik batchda botni Telegram limitiga urib, xabarni butunlay
    # yo'qotardi — batafsili `cloud/notify.py` da.
    message = build_alert(device["site_id"], new_events)
    if message:
        if any(event.has_snapshot or event.has_clip for event in new_events):
            message += (
                f"\n🔐 Rasm va klip: {public_url().rstrip('/')}/owner?site={device['site_id']}"
            )
        background_tasks.add_task(_notify_site_members, device["site_id"], message)
    return {"ok": True, "accepted": accepted}


@app.put("/api/v1/edge/events/{event_id}/snapshot")
async def upload_event_snapshot(
    event_id: str,
    request: Request,
    device: Dict[str, Any] = Depends(require_device),
) -> Dict[str, Any]:
    # Snapshot 8 MB gacha bo'lishi mumkin — kunlik chegara S3 hisobini va
    # diskni bitta buzuq qurilmadan himoya qiladi.
    ratelimit.check(
        "snapshots",
        device["site_id"],
        limit=500,
        window_sec=86_400,
        message="Kunlik snapshot chegarasi oshdi",
    )
    event = get_event_store().event(device["site_id"], event_id)
    if not event or event["device_id"] != device["device_id"]:
        raise HTTPException(404, "Event topilmadi")
    if event["event_type"] == "employee_seen":
        raise HTTPException(
            403,
            "Davomat biometrik snapshotlari cloudga yuklanmaydi",
        )
    if request.headers.get("content-type", "").split(";", 1)[0] != "image/jpeg":
        raise HTTPException(415, "Faqat image/jpeg qabul qilinadi")
    content = await request.body()
    if not content:
        raise HTTPException(400, "Snapshot bo'sh")
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(413, "Snapshot 8 MB dan katta")
    key = f"{device['site_id']}/{event_id}.jpg"
    get_snapshot_store().put(key, content, content_type="image/jpeg")
    get_event_store().set_snapshot(device["site_id"], event_id, key)
    return {"ok": True, "event_id": event_id}


@app.put("/api/v1/edge/events/{event_id}/clip")
async def upload_event_clip(
    event_id: str,
    request: Request,
    device: Dict[str, Any] = Depends(require_device),
) -> Dict[str, Any]:
    ratelimit.check(
        "event-clips",
        device["site_id"],
        limit=100,
        window_sec=86_400,
        message="Kunlik videoklip chegarasi oshdi",
    )
    event = get_event_store().event(device["site_id"], event_id)
    if not event or event["device_id"] != device["device_id"]:
        raise HTTPException(404, "Event topilmadi")
    if event["event_type"] == "employee_seen":
        raise HTTPException(403, "Davomat biometrik videolari cloudga yuklanmaydi")
    if request.headers.get("content-type", "").split(";", 1)[0] != "video/mp4":
        raise HTTPException(415, "Faqat video/mp4 qabul qilinadi")
    content = await request.body()
    if not content:
        raise HTTPException(400, "Videoklip bo'sh")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(413, "Videoklip 50 MB dan katta")
    key = f"{device['site_id']}/{event_id}.mp4"
    get_snapshot_store().put(key, content, content_type="video/mp4")
    get_event_store().set_clip(device["site_id"], event_id, key)
    return {"ok": True, "event_id": event_id}


@app.post("/api/v1/edge/heartbeat")
@app.post("/api/v1/sotqin/heartbeat")
async def edge_health_heartbeat(
    body: EdgeHeartbeatBody,
    device: Dict[str, Any] = Depends(require_device),
) -> Dict[str, Any]:
    get_event_store().record_health(device["site_id"], device["device_id"], body.model_dump())
    # Legacy connection monitoring ham yangi heartbeat bilan yangilanadi.
    get_store().heartbeat(
        device["site_id"],
        device["device_token"],
        active_cameras=body.cameras_active,
    )
    # Qurilma har daqiqada `/config` ni to'liq tortib olardi — kuniga 1440 ta
    # og'ir so'rov, javob esa deyarli har doim bir xil. Endi javobdagi shu
    # bitta son qurilmaga o'zgarish bor-yo'qligini aytadi.
    revision = get_event_store().config_revision(device["site_id"])
    return {
        "ok": True,
        "config_revision": revision,
        "config_changed": body.config_revision != revision,
        "received": body.model_dump(),
    }


@app.get("/api/v1/edge/config")
@app.get("/api/v1/sotqin/config")
async def edge_site_config(
    device: Dict[str, Any] = Depends(require_device),
) -> Dict[str, Any]:
    config = get_event_store().get_site_config(device["site_id"])
    features = get_store().site_feature_summary(device["site_id"])
    # Edge AI qarorini chiqarmaydi: faqat cloud jobiga kerakli sampling va
    # queue turini qabul qiladi. Active assignmentlar revision bilan keladi.
    config["product"] = product_payload()
    config["buffer_policy"] = {
        "max_days": BUFFER_RETENTION_DAYS,
        "max_bytes": BUFFER_MAX_BYTES,
        "min_free_bytes": MIN_FREE_BYTES,
        "critical_priority": True,
        "full_video_storage": "nvr",
    }
    config["cameras"] = get_store().list_cameras(device["site_id"], include_source=True)
    config["cloud_features"] = [
        {
            "code": item["feature_code"],
            "camera_count": item["camera_count"],
            "queue_kind": item["queue_kind"],
        }
        for item in features["assignments"]
        if item["status"] == "active"
    ]
    config["attendance"] = {
        "enabled": _attendance_enabled(),
        "mode": (
            "commercial"
            if os.environ.get("CHAQIMCHI_FACE_MODEL_LICENSED", "").lower() in {"1", "true", "yes"}
            else "closed_pilot"
            if _attendance_enabled()
            else "disabled"
        ),
        # Ism va rozilik holati enrollment uchun kerak; biometrik rasm yoki
        # embedding hech qachon cloud config'iga kirmaydi.
        "employees": (
            get_event_store().edge_employees(device["site_id"]) if _attendance_enabled() else []
        ),
    }
    return config


@app.post("/api/v1/edge/employees/{employee_id}/enrollment")
async def edge_employee_enrollment(
    employee_id: str,
    body: EnrollmentStatusBody,
    device: Dict[str, Any] = Depends(require_device),
) -> Dict[str, Any]:
    require_attendance()
    try:
        return get_event_store().update_employee(
            device["site_id"], employee_id, enrollment_status=body.status
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/v1/sotqin/config/ack")
async def sotqin_config_ack(
    body: ConfigAckBody,
    device: Dict[str, Any] = Depends(require_device),
) -> Dict[str, Any]:
    """Sotqin config'ni atomik qo'llaganini yoki rad etganini qayd etadi."""
    try:
        updated = get_store().record_config_ack(
            device["site_id"],
            device["device_id"],
            revision=body.revision,
            status=body.status,
            error=body.error,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "ok": True,
        "device_id": updated["id"],
        "revision": updated["config_revision"],
        "status": updated["config_status"],
    }


@app.post("/api/v1/sotqin/camera-probes")
async def sotqin_camera_probes(
    body: List[CameraProbeBody] = Body(max_length=GUARANTEED_CAMERAS),
    device: Dict[str, Any] = Depends(require_device),
) -> Dict[str, Any]:
    """Sotqin ffprobe natijasini yuboradi; RTSP URL hech qachon qaytib kelmaydi."""
    saved = 0
    for item in body:
        try:
            get_store().record_camera_probe(device["site_id"], **item.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        saved += 1
    return {"ok": True, "saved": saved}


# ── Owner/manager Telegram OTP va panel API ──────────────────────────────


@app.post("/api/v1/admin/sites/{site_id}/members")
async def admin_add_member(
    site_id: str,
    body: MemberBody,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    if not get_store().get_site(site_id):
        raise HTTPException(404, "Sayt topilmadi")
    return get_event_store().add_member(
        site_id,
        body.telegram_id,
        role=body.role,
        display_name=body.display_name,
    )


@app.post("/api/v1/owner/auth/request")
async def owner_request_otp(body: OtpRequestBody) -> Dict[str, Any]:
    # Har chaqiruv Telegramga xabar yuboradi — cheklovsiz bu mijozning
    # telefonini ham, botni ham ko'mib tashlaydi.
    ratelimit.check(
        "otp",
        body.telegram_id,
        limit=3,
        window_sec=600,
        message="Juda ko'p kod so'raldi. 10 daqiqadan keyin urinib ko'ring.",
    )
    members = get_event_store().members_for_telegram(body.telegram_id)
    # Akkaunt bor-yo'qligini tashqariga oshkor qilmaymiz.
    if not members:
        return {"ok": True, "message": "Agar akkaunt mavjud bo'lsa, kod yuborildi"}
    secret = _owner_secret()
    test_code = os.environ.get("CHAQIMCHI_OTP_TEST_CODE", "").strip()
    code = get_event_store().create_otp(
        body.telegram_id,
        secret=secret,
        code=test_code or None,
    )
    await _send_owner_telegram(
        body.telegram_id,
        f"Chaqimchi AI kirish kodi: {code}\nKod 5 daqiqa amal qiladi.",
    )
    response: Dict[str, Any] = {
        "ok": True,
        "message": "Agar akkaunt mavjud bo'lsa, kod yuborildi",
    }
    if os.environ.get("CHAQIMCHI_ENV", "development") != "production" and test_code:
        response["debug_code"] = code
    return response


@app.post("/api/v1/owner/auth/verify")
async def owner_verify_otp(body: OtpVerifyBody) -> Dict[str, Any]:
    secret = _owner_secret()
    if not get_event_store().verify_otp(body.telegram_id, body.code, secret=secret):
        raise HTTPException(401, "Kod noto'g'ri yoki muddati tugagan")
    members = get_event_store().members_for_telegram(body.telegram_id)
    if body.site_id:
        member = next((item for item in members if item["site_id"] == body.site_id), None)
    elif len(members) == 1:
        member = members[0]
    else:
        raise HTTPException(409, "Bir nechta obyekt bor; site_id ko'rsating")
    if not member:
        raise HTTPException(401, "Owner akkaunti topilmadi")
    try:
        token = issue_owner_token(member)
    except Exception as exc:
        raise HTTPException(503, "Owner session yaratilmadi") from exc
    return {
        "ok": True,
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 12 * 3600,
        "site_id": member["site_id"],
        "role": member["role"],
    }


@app.get("/api/v1/owner/events")
async def owner_events(
    limit: int = 100,
    event_type: Optional[str] = None,
    camera_id: Optional[str] = None,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    events = get_event_store().list_events(
        owner.site_id,
        limit=max(1, min(limit, 500)),
        event_type=event_type,
        camera_id=camera_id,
    )
    # Mijoz `line_crossed` degan so'zni tushunmaydi.  Tarjima serverda
    # qo'shiladi — panel va Telegram bitta manbadan foydalanadi.
    for item in events:
        item["label"] = event_label(str(item.get("event_type", "")))
    return {"events": events}


@app.get("/api/v1/owner/report")
async def owner_report(
    date: Optional[str] = None, owner: OwnerPrincipal = Depends(require_active_owner)
) -> Dict[str, Any]:
    """Kunlik do'kon hisoboti: kirish, gavjum soat, navbat, dwell."""
    day: Optional[date_type] = None
    if date:
        try:
            day = date_type.fromisoformat(date)
        except ValueError as exc:
            raise HTTPException(422, "Sana YYYY-MM-DD ko'rinishida bo'lishi kerak") from exc
    return get_event_store().retail_report(owner.site_id, day=day)


@app.get("/api/v1/owner/trend")
async def owner_trend(
    days: int = 7, owner: OwnerPrincipal = Depends(require_active_owner)
) -> Dict[str, Any]:
    """Kunlar bo'yicha kirish oqimi: qaysi kun kuchli, hafta qanday ketdi."""
    return get_event_store().traffic_trend(owner.site_id, days=days)


@app.get("/api/v1/owner/stats")
async def owner_stats(owner: OwnerPrincipal = Depends(require_active_owner)) -> Dict[str, Any]:
    return get_event_store().stats(owner.site_id)


@app.get("/api/v1/owner/health")
async def owner_health(owner: OwnerPrincipal = Depends(require_active_owner)) -> Dict[str, Any]:
    detail = get_store().site_detail(owner.site_id)
    return {
        "devices": get_event_store().health(owner.site_id),
        "cameras_expected": detail["cameras_expected"],
        "connection": detail["connection"],
    }


@app.get("/api/v1/owner/cameras")
async def owner_cameras(owner: OwnerPrincipal = Depends(require_active_owner)) -> Dict[str, Any]:
    # RTSP credentiallari owner brauzeriga qaytmaydi.
    return {"cameras": get_store().list_cameras(owner.site_id, include_source=False)}


@app.get("/api/v1/owner/config")
async def owner_get_config(
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    return get_event_store().get_site_config(owner.site_id)


@app.put("/api/v1/owner/config")
async def owner_update_config(
    body: SiteConfigBody,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    require_owner_role(owner, "owner", "service_admin")
    allowed_cameras = {f"camera-{number:02d}" for number in range(1, GUARANTEED_CAMERAS + 1)}
    configured_ids = (
        set(body.camera_labels)
        | set(body.camera_roles)
        | set(body.attendance_camera_ids)
        | set(body.attendance_camera_roles)
    )
    if any(camera_id not in allowed_cameras for camera_id in configured_ids):
        raise HTTPException(
            422,
            f"Pilot kamera ID camera-01..camera-{GUARANTEED_CAMERAS:02d} bo'lishi kerak",
        )
    if any(zone.camera_id not in allowed_cameras for zone in body.zones):
        raise HTTPException(422, "Zona noma'lum kameraga bog'langan")
    if any(line.camera_id not in allowed_cameras for line in body.lines):
        raise HTTPException(422, "Chiziq noma'lum kameraga bog'langan")
    if not set(body.attendance_camera_roles).issubset(body.attendance_camera_ids):
        raise HTTPException(422, "Davomat roli faqat tanlangan davomat kamerasiga beriladi")
    if bool(body.open_from) != bool(body.open_to):
        raise HTTPException(422, "Ish boshlanishi va tugashi birga berilishi kerak")
    return get_event_store().update_site_config(owner.site_id, body.model_dump())


@app.get("/api/v1/owner/employees")
async def owner_employees(
    include_inactive: bool = False,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    require_attendance()
    return {
        "mode": (
            "commercial"
            if os.environ.get("CHAQIMCHI_FACE_MODEL_LICENSED", "").lower() in {"1", "true", "yes"}
            else "closed_pilot"
        ),
        "employees": get_event_store().list_employees(
            owner.site_id, include_inactive=include_inactive
        ),
    }


@app.post("/api/v1/owner/employees")
async def owner_create_employee(
    body: EmployeeCreateBody,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    require_attendance()
    require_owner_role(owner, "owner", "service_admin")
    if not body.consent:
        raise HTTPException(422, "Xodimning yozma roziligi qayd etilishi shart")
    try:
        employee = get_event_store().create_employee(
            owner.site_id,
            name=body.name,
            external_id=body.external_id,
            consent_note=body.consent_note,
        )
        get_event_store().touch_site_config(owner.site_id)
        return employee
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.put("/api/v1/owner/employees/{employee_id}")
async def owner_update_employee(
    employee_id: str,
    body: EmployeeUpdateBody,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    require_attendance()
    require_owner_role(owner, "owner", "service_admin")
    try:
        employee = get_event_store().update_employee(
            owner.site_id,
            employee_id,
            name=body.name,
            external_id=body.external_id,
            active=body.active,
        )
        get_event_store().touch_site_config(owner.site_id)
        return employee
    except ValueError as exc:
        raise HTTPException(404 if "topilmadi" in str(exc) else 422, str(exc)) from exc


@app.put("/api/v1/owner/employees/{employee_id}/schedule")
async def owner_replace_employee_schedule(
    employee_id: str,
    body: EmployeeScheduleBody,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    require_attendance()
    require_owner_role(owner, "owner", "service_admin")
    for item in body.schedules:
        if item.enabled and item.end_time <= item.start_time:
            raise HTTPException(
                422, "MVP jadvalida tugash vaqti boshlanishdan keyin bo'lishi kerak"
            )
    try:
        schedules = get_event_store().replace_employee_schedules(
            owner.site_id,
            employee_id,
            [item.model_dump() for item in body.schedules],
        )
        get_event_store().touch_site_config(owner.site_id)
    except ValueError as exc:
        raise HTTPException(404 if "topilmadi" in str(exc) else 422, str(exc)) from exc
    return {"employee_id": employee_id, "schedules": schedules}


def _attendance_dates(start: Optional[str], end: Optional[str]) -> tuple[date_type, date_type]:
    today = datetime.now(ZoneInfo("Asia/Tashkent")).date()
    try:
        parsed_start = date_type.fromisoformat(start) if start else today
        parsed_end = date_type.fromisoformat(end) if end else parsed_start
    except ValueError as exc:
        raise HTTPException(422, "Sana YYYY-MM-DD ko'rinishida bo'lishi kerak") from exc
    if parsed_end < parsed_start or parsed_end - parsed_start > timedelta(days=366):
        raise HTTPException(422, "Davomat oralig'i noto'g'ri yoki 367 kundan uzun")
    return parsed_start, parsed_end


@app.get("/api/v1/owner/attendance")
async def owner_attendance(
    start: Optional[str] = None,
    end: Optional[str] = None,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    require_attendance()
    first, last = _attendance_dates(start, end)
    return get_event_store().attendance_report(owner.site_id, start=first, end=last)


@app.get("/api/v1/owner/attendance.csv")
async def owner_attendance_csv(
    start: Optional[str] = None,
    end: Optional[str] = None,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Response:
    require_attendance()
    first, last = _attendance_dates(start, end)
    report = get_event_store().attendance_report(owner.site_id, start=first, end=last)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "sana",
            "xodim_id",
            "tashqi_id",
            "xodim",
            "jadval_kirish",
            "jadval_chiqish",
            "keldi",
            "ketdi",
            "holat",
            "kechikish_daq",
            "erta_ketish_daq",
            "chiqish_aniqlanmadi",
        ]
    )
    for row in report["rows"]:
        writer.writerow(
            [
                row["date"],
                row["employee_id"],
                row.get("external_id") or "",
                row["employee_name"],
                row.get("scheduled_start") or "",
                row.get("scheduled_end") or "",
                row.get("first_seen") or "",
                row.get("last_seen") or "",
                row["status"],
                row["late_minutes"],
                row["early_leave_minutes"],
                "ha" if row["checkout_missing"] else "yo'q",
            ]
        )
    filename = f"davomat-{first.isoformat()}-{last.isoformat()}.csv"
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/v1/owner/features")
async def owner_features(owner: OwnerPrincipal = Depends(require_active_owner)) -> Dict[str, Any]:
    """Mijoz o'z obunasi va tanlash mumkin bo'lgan funksiyalarni ko'radi."""
    return {
        "catalog": get_store().list_feature_catalog(),
        "summary": get_store().site_feature_summary(owner.site_id),
    }


@app.post("/api/v1/owner/features/quote")
async def owner_feature_quote(
    body: FeatureDraftBody, owner: OwnerPrincipal = Depends(require_active_owner)
) -> Dict[str, Any]:
    try:
        return get_store().feature_quote([item.model_dump() for item in body.selections])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.put("/api/v1/owner/features/request")
async def owner_feature_request(
    body: FeatureDraftBody, owner: OwnerPrincipal = Depends(require_active_owner)
) -> Dict[str, Any]:
    """Mijoz so'rovi draft bo'ladi; narx o'zgarishini admin tasdiqlaydi."""
    require_owner_role(owner, "owner", "manager")
    try:
        return get_store().replace_feature_draft(
            owner.site_id, [item.model_dump() for item in body.selections]
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/owner/members")
async def owner_members(owner: OwnerPrincipal = Depends(require_active_owner)) -> Dict[str, Any]:
    return {"members": get_event_store().list_members(owner.site_id)}


@app.post("/api/v1/owner/members")
async def owner_add_member(
    body: MemberBody,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    require_owner_role(owner, "owner", "service_admin")
    if body.role == "service_admin" and owner.role != "service_admin":
        raise HTTPException(403, "Service admin rolini faqat service admin beradi")
    return get_event_store().add_member(
        owner.site_id,
        body.telegram_id,
        role=body.role,
        display_name=body.display_name,
    )


@app.delete("/api/v1/owner/members/{member_id}")
async def owner_delete_member(
    member_id: str,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    require_owner_role(owner, "owner", "service_admin")
    if member_id == owner.member_id:
        raise HTTPException(409, "O'zingizni o'chira olmaysiz")
    if not get_event_store().disable_member(owner.site_id, member_id):
        raise HTTPException(404, "Member topilmadi")
    return {"ok": True}


@app.get("/api/v1/owner/events/{event_id}/snapshot")
async def owner_snapshot(
    event_id: str,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Response:
    event = get_event_store().event(owner.site_id, event_id)
    if not event or not event.get("snapshot_key"):
        raise HTTPException(404, "Snapshot topilmadi")
    try:
        content = get_snapshot_store().get(event["snapshot_key"])
    except FileNotFoundError as exc:
        raise HTTPException(404, "Snapshot topilmadi") from exc
    return Response(content=content, media_type="image/jpeg")


@app.get("/api/v1/owner/events/{event_id}/clip")
async def owner_clip(
    event_id: str,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Response:
    event = get_event_store().event(owner.site_id, event_id)
    if not event or not event.get("clip_key"):
        raise HTTPException(404, "Videoklip topilmadi")
    try:
        content = get_snapshot_store().get(event["clip_key"])
    except FileNotFoundError as exc:
        raise HTTPException(404, "Videoklip topilmadi") from exc
    return Response(content=content, media_type="video/mp4")


@app.post("/api/v1/telegram/webhook")
async def owner_telegram_webhook(
    request: Request,
    x_telegram_secret: Optional[str] = Header(
        None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
) -> Dict[str, Any]:
    expected = os.environ.get("CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET", "").strip()
    if not expected or not x_telegram_secret or not secrets.compare_digest(
        x_telegram_secret, expected
    ):
        raise HTTPException(404, "Topilmadi")
    try:
        update = await request.json()
    except Exception as exc:
        raise HTTPException(400, "Telegram update noto'g'ri") from exc
    membership = update.get("my_chat_member") or {}
    membership_chat = membership.get("chat") or {}
    if membership_chat.get("type") in {"group", "supergroup"}:
        # Guruhlar lead qabul qiluvchi sifatida avtomatik ro'yxatdan o'tmaydi.
        # Leadlar faqat CHAQIMCHI_TELEGRAM_LEAD_CHAT_IDS dagi shaxsiy ID'larga boradi.
        return {"ok": True}

    message = update.get("message") or {}
    chat = message.get("chat") or {}
    telegram_id = str(chat.get("id") or "")
    text = str(message.get("text") or "").strip()
    command = text.split()[0].lower().split("@", 1)[0] if text else ""
    members = get_event_store().members_for_telegram(telegram_id)
    if telegram_id and chat.get("type") == "private" and command in {"/start", "/help"}:
        base = public_url().rstrip("/") or str(request.base_url).rstrip("/")
        customer_url = f"{base}/owner"
        if members:
            customer_url += f"?site={quote(str(members[0]['site_id']), safe='')}"
        await _send_owner_telegram(
            telegram_id,
            "<b>Chaqimchi AI platformasiga xush kelibsiz.</b>\n\n"
            "Yangi Sotqin mini-kompyuterini sozlash uchun o‘rnatuvchi bo‘limini tanlang. "
            "Agar tizimni harid qilgan bo‘lsangiz, mijoz panelidan kamera va qurilma "
            "holatini kuzating.",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "🖥 Sotqinni o‘rnatish", "url": f"{base}/installer"}],
                    [{"text": "🏪 Mijoz panelini ochish", "url": customer_url}],
                    [{"text": "🛒 Tarif va maslahat", "url": f"{base}/#configurator"}],
                ]
            },
        )
        return {"ok": True}
    if not telegram_id or not members:
        return {"ok": True}

    lines: List[str] = []
    for member in members:
        site = get_store().get_site(member["site_id"])
        if not site:
            continue
        if command in {"/today", "/status", "/cameras"}:
            stats = get_event_store().stats(member["site_id"])
            detail = get_store().site_detail(member["site_id"])
            lines.append(
                f"{site['name']}: {stats['total']} hodisa, "
                f"{detail['cameras_active']}/{detail['cameras_expected']} kamera, "
                f"aloqa {detail['connection']}"
            )
        else:
            lines.append(f"{site['name']} uchun buyruqlar: /status, /today, /cameras, /help")
    if lines:
        await _send_owner_telegram(telegram_id, "\n".join(lines))
    return {"ok": True}


# ── To'lov: hisob-faktura (admin) ────────────────────────────────────────


def _with_links(invoice: Dict[str, Any]) -> Dict[str, Any]:
    """Hisob-fakturaga to'lov havolalarini qo'shadi (sozlanmagan provayder — bo'sh satr)."""
    base = public_url()
    pay_page = f"{base}/pay/{invoice['id']}" if base else f"/pay/{invoice['id']}"
    return {
        **invoice,
        "pay_url": pay_page,
        "payme_url": payme_api.checkout_link(payme_config(), invoice, pay_page if base else ""),
        "click_url": click_api.checkout_link(click_config(), invoice, pay_page if base else ""),
    }


@app.get("/api/v1/admin/payments/providers")
async def admin_payment_providers(_: None = Depends(require_admin)) -> Dict[str, Any]:
    """Qaysi provayder sozlangan — panel shunga qarab tugmalarni ko'rsatadi."""
    return {
        "payme": payme_config().configured,
        "click": click_config().configured,
        "public_url": public_url(),
    }


@app.post("/api/v1/admin/sites/{site_id}/invoices")
async def admin_create_invoice(
    site_id: str,
    body: CreateInvoiceBody,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    """Obunani uzaytirish uchun hisob-faktura. Summa tarif bo'yicha serverda hisoblanadi."""
    try:
        invoice = get_payments().create_invoice(site_id, body.months, note=body.note)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return _with_links(invoice)


@app.get("/api/v1/owner/invoices")
async def owner_list_invoices(
    limit: int = 30, owner: OwnerPrincipal = Depends(require_active_owner)
) -> List[Dict[str, Any]]:
    return [_with_links(i) for i in get_payments().list_invoices(owner.site_id, limit=limit)]


@app.post("/api/v1/owner/invoices")
async def owner_create_invoice(
    body: CreateInvoiceBody, owner: OwnerPrincipal = Depends(require_active_owner)
) -> Dict[str, Any]:
    """Mijoz faol tarif bo'yicha Payme/Click hisobini mustaqil ochishi mumkin."""
    require_owner_role(owner, "owner", "manager")
    try:
        return _with_links(get_payments().create_invoice(owner.site_id, body.months))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/v1/admin/invoices")
async def admin_list_invoices(
    site_id: Optional[str] = None,
    limit: int = 100,
    _: None = Depends(require_admin),
) -> List[Dict[str, Any]]:
    return [_with_links(i) for i in get_payments().list_invoices(site_id, limit=limit)]


@app.post("/api/v1/admin/invoices/{invoice_id}/paid")
async def admin_mark_paid(
    invoice_id: str,
    body: ManualPaymentBody,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    """Naqd/bank to'lovi — obuna avtomatik uzayadi."""
    try:
        return get_payments().mark_paid(invoice_id, body.provider, provider_txn_id=body.reference)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/v1/admin/invoices/{invoice_id}/cancel")
async def admin_cancel_invoice(
    invoice_id: str,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return get_payments().cancel_invoice(invoice_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


# ── To'lov: mijoz sahifasi ───────────────────────────────────────────────


@app.get("/pay/{invoice_id}", include_in_schema=False)
async def pay_page(invoice_id: str) -> FileResponse:
    """Mijozga yuboriladigan sahifa: summa + Payme/Click tugmalari."""
    page = STATIC_DIR / "pay.html"
    if not page.is_file():
        raise HTTPException(404, "To'lov sahifasi topilmadi")
    return FileResponse(page)


@app.get("/api/v1/invoices/{invoice_id}")
async def public_invoice(invoice_id: str) -> Dict[str, Any]:
    """To'lov sahifasi uchun ochiq ma'lumot — havolani bilgan mijoz ko'radi."""
    invoice = get_payments().get_invoice(invoice_id)
    if not invoice:
        raise HTTPException(404, "Hisob-faktura topilmadi")
    linked = _with_links(invoice)
    return {
        "id": linked["id"],
        "site_name": linked["site_name"],
        "plan": linked["plan"],
        "months": linked["months"],
        "amount_uzs": linked["amount_uzs"],
        "state": linked["state"],
        "created_at": linked["created_at"],
        "paid_at": linked["paid_at"],
        "payme_url": linked["payme_url"],
        "click_url": linked["click_url"],
    }


# ── To'lov: provayder callbacklari ───────────────────────────────────────


@app.post("/api/v1/payments/payme")
async def payme_callback(request: Request) -> Dict[str, Any]:
    """Payme Merchant API. Doim HTTP 200 — xato JSON ichida qaytadi."""
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 — noto'g'ri JSON ham JSON-RPC xatosi bo'lishi kerak
        payload = None
    return payme_api.handle(
        payload,
        auth_header=request.headers.get("Authorization"),
        store=get_payments(),
        config=payme_config(),
    )


async def _click_params(request: Request) -> Dict[str, str]:
    """Click form-urlencoded yuboradi, ba'zan JSON — ikkalasini ham qabul qilamiz."""
    if "application/json" in request.headers.get("content-type", ""):
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            data = {}
    else:
        data = await request.form()
    if not isinstance(data, dict):
        data = dict(data)
    return {str(k): str(v) for k, v in data.items()}


@app.post("/api/v1/payments/click/prepare")
async def click_prepare(request: Request) -> Dict[str, Any]:
    return click_api.handle_prepare(
        await _click_params(request), store=get_payments(), config=click_config()
    )


@app.post("/api/v1/payments/click/complete")
async def click_complete(request: Request) -> Dict[str, Any]:
    return click_api.handle_complete(
        await _click_params(request), store=get_payments(), config=click_config()
    )
