"""
Chaqimchi Cloud — mijozlar, litsenziya, o‘rnatish juftlash.

Ishga tushirish: make run-cloud  (port 8750)
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import hmac
import html
import io
import json
import logging
import os
import re
import secrets
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo

from fastapi import (
    BackgroundTasks,
    Body,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from chaqimchi_ai import __version__, announcements
from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.jwt_auth import JwtError
from chaqimchi_ai.licensing.plans import (
    PLANS,
    SELLABLE_PLANS,
    PlanBullet,
    PlanTier,
    cheapest_plan_for,
    get_plan,
    is_sellable,
    plan_display_name,
    plan_feature_codes,
    usd_rate_uzs,
    uzs_from_cents,
)
from chaqimchi_ai.limits import SHOP_MAX_CAMERAS
from chaqimchi_ai.pilot_acceptance import pilot_acceptance_status
from chaqimchi_ai.settings import SceneLineSettings, SceneZoneSettings
from chaqimchi_ai.sotqin_profile import (
    BUFFER_MAX_BYTES,
    BUFFER_RETENTION_DAYS,
    GUARANTEED_CAMERAS,
    MIN_FREE_BYTES,
    product_payload,
)
from cloud import botfmt, faces, ratelimit, rtsp, server_health, trust_score, urls, vision_agent
from cloud.alerts import AlertService, test_message
from cloud.digest import DailyDigestService, build_digest
from cloud.event_store import EventStore, event_store_from_env
from cloud.notify import DEFAULT_TELEGRAM_LEVEL as notify_default_level
from cloud.notify import event_label, select_alert_events
from cloud.notify import summarize as notify_summarize
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
    normalize_username,
    validate_password,
)
from cloud.snapshots import SnapshotStore, snapshot_store_from_env
from cloud.store import DEFAULT_FEATURES, GRACE_DAYS, CloudStore, available_feature_codes

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("CHAQIMCHI_CLOUD_DB", str(BASE_DIR / "data" / "cloud" / "cloud.db")))
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

#: Qurilma heartbeat oralig'i 60 s, shuning uchun rasm so'ralgach panel
#: taxminan shuncha kutadi.  Panelga aniq raqam beriladi — "biroz kuting"
#: degan matn o'rnatuvchini ishlamayapti deb o'ylashga majbur qiladi.
PREVIEW_WAIT_HINT_SEC = 60

#: Media yuklash limitlari.  Bular deploy/Caddyfile `max_size` dan KICHIK
#: bo'lishi shart, aks holda proxy so'rovni app'gacha yetkazmay 413 qaytaradi
#: va edge kliplari jimgina dead_letter'ga tushadi (bir marta shunday
#: bo'lgan: Caddy 10MB, klip 15-22MB edi).  Moslikni
#: tests/test_proxy_limits.py qattiq tekshiradi.
SNAPSHOT_MAX_BYTES = 8 * 1024 * 1024
CLIP_MAX_BYTES = 50 * 1024 * 1024

logger = logging.getLogger(__name__)

_store: Optional[CloudStore] = None
_payments: Optional[PaymentStore] = None
_alerts: Optional[AlertService] = None
_event_store: Optional[EventStore] = None
_snapshots: Optional[SnapshotStore] = None
_event_store_key: Optional[str] = None
_digest: Optional[DailyDigestService] = None
_vision_worker_stop: Optional[asyncio.Event] = None
_vision_worker_task: Optional[asyncio.Task[Any]] = None
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


# ── Media: HAR DOIM alohida oqimda ───────────────────────────────────────
#
# MinIO mijozi sinxron: `put`/`get` tarmoq bilan ishlaydi va tugaguncha
# qaytmaydi.  `async def` ichidan to'g'ridan-to'g'ri chaqirilganda u yagona
# hodisa halqasini ushlab turadi — ya'ni 50 MB klip yuklanayotganda BUTUN
# server (barcha do'konning heartbeat'i, panel, bot) javob bermay turadi.
#
# Server bitta uvicorn ishchisida ishlagani uchun bu nazariy emas: klip
# chegarasi aynan 50 MB (`CLIP_MAX_BYTES`) va sekin do'kon internetida
# yuklash o'nlab soniya davom etadi.
#
# Shu sabab media bilan ishlashning yagona yo'li — quyidagi uchta funksiya.


async def media_put(key: str, data: bytes, *, content_type: str) -> None:
    await asyncio.to_thread(get_snapshot_store().put, key, data, content_type=content_type)


async def media_get(key: str) -> bytes:
    return await asyncio.to_thread(get_snapshot_store().get, key)


async def media_delete(key: str) -> None:
    await asyncio.to_thread(get_snapshot_store().delete, key)


async def vision_media_put(key: str, data: bytes, mime: str) -> None:
    """Vision worker adapteri: worker generic callback, storage esa keyword API."""
    await media_put(key, data, content_type=mime)


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


def _audit_actor(admin: Optional[PortalPrincipal]) -> str:
    """Audit jurnalida kim turishi.

    `require_admin` master kalit (`X-Cloud-Admin-Key`) bilan `None`
    qaytaradi.  Uni shundayligicha yozib qo'yish jurnalni ma'nosiz
    qilardi: eng kuchli kalit bilan qilingan amal `actor_id=NULL` bo'lib
    boshqa har qanday bo'sh yozuvdan farq qilmasdi.

    Endi hech bo'lmasa USULI ko'rinadi — "bu master kalit bilan
    qilingan", ya'ni akkauntdan emas.  Bu kimligini aytmaydi, lekin
    "qidirish kerak bo'lgan joy" ni aytadi.
    """
    return admin.account_id if admin else "cloud-admin-key"


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
    plan: PlanTier = "biznes"
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


class DeviceHelloBody(BaseModel):
    """Qurilma o'zini tanishtiradi (hali hech qanday tokeni yo'q)."""

    fingerprint: str = Field(min_length=16, max_length=128, pattern=r"^[0-9a-f]+$")
    label: str = Field(default="", max_length=64)
    product_name: str = Field(default="Chaqimchi Windows", max_length=64)
    app_version: str = Field(default="", max_length=32)
    os_name: str = Field(default="", max_length=64)
    local_ip: str = Field(default="", max_length=45)


class DeviceClaimBody(BaseModel):
    connect_token: str = Field(min_length=20, max_length=128)


class DeviceHandoverBody(BaseModel):
    connect_token: str = Field(min_length=20, max_length=128)
    fingerprint: str = Field(min_length=16, max_length=128, pattern=r"^[0-9a-f]+$")


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
    #: Xom dict'lar — har biri endpoint ichida ALOHIDA tekshiriladi.
    #: `List[EdgeEvent]` bo'lsa yangi edge yuborgan bitta noma'lum event_type
    #: butun batchni 422 bilan yiqitar, 20 urinishdan keyin hamma event
    #: dead_letter'ga tushib yo'qolardi.  Endi buzuq event shunchaki
    #: `accepted` ro'yxatiga kirmaydi va yolg'iz o'zi dead_letter bo'ladi.
    events: List[Dict[str, Any]] = Field(max_length=500)


class MemberBody(BaseModel):
    telegram_id: str = Field(min_length=1, max_length=32)
    role: Literal["owner", "manager", "service_admin"] = "manager"
    display_name: Optional[str] = Field(default=None, max_length=120)


class OtpRequestBody(BaseModel):
    telegram_id: str = Field(min_length=1, max_length=32)
    #: Bir necha obyektga a'zo bo'lgan odam qaysi biriga kirishini
    #: ko'rsatadi.  Odatdagi oqimda kerak emas (obyekt kod tasdiqlangach
    #: tanlanadi), sinov rejimida esa token darhol beriladi va tanlov
    #: shu yerda bo'lishi kerak.
    site_id: Optional[str] = Field(default=None, min_length=1, max_length=64)


class OtpVerifyBody(BaseModel):
    telegram_id: str = Field(min_length=1, max_length=32)
    site_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    code: str = Field(min_length=6, max_length=6)


class LinkLoginBody(BaseModel):
    #: `?key=` havoladagi token — `secrets.token_urlsafe(32)` chiqishi.
    key: str = Field(min_length=20, max_length=128)


class TelegramWebAppAuthBody(BaseModel):
    """Telegram Mini App ochilganda beradigan imzolangan query satri."""

    init_data: str = Field(min_length=20, max_length=8192)


class VisionConsentBody(BaseModel):
    """Tashqi multimodal providerga yuboriladigan ma'lumot uchun site roziligi."""

    consented: bool
    audio_reply_enabled: bool = False


class VisionQueryBody(BaseModel):
    message: str = Field(min_length=2, max_length=4000)
    want_audio_reply: bool = False


class EdgeCameraHealth(BaseModel):
    """Bitta kameraning holati — panel yolg'on chiroq ko'rsatmasin.

    Bungacha cloudga faqat SON kelardi ("2 ta kamera ishlayapti"), mijoz
    paneli esa qaysi biri ekanini bilmasdi va yashil nuqtani preview
    rasmi ochilganidan chiqarardi — ya'ni o'chgan kamera ham eski rasmi
    bo'lsa yashil turardi.
    """

    camera_id: str = Field(min_length=1, max_length=40)
    connected: bool = False
    offline: bool = False
    #: Qayta ulanishlar soni — flapping (ulanib-uzilib turish) shundan
    #: ko'rinadi; bitta suratda "ishlayapti" bo'lsa ham.
    reconnects: int = Field(default=0, ge=0)
    codec: Optional[str] = Field(default=None, max_length=16)


class EdgeHeartbeatBody(BaseModel):
    #: Qurilma javobni shuncha soniyagacha KUTIB turishga tayyor.
    #:
    #: Nol (yoki eski qurilma) — darhol javob, ya'ni bugungi xatti-harakat.
    #: Noldan katta bo'lsa server jonli ko'rish so'ralishini kutadi va
    #: so'ralishi bilan DARHOL javob beradi.
    #:
    #: Nega kerak: bungacha panel "Jonli" tugmasini bosgach birinchi kadr
    #: 14-27 soniyada kelardi — eng katta ulush qurilmaning 20 soniyalik
    #: "salom" oralig'i edi.
    wait_sec: int = Field(default=0, ge=0, le=55)
    cameras_active: int = Field(default=0, ge=0, le=64)
    #: Kamera boshiga holat.  Eski qurilma yubormaydi — bo'sh ro'yxat
    #: "ma'lumot yo'q" degani, "hammasi o'chgan" degani emas.
    cameras: List[EdgeCameraHealth] = Field(default_factory=list, max_length=16)
    temperature_c: Optional[float] = Field(default=None, ge=-40, le=150)
    disk_free_bytes: int = Field(default=0, ge=0)
    cpu_percent: Optional[float] = Field(default=None, ge=0, le=100)
    ram_percent: Optional[float] = Field(default=None, ge=0, le=100)
    disk_percent: Optional[float] = Field(default=None, ge=0, le=100)
    fps: Optional[float] = Field(default=None, ge=0, le=1000)
    inference_latency_ms: Optional[float] = Field(default=None, ge=0, le=600_000)
    uptime_sec: Optional[float] = Field(default=None, ge=0)
    #: Qurilmaning o'z soati (ISO-8601, UTC).  Eski qurilma yubormaydi —
    #: `None` "farq noma'lum" degani, "farq yo'q" degani EMAS.
    #:
    #: Ish vaqti qoidalari qurilmaning lokal soatiga ishonadi
    #: (`retail/pipeline.py`), cloud esa faqat `occurred_at` ni tuzata
    #: oladi.  Ya'ni adashgan soat tungi ogohlantirishlarni jimgina
    #: buzadi va buni faqat shu maydon ko'rsatadi.
    device_clock: Optional[str] = Field(default=None, max_length=64)
    # Faqat qurilma haqiqiy NPU o'lchovini bersa to'ladi; aks holda admin
    # panel «— / yig'ilmoqda» ko'rsatadi va marketing raqam yasamaydi.
    npu_percent: Optional[float] = Field(default=None, ge=0, le=100)
    outbox_pending: int = Field(default=0, ge=0)
    outbox_bytes: int = Field(default=0, ge=0)
    outbox_critical_pending: int = Field(default=0, ge=0)
    #: Qurilma umidsiz deb tashlagan hodisalar.  Nolga teng bo'lmasa cloud
    #: biror narsani doimiy rad etyapti — bu kod xatosi, tarmoq emas.
    outbox_poisoned: int = Field(default=0, ge=0)
    #: Eng ko'p uchragan uch sabab ("2730× 413 Payload Too Large" kabi).
    #: Sonning o'zi nima buzilganini aytmasdi.
    outbox_poisoned_reasons: List[str] = Field(default_factory=list, max_length=3)
    #: Klip yozish hisoblagichlari — hodisa bor-u klip yo'q holatini
    #: cloudda ko'rish uchun.
    clips: Dict[str, int] = Field(default_factory=dict)
    #: Karnaydan ovoz berish natijasi: `played_file`, `played_tts`, `failed`.
    #:
    #: Model maydonisiz Pydantic uni JIMGINA tashlab yuboradi
    #: (`body.model_dump()` faqat e'lon qilingan maydonlarni beradi) —
    #: qurilma yuborsa ham bulut ko'rmasdi.  Ovozni biz eshitmaymiz,
    #: shuning uchun bu yagona qaytish aloqasi.
    speak: Dict[str, int] = Field(default_factory=dict)
    #: Zanjir necha marta o'zi yiqilib ko'tarilgan (72 soat mezoni).
    chain_restarts: int = Field(default=0, ge=0)
    #: Jimgina ishlamay qolishni aniqlash uchun (`plan_device_health_alerts`).
    #: `analysis_errors` `analyzed`ga nisbatan ko'p bo'lsa tahlil zanjiri
    #: buzilgan; `queue_errors` noldan katta bo'lsa hodisa saqlanmayapti.
    analyzed: int = Field(default=0, ge=0)
    analysis_errors: int = Field(default=0, ge=0)
    queue_errors: int = Field(default=0, ge=0)
    app_version: str = Field(default="unknown", max_length=64)
    model_version: Optional[str] = Field(default=None, max_length=128)
    product_name: str = Field(default="Sotqin", max_length=64)
    hardware_model: Optional[str] = Field(default=None, max_length=120)
    hardware_revision: Optional[str] = Field(default=None, max_length=32)
    serial_number: Optional[str] = Field(default=None, max_length=120)
    config_revision: int = Field(default=0, ge=0)


class LiveRequestBody(BaseModel):
    overlay: bool = False


class ConfigAckBody(BaseModel):
    revision: int = Field(ge=0)
    status: Literal["applied", "rejected"]
    error: Optional[str] = Field(default=None, max_length=500)


class EdgeDiagnosticsBody(BaseModel):
    """Windows support snapshot — RTSP paroli va device tokeni bo'lmaydi."""

    payload: Dict[str, Any] = Field(default_factory=dict)


#: Config ichida SERVER boshqaradigan bayroqlar.  Ular panel yuborgan
#: to'liq config bilan almashtirilganda YO'QOLMASLIGI kerak: masalan
#: `cameras_authoritative` o'chsa, qurilma "cloud hech qachon o'chirmaydi"
#: rejimiga qaytib, o'chirilgan kamera lokal keshdan qayta tirilardi.
_SERVER_MANAGED_CONFIG_KEYS = ("cameras_authoritative", "cloud_feature_revision")


def _preserve_server_config_flags(site_id: str, new_config: Dict[str, Any]) -> Dict[str, Any]:
    """Panelning to'liq config yozuviga server bayroqlarini qaytaradi."""
    try:
        current = get_event_store().get_site_config(site_id)["config"]
    except Exception:  # noqa: BLE001 — sayt endi yaratilgan bo'lishi mumkin
        return new_config
    for key in _SERVER_MANAGED_CONFIG_KEYS:
        if key in current and key not in new_config:
            new_config[key] = current[key]
    return new_config


class SiteConfigBody(BaseModel):
    camera_labels: Dict[str, str] = Field(default_factory=dict)
    # `camera_roles` OLIB TASHLANDI (2026-08-22).  Uni hech kim o'qimasdi:
    # qurilma kirish kamerasini CHIZIQDAN biladi
    # (`retail/service.py: entrance_cameras`).  Panelda esa bo'sh variant
    # yo'q edi, ya'ni birinchi saqlashda hamma kamera jimgina "kirish"
    # bo'lib qolardi.  Eski configdagi maydon Pydantic'da jimgina
    # tashlanadi (`extra="ignore"`), ya'ni 422 chiqmaydi.
    #
    # DIQQAT: `attendance_camera_roles` BOSHQA narsa va u HAQIQATAN
    # o'qiladi (`event_store.py`) — u qoladi.
    occupancy_limit: int = Field(default=20, ge=1, le=10000)
    loitering_sec: int = Field(default=60, ge=5, le=86400)
    queue_limit: int = Field(default=5, ge=1, le=1000)
    #: Kassa shuncha daqiqa bo'sh qolsa xabar beriladi (qurilmada
    #: soniyaga aylantiriladi).  Mijoz panelda daqiqada ko'radi —
    #: "300 soniya" degan sozlama do'kon egasiga hech narsa aytmaydi.
    checkout_idle_minutes: int = Field(default=5, ge=1, le=60)
    open_from: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    open_to: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    attendance_camera_ids: List[str] = Field(default_factory=list, max_length=2)
    attendance_camera_roles: Dict[str, Literal["arrival", "departure", "both"]] = Field(
        default_factory=dict
    )
    #: Telegramga qaysi hodisalar borsin: `critical` (standart),
    #: `warning` (kritik + ogohlantirish) yoki `all`.
    #:
    #: Ilgari bu kodda qotirilgan edi va hech qayerda aytilmasdi.
    #: 2026-08-26 da sinov do'konida 449 hodisadan 9 tasi botga bordi —
    #: ega "bot buzilgan" deb o'yladi.  Standart o'zgarmadi: mavjud
    #: obyektlarda xabar oqimi kutilmaganda kengayib ketmasin.
    telegram_min_severity: Literal["critical", "warning", "all"] = Field(
        default=notify_default_level
    )
    zones: List[SceneZoneSettings] = Field(default_factory=list, max_length=128)
    lines: List[SceneLineSettings] = Field(default_factory=list, max_length=32)
    #: Do'kon plani: har kamera uchun pol to'rtburchagi (4 burchak, 0..1)
    #: va plandagi o'rni.  Maydon aniq e'lon qilinmasa pydantic uni jimgina
    #: tashlab yuborardi va panel saqlagani yo'qolardi.
    floor_map: Dict[str, Any] = Field(default_factory=dict)


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
    #: Landing CTA ism va telefonni so'raydi; bu bog'lanishda to'g'ri
    #: murojaat qilish uchun yetarli. Eski forma va bot yo'li ismsiz
    #: arizani yuborsa ham moslik uchun qabul qilinadi.
    full_name: Optional[str] = Field(default=None, max_length=120)
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
        # Config profili qurilma turiga qarab tanlanadi (Windows vs Sotqin).
        "product_name": str(device.get("product_name") or ""),
    }


def require_active_owner(
    owner: OwnerPrincipal = Depends(require_owner),
    x_owner_site_id: Optional[str] = Header(None, alias="X-Owner-Site-Id"),
) -> OwnerPrincipal:
    selected_site = (x_owner_site_id or owner.site_id).strip()
    if owner.auth_kind == "password":
        account = get_store().account_by_id(owner.member_id)
        if (
            not account
            or account["role"] != "customer"
            or account["status"] != "active"
            or int(account["auth_version"]) != owner.auth_version
        ):
            raise HTTPException(401, "Mijoz sessioni bekor qilingan")
        allowed = {str(item["id"]): item for item in get_store().customer_sites(owner.member_id)}
        site = allowed.get(selected_site)
        if not site:
            raise HTTPException(403, "Bu filialga kirish ruxsati yo'q")
        return owner.model_copy(
            update={"site_id": selected_site, "role": str(site.get("access_role") or "owner")}
        )
    member = get_event_store().member_for_site(selected_site, owner.telegram_id)
    if not member:
        raise HTTPException(401, "Owner session bekor qilingan")
    # Token boshqa filialdagi a'zolikdan ochilgan bo'lishi mumkin. Tanlangan
    # filialda aynan shu Telegram foydalanuvchisining faol a'zoligi bo'lsa,
    # server principalni o'sha a'zolikka almashtiradi.
    return owner.model_copy(
        update={
            "member_id": str(member["id"]),
            "site_id": selected_site,
            "role": str(member["role"]),
        }
    )


def _owner_secret() -> str:
    secret = os.environ.get("CHAQIMCHI_OWNER_JWT_SECRET", "").strip()
    if len(secret) < 32:
        raise HTTPException(503, "CHAQIMCHI_OWNER_JWT_SECRET sozlanmagan")
    return secret


#: Kirish havolasining amal qilish muddati.
#:
#: Ilgari bu o'rinda `CHAQIMCHI_OTP_BYPASS_IDS` — Telegram ID bo'yicha
#: kodsiz kirish bor edi.  U olib tashlandi: Telegram ID sir emas, uni
#: bilgan har kim panelga kira olardi.  O'rnini `?key=<token>` havolasi
#: bosdi — token uzun va tasodifiy, admin uni istalgan payt bekor qiladi
#: (yangi havola yaratish eskisini o'chiradi).
LOGIN_LINK_TTL_DAYS = 30


def _pick_member(members: List[Dict[str, Any]], site_id: Optional[str]) -> Dict[str, Any]:
    """A'zolikdan qaysi obyektga kirishni tanlaydi.

    Ikkala kirish yo'li (kod bilan va havola bilan) shu funksiyani
    ishlatadi — mantiq ikki joyda takrorlansa, biri o'zgarib ikkinchisi
    boshqacha ishlab qolardi.
    """
    if site_id:
        member = next((item for item in members if item["site_id"] == site_id), None)
    elif len(members) == 1:
        member = members[0]
    else:
        raise HTTPException(409, "Bir nechta obyekt bor; site_id ko'rsating")
    if not member:
        raise HTTPException(401, "Owner akkaunti topilmadi")
    return member


def _owner_session(member: Dict[str, Any]) -> Dict[str, Any]:
    """Owner uchun session javobi."""
    try:
        token = issue_owner_token(member)
    except Exception as exc:
        raise HTTPException(503, "Owner session yaratilmadi") from exc
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 12 * 3600,
        "site_id": member["site_id"],
        "role": member["role"],
    }


TELEGRAM_WEBAPP_AUTH_MAX_AGE_SEC = 5 * 60


def _telegram_owner_token() -> str:
    return (
        os.environ.get("CHAQIMCHI_OWNER_TELEGRAM_TOKEN", "").strip()
        or os.environ.get("CHAQIMCHI_CLOUD_TELEGRAM_TOKEN", "").strip()
    )


def _telegram_webapp_user_id(init_data: str) -> str:
    """Telegram Mini App `initData` imzosini tekshirib, user ID qaytaradi.

    Frontenddagi `initDataUnsafe` hech qachon ishonchli emas: uni brauzerda
    istalgan odam o'zgartira oladi. Faqat Bot API ko'rsatgan HMAC tekshiruvi
    va qisqa `auth_date` oynasi owner session yaratishiga ruxsat beradi.
    """
    token = _telegram_owner_token()
    if not token:
        raise HTTPException(503, "Telegram Mini App hali sozlanmagan")
    try:
        values = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError as exc:
        raise HTTPException(401, "Telegram ma'lumoti noto'g'ri") from exc
    received_hash = values.pop("hash", "")
    user_json = values.get("user", "")
    try:
        auth_date = int(values.get("auth_date", "0"))
    except ValueError as exc:
        raise HTTPException(401, "Telegram ma'lumoti noto'g'ri") from exc
    if not received_hash or not user_json or auth_date <= 0:
        raise HTTPException(401, "Telegram ma'lumoti to'liq emas")
    if abs(time.time() - auth_date) > TELEGRAM_WEBAPP_AUTH_MAX_AGE_SEC:
        raise HTTPException(401, "Telegram sessiyasi eskirgan — botdan qayta oching")
    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(received_hash, expected_hash):
        raise HTTPException(401, "Telegram imzosi noto'g'ri")
    try:
        user = json.loads(user_json)
        telegram_id = str(int(user["id"]))
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "Telegram foydalanuvchisi noto'g'ri") from exc
    return telegram_id


def _attendance_enabled() -> bool:
    """Davomat — YOPIQ PILOT: production'da faqat ataylab yoqilganda.

    Ikki shart bor va ular boshqa-boshqa savolga javob beradi:

    1. **Litsenziya** (`MODELS_LICENSED_FOR_COMMERCIAL_USE`) — modelni
       tijoratda ishlatish mumkinmi.  Bu SHART, lekin yetarli emas.
       Ilgari bu yerda `CHAQIMCHI_FACE_MODEL_LICENSED` env bayrog'i
       turardi va uni noto'g'ri qo'yish tadqiqot modelini "tijoriy"
       qilib ko'rsatardi; 2026-08-21 dan modellar Apache-2.0 va javob
       KODDAN keladi.
    2. **Pilot ruxsati** (`CHAQIMCHI_ATTENDANCE_PILOT`) — shu server
       biometrika bilan ishlashga tayyormi.

    2026-08-25 auditi: bu yerda `or` turardi, ya'ni litsenziya rost
    bo'lgani uchun production'da davomat HAMMAGA ochiq edi — holbuki
    sayt uni "yozma rozilikli yopiq pilot" deb sotardi va serverimiz
    Yevropada (`docs/AUDIT_TAHLIL.md` KRITIK-2).  Endi `and`: kod ham
    sayt bilan bir narsani aytadi.

    Pilotdan tashqari muhitda (dev/test) ochiq qoladi — aks holda
    har bir test env qo'yishi kerak bo'lardi.
    """
    if not faces.MODELS_LICENSED_FOR_COMMERCIAL_USE:
        return False
    if os.environ.get("CHAQIMCHI_ENV", "development").strip().lower() != "production":
        return True
    return os.environ.get("CHAQIMCHI_ATTENDANCE_PILOT", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def require_attendance() -> None:
    if not _attendance_enabled():
        raise HTTPException(
            403,
            "Davomat sotuvga ochilmagan: faqat yozma rozilikli yopiq pilot yoki "
            "tasdiqlangan tijoriy Face ID modeli bilan ishlaydi",
        )


def require_biometric_access(owner: OwnerPrincipal) -> None:
    """Yuz kadri yoki xodim shabloniga tegadigan HAR BIR marshrut shu yerdan o'tsin.

    `require_active_owner` yetarli emas: `manager` ham faol owner hisoblanadi.
    Xodimga imzolatilgan rozilik shabloni («uchinchi shaxslarga berilmaydi»)
    bo'yicha yuzni faqat do'kon egasi va servis admini ko'ra oladi — menejer
    o'sha xodimning boshlig'i bo'lgani uchun aynan u chetda qolishi kerak.

    Alohida funksiya sifatida ataylab: yozish marshrutlari (rasm qo'shish,
    o'chirish) `require_owner_role` ni qo'lda chaqirardi, o'qish marshrutlari
    esa unutilgan edi va bitta himoyalangan snapshot yo'li parallel URL
    orqali chetlab o'tilardi.  Endi qidiriladigan yagona nom bor.
    """
    require_owner_role(owner, "owner", "service_admin")


class TelegramSendError(HTTPException):
    """Telegram API xatosi — javob matni bilan.

    Oddiy 502 yetarli emas edi: "chat not found" (a'zo botga /start
    bosmagan) va vaqtinchalik tarmoq xatosini farqlab bo'lmasdi, natijada
    mavjud bo'lmagan chatga har batch'da qayta urinilaverardi.
    """

    def __init__(self, telegram_status: int, body: str) -> None:
        super().__init__(502, "Telegram xabari yuborilmadi")
        self.telegram_status = telegram_status
        self.body = body

    @property
    def chat_not_found(self) -> bool:
        return self.telegram_status == 400 and "chat not found" in self.body.lower()


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
            raise TelegramSendError(response.status_code, response.text[:300])


async def _send_owner_voice(
    chat_id: str, voice: bytes, caption: str = "", mime: str = "audio/wav"
) -> None:
    """Agentning ixtiyoriy native audio javobi uchun Telegram audio yuboradi.

    `sendVoice` faqat OGG/OPUS qabul qiladi — Gemini esa odatda PCM/WAV
    qaytaradi.  Mos kelmagan formatga avval baribir `sendVoice` urilib,
    Telegram 400 berardi.  Endi format bo'yicha to'g'ri metod tanlanadi.
    """
    import httpx

    token = (os.environ.get("CHAQIMCHI_OWNER_TELEGRAM_TOKEN", "").strip() or os.environ.get("CHAQIMCHI_CLOUD_TELEGRAM_TOKEN", "").strip())
    if not token:
        raise HTTPException(503, "Owner Telegram bot tokeni sozlanmagan")
    lowered = mime.lower()
    if "ogg" in lowered or "opus" in lowered:
        method, field, filename = "sendVoice", "voice", "chaqimchi-agent.ogg"
    else:
        ext = "mp3" if "mpeg" in lowered else "m4a" if "mp4" in lowered else "wav"
        method, field, filename = "sendAudio", "audio", f"chaqimchi-agent.{ext}"
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{token}/{method}",
            data={"chat_id": chat_id, "caption": caption[:900]},
            files={field: (filename, voice, mime)},
        )
        if response.status_code >= 400:
            raise TelegramSendError(response.status_code, response.text[:300])


async def _answer_callback(callback_id: str, text: str, *, alert: bool = False) -> None:
    """Tugma bosilganini Telegramga tasdiqlaydi.

    Bu chaqiruv MAJBURIY: `answerCallbackQuery` yuborilmasa Telegram
    tugmada aylanuvchi soatni ~30 soniya ushlab turadi va foydalanuvchi
    hech narsa bo'lmadi deb o'ylab qayta-qayta bosadi.
    """
    import httpx

    token = (
        os.environ.get("CHAQIMCHI_OWNER_TELEGRAM_TOKEN", "").strip()
        or os.environ.get("CHAQIMCHI_CLOUD_TELEGRAM_TOKEN", "").strip()
    )
    if not token:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                json={
                    "callback_query_id": callback_id,
                    "text": text[:200],
                    "show_alert": alert,
                },
            )
    except Exception:  # noqa: BLE001 — tasdiq yuborilmasa ham ish davom etsin
        logger.warning("answerCallbackQuery yuborilmadi", exc_info=True)


async def _send_owner_photo(
    chat_id: str,
    photo: bytes,
    caption: str,
    *,
    reply_markup: Optional[Dict[str, Any]] = None,
) -> None:
    """Rasmli xabar (sendPhoto, multipart).

    Snapshotlar maxfiy (auth talab qiladi), shuning uchun URL bilan emas —
    baytlar to'g'ridan-to'g'ri yuboriladi.  Xato turlari matnli yuborish
    bilan bir xil: `chat not found` hisobi bitta joyda yuritiladi.
    """
    import httpx

    token = (
        os.environ.get("CHAQIMCHI_OWNER_TELEGRAM_TOKEN", "").strip()
        or os.environ.get("CHAQIMCHI_CLOUD_TELEGRAM_TOKEN", "").strip()
    )
    if not token:
        raise HTTPException(503, "Owner Telegram bot tokeni sozlanmagan")
    data: Dict[str, Any] = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data=data,
            files={"photo": ("hodisa.jpg", photo, "image/jpeg")},
        )
        if response.status_code >= 400:
            raise TelegramSendError(response.status_code, response.text[:300])


#: Bot menyusida ko'rinadigan buyruqlar — foydalanuvchi yozib o'tirmaydi,
#: "/" bosganda ro'yxatdan tanlaydi.
BOT_COMMANDS = [
    {"command": "hisobot", "description": "Bugungi hisobot"},
    {"command": "kamera", "description": "Kameralardan jonli rasm"},
    {"command": "panel", "description": "Mijoz paneliga kirish"},
    {"command": "yordam", "description": "Buyruqlar ro'yxati"},
]


async def _setup_bot_commands() -> None:
    """`setMyCommands` — start'da bir marta.

    Muvaffaqiyatsizlik kritik emas: menyu eski qolsa ham bot ishlayveradi,
    shuning uchun xato faqat log'ga yoziladi.
    """
    import httpx

    token = (
        os.environ.get("CHAQIMCHI_OWNER_TELEGRAM_TOKEN", "").strip()
        or os.environ.get("CHAQIMCHI_CLOUD_TELEGRAM_TOKEN", "").strip()
    )
    if not token:
        return
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/setMyCommands",
                json={"commands": BOT_COMMANDS},
            )
            app_url = urls.app_url().rstrip("/")
            menu_response = None
            if app_url:
                menu_response = await client.post(
                    f"https://api.telegram.org/bot{token}/setChatMenuButton",
                    json={
                        "menu_button": {
                            "type": "web_app",
                            "text": "Panel",
                            "web_app": {"url": f"{app_url}/owner"},
                        }
                    },
                )
        if response.status_code >= 400:
            logger.warning("setMyCommands xatosi: %s %s", response.status_code, response.text[:200])
        if menu_response is not None and menu_response.status_code >= 400:
            logger.warning(
                "setChatMenuButton xatosi: %s %s",
                menu_response.status_code,
                menu_response.text[:200],
            )
    except Exception:
        logger.warning("Bot buyruqlar menyusi o'rnatilmadi", exc_info=True)


#: Jonli ko'rish so'ralganda qurilmani uyg'otish uchun.
#:
#: Kutish bazani so'rab turmaydi: har obyekt uchun bitta `asyncio.Event`
#: va u faqat `request_live` chaqirilganda qo'yiladi.  Ya'ni yuz qurilma
#: kutib tursa ham bazaga bitta ham qo'shimcha so'rov ketmaydi.
#:
#: Xotirada — `ratelimit` bilan bir xil sabab: server bitta ishchi
#: jarayonda ishlaydi.  Ikkinchi jarayon paydo bo'lsa bu ham umumiy
#: signalga ko'chirilishi kerak.
_live_wakeups: Dict[str, asyncio.Event] = {}


def _live_wakeup(site_id: str) -> asyncio.Event:
    event = _live_wakeups.get(site_id)
    if event is None:
        event = asyncio.Event()
        _live_wakeups[site_id] = event
    return event


def _wake_live_watchers(site_id: str) -> None:
    """Jonli ko'rish so'raldi — kutayotgan qurilma darhol javob olsin."""
    _live_wakeup(site_id).set()


class _DurableAlertThrottle:
    """`cloud/notify.py` tormozi uchun bazaga tayangan implementatsiya.

    Xotiradagi standart tormoz jarayon bilan o'ladi — har deploy'dan keyin
    hamma sayt bir vaqtda "birinchi xabar"ini qayta olardi.
    """

    def allow(self, site_id: str, event_type: str, camera_id: str) -> bool:
        from cloud import notify

        return get_store().alert_throttle_allow(
            site_id,
            f"{event_type}:{camera_id}",
            window_sec=notify.DEFAULT_THROTTLE_SEC,
        )


_durable_throttle = _DurableAlertThrottle()


#: Shuncha ketma-ket "chat not found" dan keyin a'zoga yuborish to'xtaydi.
NOTIFY_FAILURE_LIMIT = 3

#: Bitta a'zo soatiga ko'pi bilan shuncha ogohlantirish oladi — sayt/kamera
#: soni qancha bo'lmasin.  Undan ko'pi baribir o'qilmaydi va botni
#: o'chirtirishga olib keladi.
OWNER_ALERTS_PER_HOUR = 10


async def _notify_site_members(
    site_id: str,
    text: str,
    *,
    photo: Optional[bytes] = None,
    reply_markup: Optional[Dict[str, Any]] = None,
) -> None:
    # Tarifda Telegram yo'q bo'lsa — yuborilmaydi (masalan starter).
    site = get_store().get_site(site_id)
    if site is not None:
        try:
            if not get_plan(str(site.get("plan"))).telegram_allowed:
                return
        except ValueError:
            pass
    store = get_event_store()
    for member in store.list_members(site_id):
        if int(member.get("notify_failures") or 0) >= NOTIFY_FAILURE_LIMIT:
            continue
        if not ratelimit.limiter().hit(
            "owner-alerts",
            f"{site_id}:{member['telegram_id']}",
            limit=OWNER_ALERTS_PER_HOUR,
            window_sec=3600,
        ):
            continue
        try:
            chat_id = str(member["telegram_id"])
            if photo is not None:
                await _send_owner_photo(chat_id, photo, text, reply_markup=reply_markup)
            else:
                await _send_owner_telegram(chat_id, text, reply_markup=reply_markup)
            if int(member.get("notify_failures") or 0):
                store.reset_notify_failures(site_id, str(member["id"]))
        except TelegramSendError as exc:
            if exc.chat_not_found:
                failures = store.record_notify_failure(site_id, str(member["id"]))
                if failures >= NOTIFY_FAILURE_LIMIT:
                    logger.warning(
                        "A'zo %s (site %s) botga /start bosmagan — unga yuborish to'xtatildi",
                        member["telegram_id"],
                        site_id,
                    )
        except Exception:
            # Event qabul qilinishi Telegramdagi vaqtinchalik xatoga bog'lanmasin.
            continue


#: Media OLINMAYDIGAN hodisalar — rasm saqlanmaydi.
#:
#: `loitering` (uzoq turish) kunlik holat, xavfsizlik hodisasi emas: mijoz
#: uni panelda raqam sifatida ko'radi va rasmga umuman qaramaydi.  Lekin u
#: hodisalarning ~93% ini tashkil qiladi.  Jonli o'lchov (2026-08-21, bitta
#: do'kon, 7.4 soat): 321 hodisadan 300 tasi loitering va 29 MB rasmning
#: 28.9 MB'i (99.6%) aynan shundan edi.  Bundan ham yomoni — o'sha do'kon
#: kunlik 500 talik snapshot chegarasining 302 tasini yeb qo'ygan, ya'ni
#: kechqurun HAQIQIY o'g'rilik hodisasiga rasm ilinmay qolardi.
#:
#: Hodisaning O'ZI saqlanadi — issiqlik xaritasi va "eng ko'p turilgan joy"
#: hisoboti unga tayanadi.
MEDIALESS_EVENTS = frozenset({"loitering"})


def _telegram_level(site_id: str) -> str:
    """Obyekt uchun tanlangan Telegram darajasi.

    Sozlama o'qilmasa standart (`critical`) qaytadi — xabar oqimi
    kutilmaganda kengayib ketgandan ko'ra tor qolgani yaxshi.
    """
    try:
        config = get_event_store().get_site_config(site_id)["config"]
    except Exception:  # noqa: BLE001 — xabar yuborish sozlama uchun to'xtamasin
        return notify_default_level
    return str(config.get("telegram_min_severity") or notify_default_level)

#: Snapshot batchdan KEYIN alohida yuklanadi — rasm yetib kelishini shu
#: muddatgacha kutamiz (2 soniyalik qadamlar bilan).
ALERT_SNAPSHOT_WAIT_SEC = 20


#: Shu hodisalarda ogohlantirishga «Ovoz bering» tugmasi qo'yiladi.
#:
#: Ro'yxat qisqa va ataylab: uchalasi ham "do'konda kimdir bor yoki
#: kameraga tegildi" degan ma'noda — aynan shunda do'kon karnayidan
#: eshitiladigan ovoz ish beradi.  Navbat, bo'sh javon yoki kamera
#: o'chishi bunga kirmaydi.
SPEAK_WORTHY_EVENTS = frozenset({"after_hours_presence", "camera_tampered", "zone_entered"})


#: Bir vaqtda shuncha ogohlantirish tayyorlanadi, ko'p emas.
#:
#: JONLI NOSOZLIKDAN keyin qo'shildi (2026-08-23).  Qurilma uzoq
#: uzilishdan keyin 3587 ta eski hodisani qayta yubordi; ularning katta
#: qismi ogohlantirishga arziydigan turda edi va har biri fon vazifasi
#: ochdi.  Har vazifa rasm kelishini kutib bazaga O'NTA sinxron so'rov
#: yuboradi — Postgres ulanishi hodisa halqasida ochiladi va u CPU
#: yemasdan halqani to'xtatadi.  Natijada butun bulut 20-45 soniyaga
#: javob bermay qoldi va Caddy hamma so'rovni uzdi.
#:
#: To'g'ri yechim — hamma baza chaqiruvini oqimga ko'chirish; bu esa
#: darhol qo'yiladigan to'siq: bir vaqtda nechta bo'lishidan qat'i
#: nazar, halqa nafas oladi.
#: Semafor HAR HALQA uchun alohida.  Modul darajasida bitta qilib
#: yaratilsa u birinchi ishlatgan halqaga bog'lanib qoladi va boshqa
#: halqada `RuntimeError` beradi (`_live_wakeups` bilan bir xil sabab).
ALERT_CONCURRENCY = 3
_alert_slots: Dict[Any, asyncio.Semaphore] = {}


def _alert_gate() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    gate = _alert_slots.get(loop)
    if gate is None:
        gate = asyncio.Semaphore(ALERT_CONCURRENCY)
        _alert_slots[loop] = gate
    return gate


async def _notify_alert(site_id: str, events: List[EdgeEvent]) -> None:
    """Batch ogohlantirishi — imkon bo'lsa hodisa RASMI bilan.

    Muammo: qurilma avval hodisalar batchini yuboradi, snapshot esa bir
    necha soniyadan keyin alohida PUT bilan keladi.  Shuning uchun rasm
    biroz kutiladi; kelmasa matnli xabar ketadi — kechikkanidan ko'ra
    rasmsiz yetib borgani yaxshi.
    """
    async with _alert_gate():
        await _notify_alert_once(site_id, events)


async def _notify_alert_once(site_id: str, events: List[EdgeEvent]) -> None:
    site = await asyncio.to_thread(get_store().get_site, site_id)
    site_name = str(site.get("name")) if site else None
    try:
        config = (await asyncio.to_thread(get_event_store().get_site_config, site_id))["config"]
        labels = {
            str(key): str(value) for key, value in (config.get("camera_labels") or {}).items()
        }
    except Exception:
        labels = {}

    text = notify_summarize(events, site_name=site_name, camera_labels=labels)

    photo: Optional[bytes] = None
    candidate = next(
        (e for e in events if e.has_snapshot and e.severity == "critical"), None
    ) or next((e for e in events if e.has_snapshot), None)
    if candidate is not None:
        attempts = max(1, ALERT_SNAPSHOT_WAIT_SEC // 2)
        for attempt in range(attempts):
            row = await asyncio.to_thread(
                get_event_store().event, site_id, candidate.event_id
            )
            key = (row or {}).get("snapshot_key")
            if key:
                try:
                    photo = await media_get(str(key))
                except Exception:
                    photo = None
                break
            if attempt + 1 < attempts:
                await asyncio.sleep(2)

    base = urls.app_url().rstrip("/")
    # «Ovoz bering» tugmasi FAQAT o'g'rilikka o'xshash hodisalarda.
    #
    # Har xabarga qo'yilsa u odatiy tugmaga aylanadi va haqiqiy xavf
    # paytida e'tiborni tortmay qoladi.  Navbat yoki bo'sh javon
    # xabariga karnay kerak emas.
    speak_phrase = "deter" if any(e.event_type in SPEAK_WORTHY_EVENTS for e in events) else ""
    markup = botfmt.alert_buttons(base, speak_phrase=speak_phrase)
    await _notify_site_members(site_id, text, photo=photo, reply_markup=markup)


#: Bitta obyekt media (snapshot + klip) uchun ko'pi bilan shuncha joy oladi.
#:
#: Muddat bo'yicha tozalashning o'zi diskni himoya qilmaydi: kunlik
#: limitlar (500 snapshot × 8 MB + 100 klip × 50 MB) bilan bitta shovqinli
#: sayt 30 kunda ~270 GB yig'ishi mumkin edi.  Kvotadan oshsa **eng eski**
#: media o'chadi (hodisa statistikasi qoladi) — edge'dagi `outbox.prune`
#: qanday ishlasa, cloud ham shunday.
SITE_MEDIA_MAX_BYTES_DEFAULT = 10 * 1024**3


#: Video kliplar shuncha kundan keyin o'chadi.
#:
#: Tarifdagi `retention_days` (30/90/365) — bu HODISA ARXIVI: statistika,
#: hisobot va rasm.  Uni qisqartirish mijoz to'lagan narsani olib qo'yish
#: bo'lardi.  Diskni esa deyarli butunlay kliplar yeydi (bittasi 50 MB
#: gacha, snapshot ~100 KB), shuning uchun sig'im aynan shu raqamga
#: bog'liq: 30 kunda bitta VPS ~10-13 do'konni ko'taradi, 7 kunda esa
#: ~50-80 tasini.  Klip hodisani tekshirish uchun kerak — bir haftadan
#: keyin uni deyarli hech kim ochmaydi.
CLIP_RETENTION_DAYS_DEFAULT = 7


def _clip_retention_days() -> int:
    raw = os.environ.get("CHAQIMCHI_CLIP_RETENTION_DAYS", "").strip()
    try:
        return max(1, int(raw)) if raw else CLIP_RETENTION_DAYS_DEFAULT
    except ValueError:
        logger.warning("CHAQIMCHI_CLIP_RETENTION_DAYS son emas — standart qiymat")
        return CLIP_RETENTION_DAYS_DEFAULT


def _site_media_quota_bytes() -> int:
    raw = os.environ.get("CHAQIMCHI_SITE_MEDIA_MAX_BYTES", "").strip()
    try:
        return int(raw) if raw else SITE_MEDIA_MAX_BYTES_DEFAULT
    except ValueError:
        logger.warning("CHAQIMCHI_SITE_MEDIA_MAX_BYTES son emas — standart qiymat")
        return SITE_MEDIA_MAX_BYTES_DEFAULT


#: Yig'indisi yozilmagan saytlar — monitoring va purge himoyasi uchun.
#: Kalit: site_id, qiymat: oxirgi xato vaqti (ISO).  Muvaffaqiyatda o'chadi.
_demography_rollup_errors: Dict[str, str] = {}


def _rollup_demography_for_site(site_id: str) -> bool:
    """Bitta sayt demografiyasini yig'adi; muvaffaqiyat bayrog'i qaytadi.

    Xato yutilmaydi emas — log qilinadi VA `_demography_rollup_errors` da
    belgilanadi: purge shu bayroqqa qarab o'sha saytning xom hodisalarini
    O'CHIRMAY turadi.  Avval xato faqat log bo'lib, keyin purge baribir
    o'chirib yuborardi — kun qaytarib bo'lmas darajada yo'qolardi.
    """
    try:
        get_event_store().rollup_pending_demography(site_id)
        get_event_store().purge_demography(site_id)
    except Exception:  # noqa: BLE001 — bitta sayt qolganini to'xtatmasin
        logger.exception("Demografiya yig'indisi yozilmadi: %s", site_id)
        _demography_rollup_errors[site_id] = datetime.now(timezone.utc).isoformat()
        return False
    _demography_rollup_errors.pop(site_id, None)
    return True


def _rollup_all_demography() -> int:
    """Barcha saytlar uchun yig'indi — startupda va soatlik loopda."""
    done = 0
    for site in get_store().list_sites():
        if _rollup_demography_for_site(str(site["id"])):
            done += 1
    return done


async def _demography_rollup_loop() -> None:
    """Yig'indi purge'dan MUSTAQIL yuradi.

    Avval u faqat 6 soatlik purge loop ichida chaqirilardi: server qulab
    qayta ko'tarilsa yoki loop kechiksa, yig'ilmagan kunlar purge'gacha
    yetib bormasligi mumkin edi.  Soatlik alohida loop arzon (ko'pi bilan
    sayt soni marta SELECT) va kunni his qilinarli tez yopadi.
    """
    while True:
        try:
            await asyncio.to_thread(_rollup_all_demography)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Demografiya rollup loop bajarilmadi")
        await asyncio.sleep(3_600)


def _purge_expired_events() -> int:
    """Har obyektni **o'z tarifi** muddati bo'yicha tozalaydi.

    Bungacha hammaga 30 kun qo'llanardi: 90 yoki 365 kunlik arxiv uchun
    to'lagan mijoz to'lagan narsasini olmasdi.
    """
    removed = 0
    quota = _site_media_quota_bytes()
    clip_retention = _clip_retention_days()
    for site in get_store().list_sites():
        try:
            retention = get_plan(str(site["plan"])).retention_days
        except ValueError:
            retention = 30
        site_id = str(site["id"])
        # Kunlik demografiya yig'indisi hodisalar O'CHIRILISHIDAN OLDIN
        # yozilishi SHART.  Yig'ilmagan saytning hodisalari o'chirilmaydi —
        # keyingi siklda yig'ish yana uriniladi.
        if not _rollup_demography_for_site(site_id):
            logger.warning(
                "Sayt %s: rollup xatosi — hodisalar purge qilinmadi (keyingi siklga qoladi)",
                site_id,
            )
            continue
        for key in get_event_store().purge_site(site_id, retention_days=retention):
            get_snapshot_store().delete(key)
            removed += 1
        # Kliplar hodisadan OLDIN va qisqaroq muddatda ketadi — disk
        # sig'imini aynan shular belgilaydi.
        for key in get_event_store().purge_clips_older_than(
            site_id, retention_days=clip_retention
        ):
            get_snapshot_store().delete(key)
            removed += 1
        for key in get_event_store().purge_site_media_over_quota(site_id, quota):
            get_snapshot_store().delete(key)
            removed += 1
        # Yuz kadrlari qisqa muddat yashaydi (maxfiylik va'dasi) — yozuvi
        # bilan birga o'chadi; ketgan xodimning namunalari ham shu yerda.
        face_retention = _face_retention_days()
        for key in get_event_store().purge_face_media(site_id, retention_days=face_retention):
            get_snapshot_store().delete(key)
            removed += 1
        for key in get_event_store().purge_inactive_employee_faces(site_id):
            get_snapshot_store().delete(key)
            removed += 1
        # Issiqlik to'rlari 90 kun yashaydi — mavsumiy taqqoslashga yetadi,
        # cheksiz o'sishga yo'l qo'ymaydi.
        removed += get_event_store().purge_heatmaps(site_id, retention_days=90)
    # Agent yozuvlari (savol, javob, kuzatuvlar, ovoz javoblari) ham
    # muddatli: UI "suhbat tarixiga saqlanmaydi" deb va'da beradi,
    # jadval esa avval umuman tozalanmasdi.
    for key in get_event_store().purge_vision_data(retention_days=90):
        get_snapshot_store().delete(key)
        removed += 1
    return removed


def _face_retention_days() -> int:
    try:
        return max(1, int(os.environ.get("CHAQIMCHI_FACE_RETENTION_DAYS", "14")))
    except ValueError:
        return 14


#: Chegara ogohlantirishi shu obyekt uchun oxirgi marta qachon ketgani.
#: Kuniga bir marta: 2026-08-26 da rad etishlar soni 6 315 ta edi va har
#: biri uchun xabar yuborilsa u ogohlantirish emas, spam bo'lardi.
_rate_limit_notified: Dict[str, float] = {}
RATE_LIMIT_NOTICE_EVERY_SEC = 86_400


async def _notify_rate_limited_sites() -> None:
    """Chegaraga urilgan obyektlar haqida platforma adminiga xabar.

    Nega kerak: 2026-08-26 da sinov do'koni 3 soat davomida rasmsiz
    ishladi.  Yagona izi `INFO` access logdagi 429 qatorlari edi —
    ERROR yo'q, panelda son yo'q, monitoring ham ko'rmasdi.  Nosozlikni
    MIJOZ aytdi, biz emas.  Bu halqa aynan shuni oldini oladi.
    """
    recipients = _lead_recipient_ids()
    if not recipients:
        return
    now = time.monotonic()
    for site in await asyncio.to_thread(get_store().list_sites):
        site_id = str(site.get("site_id") or site.get("id") or "")
        if not site_id:
            continue
        rejected = ratelimit.limiter().rejections(site_id)
        # Faqat MEDIA chegaralari: mijoz uchun ko'rinadigan yo'qotish shu.
        media = sum(rejected.get(key, 0) for key in ("snapshots", "face-snapshots", "clips"))
        if not media:
            continue
        last = _rate_limit_notified.get(site_id)
        if last is not None and now - last < RATE_LIMIT_NOTICE_EVERY_SEC:
            continue
        _rate_limit_notified[site_id] = now
        text = (
            f"⚠️ {site.get('name') or site_id}: kunlik media chegarasi urildi.\n"
            f"Saqlanmagan: {media} ta.\n"
            f"Tafsilot: {rejected}\n"
            "Mijoz panelda rasmsiz hodisa ko'radi."
        )
        for chat_id in recipients:
            try:
                await get_alerts().sender.send_to(chat_id, text)
            except Exception as exc:  # noqa: BLE001 — xabar ketmasa ham halqa yursin
                logger.warning("Chegara ogohlantirishi %s ga yetmadi: %s", chat_id, exc)


#: Halqa shu qadam bilan aylanadi; tozalash har 12-qadamda (6 soat).
#: Ikki ish ikki tezlikda: tozalash — og'ir baza skani, chegara nazorati
#: esa arzon va tez bo'lishi kerak (chegara kun o'rtasida uriladi va biz
#: buni kun oxirida emas, o'sha payt bilishimiz kerak).
_MAINTENANCE_STEP_SEC = 1_800
_PURGE_EVERY_STEPS = 12


async def _maintenance_loop() -> None:
    step = 0
    while True:
        try:
            if step % _PURGE_EVERY_STEPS == 0:
                await asyncio.to_thread(_purge_expired_events)
            await _notify_rate_limited_sites()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Cloud maintenance bajarilmadi")
        step += 1
        await asyncio.sleep(_MAINTENANCE_STEP_SEC)


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
        # Tizim to'xtaganini do'kon egasi ham bilishi kerak: `camera_offline`
        # ni qurilma yuboradi, kompyuter o'chganda esa uni yuboradigan hech
        # kim qolmaydi.  `_notify_site_members` tarif, chegara va "botga
        # /start bosmagan a'zo" mantiqini o'zi hal qiladi.
        _alerts = AlertService(store, owner_notify=_notify_site_members)
    return _alerts


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _digest, _digest_task, _maintenance_task, _lead_notification_task
    global _vision_worker_stop, _vision_worker_task
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
        # Sinov eshiklari production'da qat'iyan taqiqlanadi.  Bular env
        # o'zgaruvchisi bo'lgani uchun "unutib qoldirish" eng real xavf:
        # OTP_TEST_CODE hamma mijozning kodini bitta doimiy qiymatga
        # aylantiradi, BYPASS_IDS esa eski kodsiz-kirish ro'yxati (kod
        # olib tashlangan, lekin o'zgaruvchi qolib ketgan bo'lsa ham
        # server yonmasin — sozlama tozalanishi shart).
        if os.environ.get("CHAQIMCHI_OTP_TEST_CODE", "").strip():
            errors.append("CHAQIMCHI_OTP_TEST_CODE production'da taqiqlanadi")
        if os.environ.get("CHAQIMCHI_OTP_BYPASS_IDS", "").strip():
            errors.append(
                "CHAQIMCHI_OTP_BYPASS_IDS olib tashlangan — o'rniga "
                "admin panel orqali kirish havolasi (login-link) ishlating"
            )
        # Gemini kaliti bor-u model nomi yo'q — har agent jobi yiqilib
        # kunlik kvotani yeydi.  Deploy'da darhol ushlanadi.
        if (
            os.environ.get("CHAQIMCHI_GEMINI_API_KEY", "").strip()
            and not os.environ.get("CHAQIMCHI_GEMINI_VISION_MODEL", "").strip()
        ):
            errors.append(
                "CHAQIMCHI_GEMINI_API_KEY berilgan, lekin "
                "CHAQIMCHI_GEMINI_VISION_MODEL yo'q — Vision Agent ishlamaydi"
            )
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
    _digest = DailyDigestService(
        get_event_store(),
        get_store().list_sites,
        _send_owner_telegram,
        panel_url=urls.app_url(),
    )
    _digest_task = asyncio.create_task(_digest.run())
    _maintenance_task = asyncio.create_task(_maintenance_loop())
    # Startupda darhol bir marta: server qulab qayta ko'tarilganda
    # yig'ilmagan kunlar 6 soatlik purge'ni kutmasin.
    _demography_rollup_task = asyncio.create_task(_demography_rollup_loop())
    _lead_notification_task = asyncio.create_task(_lead_notification_loop())
    _bot_commands_task = asyncio.create_task(_setup_bot_commands())
    # Agent joblari DB'da navbatda turadi; Gemini yoki worker qayta yonsa
    # savol yo'qolmaydi. Birinchi relizda shu cloud process ichidagi alohida
    # coroutine ishlaydi, keyingi horizontal worker ham ayni DB claim
    # kontraktidan foydalana oladi.
    if os.environ.get("CHAQIMCHI_VISION_WORKER_IN_APP", "1").lower() in {"1", "true", "yes"}:
        _vision_worker_stop = asyncio.Event()
        _vision_worker_task = asyncio.create_task(
            vision_agent.worker_loop(
                get_event_store(),
                cameras_for_site=get_store().list_cameras,
                media_get=media_get,
                media_delete=media_delete,
                media_put=vision_media_put,
                stop=_vision_worker_stop,
            )
        )
    try:
        yield
    finally:
        if _digest_task is not None:
            _digest_task.cancel()
            _digest_task = None
        if _maintenance_task is not None:
            _maintenance_task.cancel()
            _maintenance_task = None
        _demography_rollup_task.cancel()
        if _lead_notification_task is not None:
            _lead_notification_task.cancel()
            _lead_notification_task = None
        if _vision_worker_stop is not None:
            _vision_worker_stop.set()
        if _vision_worker_task is not None:
            _vision_worker_task.cancel()
            _vision_worker_task = None
        _vision_worker_stop = None
        _bot_commands_task.cancel()
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
    """Tiriklik tekshiruvi — jarayon javob beryaptimi.

    ATAYLAB yengil va ATAYLAB doim 200.  Buni Docker `HEALTHCHECK` chaqiradi,
    Caddy esa `depends_on: service_healthy` bilan kutadi: bu yerga bazani
    qo'shsak, Postgres bir soniyaga uzilgan paytda konteyner "unhealthy"
    bo'lib, deploy paytida Caddy umuman ko'tarilmay qolardi.

    Bog'liqliklar `/health/deep` da tekshiriladi — UptimeRobot o'shanga
    qaratilishi kerak.
    """
    return {"ok": True, "service": "chaqimchi-cloud"}


#: Diskda shundan kam joy qolsa `/health/deep` ogohlantiradi.  Klip va
#: rasm oqimi to'xtaganda buni oldindan bilish kerak: disk to'lgach
#: SQLite yozuvi ham yiqiladi, ya'ni butun bulut o'ladi.
HEALTH_MIN_FREE_GB = 5.0


def _probe(name: str, check: Any) -> Dict[str, Any]:
    """Bitta bog'liqlikni tekshiradi va xatoni yutmasdan qaytaradi."""
    started = time.monotonic()
    try:
        detail = check()
    except Exception as exc:  # noqa: BLE001 — sabab javobda ko'rinishi kerak
        return {
            "name": name,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}"[:200],
            "ms": round((time.monotonic() - started) * 1000, 1),
        }
    out = {"name": name, "ok": True, "ms": round((time.monotonic() - started) * 1000, 1)}
    if isinstance(detail, dict):
        out.update(detail)
    return out


def _health_checks() -> List[Dict[str, Any]]:
    def control_db() -> Dict[str, Any]:
        conn = get_store()._connect()
        try:
            sites = conn.execute("SELECT COUNT(*) AS n FROM sites").fetchone()["n"]
        finally:
            conn.close()
        return {"sites": int(sites)}

    def event_db() -> Dict[str, Any]:
        store = get_event_store()
        with store._connect() as conn:
            conn.execute(store._sql("SELECT 1"))
        return {"engine": "postgres" if store.postgres else "sqlite"}

    def media() -> Dict[str, Any]:
        store = get_snapshot_store()
        client = getattr(store, "client", None)
        if client is None:
            # Lokal papka — MinIO'siz ishlash yo'li (test va Sotqin).
            return {"engine": "local"}
        if not client.bucket_exists(store.bucket):
            raise RuntimeError(f"MinIO bucket topilmadi: {store.bucket}")
        return {"engine": "minio", "bucket": store.bucket}

    def disk() -> Dict[str, Any]:
        usage = shutil.disk_usage(get_store().db_path.parent)
        free_gb = round(usage.free / 1024**3, 1)
        if free_gb < HEALTH_MIN_FREE_GB:
            raise RuntimeError(f"Diskda atigi {free_gb} GB qoldi")
        return {"free_gb": free_gb, "used_percent": round(usage.used / usage.total * 100, 1)}

    return [
        _probe("control_db", control_db),
        _probe("event_db", event_db),
        _probe("media", media),
        _probe("disk", disk),
    ]


#: Anonim javobda qoladigan yagona maydonlar.
#:
#: Qolgani (mijozlar soni, bucket nomi, disk hajmi, versiya, xato matni)
#: FAQAT admin kaliti bilan ko'rinadi.  2026-08-25 auditi: bu endpoint
#: ochiq turardi va `{"sites": 4}` qaytarardi — ya'ni istalgan odam
#: bitta `curl` bilan mijozlar sonimizni bilib olardi.  Xato matni ham
#: sizdirardi ("MinIO bucket topilmadi: chaqimchi-snapshots").
_PUBLIC_HEALTH_FIELDS = ("name", "ok", "ms")


def _is_admin_request(
    authorization: Optional[str], x_cloud_admin_key: Optional[str]
) -> bool:
    """`require_admin` bilan bir xil qoida, lekin XATO QAYTARMAYDI.

    `/health/deep` monitoring uchun ochiq qolishi kerak (UptimeRobot 503
    ni ko'radi), shuning uchun bu yerda "kirish rad etildi" emas,
    "kamroq ma'lumot" javobi kerak.
    """
    try:
        require_admin(authorization, x_cloud_admin_key)
    except HTTPException:
        return False
    return True


@app.get("/health/deep")
async def health_deep(
    response: Response,
    authorization: Optional[str] = Header(None),
    x_cloud_admin_key: Optional[str] = Header(None, alias="X-Cloud-Admin-Key"),
) -> Dict[str, Any]:
    """Bog'liqliklar bilan birga tekshiruv — nosozlikda 503.

    Bungacha `/health` bazani ham, MinIO'ni ham, diskni ham tekshirmasdan
    `{"ok": true}` qaytarardi: Postgres o'lgan bulut ham "sog'lom" bo'lib
    ko'rinardi va tashqi monitoring nosozlikni umuman ko'rmasdi.

    Tekshiruvlar bloklovchi (SQLite, MinIO, disk), shuning uchun ular
    alohida oqimda bajariladi — aks holda bu endpoint butun serverni
    to'xtatib turardi.

    Javob **kim so'rayotganiga qarab** qisqaradi: monitoringga qaysi
    tekshiruv yiqilgani va 503 yetadi, raqamlar esa admin kalitini
    talab qiladi (`_PUBLIC_HEALTH_FIELDS`).
    """
    checks = await asyncio.to_thread(_health_checks)
    ok = all(item["ok"] for item in checks)
    if not ok:
        response.status_code = 503
    if _is_admin_request(authorization, x_cloud_admin_key):
        return {
            "ok": ok,
            "service": "chaqimchi-cloud",
            "version": __version__,
            "checks": checks,
            # Chegara tufayli rad etilgan so'rovlar — bucket bo'yicha.
            #
            # 2026-08-26 da bu raqam BO'LMAGANI uchun 6 315 ta rasm 3 soat
            # davomida jimgina rad etildi: ERROR log yo'q, panelda son yo'q,
            # `/health` esa "hammasi joyida" derdi.  Nosozlikni mijoz
            # aytganda bildik.  Bo'sh lug'at — hech narsa rad etilmagan.
            "rate_limited": ratelimit.limiter().rejections(),
        }
    return {
        "ok": ok,
        "service": "chaqimchi-cloud",
        "checks": [
            {key: item[key] for key in _PUBLIC_HEALTH_FIELDS if key in item}
            for item in checks
        ],
    }


def _static_page(name: str) -> FileResponse:
    page = STATIC_DIR / name
    if not page.is_file():
        raise HTTPException(404, "Sahifa topilmadi")
    return FileResponse(page)


#: Subdomen prefikslari → bo'lim.  Domenga bog'lanmagan (prefiks bo'yicha):
#: chaqimchi.uz ham, test.example ham bir xil ishlaydi.
_HOST_SECTIONS = ("app", "partner", "admin", "dl", "docs", "api")


def _host_section(request: Request) -> str:
    """So'rov qaysi subdomenga kelgan (apex — landing).

    `request.base_url` proxy headerlarini hurmat qiladi (uvicorn
    `--proxy-headers` bilan ishlaydi) — Caddy ortida ham to'g'ri host
    ko'rinadi.
    """
    host = (request.base_url.hostname or "").lower()
    for prefix in _HOST_SECTIONS:
        if host.startswith(prefix + "."):
            return prefix
    return "apex"


def _render_landing(request: Request) -> HTMLResponse:
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
        # Subdomen sozlanmagan bo'lsa eski bitta-domen yo'llari ishlaydi.
        .replace("__APP_URL__", urls.app_url() or origin)
        .replace("__PARTNER_URL__", urls.partner_url() or origin)
        .replace("__DL_URL__", urls.dl_url() or origin)
    )
    return HTMLResponse(content)


@app.get("/", include_in_schema=False)
async def public_site(request: Request) -> Any:
    """Bosh sahifa — host'ga qarab: subdomenlar o'z bo'limini ochadi.

    app.chaqimchi.uz — mijoz paneli, partner. — montajchi, admin. — admin,
    dl. — yuklab olish, docs. — hujjatlar, apex — landing.  Bitta ilova,
    bo'linish host darajasida: panellar API'ni nisbiy yo'ldan chaqiradi,
    ya'ni CORS umuman kerak emas.
    """
    section = _host_section(request)
    if section == "app":
        return _render_owner()
    if section == "partner":
        return _static_page("installer.html")
    if section == "admin":
        return _static_page("v2/admin.html" if _ui_v2_admin_enabled() else "admin.html")
    if section == "dl":
        return _static_page("dl.html")
    if section == "docs":
        return _docs_page("index")
    return _render_landing(request)


#: Chiziq/zona muharriri **ikkala** panelga kerak: cloud'dagi o'rnatuvchi
#: paneliga va mijozning lokal sozlash ustasiga.  Ikki nusxa saqlash bittasini
#: jimgina eskirtirardi, shuning uchun manba bitta — `chaqimchi_ai/local/static/`.
#: U yerda turgani ham ataylab: Windows o'rnatuvchisi `cloud/` ni ko'chirmaydi.
ZONE_EDITOR = Path(__file__).resolve().parents[1] / "chaqimchi_ai" / "local" / "static"


@app.get("/vendor/zone-editor.js", include_in_schema=False)
async def zone_editor_script() -> FileResponse:
    script = ZONE_EDITOR / "zone-editor.js"
    if not script.is_file():
        raise HTTPException(404, "Muharrir topilmadi")
    return FileResponse(script, media_type="application/javascript")


@app.get("/vendor/pw-eye.js", include_in_schema=False)
async def password_eye_script() -> FileResponse:
    """Parol maydonlariga "ko'z" tugmasi — manba zone-editor kabi bitta."""
    script = ZONE_EDITOR / "pw-eye.js"
    if not script.is_file():
        raise HTTPException(404, "Skript topilmadi")
    return FileResponse(script, media_type="application/javascript")


@app.get("/connect", include_in_schema=False)
async def connect_page() -> FileResponse:
    return _static_page("connect.html")


@app.get("/install", include_in_schema=False)
async def install_page() -> FileResponse:
    """Mijozning mustaqil o'rnatish yo'riqnomasi."""
    return _static_page("install.html")


@app.get("/installer", include_in_schema=False)
async def installer_page(request: Request) -> Any:
    """O'rnatuvchi ro'yxatdan o'tishi, vazifalari va pairing paneli."""
    redirect = _apex_redirect(request, "CHAQIMCHI_PARTNER_URL")
    if redirect is not None:
        return redirect
    return _static_page("installer.html")


@app.get("/installer-guide", include_in_schema=False)
async def installer_guide_page() -> FileResponse:
    """Bo'sh mini-kompyuterdan mijozga topshirishgacha rasmli yo'riqnoma."""
    return _static_page("installer-guide.html")


# Eslatma: bu yerda `/onboarding` sahifasi va `/api/v1/agent/discovery/scan`
# endpointi turardi.  Ikkalasi ham o'chirildi:
#
# * sahifa maket edi — haqiqiy web-kamera ustiga oldindan yozilgan "Mijoz #1
#   [98%]" ramkalari chizilardi, pairing kod HTML ichida qotirilgan edi va
#   tanlangan kamera hech qayerga saqlanmasdi;
# * endpoint mavjud bo'lmagan `discover_network_cameras` funksiyasini
#   chaqirardi, `except` esa `ImportError` ni yutib doim bo'sh ro'yxat
#   qaytarardi — ya'ni "kameralarni avtomatik topadi" va'dasi hech qachon
#   ishlamagan, test esa yashil turgan.
#
# Ikkalasining o'rnini mijoz kompyuterida ishlaydigan haqiqiy sozlash ustasi
# egalladi: `chaqimchi_ai/local/app.py`.  Qidiruv u yerda xatoni yutmaydi.


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


#: Nashr qilingan reliz fayllari: arxiv va uning imzolangan manifesti.
#:
#: Ataylab **ochiq** (autentifikatsiyasiz): `bootstrap_sotqin.sh` arxivni
#: qurilmada hech qanday hisob ma'lumotisiz oladi — pairing hali bo'lmagan.
#: Manifestda sir yo'q, xavfsizlik esa kirish nazoratidan emas, **Ed25519
#: imzosidan** keladi: buzilgan cloud istalgan faylni bera oladi, lekin
#: imzo yasay olmaydi va qurilma uni rad etadi.
RELEASE_FILE_PATTERN = re.compile(
    r"^chaqimchi-(?:sotqin|lite|windows)-[A-Za-z0-9.\-_]+\.(?:tar\.gz|exe|json)$"
)

RELEASE_MEDIA_TYPES = {
    ".gz": "application/gzip",
    ".json": "application/json",
    ".exe": "application/vnd.microsoft.portable-executable",
}


@app.get("/releases/{release_name}", include_in_schema=False)
async def sotqin_release(release_name: str) -> FileResponse:
    """Nashr qilingan reliz arxivi yoki manifesti."""
    if Path(release_name).name != release_name or not RELEASE_FILE_PATTERN.match(release_name):
        raise HTTPException(404, "Release topilmadi")
    archive = BASE_DIR / "releases" / release_name
    if not archive.is_file():
        raise HTTPException(404, "Release topilmadi")
    media_type = RELEASE_MEDIA_TYPES[Path(release_name).suffix]
    # Manifest keshlanmaydi: bir xil versiya qayta imzolanishi mumkin
    # (kalit almashtirilganda), arxiv esa o'zgarmas.
    cache = (
        "public, max-age=31536000, immutable"
        if release_name.endswith((".tar.gz", ".exe"))
        else "no-cache"
    )
    return FileResponse(
        archive,
        media_type=media_type,
        filename=release_name,
        headers={"Cache-Control": cache},
    )


DOCS_DIR = STATIC_DIR / "docs"


def _docs_page(name: str) -> FileResponse:
    """docs.chaqimchi.uz sahifasi (statik, SEO uchun ochiq)."""
    if not re.fullmatch(r"[a-z0-9-]{1,60}", name):
        raise HTTPException(404, "Sahifa topilmadi")
    page = DOCS_DIR / f"{name}.html"
    if not page.is_file():
        raise HTTPException(404, "Sahifa topilmadi")
    return FileResponse(page)


@app.get("/docs-static/{name}", include_in_schema=False)
async def docs_named_page(name: str, request: Request) -> Any:
    """Hujjat sahifasi (kanonik yo'l — istalgan hostda ishlaydi)."""
    return _docs_page(name)


#: Hujjat sahifalari qisqa yo'llardan ham ochiladi (docs.chaqimchi.uz/nvr-hikvision).
#: Ro'yxat qat'iy — /{name} umumiy marshruti boshqa yo'llarni yutib yubormasin.
DOCS_PAGES = (
    "ornatish-windows",
    "nvr-hikvision",
    "nvr-dahua",
    "nvr-uniview",
    "muammolar",
    "xavfsizlik",
)


def _make_docs_route(page_name: str):
    async def _route() -> FileResponse:
        return _docs_page(page_name)

    return _route


for _docs_name in DOCS_PAGES:
    app.add_api_route(
        f"/{_docs_name}", _make_docs_route(_docs_name), methods=["GET"], include_in_schema=False
    )


@app.get("/docs-static/assets/docs.css", include_in_schema=False)
async def docs_css() -> FileResponse:
    style = DOCS_DIR / "docs.css"
    if not style.is_file():
        raise HTTPException(404, "Topilmadi")
    return FileResponse(style, media_type="text/css")


@app.get("/api/v1/public/urls")
async def public_platform_urls(request: Request) -> Dict[str, str]:
    """Platforma bo'limlari manzillari — sahifalar buyruq/havolalarni
    to'g'ri subdomen bilan qursin (`location.origin` bo'lim hostini
    ko'rsatadi, u esa yuklab olish yoki API uchun noto'g'ri bo'lardi)."""
    fallback = str(request.base_url).rstrip("/")
    return {
        "apex": urls.public_url() or fallback,
        "app": urls.app_url() or fallback,
        "api": urls.api_url() or fallback,
        "dl": urls.dl_url() or fallback,
        "partner": urls.partner_url() or fallback,
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    """Brauzer sahifada `<link rel="icon">` bo'lsa ham ba'zan ildizdan
    so'raydi.  Ilgari bu har safar 404 berardi (olti soatda 44 marta)."""
    icon = STATIC_DIR / "favicon.ico"
    if not icon.is_file():
        raise HTTPException(404, "Favicon topilmadi")
    return FileResponse(icon, media_type="image/x-icon")


@app.get("/owner-sw.js", include_in_schema=False)
async def owner_service_worker() -> FileResponse:
    worker = STATIC_DIR / "v2/owner-sw.js"
    if not worker.is_file():
        raise HTTPException(404, "Service worker topilmadi")
    return FileResponse(
        worker,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt(request: Request) -> Response:
    """Host bo'yicha: landing va docs indekslanadi, panellar/API — yo'q."""
    section = _host_section(request)
    if section in ("apex", "docs"):
        lines = ["User-agent: *", "Allow: /"]
        base = urls.public_url()
        if section == "apex" and base:
            lines.append(f"Sitemap: {base}/sitemap.xml")
    else:
        lines = ["User-agent: *", "Disallow: /"]
    return Response("\n".join(lines) + "\n", media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml(request: Request) -> Response:
    if _host_section(request) != "apex":
        raise HTTPException(404, "Topilmadi")
    base = urls.public_url() or str(request.base_url).rstrip("/")
    pages = [
        "/", "/edu", "/install", "/maxfiylik", "/oferta", "/hamkorlik",
        "/aloqa", "/rozilik-shabloni", "/kuzatuv-eslatmasi",
    ]
    body = "".join(f"<url><loc>{base}{page}</loc></url>" for page in pages)
    return Response(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + body + "</urlset>",
        media_type="application/xml",
    )


@app.get("/privacy", include_in_schema=False)
@app.get("/maxfiylik", include_in_schema=False)
async def privacy_page() -> FileResponse:
    return _static_page("privacy.html")


@app.get("/tariflar", include_in_schema=False)
async def tariffs_redirect() -> RedirectResponse:
    """Narx bitta joyda (landing #narx) — alohida sahifa saqlanmaydi."""
    return RedirectResponse("/#narx", status_code=301)


def _render_public(name: str, request: Request) -> HTMLResponse:
    """Placeholder'li ochiq sahifa: bo'lim manzillari va bot havolasi qo'yiladi."""
    page = STATIC_DIR / name
    if not page.is_file():
        raise HTTPException(404, "Sahifa topilmadi")
    origin = str(request.base_url).rstrip("/")
    bot_username = os.environ.get("CHAQIMCHI_TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    register_url = (
        f"https://t.me/{bot_username}?start=register"
        if re.fullmatch(r"[A-Za-z0-9_]{5,32}", bot_username)
        else f"{urls.public_url() or origin}/#pilot"
    )
    content = (
        page.read_text(encoding="utf-8")
        .replace("__TELEGRAM_REGISTER_URL__", register_url)
        .replace("__APP_URL__", urls.app_url() or origin)
        .replace("__PARTNER_URL__", urls.partner_url() or origin)
        .replace("__DL_URL__", urls.dl_url() or origin)
    )
    return HTMLResponse(content)


@app.get("/rozilik-shabloni", include_in_schema=False)
async def consent_template_page() -> FileResponse:
    """Xodim biometrik roziligi shabloni — montajchi chop etib olib boradi."""
    return _static_page("rozilik-shabloni.html")


@app.get("/oferta", include_in_schema=False)
async def public_offer_page() -> FileResponse:
    """Ommaviy oferta — to'lov qabul qilish uchun huquqiy asos.

    2026-08-25 gacha bu sahifa umuman yo'q edi, holbuki sayt
    hisob-faktura beryapti (`docs/AUDIT_TAHLIL.md` KRITIK-3).  Bahsli
    holatda xizmat doirasi, javobgarlik chegarasi va pul qaytarish
    tartibini ko'rsatadigan hujjat bo'lmasdi.
    """
    return _static_page("oferta.html")


@app.get("/hamkorlik", include_in_schema=False)
async def partnership_page(request: Request) -> HTMLResponse:
    return _render_public("hamkorlik.html", request)


@app.get("/aloqa", include_in_schema=False)
async def contact_page(request: Request) -> HTMLResponse:
    return _render_public("aloqa.html", request)


@app.get("/kuzatuv-eslatmasi", include_in_schema=False)
async def surveillance_notice_page() -> FileResponse:
    """Do'kon eshigiga osiladigan eslatma.

    `rozilik-shabloni.html` ga qo'shilmadi: u IMZOLANADIGAN xodim
    biometrikasi hujjati.  Mijoz demografiyasi esa anonim va rozilik
    talab qilmaydi — uni o'sha hujjatga kiritish mijozdan imzo talab
    qilinadi degan noto'g'ri ma'no berardi.
    """
    return _static_page("kuzatuv-eslatmasi.html")


@app.get("/edu", include_in_schema=False)
async def edu_page(request: Request) -> HTMLResponse:
    """Chaqimchi Edu — ta'lim muassasalari uchun alohida sahifa.

    Bosh sahifa do'kon tilida gapiradi ("mijozlar oqimi", "kassa
    navbati") va maktab direktoriga u begona.  Shuning uchun alohida
    sahifa: umumiy kirish, ta'limga xos funksiyalar va o'z
    kalkulyatori.
    """
    return _render_public("edu.html", request)


@app.get("/status", include_in_schema=False)
async def status_page() -> FileResponse:
    return _static_page("status.html")


@app.get("/admin", include_in_schema=False)
async def admin_panel(request: Request) -> Any:
    """Admin paneli. Kirish admin kalit bilan — brauzerda so‘raladi va API ga yuboriladi."""
    redirect = _apex_redirect(request, "CHAQIMCHI_ADMIN_URL")
    if redirect is not None:
        return redirect
    page = STATIC_DIR / ("v2/admin.html" if _ui_v2_admin_enabled() else "admin.html")
    if not page.is_file():
        raise HTTPException(404, "Admin paneli topilmadi")
    return FileResponse(page)


def _ui_v2_enabled() -> bool:
    return os.environ.get("CHAQIMCHI_UI_V2", "0").strip().lower() in {"1", "true", "yes", "on"}


def _ui_v2_owner_enabled() -> bool:
    """Egalar paneli uchun alohida flag.

    Onboarding (qurilma ulash, kamera qo'shish, chiziq chizish) faqat v2'da
    bor, support vositalari esa hozircha legacy adminda — shuning uchun ikki
    panel alohida yoqiladi.  `CHAQIMCHI_UI_V2` eski umumiy flag sifatida
    fallback bo'lib qoladi.
    """
    raw = os.environ.get("CHAQIMCHI_UI_V2_OWNER", "").strip().lower()
    if raw:
        return raw in {"1", "true", "yes", "on"}
    return _ui_v2_enabled()


def _ui_v2_admin_enabled() -> bool:
    raw = os.environ.get("CHAQIMCHI_UI_V2_ADMIN", "").strip().lower()
    if raw:
        return raw in {"1", "true", "yes", "on"}
    return _ui_v2_enabled()


def _render_owner() -> HTMLResponse:
    page = STATIC_DIR / ("v2/owner.html" if _ui_v2_owner_enabled() else "owner.html")
    if not page.is_file():
        raise HTTPException(404, "Owner panel topilmadi")
    # Kirish ekranidagi "Telegram botdan havola oling" tugmasi uchun bot
    # manzili shu yerda qo'yiladi — sahifaga qo'lda yozilmaydi.
    bot_username = os.environ.get("CHAQIMCHI_TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    bot_url = (
        f"https://t.me/{bot_username}" if re.fullmatch(r"[A-Za-z0-9_]{5,32}", bot_username) else ""
    )
    content = page.read_text(encoding="utf-8").replace("__TELEGRAM_BOT_URL__", bot_url)
    return HTMLResponse(content)


def _apex_redirect(request: Request, env_key: str, path: str = "/") -> Optional[RedirectResponse]:
    """Apexdagi eski panel yo'li subdomenga ko'chgan bo'lsa — 301.

    Subdomen env sozlanmagan bo'lsa `None` — eski bitta-domen rejimi
    o'zgarishsiz ishlaydi (orqaga moslik).
    """
    target = os.environ.get(env_key, "").strip().rstrip("/")
    if target and _host_section(request) == "apex":
        # Query saqlanadi: eski `?key=...` kirish havolalari sinmasin.
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(f"{target}{path}{query}", status_code=301)
    return None


@app.get("/owner", include_in_schema=False)
async def owner_panel(request: Request) -> Any:
    redirect = _apex_redirect(request, "CHAQIMCHI_APP_URL")
    if redirect is not None:
        return redirect
    return _render_owner()


@app.get("/owner/{panel_path:path}", include_in_schema=False)
async def owner_panel_route(panel_path: str, request: Request) -> Any:
    """Owner SPA clean route'lari; legacy flagda eski panelga qaytadi."""
    redirect = _apex_redirect(request, "CHAQIMCHI_APP_URL", f"/{panel_path}" if panel_path else "/")
    if redirect is not None:
        return redirect
    return _render_owner()


@app.get("/admin/{panel_path:path}", include_in_schema=False)
async def admin_panel_route(panel_path: str, request: Request) -> Any:
    redirect = _apex_redirect(
        request, "CHAQIMCHI_ADMIN_URL", f"/{panel_path}" if panel_path else "/"
    )
    if redirect is not None:
        return redirect
    page = STATIC_DIR / ("v2/admin.html" if _ui_v2_admin_enabled() else "admin.html")
    if not page.is_file():
        raise HTTPException(404, "Admin paneli topilmadi")
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
                # Eski tariflar hisob-kitob uchun qoladi (mavjud obyektlar va
                # hisob-fakturalar ular orqali hisoblanadi), lekin yangi
                # obyektga taklif qilinmaydi.
                "sellable": is_sellable(k),
            }
            for k, v in PLANS.items()
        },
        "sellable": sorted(SELLABLE_PLANS),
    }


#: Yillik to'lovda necha oy hisoblanadi (2 oy bepul). Sayt ham, hisob-faktura
#: ham shu bitta qoidani ishlatadi.
YEARLY_MONTHS_CHARGED = billable_months(12)

#: Bazaviy paketga kiradigan narsalar.
#:
#: Endi manba `plans.py` — matn ikki joyda yozilib, bir-biridan uzoqlashib
#: ketmasin.  Ilgari bu ro'yxat HAMMA mijozga "Kassa navbati nazorati" va
#: "Xavfsizlik" ni va'da qilardi; uch tarif joriy qilingach bu Boshlang'ich
#: mijoziga yolg'on bo'lib qolardi.
BASE_PLAN_INCLUDES = PLANS["biznes"].includes

#: Saytda ko'rsatiladigan tariflar tartibi.  O'rtadagisi ajratiladi:
#: uchta teng ustun qaror qabul qilishni qiyinlashtiradi, ajratilgan
#: o'rta esa ko'zni birinchi o'ziga tortadi.
PUBLIC_PLAN_ORDER = ("boshlangich", "biznes")

#: Tarmoq — bazadagi tarif emas, saytdagi qator.  Har do'kon o'zining
#: `biznes` obyekti sifatida ochiladi, shartlar qo'lda kelishiladi.
#: Narxsiz tarif `PLANS` ga qo'shilsa `create_invoice` unga 0 so'mlik
#: hisob-faktura yozib qo'yardi.
NETWORK_PLAN_CARD = {
    "code": "tarmoq",
    "name": "Tarmoq",
    "price_kind": "on_request",
    "price_label": "So'rov bo'yicha",
    "monthly_usd_cents": None,
    "monthly_uzs": None,
    "max_cameras": None,
    "max_shops": None,
    "retention_days": 90,
    "highlight": False,
    "badge": None,
    "bullets": (
        PlanBullet(
            icon="dokon",
            label="Bir nechta do'kon",
            detail="Har do'kon alohida ulanadi, shartlar birga kelishiladi.",
        ),
        PlanBullet(
            icon="kamera",
            label="Har do'konda 4 kamera",
            detail="Har obyekt uchun to'rttagacha kamera.",
        ),
        PlanBullet(
            icon="qalqon",
            label="Biznesdagi hammasi",
            detail="Navbat, xavfsizlik, xarita, mijoz portreti va xodim davomati.",
        ),
        PlanBullet(
            icon="quti",
            label="Arxiv 90 kun",
            detail="Hodisalar va hisobotlar uch oy saqlanadi.",
            example="Mavsumiy taqqoslash uchun yetadi.",
        ),
        PlanBullet(
            icon="kompyuter",
            label="Ulashda yordam",
            detail="Kamera sozlash va ulashni biz bilan birga qilasiz.",
        ),
    ),
    # Halollik: bitta login bilan hamma do'konni ko'rish kodi HALI YO'Q
    # (`portal_accounts.site_id` bitta).  Buni sayt va'da qilmasin.
    "note": (
        "Hozircha har do'kon alohida panelda ochiladi. "
        "Bitta logindan hammasini ko'rish ustida ishlayapmiz."
    ),
    "cta": "Bog'lanish",
}


def _bullet_payload(bullets: Any) -> List[Dict[str, str]]:
    """`PlanBullet` -> JSON.

    `icon` `cloud/static/icons.svg` dagi symbol id bo'lishi shart:
    xato yozilsa kartada shunchaki bo'sh joy qoladi va buni ko'z bilan
    sezish qiyin — shu sabab test uni tekshiradi.
    """
    return [
        {
            "icon": bullet.icon,
            "label": bullet.label,
            "detail": bullet.detail,
            "example": bullet.example,
        }
        for bullet in bullets
    ]


def _public_plan_card(code: str) -> Dict[str, Any]:
    """Saytdagi tarif kartasi.

    So'm summasi shu yerda hisoblanadi va JS uni QAYTA hisoblamaydi —
    formula ikki joyda turgan paytda ular bir-biridan uzoqlashib ketishi
    mumkin edi va sayt hisob-fakturadan boshqa narx ko'rsatardi.
    """
    limits = PLANS[code]  # type: ignore[index]
    return {
        "code": code,
        "name": limits.display_name or code,
        "price_kind": "fixed",
        "price_label": None,
        "monthly_usd_cents": limits.monthly_price_usd_cents,
        "monthly_uzs": limits.monthly_price(),
        "max_cameras": limits.max_cameras,
        "max_shops": 1,
        "retention_days": limits.retention_days,
        "highlight": code == "biznes",
        "badge": "Eng ommabop" if code == "biznes" else None,
        # `bullets` — kartada ikonka + qisqa nom, bosilganda izoh.
        "bullets": _bullet_payload(limits.bullets),
        # `includes` — tekis matn.  Saqlanadi: keshdagi eski `site.js`
        # hali shuni o'qiydi, va `<noscript>` uchun ham kerak.
        "includes": list(limits.includes),
        "note": None,
        "cta": f"{limits.display_name or code}ni tanlash",
    }


@app.get("/api/v1/public/edu-pricing")
async def public_edu_pricing() -> Dict[str, Any]:
    """Chaqimchi Edu kalkulyatori uchun konstantalar.

    Sahifa hisobni O'ZI qiladi — har bosishda so'rov yuborish
    kalkulyatorni sekin va cheklovlarga bog'liq qilardi.  Lekin
    RAQAMLAR faqat shu yerdan keladi (`chaqimchi_ai/licensing/edu.py`):
    ular ikki joyda saqlansa biri o'zgarib, ikkinchisi eskirib
    qolardi va sayt yolg'on narx ko'rsatardi.

    Tannarx yoki marja bu yerda umuman yo'q — Edu modeli faqat
    sotuv narxlaridan iborat.
    """
    from chaqimchi_ai.licensing import edu

    return edu.catalog()


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
        # Uchta tarif kartasi.  Sayt shu ro'yxatni chizadi va so'm
        # summasini o'zi hisoblamaydi.
        "plans": [_public_plan_card(code) for code in PUBLIC_PLAN_ORDER]
        + [
            dict(
                NETWORK_PLAN_CARD,
                bullets=_bullet_payload(NETWORK_PLAN_CARD["bullets"]),
                includes=[b.summary for b in NETWORK_PLAN_CARD["bullets"]],
            )
        ],
        # `base` — alohida funksiya shartnomalari (`feature_quote`) uchun
        # platforma bazasi.  Tarif narxi endi `plans` dan olinadi.
        "base": {
            "monthly_usd_cents": base_cents,
            "monthly_uzs": uzs_from_cents(base_cents),
            "includes": list(BASE_PLAN_INCLUDES),
        },
        "features": [
            {
                "code": item["code"],
                "name": item["name"],
                "category": item["category"],
                "queue_kind": item["queue_kind"],
                "monthly_usd_cents": int(item["monthly_usd_cents"]),
                "monthly_uzs": uzs_from_cents(int(item["monthly_usd_cents"])),
                "available": item["code"] in available,
            }
            for item in catalog["features"]
            # Davomat public sotuvda YO'Q (litsenziyali model kelgunicha
            # yopiq pilot) — saytda ko'rinmasin.
            if item["active"] and item["category"] != "attendance"
        ],
        # Eng katta tarifdagi kamera soni.  8 kamera apparat maksimumi,
        # lekin public sotuv va'dasi 72 soatlik soak-test tugamaguncha
        # faqat 4 kamera.
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
        # Saytdagi forma ism so'ramaydi — bo'sh joyda "—" turadi,
        # yolg'on ism o'ylab topilmaydi.
        f"Ism: {html.escape(str(lead.get('full_name') or '—'))}\n"
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
    # `reset=duplicate` EMAS: takroriy ariza (bir xil telefon 24 soat
    # ichida) yuborilgan xabarni "pending"ga qaytarib, adminga o'sha
    # arizani qayta-qayta yubortirardi — 5 marta bosgan mehmon 5 ta xabar
    # demak edi.  Yangi qabul qiluvchi qo'shilsa `ensure` uni baribir
    # yaratadi; yuborilganlar esa yuborilganligicha qoladi.
    get_store().ensure_lead_notification_deliveries(str(lead["id"]), recipients)
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
        try:
            await _deliver_lead_notification(lead, str(delivery["chat_id"]))
        except Exception:
            # Bitta yozuv butun navbatni to'smasin.  Navbat `updated_at ASC`
            # bo'yicha tartiblangan: xato chiqqan qatorning vaqti
            # yangilanmaydi, ya'ni u boshda qolib, keyingi aylanishda ham
            # aynan shu yerda to'xtatardi — ya'ni bitta nosoz chat butun
            # sotuv voronkasini o'ldirardi.
            logger.exception(
                "Lead %s -> %s yetkazilmadi, navbat davom etadi",
                delivery["lead_id"],
                delivery["chat_id"],
            )


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
    full_name = " ".join((body.full_name or "").split())
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


class QuickTrialBody(BaseModel):
    phone: str = Field(min_length=5, max_length=40)
    full_name: Optional[str] = "Do'kondor"
    company: Optional[str] = "Mening Do'konim"
    #: Mijoz panelga kirish uchun **o'zi** tanlaydi.  Ilgari parolni admin
    #: yaratib, qo'lda yuborardi — ya'ni har mijoz operatorning ish
    #: vaqtini kutardi va o'z-o'zidan ulanish yo'li yo'q edi.
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=128)
    #: Standart qiymat **yo'q**: bu endpoint haqiqiy `site` yozuvi yaratadi va
    #: telefon raqamini saqlaydi, ya'ni `/public/leads` bilan bir xil roziliq
    #: talab qiladi. Oldin `True` turardi — forma katagi belgilanmasa ham
    #: ma'lumot yozilaverardi.
    consent: bool = False
    website: Optional[str] = ""
    #: Saytdagi tarif kartasi qaysi tugmani bosgani.  Boshlang'ichni
    #: tanlagan mijoz Biznes obyektini olib qolmasin — u 4 kamera ulab,
    #: keyin "nega chegara" deb so'raydi.  Faqat sotiladigan ikkitasi.
    plan: Literal["boshlangich", "biznes"] = "biznes"


#: Nechta do'kon o'z-o'zidan ochilishi mumkin.  Mahsulot hali 72 soatlik
#: qabul sinovidan o'tmagan, shuning uchun birinchi mijozlar soni ataylab
#: cheklangan: nosozlik chiqsa u o'nta do'kondan nariga tarqalmaydi.
SELF_SERVICE_LIMIT_DEFAULT = 10

#: Bepul sinov o'rnatish va ma'lumot yig'ishga yetishi, ammo pullik
# mahsulotni uch oyga bepul almashtirib yubormasligi kerak.
SELF_SERVICE_TRIAL_DAYS_DEFAULT = 14


def _self_service_limit() -> int:
    raw = os.environ.get("CHAQIMCHI_SELF_SERVICE_LIMIT", "").strip()
    try:
        return max(0, int(raw)) if raw else SELF_SERVICE_LIMIT_DEFAULT
    except ValueError:
        logger.warning("CHAQIMCHI_SELF_SERVICE_LIMIT son emas — standart qiymat")
        return SELF_SERVICE_LIMIT_DEFAULT


def _self_service_trial_days() -> int:
    raw = os.environ.get("CHAQIMCHI_SELF_SERVICE_TRIAL_DAYS", "").strip()
    try:
        return max(1, int(raw)) if raw else SELF_SERVICE_TRIAL_DAYS_DEFAULT
    except ValueError:
        return SELF_SERVICE_TRIAL_DAYS_DEFAULT


@app.post("/api/v1/public/quick-trial")
async def public_quick_trial(
    body: QuickTrialBody,
    request: Request,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """1-bosishda bepul sinov do'koni ochish.

    Bu endpoint `/public/leads` dan **qimmatroq**: u bazada haqiqiy `site` va
    pairing kod yaratadi. Shuning uchun cheklov ham qattiqroq — soatiga 3 ta.
    Cheklovsiz oddiy skript bilan cheksiz do'kon yozuvi yaratish mumkin edi.
    """
    if body.website:
        return {"ok": True, "message": "Qabul qilindi"}
    ratelimit.check(
        "quick-trial",
        request.client.host if request.client else "unknown",
        limit=3,
        window_sec=3_600,
        message="Juda ko'p so'rov yuborildi. Bir soatdan keyin urinib ko'ring.",
    )
    if not body.consent:
        raise HTTPException(422, "Bog'lanish uchun rozilik talab qilinadi")
    phone = " ".join(body.phone.split())
    if sum(char.isdigit() for char in phone) < 5:
        raise HTTPException(422, "Telefon raqami noto'g'ri")
    name = (body.company or "Do'kon").strip()
    full_name = (body.full_name or "Mijoz").strip()

    # Login va parolni do'kon YARATILISHIDAN OLDIN tekshiramiz: `create_site`
    # ni orqaga qaytarib bo'lmaydi (o'chirish funksiyasi yo'q), ya'ni
    # keyinroq chiqqan xato egasiz do'kon yozuvini qoldirardi.
    try:
        username = normalize_username(body.username)
        validate_password(body.password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if get_store().account_by_username(username):
        raise HTTPException(409, "Bu login band — boshqasini tanlang")

    # Sinov o'rinlari cheklangan: mahsulot hali 72 soatlik qabul sinovidan
    # o'tmagan, shuning uchun nosozlik chiqsa u o'nta do'kondan nariga
    # tarqalmaydi.  Chegara to'lganda mijoz "yo'q" degan javob emas,
    # odatdagi ariza yo'lini ko'radi.
    limit = _self_service_limit()
    if get_store().count_sites() >= limit:
        raise HTTPException(
            503,
            "Sinov o'rinlari hozircha to'ldi. Telefon raqamingizni qoldiring — "
            "joy ochilishi bilan o'zimiz bog'lanamiz.",
        )

    # Nom oxiriga telefonning oxirgi to'rt RAQAMI qo'shiladi: bir xil
    # nomli do'konlarni operator ajrata olsin.  Ilgari bu `phone[-4:]`
    # edi va formatlangan raqamda ("+998 90 123 45 67") probel bilan
    # "5 67" bo'lib chiqardi — nom egasining panelida ham shunday
    # ko'rinardi.
    digits = "".join(char for char in phone if char.isdigit())
    site = get_store().create_site(
        name=f"{name} ({digits[-4:]})" if len(digits) >= 4 else name,
        # Mijoz saytda qaysi kartani bosgan bo'lsa — o'sha.  Standart
        # "biznes": tarif tanlanmagan yo'l (masalan to'g'ridan-to'g'ri
        # forma) mijozni cheklangan tarifga tushirib qo'ymasin.
        plan=body.plan,
        contact_phone=phone,
        subscription_days_override=_self_service_trial_days(),
    )

    site_id = site["site_id"]
    code = site["pairing_code"]

    login_error: Optional[str] = None
    try:
        get_store().create_account(
            username=username,
            password=body.password,
            role="customer",
            status="active",
            full_name=full_name,
            phone=phone,
            company=name,
            site_id=site_id,
        )
    except ValueError as exc:
        # Do'kon allaqachon ochildi va pairing kod berildi — buni orqaga
        # qaytarmaymiz.  Mijoz dasturni o'rnatib, ishlatishda davom etadi;
        # panel logini esa admin yaratadi.
        logger.warning("Self-service login yaratilmadi: %s", exc)
        login_error = str(exc)

    try:
        created = get_store().create_lead(
            full_name=full_name,
            phone=phone,
            company=name,
            message=f"[1-Bosishda Bepul Sinov] Sayt ID: {site_id}, Kod: {code}",
        )
        lead = get_store().get_lead(created["id"])
        if lead:
            background_tasks.add_task(_notify_new_lead, lead, duplicate=False)
    except Exception:
        pass

    fallback = str(request.base_url).rstrip("/")
    dl_base = urls.dl_url() or fallback
    api_base = urls.api_url() or fallback
    app_base = urls.app_url() or fallback
    return {
        "ok": True,
        "site_id": site_id,
        "pairing_code": code,
        # Kod fayl NOMIGA tushadi — o'rnatuvchi uni o'qib, dastur cloudga
        # o'zi ulanadi.  Mijoz 6 ta belgini qo'lda ko'chirmaydi.
        "download_windows_url": f"/api/v1/public/download-installer?os=windows&code={code}&site_id={site_id}",
        "linux_command": f"curl -fsSL {dl_base}/downloads/sotqin-installer.sh | sudo bash -s -- --cloud {api_base} --code {code}",
        "owner_url": f"{app_base}/owner",
        # Parol javobda YO'Q: uni mijozning o'zi tanladi va bazada faqat
        # hash saqlanadi.
        "username": username,
        "login_error": login_error,
        "trial_days": _self_service_trial_days(),
        "message": "Do'koningiz ochildi — endi dasturni yuklab oling.",
    }


#: Windows o'rnatuvchisi ~70 MB.  Uni Docker image ichiga solish image'ni
#: shuncha shishiradi va har deployda qayta yuklashga majbur qiladi, shuning
#: uchun production'da fayl GitHub Releases'da turadi va cloud faqat
#: yo'naltiradi.  Bu Linux relizi bilan bir xil naqsh
#: (`CHAQIMCHI_SOTQIN_RELEASE_URL`).
ENV_WINDOWS_INSTALLER_URL = "CHAQIMCHI_WINDOWS_INSTALLER_URL"
ENV_WINDOWS_INSTALLER_SIZE = "CHAQIMCHI_WINDOWS_INSTALLER_SIZE_MB"

#: Ishlab chiqishda va lokal sinovda fayl repo ichida bo'ladi.
WINDOWS_INSTALLER_PATHS = (
    BASE_DIR / "releases" / "Chaqimchi_AI_Setup.exe",
    Path("/app/releases/Chaqimchi_AI_Setup.exe"),
)

#: Imzolangan Windows relizi: `chaqimchi-windows-<versiya>.exe` va yonida
#: `.json` manifest.  Qurilma yangilanishni aynan shu juftlikdan oladi.
WINDOWS_RELEASE_PATTERN = re.compile(r"^chaqimchi-windows-(?P<version>[A-Za-z0-9.\-_]+)\.exe$")


def _release_dirs() -> List[Path]:
    return [BASE_DIR / "releases", Path("/app/releases")]


def _version_key(version: str) -> tuple:
    """`0.10.0` `0.9.0` dan katta bo'lishi uchun raqamlar bo'yicha taqqoslash.

    Matn sifatida taqqoslansa `"0.10" < "0.9"` chiqardi va qurilma yangi
    versiyani eski deb hisoblab, hech qachon yangilanmasdi.
    """
    parts = []
    for chunk in re.split(r"[.\-_]", version):
        parts.append((0, int(chunk)) if chunk.isdigit() else (1, 0, chunk))
    return tuple(parts)


def latest_windows_release() -> Optional[Dict[str, Any]]:
    """Eng yangi imzolangan Windows relizi (manifest bilan birga).

    Manifestsiz `.exe` **e'tiborsiz qoldiriladi**: imzosiz faylni qurilma
    baribir rad etadi, uni yangilanish deb e'lon qilish esa faqat
    chalkashlik keltirardi.
    """
    best: Optional[Dict[str, Any]] = None
    for directory in _release_dirs():
        if not directory.is_dir():
            continue
        for exe in directory.glob("chaqimchi-windows-*.exe"):
            match = WINDOWS_RELEASE_PATTERN.match(exe.name)
            if not match:
                continue
            manifest = exe.with_name(f"{exe.name[: -len('.exe')]}.json")
            if not manifest.is_file():
                logger.warning("Manifestsiz Windows relizi e'tiborsiz: %s", exe.name)
                continue
            version = match.group("version")
            candidate = {
                "version": version,
                "exe": exe,
                "manifest": manifest,
                "size_bytes": exe.stat().st_size,
            }
            if best is None or _version_key(version) > _version_key(best["version"]):
                best = candidate
    return best


def _windows_installer_url() -> str:
    url = os.environ.get(ENV_WINDOWS_INSTALLER_URL, "").strip()
    return url if url.startswith("https://") else ""


def _windows_installer_file() -> Optional[Path]:
    release = latest_windows_release()
    if release is not None:
        return release["exe"]
    return next((path for path in WINDOWS_INSTALLER_PATHS if path.is_file()), None)


@app.get("/api/v1/public/windows-release")
async def public_windows_release() -> Dict[str, Any]:
    """Windows o'rnatuvchisi tayyormi va hajmi qancha.

    Sayt shu javobga qarab tugmani ko'rsatadi: tayyor bo'lmasa yuklab olish
    o'rniga "xabar bering" formasi chiqadi.  Hajm **o'lchanadi** yoki
    deployda beriladi, sahifaga qo'lda yozilmaydi — ilgari saytda "115 MB"
    deb turardi, fayl esa umuman mavjud emas edi va tugma 503 qaytarardi.
    """
    if _windows_installer_url():
        size = os.environ.get(ENV_WINDOWS_INSTALLER_SIZE, "").strip()
        # URL rejimida ham versiya RELIZDAN olinadi (pastdagi izoh bilan
        # bir sabab): cloud image raqami tashqi o'rnatuvchi versiyasini
        # bildirmaydi.  Tashqi URL uchun aniq raqam env bilan beriladi.
        env_version = os.environ.get("CHAQIMCHI_WINDOWS_INSTALLER_VERSION", "").strip()
        release = latest_windows_release()
        return {
            "available": True,
            "size_mb": int(size) if size.isdigit() else None,
            "version": env_version or (release["version"] if release else __version__),
            "url": "/api/v1/public/download-installer",
        }
    installer = _windows_installer_file()
    if installer is None:
        return {"available": False, "size_mb": None, "version": __version__}
    # Versiya **relizdan** olinadi, cloud image'idan emas.  Ilgari bu yerda
    # `__version__` turardi, ya'ni serverning o'z raqami: yangi
    # o'rnatuvchi yuklangan bo'lsa ham sayt eski raqamni ko'rsatardi.
    # Yuklab olinadigan fayl nomi esa relizdan olinardi — natijada badge
    # 0.6.1, fayl 0.6.2 bo'lib chiqardi va "yangisi chiqdimi?" degan
    # savolga javob berib bo'lmasdi.
    release = latest_windows_release()
    return {
        "available": True,
        "size_mb": round(installer.stat().st_size / 1024 / 1024),
        "version": release["version"] if release else __version__,
        "url": "/api/v1/public/download-installer",
    }


@app.get("/api/v1/public/download-installer")
async def public_download_installer(code: str = "") -> Response:
    """Windows o'rnatuvchisi (.exe).

    `code` berilsa **fayl nomiga** qo'shiladi:
    `Chaqimchi_AI_Setup-A1B2C3.exe`.  O'rnatuvchi nomdan kodni o'qiydi va
    dastur birinchi ishga tushishda cloudga o'zi ulanadi — mijoz 6 ta
    belgini qo'lda ko'chirmaydi.

    Nega aynan fayl nomi: 68 MB paketni har mijoz uchun qayta qurish
    mumkin emas, brauzer esa serverdan kelgan nomni saqlaydi.  Nom
    buzilsa (masalan `... (1).exe`) sehrgar kodni odatdagidek so'raydi —
    ya'ni bu qulaylik, majburiyat emas.

    Kod maxfiy emas: u bir martalik, 48 soat amal qiladi va baribir
    mijozga beriladi.  Shu sabab uni havolada tashish xavf tug'dirmaydi.
    """
    safe_code = re.sub(r"[^A-Fa-f0-9]", "", code).upper()[:6]

    # Versiya fayl nomida bo'lishi shart.  Usiz `Chaqimchi_AI_Setup.exe`
    # har safar bir xil nom va deyarli bir xil hajm bilan tushardi —
    # mijoz yangi versiyani yuklab olganini **ko'ra olmasdi** va eski
    # faylni qayta o'rnatib, muammo tuzalmadi deb o'ylardi.
    release = latest_windows_release()
    version = release["version"] if release else __version__
    parts = ["Chaqimchi_AI_Setup", version]
    if len(safe_code) == 6:
        parts.append(safe_code)
    filename = "-".join(parts) + ".exe"

    url = _windows_installer_url()
    installer = _windows_installer_file()

    # Kodli havolada fayl NOMI muhim: o'rnatuvchi pairing kodni aynan
    # nomdan o'qiydi.  Redirect esa nomni yo'qotadi — brauzer manzildagi
    # nomni saqlaydi (`chaqimchi-windows-0.6.8.exe`), kod esa yo'qoladi va
    # mijoz sehrgarda kodni QO'LDA kiritishga majbur bo'ladi.
    #
    # Shuning uchun kod berilgan bo'lsa faylni o'zimiz beramiz — bu
    # kamdan-kam so'rov (har mijozga bir marta), kodsiz havola esa
    # statik manzilga yo'naltiriladi.
    if url and (len(safe_code) != 6 or installer is None):
        if len(safe_code) == 6:
            logger.warning(
                "Kodli yuklab olish redirect bilan berildi — fayl lokal "
                "topilmadi, kod fayl nomida ketmaydi"
            )
        return RedirectResponse(url, status_code=307)
    if installer is None:
        raise HTTPException(
            503,
            "Windows dasturi hali nashr qilinmagan. Saytda raqamingizni "
            "qoldiring — tayyor bo'lganda xabar beramiz.",
        )
    return FileResponse(
        path=installer,
        filename=filename,
        media_type="application/vnd.microsoft.portable-executable",
        # O'rnatuvchi versiya bilan almashadi — brauzer eskisini keshda
        # ushlab qolmasin.  Kodli havola esa umuman keshlanmasin: har
        # mijozga o'z fayli ketishi kerak.
        headers={"Cache-Control": "no-store" if len(safe_code) == 6 else "no-cache"},
    )


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


@app.get("/api/v1/admin/dashboard")
async def admin_dashboard(
    range: Literal["7d", "30d"] = "7d",
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    """Admin V2 uchun umumiy, faqat real ma'lumotli snapshot."""
    store = get_store()
    sites = store.list_sites()
    site_names = {str(site["id"]): str(site["name"]) for site in sites}
    device_names: Dict[str, str] = {}
    for site in sites:
        detail = store.site_detail(str(site["id"]))
        for device in detail.get("devices") or []:
            device_names[str(device["id"])] = str(device.get("label") or device["id"])
    telemetry = []
    for metric in get_event_store().latest_device_metrics():
        telemetry.append(
            {
                **metric,
                "site_name": site_names.get(str(metric.get("site_id"))),
                "label": device_names.get(str(metric.get("device_id"))),
            }
        )
    invoice_stats = get_payments().invoice_stats()
    return {
        "range": range,
        "stats": {**store.stats(), **invoice_stats},
        "sites": sites,
        "telemetry": telemetry,
        # Serverning O'ZI: mijoz qurilmalari yashil bo'lib turib, VPS
        # xotirasi tugab qolishi mumkin.  Alohida endpoint qilinmadi —
        # panel shu javobni har 15 soniyada so'raydi va CPU foizi aynan
        # shu oraliqdan hisoblanadi (`cloud/server_health.py`).
        "server": server_health.snapshot(),
        "invoices": invoice_stats,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/admin/events")
async def admin_events(
    limit: int = 100,
    event_type: Optional[str] = None,
    site_id: Optional[str] = None,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    """Admin V2 uchun filiallar bo'yicha so'nggi haqiqiy AI hodisalari."""
    store = get_store()
    sites = store.list_sites()
    selected = [site for site in sites if not site_id or str(site["id"]) == site_id]
    if site_id and not selected:
        raise HTTPException(404, "Filial topilmadi")
    bounded = max(1, min(limit, 500))
    events: List[Dict[str, Any]] = []
    for site in selected:
        for item in get_event_store().list_events(
            str(site["id"]), limit=bounded, event_type=event_type
        ):
            events.append(
                {
                    **item,
                    "site_name": site.get("name"),
                    "label": event_label(str(item.get("event_type", ""))),
                }
            )
    events.sort(key=lambda item: str(item.get("occurred_at") or ""), reverse=True)
    return {"events": events[:bounded]}


@app.get("/api/v1/admin/sites/{site_id}/diagnostics")
async def admin_site_diagnostics(
    site_id: str,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    if not get_store().get_site(site_id):
        raise HTTPException(404, "Filial topilmadi")
    return {"diagnostics": get_event_store().latest_device_diagnostics(site_id)}


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
    admin: Optional[PortalPrincipal] = Depends(require_admin),
) -> Dict[str, Any]:
    lead = get_store().get_lead(lead_id)
    if not lead:
        raise HTTPException(404, "Ariza topilmadi")
    if lead.get("site_id"):
        raise HTTPException(409, "Bu ariza allaqachon mijozga aylantirilgan")
    name = lead.get("company") or lead.get("full_name") or f"Do'kon {lead['phone']}"
    site = get_store().create_site(
        name,
        "biznes",
        subscription_months=body.subscription_months,
        contact_phone=lead["phone"],
        address=lead.get("city"),
    )
    get_store().link_lead_site(lead_id, site["site_id"])
    # Do'kon ochilishining o'zi yetarli emas edi: mijozning paneliga
    # kirish yo'li yo'q qolardi.  Endi login/parol shu yerda tug'iladi
    # va javobda BIR MARTA qaytariladi.
    try:
        login = get_store().create_customer_login(
            site["site_id"],
            full_name=lead.get("full_name") or name,
            phone=lead["phone"],
            created_by=admin.account_id if admin else None,
        )
        site["login"] = {"username": login["username"], "password": login["password"]}
    except ValueError as exc:
        # Do'kon allaqachon ochildi — buni orqaga qaytarmaymiz.  Admin
        # login'ni mijoz sahifasidan qo'lda yaratadi.
        logger.warning("mijoz login'i yaratilmadi: %s", exc)
        site["login_error"] = str(exc)
    return site


@app.post("/api/v1/admin/sites/{site_id}/login")
async def admin_create_site_login(
    site_id: str,
    admin: Optional[PortalPrincipal] = Depends(require_admin),
) -> Dict[str, Any]:
    """Do'kon egasiga panelga kirish uchun login va parol yaratadi.

    Parol javobda faqat SHU SAFAR ko'rinadi — bazada scrypt hash'i
    saqlanadi.  Yo'qolsa yangisi yaratiladi (`.../password`).
    """
    site = get_store().get_site(site_id)
    if not site:
        raise HTTPException(404, "Do'kon topilmadi")
    existing = get_store().customer_account_for_site(site_id)
    if existing:
        raise HTTPException(409, f"Bu do'konda login allaqachon bor: {existing['username']}")
    try:
        login = get_store().create_customer_login(
            site_id,
            full_name=str(site.get("name") or "Do'kon egasi"),
            phone=site.get("contact_phone"),
            created_by=admin.account_id if admin else None,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    get_store().audit_portal_action(
        "account.created",
        actor_id=admin.account_id if admin else None,
        target_type="account",
        target_id=login["account"]["id"],
        detail={"role": "customer", "site_id": site_id},
    )
    return {"username": login["username"], "password": login["password"]}


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
            "label": "Windows 4 kamera benchmark + 72 soat soak",
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
            "label": "Sayt arizalari Telegram yetkazilishi (sotuv boti)",
            "ok": bool(get_alerts().config.token and lead_recipients),
            "required": True,
            "recipients": len(lead_recipients),
            # Alohida sotuv boti bormi — arizalar mijoz hisobotlari bilan
            # bitta chatda aralashib ketmasligi shundan ko'rinadi.
            "separate_bot": bool(os.environ.get("CHAQIMCHI_SALES_TELEGRAM_TOKEN", "").strip()),
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


# ── Moliya paneli ────────────────────────────────────────────────────────
#
# Platforma nechchiga tushayapti va har mijoz alohida nechchiga tushayapti.
# Gemini xarajati HAQIQIY token sarfidan (`usageMetadata`), infra xarajati
# esa env'dagi summalardan hisoblanadi — panelda qo'lda yozilgan raqam yo'q.

#: Gemini narxlari, 1 mln token uchun USD.  Standart qiymatlar flash-sinf
#: modellari uchun; Google narxni o'zgartirsa env bilan yangilanadi.
GEMINI_INPUT_USD_PER_M_DEFAULT = 0.30
GEMINI_OUTPUT_USD_PER_M_DEFAULT = 2.50

#: 1 kVt·soat elektr narxi.  Tarif viloyat va iste'molchi turiga qarab
#: farq qiladi, shuning uchun env bilan boshqariladi.
KWH_UZS_DEFAULT = 1_000.0

#: Qurilma turi bo'yicha quvvat.  Do'kon kompyuteri — odatiy ofis
#: desktop'i (i5 sinf, `docs/DOKON_MVP.md` dagi sinov mashinasi);
#: Box — N100 mini-PC.
#:
#: Bu O'LCHANGAN emas, BAHOLANGAN qiymat: rozetka o'lchagichi bilan
#: tekshirilmagan.  Panelda ham shunday deb yoziladi.
DEVICE_WATTS_WINDOWS_DEFAULT = 65.0
DEVICE_WATTS_BOX_DEFAULT = 12.0


def _finance_env_float(key: str, default: float) -> float:
    raw = os.environ.get(key, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        logger.warning("%s son emas — standart qiymat ishlatiladi", key)
        return default


@app.get("/api/v1/admin/finance")
async def admin_finance(
    month: Optional[str] = None,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    """Oylik xarajat/daromad hisobi.

    `month` — `YYYY-MM` (Toshkent bo'yicha); berilmasa joriy oy.
    Umumiy infra (server + domen) qurilma ulangan do'konlar orasida teng
    bo'linadi: stub-saytlar haqiqiy mijoz ulushini shishirmasin.
    """
    tz = ZoneInfo("Asia/Tashkent")
    if month:
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            raise HTTPException(422, "month YYYY-MM ko'rinishida bo'lishi kerak")
        year, mon = int(month[:4]), int(month[5:7])
    else:
        today = datetime.now(tz)
        year, mon = today.year, today.month
        month = f"{year:04d}-{mon:02d}"
    start_local = datetime(year, mon, 1, tzinfo=tz)
    end_local = datetime(year + (mon == 12), (mon % 12) + 1, 1, tzinfo=tz)
    start_iso = start_local.astimezone(timezone.utc).isoformat()
    end_iso = end_local.astimezone(timezone.utc).isoformat()

    rate = usd_rate_uzs()
    server_monthly_usd = _finance_env_float("CHAQIMCHI_COST_SERVER_MONTHLY_USD", 0.0)
    domain_yearly_uzs = int(_finance_env_float("CHAQIMCHI_COST_DOMAIN_YEARLY_UZS", 27_000))
    input_usd_per_m = _finance_env_float(
        "CHAQIMCHI_GEMINI_INPUT_USD_PER_M", GEMINI_INPUT_USD_PER_M_DEFAULT
    )
    output_usd_per_m = _finance_env_float(
        "CHAQIMCHI_GEMINI_OUTPUT_USD_PER_M", GEMINI_OUTPUT_USD_PER_M_DEFAULT
    )

    kwh_uzs = _finance_env_float("CHAQIMCHI_COST_KWH_UZS", KWH_UZS_DEFAULT)
    watts_windows = _finance_env_float(
        "CHAQIMCHI_DEVICE_WATTS_WINDOWS", DEVICE_WATTS_WINDOWS_DEFAULT
    )
    watts_box = _finance_env_float("CHAQIMCHI_DEVICE_WATTS_BOX", DEVICE_WATTS_BOX_DEFAULT)

    server_monthly_uzs = round(server_monthly_usd * rate)
    domain_monthly_uzs = round(domain_yearly_uzs / 12)
    fixed_monthly_uzs = server_monthly_uzs + domain_monthly_uzs

    def gemini_cost_uzs(input_tokens: int, output_tokens: int) -> int:
        usd = (input_tokens / 1_000_000) * input_usd_per_m + (
            output_tokens / 1_000_000
        ) * output_usd_per_m
        return round(usd * rate)

    sites = get_store().list_sites()
    usage_rows = {
        item["site_id"]: item
        for item in get_event_store().vision_usage_by_site(start_iso, end_iso)
    }
    # Elektr O'LCHANGAN ish vaqtidan hisoblanadi.  Kompyuter kechasi
    # o'chirilsa yoki bir hafta ishlamasa, xarajat ham shunga yarasha
    # kamayadi — taxminiy "24/7" bilan hisoblash mijozning haqiqiy
    # tannarxini yolg'on ko'rsatardi.
    uptime_minutes = get_event_store().device_uptime_minutes_by_site(start_iso, end_iso)
    # Infra ulushi faqat QURILMA ULANGAN saytlarga bo'linadi; birorta ham
    # bo'lmasa hammasiga (bo'linmagan xarajat yashirin qolmasin).
    billable_ids = {str(s["id"]) for s in sites if int(s.get("devices") or 0) > 0}
    if not billable_ids:
        billable_ids = {str(s["id"]) for s in sites}
    share_uzs = round(fixed_monthly_uzs / len(billable_ids)) if billable_ids else 0

    site_rows: List[Dict[str, Any]] = []
    totals = {
        "revenue_uzs": 0,
        "gemini_cost_uzs": 0,
        "energy_cost_uzs": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "jobs": 0,
        "untracked_jobs": 0,
    }
    for site in sites:
        site_id = str(site["id"])
        usage = usage_rows.get(site_id) or {}
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        gemini_uzs = gemini_cost_uzs(input_tokens, output_tokens)
        shared = share_uzs if site_id in billable_ids else 0
        billable = site_id in billable_ids
        # Daromad faqat TO'LOVI JOYIDA bo'lgan mijozdan sanaladi.  Ilgari
        # bu shart yo'q edi va obunasi tugagan do'kon ham daromad bo'lib
        # turardi — "Boshqaruv" sahifasi esa (`store.stats()`) uni
        # sanamasdi, ya'ni ikki sahifa ikki xil raqam ko'rsatardi.
        paying = billable and str(site.get("license_status") or "") in ("active", "grace")
        revenue = int(site.get("monthly_price_uzs") or 0) if paying else 0

        # `None` — "o'lchov yo'q" (bucket 30 kun saqlanadi, eski oyda
        # ma'lumot bo'lmaydi).  Uni nolga aylantirish "elektr bepul edi"
        # degan yolg'on ko'rsatkich berardi.
        minutes = uptime_minutes.get(site_id)
        watts = watts_windows if int(site.get("windows_devices") or 0) > 0 else watts_box
        if minutes:
            uptime_hours = round(minutes / 60, 1)
            energy_kwh = round(uptime_hours * watts / 1000, 2)
            energy_uzs = round(energy_kwh * kwh_uzs)
        else:
            uptime_hours = 0.0
            energy_kwh = 0.0
            energy_uzs = 0

        # Elektr BIZNING tannarxga KIRMAYDI: Windows yo'lida dastur
        # mijozning o'z kompyuterida ishlaydi va tokni u to'laydi.  Uni
        # bizning xarajatga qo'shish foydani soxta kamaytirardi.
        #
        # Lekin raqam yo'qolmaydi — u mijozning JAMI xarajatini ko'rsatadi
        # ("bizning obuna 299 000 + elektr 47 000 = 346 000") va sotuvda
        # aynan shu savolga javob beradi.
        cost = gemini_uzs + shared
        site_rows.append(
            {
                "site_id": site_id,
                "name": site.get("name"),
                "plan": site.get("plan"),
                "devices": int(site.get("devices") or 0),
                "billable": billable,
                "license_status": site.get("license_status"),
                "revenue_uzs": revenue,
                "gemini_jobs": int(usage.get("jobs") or 0),
                "gemini_untracked_jobs": int(usage.get("untracked_jobs") or 0),
                "gemini_input_tokens": input_tokens,
                "gemini_output_tokens": output_tokens,
                "gemini_cost_uzs": gemini_uzs,
                "shared_cost_uzs": shared,
                # ── Mijozning xarajati (bizniki EMAS) ──
                "energy_measured": bool(minutes),
                "energy_watts": watts,
                "energy_uptime_hours": uptime_hours,
                "energy_kwh": energy_kwh,
                "energy_cost_uzs": energy_uzs,
                # Mijozga oyiga jami nechchiga tushadi: obuna + o'z toki.
                "customer_total_uzs": revenue + energy_uzs,
                # ── Bizning tannarx va foyda ──
                "total_cost_uzs": cost,
                "margin_uzs": revenue - cost,
                "margin_percent": round((revenue - cost) / revenue * 100, 1) if revenue else None,
            }
        )
        totals["revenue_uzs"] += revenue
        totals["gemini_cost_uzs"] += gemini_uzs
        totals["energy_cost_uzs"] += energy_uzs
        totals["input_tokens"] += input_tokens
        totals["output_tokens"] += output_tokens
        totals["jobs"] += int(usage.get("jobs") or 0)
        totals["untracked_jobs"] += int(usage.get("untracked_jobs") or 0)
    # Eng qimmat mijoz tepada — panel savoli aynan "kim nechchiga tushyapti".
    site_rows.sort(key=lambda item: item["total_cost_uzs"], reverse=True)

    # Elektr bu yig'indiga QO'SHILMAYDI — u mijozning xarajati (yuqoridagi
    # izohga qarang), shuning uchun alohida maydonda turadi.
    total_cost_uzs = fixed_monthly_uzs + totals["gemini_cost_uzs"]
    total_revenue_uzs = totals["revenue_uzs"]
    return {
        "month": month,
        "usd_rate_uzs": rate,
        "fixed": {
            "server_monthly_usd": server_monthly_usd,
            "server_monthly_uzs": server_monthly_uzs,
            "server_configured": server_monthly_usd > 0,
            "domain_yearly_uzs": domain_yearly_uzs,
            "domain_monthly_uzs": domain_monthly_uzs,
            "total_monthly_uzs": fixed_monthly_uzs,
            "split_between": len(billable_ids),
            "share_per_site_uzs": share_uzs,
            "kwh_uzs": kwh_uzs,
            "watts_windows": watts_windows,
            "watts_box": watts_box,
        },
        "energy": {
            "cost_uzs": totals["energy_cost_uzs"],
            "kwh_uzs": kwh_uzs,
            # Kimning xarajati: elektrni mijoz to'laydi (dastur uning o'z
            # kompyuterida ishlaydi), shuning uchun bu son bizning
            # tannarxga KIRMAYDI.  Panel shuni aniq yozishi uchun.
            "paid_by": "customer",
            # Ish vaqti o'lchanadi, quvvat esa baholangan.
            "watts_measured": False,
        },
        "gemini": {
            "jobs": totals["jobs"],
            "untracked_jobs": totals["untracked_jobs"],
            "input_tokens": totals["input_tokens"],
            "output_tokens": totals["output_tokens"],
            "cost_uzs": totals["gemini_cost_uzs"],
            "input_usd_per_m": input_usd_per_m,
            "output_usd_per_m": output_usd_per_m,
            "model": vision_agent._model() if vision_agent.configured() else None,
        },
        "sites": site_rows,
        "totals": {
            "revenue_uzs": total_revenue_uzs,
            "cost_uzs": total_cost_uzs,
            "gemini_cost_uzs": totals["gemini_cost_uzs"],
            "fixed_cost_uzs": fixed_monthly_uzs,
            # Mijozlar to'laydigan elektr — bizning tannarxdan tashqarida.
            "energy_cost_uzs": totals["energy_cost_uzs"],
            "customer_total_uzs": total_revenue_uzs + totals["energy_cost_uzs"],
            "margin_uzs": total_revenue_uzs - total_cost_uzs,
            "margin_percent": (
                round((total_revenue_uzs - total_cost_uzs) / total_revenue_uzs * 100, 1)
                if total_revenue_uzs
                else None
            ),
            "sites_billable": len(billable_ids),
            "sites_paying": sum(1 for row in site_rows if row["revenue_uzs"] > 0),
        },
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


class PlanBody(BaseModel):
    plan: str = Field(min_length=2, max_length=32)


@app.post("/api/v1/admin/sites/{site_id}/plan")
async def admin_set_plan(
    site_id: str,
    body: PlanBody,
    admin: Optional[PortalPrincipal] = Depends(require_admin),
) -> Dict[str, Any]:
    """Obyekt tarifini almashtirish.

    Sotilmaydigan tarif ham qabul qilinadi (`lite` kabi) — sotuvchi eski
    mijozni kerak bo'lsa o'z tarifida qoldira olishi kerak.  Yangi obyekt
    yaratishda esa faqat `SELLABLE_PLANS` ko'rsatiladi.
    """
    try:
        detail = get_store().set_plan(site_id, body.plan)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    # Qurilma yangi funksiya to'plamini va kamera chegarasini keyingi
    # config poll'ida (20 soniya) olishi uchun revizya suriladi.
    get_event_store().touch_site_config(site_id)
    # Tarif — pul va funksiya to'plami.  O'zgarishi mijozga sezilarli,
    # ya'ni "men buni so'ramagandim" bahsi mumkin.
    get_store().audit_portal_action(
        "site.plan.changed",
        actor_id=_audit_actor(admin),
        target_type="site",
        target_id=site_id,
        detail={"plan": body.plan},
    )
    return detail


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


# ── Admin: masofadan sozlash ─────────────────────────────────────────────
#
# Bugungacha chiziq va zonani faqat USTA paneli yoki do'kondagi sehrgar
# chiza olardi.  Amalda bu shuni anglatardi: do'kon sozlanmasa, uni
# masofadan tuzatishning YO'LI YO'Q edi.
#
# Jonli do'konda oqibati o'lchandi (2026-08-21): `lines: []`, `zones: []`,
# ya'ni kuniga atigi 5 ta kirish sanalgan (chiqqan esa 7 ta) va navbat
# umuman ishlamagan — navbat uchun zona SHART.
#
# Endpointlar ataylab yupqa: mantiq usta variantidagi bilan bir xil
# yordamchilarga tayanadi, faqat autentifikatsiya boshqa.


@app.get("/api/v1/admin/sites/{site_id}/config")
async def admin_get_config(site_id: str, _: None = Depends(require_admin)) -> Dict[str, Any]:
    if not get_store().get_site(site_id):
        raise HTTPException(404, "Sayt topilmadi")
    return get_event_store().get_site_config(site_id)


@app.put("/api/v1/admin/sites/{site_id}/config")
async def admin_update_config(
    site_id: str,
    body: SiteConfigBody,
    admin: Optional[PortalPrincipal] = Depends(require_admin),
) -> Dict[str, Any]:
    """Chiziq, zona va kamera rollarini admin qo'yadi.

    Mijozning oldiga bormasdan tuzatish uchun.  Usta variantidan farqi
    faqat autentifikatsiyada — tekshiruv va saqlash bir xil.
    """
    if not get_store().get_site(site_id):
        raise HTTPException(404, "Sayt topilmadi")
    _validate_site_config(body)
    updated = get_event_store().update_site_config(
        site_id, _preserve_server_config_flags(site_id, body.model_dump())
    )
    get_store().audit_portal_action(
        "admin.config.saved",
        # `require_admin` statik kalit ishlatilganda `None` qaytaradi —
        # o'sha holatda audit yozuvi egasiz qoladi, bu mavjud naqsh.
        actor_id=admin.account_id if admin else None,
        target_type="site",
        target_id=site_id,
        detail={"zones": len(body.zones), "lines": len(body.lines)},
    )
    return updated


@app.post("/api/v1/admin/sites/{site_id}/cameras/{camera_id}/preview")
async def admin_request_camera_preview(
    site_id: str, camera_id: str, _: None = Depends(require_admin)
) -> Dict[str, Any]:
    """"Rasmni ko'rsat" — qurilma keyingi heartbeat'da bitta kadr yuboradi."""
    try:
        camera = get_store().request_camera_preview(site_id, camera_id)
        # Kutib turgan qurilma darhol javob olsin: usiz keyingi
        # "salom"gacha 60 soniyagacha ketardi.  Mexanizm jonli ko'rish
        # uchun yozilgan edi, lekin bu yerda chaqirilmagan.
        _wake_live_watchers(site_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"camera": camera, "wait_sec": PREVIEW_WAIT_HINT_SEC}


@app.get("/api/v1/admin/sites/{site_id}/cameras/{camera_id}/preview")
async def admin_camera_preview(
    site_id: str, camera_id: str, _: None = Depends(require_admin)
) -> Response:
    return await _camera_preview_response(site_id, camera_id)


@app.get("/api/v1/admin/sites/{site_id}/cameras/{camera_id}/live-frame")
async def admin_camera_live_frame(
    site_id: str, camera_id: str, _: None = Depends(require_admin)
) -> Response:
    """Jonli oqimning oxirgi kadri.

    Jonli ko'rish tayanch kadrdan ajratilgach shu endpoint SHART bo'ldi:
    `.../live` ni yoqish mumkin edi-yu, natijasini ko'rishning yo'li
    qolmasdi.
    """
    return await _camera_preview_response(site_id, camera_id, live=True)


@app.post("/api/v1/admin/sites/{site_id}/cameras/{camera_id}/live")
async def admin_request_live(
    site_id: str,
    camera_id: str,
    body: Optional[LiveRequestBody] = None,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    """Jonli ko'rish — mijoz panelidagi bilan bir xil mexanizm.

    Video oqim emas: qurilma har 2-3 soniyada bitta JPEG yuboradi.
    Chiziqni to'g'ri joyga qo'yish uchun kadrni ko'rish shart.
    """
    try:
        until = get_store().request_live(site_id, camera_id, overlay=bool(body and body.overlay))
        _wake_live_watchers(site_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"ok": True, "until": until, "first_frame_wait_sec": 25}


# Eslatma: bu yerda ilgari `/discover-cameras` (admin va installer varianti)
# bor edi.  U **VPS konteynerining o'z tarmog'ini** skanerlardi — do'kon
# tarmog'ini emas, ya'ni hech qachon kamera topa olmasdi; ustiga
# autentifikatsiyalangan port-scan primitivi edi.  To'g'ri qidiruv
# qurilmaning o'zida: `chaqimchi_ai/local/app.py` (`/api/setup/auto-find`)
# va `chaqimchi_ai/sotqin_agent.py` (`/api/v1/discover-cameras`).


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
    cameras = get_store().list_cameras(site_id)
    cameras_configured = bool(cameras)
    cameras_seen = int(detail["cameras_expected"] or 0) > 0
    previews_confirmed = bool(cameras) and all(camera["has_preview"] for camera in cameras)
    # Chiziqsiz `line_crossed` chiqmaydi, ya'ni kirganlar sanalmaydi va
    # konversiya hisoblanmaydi.  Shu sabab bu ham qadam: progress bar
    # chiziq chizilmasdan 100% ga yetmasin.
    site_config = get_event_store().get_site_config(site_id)["config"]
    geometry_drawn = bool(site_config.get("lines")) or bool(site_config.get("zones"))
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
        {
            "key": "preview",
            "label": "Har kameraning rasmi tekshirildi",
            "done": previews_confirmed,
        },
        {
            "key": "geometry",
            "label": "Chiziq va zona chizildi",
            "done": geometry_drawn,
        },
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
        dl_base = urls.dl_url() or origin
        api_base = urls.api_url() or origin
        install_command = (
            f"curl -fsSL {dl_base}/downloads/sotqin-installer.sh | "
            f"sudo bash -s -- --cloud {api_base} --code {active_code['code']}"
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


async def _camera_preview_response(
    site_id: str, camera_id: str, *, live: bool = False
) -> Response:
    """Kameraning oxirgi kadri.  Hali kelmagan bo'lsa 404.

    `live=False` — TAYANCH kadr: bir marta so'ralib olinadi va xarita
    foni, zona muharriri, kamera kartochkasi o'shani ishlatadi.
    `live=True` — jonli oqimning oxirgi kadri; u tez o'zgaradi va
    tayanchni almashtirmasligi kerak.

    Rasm hech qachon to'g'ridan-to'g'ri obyekt saqlagichdan berilmaydi —
    faqat autentifikatsiyadan o'tgan so'rov orqali, `site_id` esa
    chaqiruvchining o'z tokenidan olinadi.
    """
    store = get_store()
    key = (
        store.camera_live_key(site_id, camera_id)
        if live
        else store.camera_preview_key(site_id, camera_id)
    )
    if not key:
        raise HTTPException(404, "Kamera rasmi hali yuborilmagan")
    try:
        content = await media_get(key)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Kamera rasmi topilmadi") from exc
    # Kamera qayta qaratilganda eski rasm ko'rinib qolmasin.
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


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


@app.post("/api/v1/installer/sites/{site_id}/cameras/{camera_id}/preview")
async def installer_request_camera_preview(
    site_id: str,
    camera_id: str,
    installer: PortalPrincipal = Depends(require_active_installer),
) -> Dict[str, Any]:
    """ "Rasmni ko'rsat" — qurilma keyingi heartbeat'da bitta kadr yuboradi."""
    _require_installer_site(installer, site_id)
    try:
        camera = get_store().request_camera_preview(site_id, camera_id)
        _wake_live_watchers(site_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"camera": camera, "wait_sec": PREVIEW_WAIT_HINT_SEC}


@app.get("/api/v1/installer/sites/{site_id}/config")
async def installer_get_config(
    site_id: str,
    installer: PortalPrincipal = Depends(require_active_installer),
) -> Dict[str, Any]:
    _require_installer_site(installer, site_id)
    return get_event_store().get_site_config(site_id)


@app.put("/api/v1/installer/sites/{site_id}/config")
async def installer_update_config(
    site_id: str,
    body: SiteConfigBody,
    installer: PortalPrincipal = Depends(require_active_installer),
) -> Dict[str, Any]:
    """Chiziq va zonani obyektda o'rnatuvchi chizadi.

    Bu ish do'kon egasiga tushmasligi kerak: chiziq kadr ustida, kamera
    o'rnatilgan joydan turib chiziladi.  Ilgari uni kiritishning yagona yo'li
    owner panelidagi xom JSON maydoni edi — ya'ni amalda hech kim chizmasdi
    va `line_crossed` hech qachon chiqmasdi.
    """
    _require_installer_site(installer, site_id)
    _validate_site_config(body)
    updated = get_event_store().update_site_config(
        site_id, _preserve_server_config_flags(site_id, body.model_dump())
    )
    get_store().audit_portal_action(
        "installer.config.saved",
        actor_id=installer.account_id,
        target_type="site",
        target_id=site_id,
        detail={"zones": len(body.zones), "lines": len(body.lines)},
    )
    return updated


@app.get("/api/v1/installer/sites/{site_id}/cameras/{camera_id}/preview")
async def installer_camera_preview(
    site_id: str,
    camera_id: str,
    installer: PortalPrincipal = Depends(require_active_installer),
) -> Response:
    _require_installer_site(installer, site_id)
    return await _camera_preview_response(site_id, camera_id)


@app.get("/api/v1/owner/cameras/{camera_id}/preview")
async def owner_camera_preview(
    camera_id: str,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Response:
    return await _camera_preview_response(owner.site_id, camera_id)


@app.post("/api/v1/owner/cameras/{camera_id}/preview")
async def owner_request_camera_preview(
    camera_id: str,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    """Mijoz kadrni O'ZI so'raydi.

    Bungacha bu tugma faqat admin va o'rnatuvchida bor edi.  Ustasiz
    ochilgan do'konda kadr HECH QACHON kelmasdi va panelda "rasm hali
    kelmagan" degan yozuv boshi berk ko'cha bo'lardi — mijozda uni
    tuzatadigan birorta tugma yo'q edi.

    Rol talab qilinmaydi (`owner_request_live` bilan bir xil): kadrni
    ko'rish sozlamani o'zgartirish emas.

    Chegara SHART: yuklash tomonidagi kunlik byudjet 96 ta kadr
    (`upload_camera_preview`) — cheklovsiz tugma uni bir daqiqada yeb
    qo'yardi va bot `/kamera` buyrug'i ishlamay qolardi.
    """
    ratelimit.check(
        "owner-preview",
        owner.site_id,
        limit=30,
        window_sec=3600,
        message="Juda ko'p rasm so'raldi. Bir soatdan keyin urinib ko'ring.",
    )
    try:
        camera = get_store().request_camera_preview(owner.site_id, camera_id)
        _wake_live_watchers(owner.site_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"camera": camera, "wait_sec": PREVIEW_WAIT_HINT_SEC}


@app.get("/api/v1/owner/cameras/{camera_id}/live-frame")
async def owner_camera_live_frame(
    camera_id: str,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Response:
    """Jonli oqimning oxirgi kadri — tayanch kadrga tegmaydi."""
    return await _camera_preview_response(owner.site_id, camera_id, live=True)


@app.post("/api/v1/owner/cameras/{camera_id}/live")
async def owner_request_live(
    camera_id: str,
    body: Optional[LiveRequestBody] = None,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    """Jonli ko'rishni yoqadi (90 s; panel ochiq ekan qayta chaqiradi).

    Video oqim emas: qurilma har 2-3 soniyada bitta JPEG yuboradi, panel
    esa preview endpointini o'sha tezlikda qayta o'qiydi.  Zaif do'kon
    kompyuteri va VPS uchun eng arzon "jonli" — kadr allaqachon tahlil
    uchun xotirada turadi, faqat siqib yuboriladi.
    """
    try:
        until = get_store().request_live(
            owner.site_id, camera_id, overlay=bool(body and body.overlay)
        )
        _wake_live_watchers(owner.site_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    # Birinchi kadrgacha kutish: qurilma so'rovni keyingi heartbeat'da
    # ko'radi (20 soniyagacha).
    return {
        "ok": True,
        "until": until,
        "overlay": bool(body and body.overlay),
        "first_frame_wait_sec": 25,
    }


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
        detail = get_store().site_detail(site_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    # Qurilma diagnostikasi admin panelida KO'RINSIN.  Bungacha
    # heartbeat'dagi raqamlar (tashlangan hodisalar, klip hisoblagichlari,
    # zanjirning qayta ishga tushishlari) faqat bazada yotardi va
    # do'kondagi nosozlikni faqat SSH bilan ko'rish mumkin edi.
    health = {item["device_id"]: item for item in get_event_store().health(site_id)}
    for device in detail.get("devices") or []:
        record = health.get(device.get("id")) or health.get(device.get("device_id"))
        if record:
            device["health"] = record.get("health") or {}
            device["health_at"] = record.get("received_at")
    # Chegara tufayli rad etilgan so'rovlar — shu obyekt kesimida.
    #
    # `snapshots`/`face-snapshots` noldan katta bo'lsa mijoz RASMSIZ
    # qolyapti.  2026-08-26 da aynan shu holat 3 soat sezilmadi: yagona
    # izi `INFO` access log edi va uni hech kim o'qimasdi.
    detail["rate_limited"] = ratelimit.limiter().rejections(site_id)
    return detail


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
    admin: Optional[PortalPrincipal] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        result = get_store().extend_subscription(site_id, body.months)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    # Pul bilan bog'liq amal: mijoz "men to'lamaganman" desa, kim va
    # qachon muddat qo'shganini ko'rsata olishimiz kerak.
    get_store().audit_portal_action(
        "site.subscription.extended",
        actor_id=_audit_actor(admin),
        target_type="site",
        target_id=site_id,
        detail={"months": body.months, "until": result.get("until")},
    )
    return result


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


#: Bir vaqtda ulanishni kutayotgan qurilmalar chegarasi.  Cheklovsiz
#: soxta `fingerprint` bilan bazani to'ldirish mumkin edi.
PENDING_DEVICE_LIMIT_DEFAULT = 200


def _pending_device_limit() -> int:
    raw = os.environ.get("CHAQIMCHI_PENDING_DEVICE_LIMIT", "").strip()
    try:
        return max(1, int(raw)) if raw else PENDING_DEVICE_LIMIT_DEFAULT
    except ValueError:
        logger.warning("CHAQIMCHI_PENDING_DEVICE_LIMIT son emas — standart qiymat")
        return PENDING_DEVICE_LIMIT_DEFAULT


def _device_hello_enabled() -> bool:
    """Yangi ulanish oqimini bir zumda o'chirish uchun bayroq.

    Qurilmadagi dastur bu endpoint 404 qaytarsa ESKI yo'lga (sehrgar +
    pairing kodi) tushadi.  Ya'ni yangi reliz tarqab bo'lgach ham
    nosozlik chiqsa, bayroqni o'chirish butun parkni eski, sinalgan
    xatti-harakatga qaytaradi — OTA kutish shart emas.
    """
    raw = os.environ.get("CHAQIMCHI_DEVICE_HELLO", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


@app.post("/api/v1/public/device-hello")
async def public_device_hello(body: DeviceHelloBody, request: Request) -> Dict[str, Any]:
    """Qurilma o'zini tanishtiradi va ulanish havolasini oladi.

    Pairing kodidan farqi yo'nalishda: kodni admin yoki usta yaratib
    egaga berardi, bu yerda esa qurilmaning o'zi boshlaydi va egasi uni
    panelidan ko'rib tasdiqlaydi.  Shu bilan "dasturni o'rnatdim, endi
    kimdan kod so'rayman?" degan tugun yo'qoladi.
    """
    if not _device_hello_enabled():
        raise HTTPException(404, "Topilmadi")
    client_host = request.client.host if request.client else "unknown"
    # Ikki o'lchov: bitta IP ortida do'kon tarmog'i bo'lishi mumkin
    # (bir necha kompyuter), lekin bitta kompyuter soatiga o'nlab
    # marta qayta ulanmaydi.
    ratelimit.check(
        "device-hello",
        client_host,
        limit=12,
        window_sec=3_600,
        message="Juda ko'p urinish. Bir soatdan keyin qayta urinib ko'ring.",
    )
    ratelimit.check(
        "device-hello-fp",
        body.fingerprint,
        limit=30,
        window_sec=3_600,
        message="Juda ko'p urinish. Bir soatdan keyin qayta urinib ko'ring.",
    )
    if get_store().count_pending_devices() >= _pending_device_limit():
        raise HTTPException(503, "Hozir yangi ulanishlar qabul qilinmayapti — birozdan keyin urining")

    result = get_store().device_hello(
        fingerprint=body.fingerprint,
        label=body.label.strip(),
        product_name=body.product_name,
        app_version=body.app_version,
        os_name=body.os_name,
        local_ip=body.local_ip,
    )
    panel = f"{urls.app_url()}/owner"
    return {
        "ok": True,
        "pending_id": result["pending_id"],
        "status": "pending",
        "connect_token": result["connect_token"],
        "connect_url": f"{panel}?connect={result['connect_token']}",
        "panel_url": panel,
        "verify_code": result["verify_code"],
        "expires_in_sec": CloudStore.CONNECT_TOKEN_TTL_SEC,
        "poll_after_sec": 5,
    }


@app.get("/api/v1/public/device-connect")
async def public_device_connect(token: str, request: Request) -> Dict[str, Any]:
    """Tasdiqdan oldin qurilmani tasvirlaydi.

    Autentifikatsiyasiz, shuning uchun bu yerdan faqat ko'z bilan
    solishtirish uchun kerak bo'lgan narsa chiqadi: kompyuter nomi va
    tekshiruv kodi.  Noma'lum, eskirgan va allaqachon ulangan token —
    hammasi BIR XIL 404: aks holda bu endpoint "bu token haqiqiymi?"
    degan savolga javob beradigan orakulga aylanardi.
    """
    if not _device_hello_enabled():
        raise HTTPException(404, "Topilmadi")
    ratelimit.check(
        "device-connect-peek",
        request.client.host if request.client else "unknown",
        limit=60,
        window_sec=3_600,
        message="Juda ko'p so'rov. Birozdan keyin urinib ko'ring.",
    )
    found = get_store().peek_pending_device(token)
    if not found:
        raise HTTPException(404, "Ulanish havolasi topilmadi yoki eskirgan")
    return {"ok": True, **found}


@app.post("/api/v1/owner/devices/claim")
async def owner_claim_device(
    body: DeviceClaimBody,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    """Egasi kutayotgan kompyuterni o'z filialiga biriktiradi.

    Sayt SESSIYADAN olinadi (`owner.site_id`), so'rovdan emas — shu
    sabab o'g'irlangan token bilan ham begona do'konga qurilma
    biriktirib bo'lmaydi.
    """
    require_owner_role(owner, "owner", "service_admin")
    ratelimit.check(
        "owner-device-claim",
        owner.member_id,
        limit=10,
        window_sec=3_600,
        message="Juda ko'p urinish. Bir soatdan keyin qayta urinib ko'ring.",
    )
    try:
        result = get_store().approve_pending_device(
            body.connect_token, site_id=owner.site_id, account_id=owner.member_id
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    get_store().audit_portal_action(
        "owner.device.claimed",
        actor_id=owner.member_id,
        target_type="pending_device",
        target_id=result["pending_id"],
        detail={"site_id": owner.site_id, "label": result["label"]},
    )
    return {"ok": True, **result}


@app.post("/api/v1/public/device-handover")
async def public_device_handover(body: DeviceHandoverBody, request: Request) -> Dict[str, Any]:
    """Qurilma tasdiqni kutadi va hisob ma'lumotlarini oladi.

    Qurilma buni sekundlab so'raydi, shuning uchun cheklov keng.
    `fingerprint` qatordagisiga mos kelmasa — 404: token sizib ketgan
    bo'lsa ham uni boshqa mashinada ishlatib bo'lmaydi.
    """
    if not _device_hello_enabled():
        raise HTTPException(404, "Topilmadi")
    ratelimit.check(
        "device-handover",
        body.fingerprint,
        limit=400,
        window_sec=3_600,
        message="Juda ko'p so'rov.",
    )
    try:
        result = get_store().handover_pending_device(body.connect_token, body.fingerprint)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    if result.get("status") == "claimed":
        result = {**result, "cloud_url": urls.api_url(), "panel_url": f"{urls.app_url()}/owner"}
    else:
        result = {**result, "poll_after_sec": 5}
    return {"ok": True, **result}


@app.post("/api/v1/devices/claim")
@app.post("/api/v1/sotqin/claim")
async def claim_device(body: ClaimDeviceBody, request: Request) -> Dict[str, str]:
    # Bu endpoint ataylab autentifikatsiyasiz (qurilmada hali token yo'q),
    # shuning uchun IP bo'yicha cheklov shart: pairing kod 6 hex belgi va
    # 48 soat yashaydi — cheklovsiz uni qo'pol kuch bilan topish mumkin,
    # topilgan kod esa begona do'kon uchun doimiy qurilma tokenini (va u
    # orqali kamera RTSP parollarini) beradi.  Halol qurilma bitta-ikkita
    # so'rov qiladi, limitga hech qachon urilmaydi.
    client_host = request.client.host if request.client else "unknown"
    ratelimit.check(
        "device-claim",
        client_host,
        limit=10,
        window_sec=600,
        message="Juda ko'p urinish. 10 daqiqadan keyin qayta urinib ko'ring.",
    )
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
    # Har bir event ALOHIDA tekshiriladi (`EventBatchBody` izohiga qarang):
    # buzuqlari `accepted` ga kirmaydi va edge ularni yolg'iz dead_letter
    # qiladi — sog'lom eventlar yo'qolmaydi.
    valid_events: List[EdgeEvent] = []
    rejected: List[str] = []
    for raw in body.events:
        try:
            valid_events.append(EdgeEvent.model_validate(raw))
        except ValidationError:
            event_id = str(raw.get("event_id", "")) if isinstance(raw, dict) else ""
            rejected.append(event_id)
    if rejected:
        logger.warning(
            "Batch'da %d ta yaroqsiz event rad etildi (qurilma %s): %s",
            len(rejected),
            device["device_id"],
            ", ".join(filter(None, rejected[:5])) or "id'siz",
        )
    # Media olinmaydigan hodisada "rasm bor" bayrog'ini O'CHIRAMIZ.
    #
    # Bayroq qurilmaning DA'VOSI bilan keladi va u eski qurilmalarda
    # `true` bo'lib turaveradi.  Rasm esa saqlanmaydi (`MEDIALESS_EVENTS`).
    # Tozalanmasa panel "rasm bor" deb ko'rsatib, mijoz bosganda 404
    # olardi — ya'ni bazadagi ma'lumot yolg'on bo'lardi.
    for event in valid_events:
        if event.event_type in MEDIALESS_EVENTS:
            event.has_snapshot = False
    existing = event_store.existing_event_ids(
        device["site_id"], [event.event_id for event in valid_events]
    )
    accepted = event_store.ingest(device["site_id"], device["device_id"], valid_events)
    new_events = [event for event in valid_events if event.event_id not in existing]
    # Butun batch uchun **bitta** yig'ma xabar. Har event uchun alohida yuborish
    # 500 talik batchda botni Telegram limitiga urib, xabarni butunlay
    # yo'qotardi — batafsili `cloud/notify.py` da.  Tormoz bazada turadi:
    # xotiradagisi har deploy'da nolga qaytib, xabar bo'roni berardi.
    # Xabar imkon bo'lsa hodisa RASMI bilan ketadi (`_notify_alert`).
    allowed = select_alert_events(
        device["site_id"],
        new_events,
        throttle_service=_durable_throttle,
        level=_telegram_level(device["site_id"]),
    )
    if allowed:
        background_tasks.add_task(_notify_alert, device["site_id"], allowed)
    return {"ok": True, "accepted": accepted, "rejected": rejected}


@app.put("/api/v1/edge/events/{event_id}/snapshot")
async def upload_event_snapshot(
    event_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    device: Dict[str, Any] = Depends(require_device),
) -> Dict[str, Any]:
    event = get_event_store().event(device["site_id"], event_id)
    if not event or event["device_id"] != device["device_id"]:
        raise HTTPException(404, "Event topilmadi")

    # Media olinmaydigan hodisa: 200 qaytariladi, lekin rasm SAQLANMAYDI
    # va kunlik chegara ham SARFLANMAYDI.
    #
    # 4xx EMAS — `cloud_sync.py:142` da yuklash xatosi butun hodisani
    # `outbox.fail()` ga tashlaydi va u 20 marta qayta yuboriladi, oxirida
    # esa hodisaning O'ZI dead_letter'ga tushib yo'qoladi.  Ya'ni rad javob
    # bizga kerakli ma'lumotni ham o'ldirardi.  Xuddi `edge/heatmap` dagi
    # kabi: qabul qilamiz, yozmaymiz.
    #
    # Chegara tekshiruvi ataylab shu tekshiruvdan KEYIN: aks holda
    # tashlab yuboriladigan rasm kunlik 500 talik byudjetni yeb qo'yardi —
    # muammoning o'zi shu edi.
    if event["event_type"] in MEDIALESS_EVENTS:
        return {"ok": True, "stored": False}

    if event["event_type"] == "employee_seen":
        # `employee_seen` — moslash NATIJASI, media'siz qoladi.  Yuz kadri
        # faqat `face_captured` orqali keladi va davomat darvozasi ortida.
        raise HTTPException(
            403,
            "Davomat biometrik snapshotlari cloudga yuklanmaydi",
        )
    face_capture = event["event_type"] == "face_captured"
    # Chegara IKKIGA BO'LINGAN va yuz kadri umumiy byudjetni SARFLAMAYDI.
    #
    # Ilgari `snapshots` (500) tekshiruvi eng birinchi turardi, ya'ni yuz
    # kadri avval umumiy byudjetdan yeb, keyin o'z chegarasiga tegardi.
    # 2026-08-26 da jonli do'konda oqibati shu bo'ldi: 45 daqiqada 399 ta
    # `face_captured` umumiy 500 talik byudjetning 78% ini yedi, qolgani
    # 20 daqiqada tugadi va SHUNDAN KEYIN do'konning hamma hodisasi —
    # navbat, dwell, chiziq — rasmsiz qoldi (har yuklash 429).
    #
    # Endi ikki oqim bir-birini och qoldira olmaydi: davomat qanchalik
    # toshib ketmasin, do'kon hodisalarining rasmi o'z byudjetida qoladi.
    if face_capture:
        if not _attendance_enabled():
            raise HTTPException(403, "Davomat piloti yoqilmagan")
        # Yuz kadrlari uchun alohida, qattiqroq chegara: davomat kamerasi
        # kuniga yuzlab kadr yubormasligi kerak (qurilma o'zi debounce
        # qiladi, bu — buzilgan qurilmadan himoya).
        ratelimit.check(
            "face-snapshots",
            device["site_id"],
            limit=200,
            window_sec=86_400,
            message="Kunlik yuz kadrlari chegarasi oshdi",
        )
    else:
        # Snapshot 8 MB gacha bo'lishi mumkin — kunlik chegara S3 hisobini va
        # diskni bitta buzuq qurilmadan himoya qiladi.
        ratelimit.check(
            "snapshots",
            device["site_id"],
            limit=500,
            window_sec=86_400,
            message="Kunlik snapshot chegarasi oshdi",
        )
    if request.headers.get("content-type", "").split(";", 1)[0] != "image/jpeg":
        raise HTTPException(415, "Faqat image/jpeg qabul qilinadi")
    content = await request.body()
    if not content:
        raise HTTPException(400, "Snapshot bo'sh")
    if len(content) > SNAPSHOT_MAX_BYTES:
        raise HTTPException(413, "Snapshot 8 MB dan katta")
    key = (
        f"{device['site_id']}/faces/{event_id}.jpg"
        if face_capture
        else f"{device['site_id']}/{event_id}.jpg"
    )
    await media_put(key, content, content_type="image/jpeg")
    get_event_store().set_snapshot(device["site_id"], event_id, key, size_bytes=len(content))
    if face_capture:
        background_tasks.add_task(
            _process_face_capture, device["site_id"], device["device_id"], event_id
        )
    return {"ok": True, "event_id": event_id}


async def _process_face_capture(site_id: str, device_id: str, event_id: str) -> None:
    """Kelgan yuz kadrini xodimlar bilan solishtiradi.

    Moslik topilsa server tomonda `employee_seen` yoziladi — davomat
    hisoboti shu hodisadan o'zgarishsiz ishlayveradi.  Topilmasa kadr
    galereyada "notanish" bo'lib qoladi va 14 kunda o'chadi.
    """
    ok, reason = faces.available()
    if not ok:
        logger.warning("Yuz kadri qayta ishlanmadi (site=%s): %s", site_id, reason)
        return
    store = get_event_store()
    event = store.event(site_id, event_id)
    if not event or not event.get("snapshot_key"):
        return
    try:
        content = await media_get(str(event["snapshot_key"]))
    except FileNotFoundError:
        return
    try:
        # Aniqlash + embedding CPUda ~0.5 s — event loop bandligiga yo'l
        # qo'ymaslik uchun alohida thread'da.
        embedding = await asyncio.to_thread(faces.get_face_service().embed_jpeg, content)
    except Exception:
        logger.exception("Yuz kadrida xato: site=%s event=%s", site_id, event_id)
        return
    if embedding is None:
        store.set_face_result(site_id, event_id, matched=False, note="yuz topilmadi")
        return
    candidates = []
    stale = 0
    current_dim = faces.current_embedding_dim()
    for row in store.face_embeddings(site_id):
        # Eski modeldan qolgan yozuv (512 o'lchamli ArcFace) — moslashga
        # kiritilmaydi.  Rasmlar saqlanib turibdi, ular
        # `scripts/reembed_faces.py` bilan qayta hisoblanadi.
        if int(row.get("embedding_dim") or 0) != current_dim:
            stale += 1
            continue
        try:
            candidates.append(
                (str(row["employee_id"]), faces.decrypt_embedding(row["embedding_b64"]))
            )
        except Exception:  # pragma: no cover - buzuq yozuv moslashni to'xtatmasin
            logger.warning("Embedding o'qilmadi: site=%s", site_id, exc_info=True)
    if stale:
        logger.warning(
            "site=%s: %d ta xodim rasmi eski modeldan — qayta hisoblang "
            "(scripts/reembed_faces.py)",
            site_id,
            stale,
        )
    result = faces.FaceService.match(embedding.vector, candidates)
    if result is None:
        store.set_face_result(site_id, event_id, matched=False)
        return
    employee_id, score = result
    store.set_face_result(
        site_id, event_id, matched=True, employee_id=employee_id, score=round(score, 3)
    )
    seen = EdgeEvent(
        event_type="employee_seen",
        camera_id=event.get("camera_id"),
        severity="info",
        person_id=employee_id,
        score=round(score, 3),
        occurred_at=event.get("occurred_at"),
        # track_id ham ko'chiriladi: xodimni kirdi-chiqdi sonidan,
        # soatlik grafikdan va demografiyadan chiqarib tashlash aynan
        # (kamera, trek) juftligi orqali bo'ladi.
        track_id=event.get("track_id"),
        metadata={"source_event_id": event_id},
    )
    store.ingest(site_id, device_id, [seen])


@app.put("/api/v1/edge/events/{event_id}/clip")
async def upload_event_clip(
    event_id: str,
    request: Request,
    device: Dict[str, Any] = Depends(require_device),
) -> Dict[str, Any]:
    event = get_event_store().event(device["site_id"], event_id)
    if not event or event["device_id"] != device["device_id"]:
        raise HTTPException(404, "Event topilmadi")
    # Snapshot yo'lidagi bilan SIMMETRIK: media olinmaydigan hodisaning
    # klipi ham saqlanmaydi va kunlik 100 talik chegarani YEMAYDI.
    # Avval bu guard faqat snapshotda edi — eski qurilmalar loitering
    # klipini yuklab kvotani behuda sarflardi.  200 qaytadi (4xx emas):
    # rad javob edge'da butun hodisani dead_letter'ga olib borardi.
    if event["event_type"] in MEDIALESS_EVENTS:
        return {"ok": True, "stored": False}
    ratelimit.check(
        "event-clips",
        device["site_id"],
        limit=100,
        window_sec=86_400,
        message="Kunlik videoklip chegarasi oshdi",
    )
    if event["event_type"] == "employee_seen":
        raise HTTPException(403, "Davomat biometrik videolari cloudga yuklanmaydi")
    if request.headers.get("content-type", "").split(";", 1)[0] != "video/mp4":
        raise HTTPException(415, "Faqat video/mp4 qabul qilinadi")
    content = await request.body()
    if not content:
        raise HTTPException(400, "Videoklip bo'sh")
    if len(content) > CLIP_MAX_BYTES:
        raise HTTPException(413, "Videoklip 50 MB dan katta")
    key = f"{device['site_id']}/{event_id}.mp4"
    await media_put(key, content, content_type="video/mp4")
    get_event_store().set_clip(device["site_id"], event_id, key, size_bytes=len(content))
    return {"ok": True, "event_id": event_id}


#: Qurilma soati serverdan shuncha soniyadan ko'p farq qilsa — muammo.
#:
#: 300 s (5 daqiqa) ataylab: ONVIF autentifikatsiyasi ham shu atrofda
#: buziladi (`local/onvif_client.py`), ya'ni bu chegaradan oshgan
#: qurilmada kamera ulanishi ham ishonchsiz bo'ladi.
CLOCK_SKEW_WARN_SEC = 300


def _clock_skew_seconds(device_clock: Optional[str]) -> Optional[float]:
    """Qurilma soati serverdan necha soniya farq qiladi.

    `None` — qurilma soatini yubormagan (eski versiya).  Buni nol deb
    hisoblash xato bo'lardi: "farq yo'q" bilan "bilmaymiz" bir narsa
    emas va ikkinchisiga ogohlantirish chiqarib bo'lmaydi.

    Ishora saqlanadi: musbat — qurilma OLDINDA, manfiy — ORQADA.
    Sabab boshqa-boshqa (kelajakdagi soat odatda noto'g'ri timezone,
    orqadagi soat esa o'lgan CMOS batareyasi), shuning uchun ustaga
    qaysi tomonga adashganini aytish kerak.
    """
    if not device_clock:
        return None
    try:
        stamp = datetime.fromisoformat(device_clock.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return round((stamp - datetime.now(timezone.utc)).total_seconds(), 1)


@app.post("/api/v1/edge/heartbeat")
@app.post("/api/v1/sotqin/heartbeat")
async def edge_health_heartbeat(
    body: EdgeHeartbeatBody,
    device: Dict[str, Any] = Depends(require_device),
) -> Dict[str, Any]:
    health = body.model_dump()
    health["clock_skew_sec"] = _clock_skew_seconds(body.device_clock)
    get_event_store().record_health(device["site_id"], device["device_id"], health)
    # Legacy connection monitoring ham yangi heartbeat bilan yangilanadi.
    get_store().heartbeat(
        device["site_id"],
        device["device_token"],
        active_cameras=body.cameras_active,
    )
    # Qurilmadagi versiya saqlanadi: masofadan yangilash chiqarilgach
    # admin panelda "qaysi do'kon qaysi versiyada" ko'rinishi kerak,
    # aks holda rolloutni kuzatib bo'lmaydi.
    get_store().record_device_version(device["device_id"], body.app_version)
    # Qurilma har daqiqada `/config` ni to'liq tortib olardi — kuniga 1440 ta
    # og'ir so'rov, javob esa deyarli har doim bir xil. Endi javobdagi shu
    # bitta son qurilmaga o'zgarish bor-yo'qligini aytadi.
    revision = get_event_store().config_revision(device["site_id"])

    # Qurilma kutishga tayyor bo'lsa va hozir ish yo'q bo'lsa — jonli
    # ko'rish so'ralishini kutamiz.  So'ralishi bilan darhol qaytamiz.
    #
    # Kutish bazani so'rab turmaydi (`_live_wakeups` — xotirada).  Kutish
    # tugagach ro'yxat BIR MARTA qayta o'qiladi: shu oraliqda so'ralgan
    # bo'lsa u ham tushadi.
    live = get_store().live_cameras(device["site_id"])
    previews = get_store().pending_preview_cameras(device["site_id"])
    jobs = get_store().take_pending_jobs(device["site_id"])
    if body.wait_sec and not live and not previews and not jobs:
        wakeup = _live_wakeup(device["site_id"])
        wakeup.clear()
        try:
            await asyncio.wait_for(wakeup.wait(), timeout=float(body.wait_sec))
        except asyncio.TimeoutError:
            pass
        else:
            live = get_store().live_cameras(device["site_id"])
            previews = get_store().pending_preview_cameras(device["site_id"])
            jobs = get_store().take_pending_jobs(device["site_id"])

    # Ovoz navbati HAR heartbeat'da o'qiladi (uzoq kutishdan tashqarida
    # ham): eski qurilma `wait_sec` yubormaydi va u ham ovozni olishi kerak.
    speak = get_store().take_pending_speak(device["site_id"])

    return {
        "ok": True,
        "config_revision": revision,
        "config_changed": body.config_revision != revision,
        # O'rnatuvchi rasm so'ragan kameralar. Bu ataylab config revizyasi
        # orqali kelmaydi: revizya o'zgarsa retail xizmati o'zini qayta ishga
        # tushiradi (`restart_on_config_change`), ya'ni har "rasmni ko'rsat"
        # bosilganda do'kon analitikasi bir necha soniyaga uzilardi.
        "preview_requested": previews,
        # Jonli ko'rish: panel ochiq turgan kameralar. Muddat bilan keladi —
        # qurilma muddati o'tguncha har 2-3 soniyada kadr yuboradi.
        "live_requested": live,
        # Karnaydan aytiladigan iboralar.  O'qish bilan birga "yetkazildi"
        # deb belgilanadi — ikkita heartbeat ketma-ket kelsa bir xil
        # ibora ikki marta yangramaydi.
        "speak_requested": speak,
        # Tarmoqni skanerlash kabi topshiriqlar.  Ular do'kon
        # tarmog'idan bajarilishi SHART (multicast, xususiy IP), lekin
        # boshlanishi bulutdagi tugmadan.  O'qish bilan "olindi" deb
        # belgilanadi — ketma-ket kelgan ikki heartbeat bir xil
        # skanerni ikki marta ishga tushirmasin.
        "job_requested": jobs,
        "received": body.model_dump(),
    }


class EdgeCameraItem(BaseModel):
    camera_id: str = Field(min_length=1, max_length=40)
    label: str = Field(default="", max_length=120)


class EdgeCamerasBody(BaseModel):
    #: Tarif chegarasi `register_device_cameras` da tekshiriladi; bu yerdagi
    #: chegara faqat buzuq qurilmadan himoya.
    cameras: List[EdgeCameraItem] = Field(default_factory=list, max_length=16)


@app.post("/api/v1/edge/cameras")
@app.post("/api/v1/sotqin/cameras")
async def edge_register_cameras(
    body: EdgeCamerasBody,
    device: Dict[str, Any] = Depends(require_device),
) -> Dict[str, Any]:
    """Qurilma o'zining kamera ro'yxatini cloudga bildiradi.

    Mijoz kamerani do'kon kompyuteridagi sehrgarda qo'shadi, cloudda esa
    kamera yozadigan yo'l faqat admin va o'rnatuvchi portalida edi.  Natijada
    o'zi ro'yxatdan o'tgan do'konda panel kameralarni umuman ko'rmasdi va
    to'rtta bo'lim (jonli ko'rish, xarita, davomat kamerasi, kamera rollari)
    jimgina bo'sh turardi.

    Manzil YUBORILMAYDI — faqat ID va nom (`register_device_cameras`).
    """
    try:
        cameras = get_store().register_device_cameras(
            device["site_id"], [item.model_dump() for item in body.cameras]
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "ok": True,
        "cameras": [
            {"camera_id": item["camera_id"], "label": item["label"], "origin": item["origin"]}
            for item in cameras
        ],
    }


@app.put("/api/v1/edge/cameras/{camera_id}/preview")
@app.put("/api/v1/sotqin/cameras/{camera_id}/preview")
async def upload_camera_preview(
    camera_id: str,
    request: Request,
    device: Dict[str, Any] = Depends(require_device),
) -> Dict[str, Any]:
    """Qurilma o'rnatuvchi so'ragan bitta kadrni yuboradi.

    Bu jonli video emas: faqat so'ralganda, kamera boshiga kuniga 24 martagacha.
    """
    ratelimit.check(
        "camera-preview",
        device["site_id"],
        limit=24 * GUARANTEED_CAMERAS,
        window_sec=86_400,
        message="Kunlik kamera rasmi chegarasi oshdi",
    )
    if request.headers.get("content-type", "").split(";", 1)[0] != "image/jpeg":
        raise HTTPException(415, "Faqat image/jpeg qabul qilinadi")
    content = await request.body()
    if not content:
        raise HTTPException(400, "Rasm bo'sh")
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(413, "Rasm 2 MB dan katta")
    key = f"{device['site_id']}/preview/{camera_id}.jpg"
    await media_put(key, content, content_type="image/jpeg")
    try:
        get_store().set_camera_preview(device["site_id"], camera_id, key)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return {"ok": True, "camera_id": camera_id}


class JobProgressBody(BaseModel):
    percent: int = Field(default=0, ge=0, le=100)
    note: str = Field(default="", max_length=200)


class JobResultBody(BaseModel):
    ok: bool = True
    error: str = Field(default="", max_length=300)
    result: Dict[str, Any] = Field(default_factory=dict)


@app.post("/api/v1/edge/jobs/{job_id}/progress")
async def edge_job_progress(
    job_id: str, body: JobProgressBody, device: Dict[str, str] = Depends(require_device)
) -> Dict[str, Any]:
    """Skaner o'z holatini xabar qiladi.

    Bu heartbeat halqasidan ALOHIDA keladi: skanerlash 90 soniyagacha
    cho'zilishi mumkin, heartbeat esa 25 soniyada javob berishi kerak.
    Ular bir halqada bo'lsa sayt "oflayn" bo'lib ko'rinardi.
    """
    ratelimit.check(
        "edge-job-progress",
        device["site_id"],
        limit=240,
        window_sec=3_600,
        message="Juda ko'p progress xabari",
    )
    if not get_store().job_progress(device["site_id"], job_id, percent=body.percent, note=body.note):
        raise HTTPException(404, "Topshiriq topilmadi yoki tugagan")
    return {"ok": True}


@app.put("/api/v1/edge/jobs/{job_id}/result")
async def edge_job_result(
    job_id: str, body: JobResultBody, device: Dict[str, str] = Depends(require_device)
) -> Dict[str, Any]:
    payload = json.dumps(body.result, ensure_ascii=False).encode("utf-8")
    if len(payload) > CloudStore.JOB_RESULT_MAX_BYTES:
        raise HTTPException(413, "Natija juda katta")
    if not get_store().job_result(
        device["site_id"], job_id, ok=body.ok, result=body.result, error=body.error
    ):
        raise HTTPException(404, "Topshiriq topilmadi yoki allaqachon yopilgan")
    return {"ok": True}


@app.put("/api/v1/edge/jobs/{job_id}/frame")
async def edge_job_frame(
    job_id: str, request: Request, device: Dict[str, str] = Depends(require_device)
) -> Dict[str, Any]:
    """Sinov kadri — hali saqlanmagan kamera uchun.

    `set_camera_preview` mavjud `site_cameras` qatorini talab qiladi;
    kamerani saqlashdan OLDIN tekshirish uchun bazaga chala qator
    yozish kerak bo'lardi.  Shuning uchun kadr topshiriq kalitiga
    yoziladi va kamera saqlangach oddiy preview oqimi davom etadi.
    """
    if request.headers.get("content-type", "").split(";", 1)[0] != "image/jpeg":
        raise HTTPException(415, "Faqat image/jpeg qabul qilinadi")
    content = await request.body()
    if not content:
        raise HTTPException(400, "Rasm bo'sh")
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(413, "Rasm 2 MB dan katta")
    key = f"{device['site_id']}/scan/{job_id}.jpg"
    await media_put(key, content, content_type="image/jpeg")
    if not get_store().job_frame_saved(device["site_id"], job_id, key):
        raise HTTPException(404, "Topshiriq topilmadi")
    return {"ok": True}


class HeatmapItem(BaseModel):
    camera_id: str = Field(min_length=1, max_length=40)
    #: UTC soat bucket'i, "2026-08-18T14" ko'rinishida.
    hour: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}$")
    grid: List[List[int]]
    frames: int = Field(default=0, ge=0, le=1_000_000)


class HeatmapBody(BaseModel):
    items: List[HeatmapItem] = Field(max_length=200)


@app.post("/api/v1/edge/heatmap")
@app.post("/api/v1/sotqin/heatmap")
async def upload_heatmap(
    body: HeatmapBody,
    device: Dict[str, Any] = Depends(require_device),
) -> Dict[str, Any]:
    """Kamera issiqlik to'rlari (soatlik, sonlar — rasm emas).

    Qurilma har 10 daqiqada yig'ib yuboradi; internet uzilsa fayllar
    diskda kutadi va keyin jamlanib keladi — shu sababli qabul ham
    JAMLAB yozadi (bir soat uchun bir necha kelishi normal).
    """
    ratelimit.check(
        "heatmap",
        device["site_id"],
        limit=600,
        window_sec=86_400,
        message="Kunlik issiqlik to'ri chegarasi oshdi",
    )
    # Tarifda xarita yo'q bo'lsa: 200 qaytariladi, lekin yozilmaydi.
    #
    # 403 EMAS.  Qurilmadagi outbox xatoni "keyin qayta yuboraman" deb
    # tushunadi va to'r fayllari diskda yig'ilib boraveradi — do'kon
    # kompyuterining diski to'ladi.  Rad javob mijozning kompyuterini
    # buzmasligi kerak.
    if not _panel_feature_open(device["site_id"], "xarita"):
        return {"ok": True, "accepted": 0}

    store = get_event_store()
    accepted = 0
    for item in body.items:
        grid = item.grid
        if len(grid) != store.HEATMAP_ROWS or any(len(row) != store.HEATMAP_COLS for row in grid):
            raise HTTPException(422, "To'r o'lchami 48×27 bo'lishi kerak")
        if any(cell < 0 or cell > 1_000_000 for row in grid for cell in row):
            raise HTTPException(422, "To'r qiymatlari chegaradan tashqarida")
        store.add_heatmap(
            device["site_id"], item.camera_id, item.hour, [list(row) for row in grid], item.frames
        )
        accepted += 1
    return {"ok": True, "accepted": accepted}


@app.get("/api/v1/owner/heatmap")
async def owner_heatmap(
    camera_id: str,
    date: Optional[str] = None,
    hour: Optional[int] = None,
    days: int = 1,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    """Panel xaritasi: kamera ko'rinishi bo'yicha odam-borligi to'ri.

    `days=7` — plan rejimi uchun haftalik yig'indi (odam yurmagan joylar
    jihoz sifatida qorayadi).
    """
    if not _panel_feature_open(owner.site_id, "xarita"):
        raise HTTPException(403, "Do'kon xaritasi Biznes tarifidan boshlab ishlaydi.")
    zone = ZoneInfo("Asia/Tashkent")
    try:
        day = date_type.fromisoformat(date) if date else datetime.now(zone).date()
    except ValueError as exc:
        raise HTTPException(422, "Sana YYYY-MM-DD ko'rinishida bo'lsin") from exc
    if hour is not None and not 0 <= hour <= 23:
        raise HTTPException(422, "Soat 0..23 oralig'ida")
    if not 1 <= days <= 30:
        raise HTTPException(422, "Kunlar 1..30 oralig'ida")
    return get_event_store().heatmap(owner.site_id, camera_id, day=day, hour=hour, days=days)


@app.put("/api/v1/edge/cameras/{camera_id}/live-frame")
@app.put("/api/v1/sotqin/cameras/{camera_id}/live-frame")
async def upload_live_frame(
    camera_id: str,
    request: Request,
    device: Dict[str, Any] = Depends(require_device),
) -> Dict[str, Any]:
    """Jonli ko'rish kadri (har 2-3 soniyada, panel ochiq ekan).

    Tayanch kadrdan ALOHIDA kalitga yoziladi.  Ilgari ikkalasi bitta
    kalitni bo'lishardi va oqibati ko'rinib turardi: mijoz jonli
    ko'rishni ochishi bilan do'kon xaritasining foni o'sha lahzadagi
    kadrga — odamlari va boshqa yorug'ligi bilan — almashib ketardi.
    Endi xarita va zona muharriri barqaror tayanch kadrni oladi.

    Limit alohida va saxiy: 2.5 soniyalik
    qadam bilan bu kuniga ~3 soat tomoshaga yetadi.  Javobdagi
    `continue` qurilmaga davom etish-etmaslikni aytadi — muddat panel
    tomonidan uzaytirilmasa oqim o'zi to'xtaydi.
    """
    ratelimit.check(
        "camera-live",
        device["site_id"],
        limit=4_000,
        window_sec=86_400,
        message="Kunlik jonli ko'rish chegarasi oshdi",
    )
    if request.headers.get("content-type", "").split(";", 1)[0] != "image/jpeg":
        raise HTTPException(415, "Faqat image/jpeg qabul qilinadi")
    content = await request.body()
    if not content:
        raise HTTPException(400, "Kadr bo'sh")
    if len(content) > 512 * 1024:
        # Jonli kadr 640px va past sifat — 512 KB ham ortig'i bilan yetadi.
        raise HTTPException(413, "Jonli kadr 512 KB dan katta")
    key = f"{device['site_id']}/live/{camera_id}.jpg"
    await media_put(key, content, content_type="image/jpeg")
    try:
        get_store().set_camera_live_frame(device["site_id"], camera_id, key)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return {
        "ok": True,
        "camera_id": camera_id,
        "continue": get_store().live_active(device["site_id"], camera_id),
    }


@app.get("/api/v1/edge/update")
async def edge_update(
    request: Request,
    device: Dict[str, Any] = Depends(require_device),
) -> Dict[str, Any]:
    """Qurilma uchun mavjud yangilanish.

    Qurilma o'z versiyasini `current` da yuboradi va javobdagi
    `available` ni ko'radi.  Qaror **qurilmada** qabul qilinadi: u
    manifestni Ed25519 bilan tekshiradi va faqat shundan keyin o'rnatadi.
    Cloud buzilgan taqdirda ham imzosiz paket qabul qilinmaydi.
    """
    release = latest_windows_release()
    policy = get_store().update_policy(device["site_id"])
    base = urls.dl_url().rstrip("/") or str(request.base_url).rstrip("/")

    # Global to'xtatuvchi.  Buzuq reliz chiqib ketsa uni har do'konda
    # alohida `hold` ga o'tkazishga ulgurib bo'lmaydi — qurilmalar har
    # 15 daqiqada so'raydi.  Bu bayroq hammasini bir zumda to'xtatadi.
    if get_store().updates_paused():
        return {
            "available": False,
            "reason": "yangilanish vaqtincha to'xtatilgan",
            "policy": policy,
        }
    if release is None:
        return {"available": False, "reason": "nashr qilingan reliz yo'q", "policy": policy}
    if policy["channel"] == "hold":
        return {
            "available": False,
            "reason": "obyekt uchun yangilanish to'xtatilgan",
            "policy": policy,
        }
    if policy["channel"] == "pin" and policy["version"] != release["version"]:
        pinned = _windows_release_by_version(str(policy["version"]))
        if pinned is None:
            return {
                "available": False,
                "reason": f"qotirilgan versiya topilmadi: {policy['version']}",
                "policy": policy,
            }
        release = pinned

    name = release["exe"].name
    return {
        "available": True,
        "version": release["version"],
        "size_bytes": release["size_bytes"],
        "download_url": f"{base}/releases/{name}",
        "manifest_url": f"{base}/releases/{release['manifest'].name}",
        "policy": policy,
    }


def _windows_release_by_version(version: str) -> Optional[Dict[str, Any]]:
    for directory in _release_dirs():
        exe = directory / f"chaqimchi-windows-{version}.exe"
        manifest = directory / f"chaqimchi-windows-{version}.json"
        if exe.is_file() and manifest.is_file():
            return {
                "version": version,
                "exe": exe,
                "manifest": manifest,
                "size_bytes": exe.stat().st_size,
            }
    return None


@app.get("/api/v1/edge/config")
@app.get("/api/v1/sotqin/config")
async def edge_site_config(
    device: Dict[str, Any] = Depends(require_device),
) -> Dict[str, Any]:
    config = get_event_store().get_site_config(device["site_id"])
    features = get_store().site_feature_summary(device["site_id"])
    # Edge AI qarorini chiqarmaydi: faqat cloud jobiga kerakli sampling va
    # queue turini qabul qiladi. Active assignmentlar revision bilan keladi.
    #
    # Profil qurilma turiga qarab: ilgari HAMMA qurilmaga N100 pasporti va
    # 40 GB bufer siyosati ketardi — Windows do'kon kompyuteri o'zini
    # "Intel N100" deb hisoblab, yarim bo'sh 250 GB diskda 20 GB bo'sh joy
    # talab qilardi.
    #
    # Kamera soni tarifdan keladi: Boshlang'ich mijozining sehrgari 3-chi
    # kamerani taklif qilmasligi kerak.  Apparat maksimumidan yuqoriga
    # chiqmaydi — `min` shu uchun.
    site_plan = str((get_store().get_site(device["site_id"]) or {}).get("plan") or "")
    plan_cameras = SHOP_MAX_CAMERAS
    if site_plan:
        plan_cameras = min(SHOP_MAX_CAMERAS, get_plan(site_plan).max_cameras)
    if str(device.get("product_name") or "").lower().startswith("chaqimchi windows"):
        config["product"] = {
            "name": "Chaqimchi Windows",
            "hardware_profile": "WINDOWS-SHOP-PC",
            "guaranteed_cameras": plan_cameras,
            "max_cameras": plan_cameras,
        }
        # Windows'da bufer chegaralarini qurilmaning o'zi diskiga qarab
        # boshqaradi (`chaqimchi_ai/outbox.py` prune + settings).
        config["buffer_policy"] = {
            "critical_priority": True,
            "full_video_storage": "nvr",
        }
    else:
        # Box (Sotqin) ham xuddi shu tarifga bo'ysunadi: apparat 8 kamera
        # ko'tarsa ham, sotilgan tarif nechta bo'lsa shuncha.
        config["product"] = {**product_payload(), "guaranteed_cameras": plan_cameras}
        config["product"]["max_cameras"] = min(
            int(config["product"]["max_cameras"]), plan_cameras
        )
        config["buffer_policy"] = {
            "max_days": BUFFER_RETENTION_DAYS,
            "max_bytes": BUFFER_MAX_BYTES,
            "min_free_bytes": MIN_FREE_BYTES,
            "critical_priority": True,
            "full_video_storage": "nvr",
        }
    config["cameras"] = get_store().list_cameras(device["site_id"], include_source=True)
    # Cloud kamerani o'zi boshqarayotganini faqat owner/installer shu
    # inventarni kamida bir marta saqlaganidan keyin aytamiz.  Bu bayroq
    # bo'lmasa lokal sehrgardagi kamera bo'sh cloud ro'yxati tufayli
    # yo'qolib ketmaydi; bo'lsa oxirgi kamera delete'i ham edgega o'tadi.
    config["cameras_authoritative"] = bool(
        (config.get("config") or {}).get("cameras_authoritative")
    )
    config["cloud_features"] = [
        {
            "code": item["feature_code"],
            "camera_count": item["camera_count"],
            "queue_kind": item["queue_kind"],
        }
        for item in features["assignments"]
        if item["status"] == "active"
    ]
    # Funksiyalar tarifdan keladi.  Ilgari kodlar faqat qo'lda approve
    # qilingan assignmentlardan kelardi va hech bir saytga
    # avto-biriktirilmasdi — pullik mijozning qurilmasi litsenziya filtri
    # sabab hodisalarni jimgina tashlab yuborardi.  Assignmentlar bo'lsa
    # ular ustun (maxsus shartnomalar uchun), bo'lmasa tarifdan keladi.
    #
    # `is_sellable()` EMAS, `plan_feature_codes()`: uch tarif joriy
    # qilinganda `lite` sotuvdan chiqdi, ya'ni `is_sellable("lite")` False
    # bo'ldi.  Eski tekshiruv qolganda mavjud to'lovchi mijozning qurilmasi
    # hamma funksiyani jimgina yo'qotardi va do'kon nazoratsiz qolardi.
    # Obuna tugagan bo'lsa funksiyalar berilmaydi.
    #
    # Bungacha obuna muddati QURILMADA umuman majburlanmasdi:
    # `require_device` faqat tokenni tekshirardi, `/edge/heartbeat` esa
    # litsenziya maydonlarini tashlab yuborardi.  Bitta tarif va tekin
    # sinov paytida bu yumshoq oqim edi; uch xil narx e'lon qilingach —
    # to'lashni to'xtatishning eng oson yo'li.
    #
    # `grace` (14 kun) ATAYLAB to'xtatilmaydi: sayt va FAQ aynan shuni
    # va'da qiladi — "obuna tugagach tizim yana 14 kun ishlaydi".
    # Kamera sog'ligi hodisalari baribir chiqaveradi (`HEALTH_EVENTS`
    # qurilmada filtrdan o'tmaydi), ya'ni do'kon "kamerangiz o'chdi"
    # xabarini yo'qotmaydi.
    subscription = get_store().subscription_status(device["site_id"])
    config["subscription"] = {
        "status": subscription["status"],
        "days_left": subscription["days_left"],
        "message": subscription["message"],
    }
    expired = subscription["status"] in {"expired", "suspended"}
    if expired:
        # Erta `return` QILINMAYDI: quyida `attendance` va boshqa
        # maydonlar to'ldiriladi va yarim javob qurilmani chalg'itardi.
        config["cloud_features"] = []

    if not expired and not config["cloud_features"]:
        site = get_store().get_site(device["site_id"])
        plan_key = str((site or {}).get("plan") or "")
        allowed = set(plan_feature_codes(plan_key))
        # Tarif funksiyani belgilaydi, ammo production'da qabul sinovidan
        # o'tmagan funksiyani qurilmaga yubora olmaydi. Oldin bu fallback
        # `available_feature_codes()` gate'ini chetlab o'tib, sayt
        # "available: false" degan funksiyalarni ham yashirin yoqardi.
        if os.environ.get("CHAQIMCHI_ENV", "development").strip().lower() == "production":
            allowed &= set(available_feature_codes())
        if allowed:
            limits = get_plan(plan_key)
            config["cloud_features"] = [
                {
                    "code": code,
                    "camera_count": limits.max_cameras,
                    "queue_kind": queue_kind,
                }
                for code, _name, _category, queue_kind, _price in DEFAULT_FEATURES
                if code in allowed
            ]
    config["attendance"] = {
        # Obuna tugagan bo'lsa davomat ham to'xtaydi — u ham sotiladigan
        # funksiya, faqat boshqa yo'l bilan yetkaziladi.
        "enabled": _attendance_enabled() and not expired,
        "mode": (
            "commercial"
            if faces.MODELS_LICENSED_FOR_COMMERCIAL_USE
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
    # Bulut panelining manzili.  Qurilma buni birinchi ishga tushganda
    # brauzerni ochish uchun ishlatadi — build vaqtida yozilgan
    # konstanta emas, chunki domen o'zgarsa dala'dagi dastur uni
    # yangilashsiz ham bilishi kerak.
    config["panel_url"] = f"{urls.app_url()}/owner"
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


_DIAGNOSTICS_FORBIDDEN = ("rtsp://", "device_token", "password", "authorization")


def _redact_diagnostics(value: Any) -> Any:
    """Maxfiy iz bor satrlarni OLIB TASHLAB paketni qabul qiladi.

    Avval bunday paket butunlay 422 bilan rad etilardi — eng yomon holat:
    dead_letter xatosida `rtsp://` bo'lgan (ya'ni aynan muammoli) qurilma
    diagnostika yubora OLMASDI.  Endi maxfiy satr belgiga almashadi,
    qolgan ma'lumot supportga yetib boradi.
    """
    if isinstance(value, dict):
        return {key: _redact_diagnostics(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_diagnostics(item) for item in value]
    if isinstance(value, str) and any(m in value.lower() for m in _DIAGNOSTICS_FORBIDDEN):
        return "[maxfiy — olib tashlandi]"
    return value


@app.post("/api/v1/edge/diagnostics")
async def edge_diagnostics(
    request: Request,
    device: Dict[str, Any] = Depends(require_device),
) -> Dict[str, Any]:
    """Edge yuborgan redakt qilingan support snapshotini saqlaydi."""
    # O'lcham JSON parse'dan OLDIN tekshiriladi: api. vhost kliplar uchun
    # 60 MB gacha ruxsat beradi va shu endpointga 60 MB JSON kelsa parse
    # o'zi DoS bo'lardi.
    raw = await request.body()
    if len(raw) > 200_000:
        raise HTTPException(413, "Diagnostika paketi 180 KB dan kichik bo'lishi kerak")
    try:
        body = EdgeDiagnosticsBody.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(422, "Diagnostika formati noto'g'ri") from exc
    payload = _redact_diagnostics(body.payload)
    item = get_event_store().save_device_diagnostics(
        device["site_id"], device["device_id"], payload
    )
    return {"ok": True, "id": item["id"], "created_at": item["created_at"]}


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


class UpdatePolicyBody(BaseModel):
    channel: Literal["auto", "hold", "pin"] = "auto"
    version: Optional[str] = Field(default=None, max_length=64)


@app.put("/api/v1/admin/sites/{site_id}/update-policy")
async def admin_set_update_policy(
    site_id: str,
    body: UpdatePolicyBody,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    """Obyektning yangilanish siyosati.

    Bitta buzuq reliz hamma do'konni birdan yiqitmasligi uchun: yangi
    versiya avval bitta obyektda sinaladi, muammo chiqsa qolganlari
    `hold` ga o'tkaziladi.
    """
    try:
        return get_store().set_update_policy(site_id, channel=body.channel, version=body.version)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class UpdatesPausedBody(BaseModel):
    paused: bool


@app.get("/api/v1/admin/updates-paused")
async def admin_updates_paused(_: None = Depends(require_admin)) -> Dict[str, Any]:
    return {"paused": get_store().updates_paused()}


@app.put("/api/v1/admin/updates-paused")
async def admin_set_updates_paused(
    body: UpdatesPausedBody, _: None = Depends(require_admin)
) -> Dict[str, Any]:
    """Barcha do'konlarga yangilanish tarqatishni to'xtatadi yoki yoqadi.

    Buzuq reliz chiqib ketganda har do'konni alohida `hold` ga
    o'tkazishga ulgurib bo'lmaydi: qurilmalar har 15 daqiqada so'raydi.
    """
    paused = get_store().set_updates_paused(body.paused)
    logger.warning("Yangilanish tarqatish %s", "TO'XTATILDI" if paused else "yoqildi")
    return {"paused": paused}


@app.get("/api/v1/admin/windows-releases")
async def admin_windows_releases(_: None = Depends(require_admin)) -> Dict[str, Any]:
    """Nashr qilingan Windows relizlari — admin panel ro'yxati uchun."""
    releases = []
    seen = set()
    for directory in _release_dirs():
        if not directory.is_dir():
            continue
        for exe in sorted(directory.glob("chaqimchi-windows-*.exe")):
            match = WINDOWS_RELEASE_PATTERN.match(exe.name)
            manifest = exe.with_name(f"{exe.name[: -len('.exe')]}.json")
            if not match or match.group("version") in seen:
                continue
            seen.add(match.group("version"))
            releases.append(
                {
                    "version": match.group("version"),
                    "size_mb": round(exe.stat().st_size / 1024 / 1024),
                    "signed": manifest.is_file(),
                }
            )
    releases.sort(key=lambda item: _version_key(item["version"]), reverse=True)
    return {"releases": releases, "latest": releases[0]["version"] if releases else None}


@app.post("/api/v1/admin/sites/{site_id}/members")
async def admin_add_member(
    site_id: str,
    body: MemberBody,
    admin: Optional[PortalPrincipal] = Depends(require_admin),
) -> Dict[str, Any]:
    if not get_store().get_site(site_id):
        raise HTTPException(404, "Sayt topilmadi")
    member = get_event_store().add_member(
        site_id,
        body.telegram_id,
        role=body.role,
        display_name=body.display_name,
    )
    # A'zolik — do'kon ma'lumotiga kirish huquqi.  Kim kimni qo'shgani
    # yozilmasa, keyin "bu odam qayerdan paydo bo'ldi?" degan savolga
    # javob yo'q.
    get_store().audit_portal_action(
        "site.member.added",
        actor_id=_audit_actor(admin),
        target_type="site",
        target_id=site_id,
        detail={"telegram_id": body.telegram_id, "role": body.role},
    )
    return member


@app.post("/api/v1/admin/sites/{site_id}/members/{telegram_id}/login-link")
async def admin_create_owner_login_link(
    site_id: str,
    telegram_id: str,
    request: Request,
    admin: Optional[PortalPrincipal] = Depends(require_admin),
) -> Dict[str, Any]:
    """A'zo uchun kirish havolasi.

    Havola o'zi credential, shuning uchun faqat admin yaratadi va faqat
    haqiqiy a'zoga.  Yangi havola eskisini bekor qiladi — "havolani
    almashtirish" = "eskisini o'chirish".
    """
    member = get_event_store().member_for_site(site_id, telegram_id)
    if not member:
        raise HTTPException(404, "A'zo topilmadi")
    token = get_event_store().create_login_link(
        site_id,
        telegram_id,
        secret=_owner_secret(),
        ttl_days=LOGIN_LINK_TTL_DAYS,
    )
    base = urls.app_url().rstrip("/") or str(request.base_url).rstrip("/")
    # Havolaning O'ZI parol.  Uni kim va kimga yaratganini yozmasak,
    # begona odam panelga kirib qolgan holatda izlanadigan iz qolmaydi.
    # Tokenning o'zi ATAYLAB yozilmaydi — jurnal credential saqlamasin.
    get_store().audit_portal_action(
        "owner.login_link.created",
        actor_id=_audit_actor(admin),
        target_type="site",
        target_id=site_id,
        detail={"telegram_id": telegram_id, "ttl_days": LOGIN_LINK_TTL_DAYS},
    )
    return {
        "ok": True,
        "url": f"{base}/owner?key={token}",
        "expires_days": LOGIN_LINK_TTL_DAYS,
    }


@app.delete("/api/v1/admin/sites/{site_id}/members/{telegram_id}/login-link")
async def admin_revoke_owner_login_link(
    site_id: str,
    telegram_id: str,
    admin: Optional[PortalPrincipal] = Depends(require_admin),
) -> Dict[str, Any]:
    revoked = get_event_store().revoke_login_links(site_id, telegram_id)
    get_store().audit_portal_action(
        "owner.login_link.revoked",
        actor_id=_audit_actor(admin),
        target_type="site",
        target_id=site_id,
        detail={"telegram_id": telegram_id, "revoked": revoked},
    )
    return {"ok": True, "revoked": revoked}


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
    # Qat'iy test kodi FAQAT test muhitida ishlaydi.  Ilgari bu shart
    # yo'q edi: production'da unutilib qolgan bitta env o'zgaruvchisi
    # hamma mijozning OTP'sini bitta doimiy kodga aylantirardi.  Lifespan
    # ham production'da bu o'zgaruvchi qo'yilgan bo'lsa serverni yoqmaydi.
    test_code = ""
    if os.environ.get("CHAQIMCHI_ENV", "development") != "production":
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
    member = _pick_member(members, body.site_id)
    return {"ok": True, **_owner_session(member)}


@app.post("/api/v1/owner/auth/link")
async def owner_login_with_link(body: LinkLoginBody, request: Request) -> Dict[str, Any]:
    """`?key=<token>` havolasi orqali kirish.

    Token taxmin qilib topilmaydigan darajada uzun, lekin baribir IP
    bo'yicha cheklaymiz — aks holda bu endpoint hash'ni sinab ko'rish
    uchun bepul oracle bo'lib qolardi.
    """
    client_host = request.client.host if request.client else "unknown"
    ratelimit.check(
        "owner-link",
        client_host,
        limit=10,
        window_sec=600,
        message="Juda ko'p urinish. 10 daqiqadan keyin qayta urinib ko'ring.",
    )
    member = get_event_store().member_for_login_token(body.key, secret=_owner_secret())
    if not member:
        raise HTTPException(401, "Havola eskirgan yoki bekor qilingan")
    return {"ok": True, **_owner_session(member)}


@app.post("/api/v1/owner/auth/telegram-webapp")
async def owner_login_with_telegram_webapp(
    body: TelegramWebAppAuthBody, request: Request
) -> Dict[str, Any]:
    """Mini App ichidan parolsiz owner session.

    Rate limit faqat Telegram imzosi tasdiqlangandan keyin qo'yiladi: aks
    holda hujumchi soxta user ID bilan haqiqiy egani bloklab qo'ya olardi.
    """
    telegram_id = _telegram_webapp_user_id(body.init_data)
    ratelimit.check(
        "owner-webapp",
        telegram_id,
        limit=20,
        window_sec=600,
        message="Juda ko'p urinish. Botni qayta ochib urinib ko'ring.",
    )
    members = get_event_store().members_for_telegram(telegram_id)
    owner_members = [item for item in members if str(item.get("role")) == "owner"]
    member = owner_members[0] if owner_members else None
    if member is None:
        raise HTTPException(403, "Mini App faqat do'kon egasi uchun ochilgan")
    if str(member.get("role")) != "owner":
        raise HTTPException(403, "Mini App faqat do'kon egasi uchun ochilgan")
    return {"ok": True, **_owner_session(member)}


@app.get("/api/v1/owner/sites")
async def owner_sites(owner: OwnerPrincipal = Depends(require_active_owner)) -> Dict[str, Any]:
    """Joriy akkaunt ko'ra oladigan filiallar.

    Password va Telegram kirishi bitta shape qaytaradi. Filial tanlash
    `X-Owner-Site-Id` bilan bo'ladi va har keyingi endpoint uni qaytadan
    server tomonda tekshiradi.
    """
    if owner.auth_kind == "password":
        rows = get_store().customer_sites(owner.member_id)
        sites = []
        for row in rows:
            detail = get_store().site_detail(str(row["id"]))
            sites.append(
                {
                    "id": detail["id"],
                    "name": detail["name"],
                    "address": detail.get("address"),
                    "connection": detail.get("connection"),
                    "cameras_active": detail.get("cameras_active"),
                    "cameras_expected": detail.get("cameras_expected") or None,
                    "role": row.get("access_role") or "owner",
                }
            )
    else:
        members = get_event_store().members_for_telegram(owner.telegram_id)
        sites = []
        for member in members:
            detail = get_store().site_detail(str(member["site_id"]))
            sites.append(
                {
                    "id": detail["id"],
                    "name": detail["name"],
                    "address": detail.get("address"),
                    "connection": detail.get("connection"),
                    "cameras_active": detail.get("cameras_active"),
                    "cameras_expected": detail.get("cameras_expected") or None,
                    "role": member.get("role"),
                }
            )
    return {"sites": sites, "selected_site_id": owner.site_id}


@app.get("/api/v1/owner/dashboard")
async def owner_dashboard(
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    """V2 bosh sahifasi uchun bitta izchil snapshot.

    Oldingi panel bir ekran uchun 8–12 ta so'rov yuborardi; ular turli
    vaqtda tugab, kamera holati bir kartada yashil, boshqasida oflayn
    ko'rinishi mumkin edi. Bu endpoint hammasini bitta tanlangan tenant
    ichida yig'adi va frontend faqat shu snapshotni yangilaydi.
    """
    store = get_store()
    events_store = get_event_store()
    detail = store.site_detail(owner.site_id)
    health = await owner_health(owner)
    report = events_store.retail_report(owner.site_id)
    if not _panel_feature_open(owner.site_id, "demografiya"):
        report.pop("demografiya", None)
    event_rows = events_store.list_events(owner.site_id, limit=12)
    for item in event_rows:
        item["label"] = event_label(str(item.get("event_type", "")))
    subscription = await owner_subscription(owner)
    updated_at = datetime.now(timezone.utc).isoformat()
    config_revision = events_store.config_revision(owner.site_id)
    devices = detail.get("devices") or []
    expected = int(health.get("cameras_expected") or 0)
    active = int(detail.get("cameras_active") or 0)
    # Tasdiqni faqat JONLI qurilmalardan kutamiz.  Almashtirilgan eski
    # kompyuter `devices` da qolib ketadi va hech qachon tasdiqlamaydi —
    # u tufayli panel "sozlama tasdiqlanmagan" ni abadiy ko'rsatardi.
    live_devices = [
        item for item in devices if str(item.get("connection") or "") != "offline"
    ] or devices
    applied = bool(live_devices) and all(
        item.get("config_status") == "applied"
        and int(item.get("config_revision") or 0) >= config_revision
        for item in live_devices
    )
    plan_codes = set(plan_feature_codes(str(detail.get("plan") or "")))
    if os.environ.get("CHAQIMCHI_ENV", "development").strip().lower() == "production":
        plan_codes &= set(available_feature_codes())
    capabilities = {
        "cameras": {
            "ready": bool(active) and (not expected or active >= expected),
            "active": active,
            "expected": expected or None,
            "reason": (
                None if not expected or active >= expected
                else f"{expected} kameradan {active} tasi faol"
            ),
        },
        "edge_config": {
            "ready": applied,
            "revision": config_revision,
            "reason": None if applied else "Qurilma yangi sozlamani hali tasdiqlamagan",
        },
        "features": {
            "panel": (health.get("plan") or {}).get("panel_features") or [],
            "edge": sorted(plan_codes),
        },
    }
    # Chiziq chizilmagani — "nega 0 ko'rinyapti?"ning eng keng tarqalgan
    # javobi.  Server buni allaqachon biladi (installer onboarding'da bor
    # edi), endi EGA ham ko'radi: panel bo'sh holat o'rniga aniq sabab va
    # yo'l ko'rsata oladi.
    try:
        site_config = events_store.get_site_config(owner.site_id)["config"]
    except Exception:  # noqa: BLE001 — config hali yaratilmagan yangi sayt
        site_config = {}
    lines_drawn = bool(site_config.get("lines"))
    if not lines_drawn:
        # Chiziq qurilmaning LOKAL sehrgarida chizilgan bo'lishi mumkin —
        # cloud config bo'sh, sanash esa ishlayapti.  Yaqin kunlarda
        # kirish-chiqish kelgan bo'lsa "chizilmagan" ogohlantirishi yolg'on.
        lines_drawn = events_store.has_recent_line_crossings(owner.site_id)
    capabilities["geometry"] = {
        "ready": lines_drawn,
        "lines_drawn": lines_drawn,
        "zones_drawn": bool(site_config.get("zones")),
        "reason": (
            None
            if lines_drawn
            else "Kirish chizig'i chizilmagan — chiziqsiz mijozlar sanalmaydi"
        ),
    }
    return {
        "site": {
            "id": detail["id"],
            "name": detail["name"],
            "address": detail.get("address"),
            "connection": detail.get("connection") or "offline",
            "minutes_since_seen": detail.get("minutes_since_seen"),
            "cameras_active": detail.get("cameras_active"),
            "cameras_expected": health.get("cameras_expected"),
            "plan": {
                "code": detail.get("plan"),
                "name": plan_display_name(str(detail.get("plan") or "")),
                # Panel qulfi shu ro'yxatdan yasaladi.  `health` baribir
                # yuqorida chaqirilgan, ya'ni qo'shimcha so'rov yo'q.
                #
                # Alohida `/owner/health` so'rovi bilan olinsa karta bir
                # zumga qulfsiz, keyin qulfli bo'lib chaqnab ketardi —
                # ikki javob turli vaqtda keladi.
                "panel_features": (health.get("plan") or {}).get("panel_features") or [],
            },
        },
        "today": report,
        # Do'kon kompyuterining holati.  Egasi uchun bu bitta savolga
        # javob: "kompyuter yaxshi ishlayaptimi?"  Qizigan yoki diski
        # to'lgan kompyuterni u o'zi hal qila oladi — biz aytmasak esa
        # hech qachon bilmaydi.
        "device": _owner_device_health(health),
        "cameras": store.list_cameras(owner.site_id, include_source=False),
        "camera_states": health.get("camera_states") or [],
        "events": event_rows,
        "trend": events_store.traffic_trend(owner.site_id, days=14).get("daily", []),
        "subscription": {
            **subscription,
            "monthly_price_uzs": subscription.get("monthly_uzs"),
        },
        "capabilities": capabilities,
        "diagnostics": events_store.latest_device_diagnostics(owner.site_id),
        # Chegara tufayli saqlanmagan rasm/klip soni.
        #
        # Ega buni KO'RISHI kerak.  2026-08-26 da rasm kelmayotgani uch
        # soat sezilmadi, chunki panel rasm yo'qligini jimgina yashirar
        # edi — "hodisa bor, rasmi yo'q" holati hech qanday izoh bermasdi.
        "media_dropped": ratelimit.limiter().rejections(owner.site_id).get("snapshots", 0),
        "updated_at": updated_at,
        "revision": f"{owner.site_id}:{updated_at}",
    }


@app.get("/api/v1/owner/diagnostics")
async def owner_diagnostics(
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    """Ownerga faqat oxirgi redakt qilingan Windows support snapshotini beradi."""
    return {"diagnostics": get_event_store().latest_device_diagnostics(owner.site_id)}


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


def _vision_ready(site_id: str) -> Dict[str, Any]:
    settings = get_event_store().vision_settings(site_id)
    if not settings["consented"]:
        raise HTTPException(
            403,
            "Vision Agent uchun filial egasining tasvir va ovozni Gemini'ga yuborish roziligi kerak",
        )
    if not vision_agent.configured():
        raise HTTPException(503, "Vision Agent provideri hali sozlanmagan")
    return settings


def _check_vision_daily_limit(site_id: str) -> None:
    """Bitta filial uchun barcha UI va Telegram bo'ylab yagona pilot limit.

    Hisob BAZADAN olinadi: bu limit to'g'ridan-to'g'ri pul (Gemini
    chaqiruvi) himoyasi, xotiradagi hisoblagich esa har restart'da nolga
    tushardi — restart sikli cheksiz sarfga aylanishi mumkin edi.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    used = get_event_store().count_vision_jobs_since(site_id, since)
    if used >= 20:
        raise HTTPException(
            429, "Bu filial uchun bugungi 20 ta Vision Agent so'rov limiti tugadi"
        )


def _vision_job_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    """Internal keylarni panelga bermaydigan, barcha yuzalar uchun bitta shape."""
    result = job.get("result") or {}
    return {
        "job_id": job["id"],
        "status": job["status"],
        "created_at": job.get("created_at"),
        "completed_at": job.get("completed_at"),
        "error": job.get("error_text"),
        "has_audio_reply": bool(job.get("audio_reply_key")),
        "result": result,
    }


@app.get("/api/v1/owner/agent/settings")
async def owner_vision_settings(
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    return {**get_event_store().vision_settings(owner.site_id), "provider_configured": vision_agent.configured()}


@app.put("/api/v1/owner/agent/settings")
async def owner_update_vision_settings(
    body: VisionConsentBody,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    require_owner_role(owner, "owner", "service_admin")
    return get_event_store().set_vision_consent(
        owner.site_id,
        consented=body.consented,
        actor_id=owner.member_id,
        audio_reply_enabled=body.audio_reply_enabled,
    )


@app.post("/api/v1/owner/agent/queries", status_code=202)
async def owner_vision_query(
    body: VisionQueryBody,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    settings = _vision_ready(owner.site_id)
    _check_vision_daily_limit(owner.site_id)
    job = get_event_store().create_vision_job(
        owner.site_id, requester_id=owner.member_id, requester_kind="owner",
        question=body.message.strip(), want_audio_reply=body.want_audio_reply and settings["audio_reply_enabled"],
    )
    return _vision_job_payload(job)


@app.post("/api/v1/owner/agent/audio", status_code=202)
async def owner_vision_audio_query(
    audio: UploadFile = File(...),
    # `Form(...)` SHART: panel qiymatni multipart form ichida yuboradi.
    # Oddiy `bool` FastAPI'da query-param bo'lib, checkbox jimgina
    # e'tiborsiz qolardi — ovozli javob paneldan hech qachon so'ralmasdi.
    want_audio_reply: bool = Form(False),
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    settings = _vision_ready(owner.site_id)
    _check_vision_daily_limit(owner.site_id)
    mime = str(audio.content_type or "audio/ogg").lower()
    if mime not in {"audio/ogg", "audio/opus", "audio/mpeg", "audio/mp4", "audio/wav", "audio/x-wav", "video/ogg"}:
        raise HTTPException(415, "Faqat ogg, mp3, m4a yoki wav ovoz qabul qilinadi")
    payload = await audio.read(10 * 1024 * 1024 + 1)
    if not payload or len(payload) > 10 * 1024 * 1024:
        raise HTTPException(413, "Ovozli savol 10 MB dan kichik bo'lishi kerak")
    key = f"agent/audio/{owner.site_id}/{uuid.uuid4()}.bin"
    await media_put(key, payload, content_type=mime)
    job = get_event_store().create_vision_job(
        owner.site_id, requester_id=owner.member_id, requester_kind="owner", audio_key=key,
        audio_mime=mime, want_audio_reply=want_audio_reply and settings["audio_reply_enabled"],
    )
    return _vision_job_payload(job)


@app.get("/api/v1/owner/agent/jobs/{job_id}")
async def owner_vision_job(
    job_id: str,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    # Job FILIAL bo'yicha ochiladi, so'ragan a'zo bo'yicha emas.
    # Telegram'dan berilgan savol `requester_id=telegram_id` bilan
    # yoziladi — qat'iy tenglik egasining O'Z savolini panelda 404
    # qilardi.  `vision_job(site_id, ...)` tenant chegarasini baribir
    # ushlab turadi.
    job = get_event_store().vision_job(owner.site_id, job_id)
    if not job:
        raise HTTPException(404, "Agent so'rovi topilmadi")
    return _vision_job_payload(job)


@app.get("/api/v1/owner/agent/jobs/{job_id}/audio")
async def owner_vision_job_audio(
    job_id: str, owner: OwnerPrincipal = Depends(require_active_owner)
) -> Response:
    job = get_event_store().vision_job(owner.site_id, job_id)
    if not job or not job.get("audio_reply_key"):
        raise HTTPException(404, "Ovozli javob topilmadi")
    try:
        content = await media_get(str(job["audio_reply_key"]))
    except Exception as exc:  # noqa: BLE001 — MinIO S3Error ham 404 bo'lsin, 500 emas
        raise HTTPException(404, "Ovozli javob topilmadi") from exc
    # Haqiqiy mime natijada saqlanadi (Gemini ko'pincha PCM qaytaradi) —
    # "audio/wav" deb qattiq yozish brauzerda o'ynalmaslikka olib kelardi.
    mime = str(((job.get("result") or {}).get("audio_reply_mime")) or "audio/wav")
    return Response(content, media_type=mime, headers={"Cache-Control": "no-store"})


@app.get("/api/v1/owner/agent/memory")
async def owner_vision_memory(
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    return {"items": get_event_store().vision_memory(owner.site_id, owner.member_id)}


@app.post("/api/v1/admin/sites/{site_id}/agent/queries", status_code=202)
async def admin_vision_query(
    site_id: str,
    body: VisionQueryBody,
    admin: Optional[PortalPrincipal] = Depends(require_admin),
) -> Dict[str, Any]:
    if not get_store().get_site(site_id):
        raise HTTPException(404, "Filial topilmadi")
    settings = _vision_ready(site_id)
    _check_vision_daily_limit(site_id)
    requester = admin.account_id if admin else "cloud-admin-key"
    job = get_event_store().create_vision_job(
        site_id, requester_id=requester, requester_kind="admin", question=body.message.strip(),
        want_audio_reply=body.want_audio_reply and settings["audio_reply_enabled"],
    )
    return _vision_job_payload(job)


@app.get("/api/v1/admin/sites/{site_id}/agent/settings")
async def admin_vision_settings(
    site_id: str, _: Optional[PortalPrincipal] = Depends(require_admin)
) -> Dict[str, Any]:
    if not get_store().get_site(site_id):
        raise HTTPException(404, "Filial topilmadi")
    return {**get_event_store().vision_settings(site_id), "provider_configured": vision_agent.configured()}


@app.put("/api/v1/admin/sites/{site_id}/agent/settings")
async def admin_update_vision_settings(
    site_id: str, body: VisionConsentBody, admin: Optional[PortalPrincipal] = Depends(require_admin)
) -> Dict[str, Any]:
    if not get_store().get_site(site_id):
        raise HTTPException(404, "Filial topilmadi")
    return get_event_store().set_vision_consent(
        site_id, consented=body.consented, actor_id=admin.account_id if admin else "cloud-admin-key",
        audio_reply_enabled=body.audio_reply_enabled,
    )


@app.get("/api/v1/admin/sites/{site_id}/agent/jobs/{job_id}")
async def admin_vision_job(
    site_id: str, job_id: str, _: Optional[PortalPrincipal] = Depends(require_admin)
) -> Dict[str, Any]:
    job = get_event_store().vision_job(site_id, job_id)
    if not job:
        raise HTTPException(404, "Agent so'rovi topilmadi")
    return _vision_job_payload(job)


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
    report = get_event_store().retail_report(owner.site_id, day=day)
    # Demografiya hisobotdan CHIQARILADI, qabuldan emas.
    #
    # Ma'lumot yozilib turaveradi — mijoz tarifni ko'targanda tarix
    # o'zidan paydo bo'ladi.  Qabulda to'xtatilsa, o'sha oyning
    # o'rtasidan boshlanadigan doimiy teshik qolardi.
    if not _panel_feature_open(owner.site_id, "demografiya"):
        report.pop("demografiya", None)
    return report


#: «Mijoz portreti» davri → nechta kun orqaga.
#:
#: Yil 365 kun deb olinadi (kabisa yiliga bir kun farq) — bu
#: solishtirish uchun yetarli aniqlik va oy chegaralarini hisoblash
#: murakkabligidan xoli.
DEMOGRAPHY_PERIODS = {"week": 7, "month": 30, "year": 365}


@app.get("/api/v1/owner/demography")
async def owner_demography(
    period: Literal["week", "month", "year"] = "week",
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    """Haftalik, oylik va yillik mijoz portreti.

    Xom hodisalar tarif muddatida o'chiriladi, shuning uchun bu javob
    KUNLIK YIG'INDI jadvalidan o'qiladi (`demography_daily`).  U
    hodisalar o'chirilishidan oldin yoziladi va uch yil saqlanadi —
    aynan shu tufayli «o'tgan yilning shu oyi» bilan solishtirish
    mumkin.

    Bugungi kun bu yerga KIRMAYDI: u hali tugamagan va panel uni
    hisobotdan jonli oladi.  Aks holda bir xil kun ikki manbadan ikki
    xil ko'rinardi.
    """
    if not _panel_feature_open(owner.site_id, "demografiya"):
        raise HTTPException(403, "Mijoz portreti Biznes tarifida ochiladi")

    today = datetime.now(ZoneInfo("Asia/Tashkent")).date()
    days = DEMOGRAPHY_PERIODS[period]
    end = today - timedelta(days=1)
    data = get_event_store().demography_range(
        owner.site_id, start=end - timedelta(days=days - 1), end=end
    )
    return {"period": period, **data}


def _trust_score_for(site_id: str, day: Optional[date_type] = None) -> Dict[str, Any]:
    """Ball uchun kirish ma'lumotini yig'adi.

    Hammasi MAVJUD funksiyalardan keladi — yangi ma'lumot yig'ilmaydi.
    Hisoblashning o'zi `cloud/trust_score.py` da: u sof funksiya va
    panel, Telegram xabari hamda bu endpoint uchun bitta manba.
    """
    events = get_event_store()
    store = get_store()
    day = day or datetime.now(ZoneInfo("Asia/Tashkent")).date()

    detail = store.site_detail(site_id)
    # `cameras_expected` obyekt yaratilganda qo'lda kiritiladi va o'zi
    # ro'yxatdan o'tgan do'konda BO'SH qoladi — `owner_health` dagi kabi
    # ro'yxatdagi kamera soni zaxira sifatida olinadi.
    expected = int(detail.get("cameras_expected") or 0) or len(store.list_cameras(site_id))

    # Navbat zonasi chizilganmi.  Bu SHART: zonasiz `queue_threshold_exceeded`
    # hech qachon chiqmaydi, ya'ni "0 ta signal" mukammal navbat emas.
    config = events.get_site_config(site_id).get("config") or {}
    queue_configured = any(
        bool(zone.get("queue")) for zone in (config.get("zones") or []) if isinstance(zone, dict)
    )

    return trust_score.score(
        report=events.retail_report(site_id, day=day),
        shifts=events.shift_summary(site_id, start=day, end=day),
        minutes_since_seen=detail.get("minutes_since_seen"),
        cameras_active=int(detail.get("cameras_active") or 0),
        cameras_expected=expected,
        queue_configured=queue_configured,
    )


@app.get("/api/v1/owner/trust-score")
def owner_trust_score(owner: OwnerPrincipal = Depends(require_active_owner)) -> Dict[str, Any]:
    """Kunning bitta raqami — panel va Telegram uchun.

    `async def` EMAS: ichida faqat bloklovchi baza chaqiruvlari bor va
    FastAPI oddiy `def` ni o'zi alohida oqimda ishlatadi.  `async` qilib
    qo'yilsa, bu endpoint yagona hodisa halqasini ushlab turardi.
    """
    today = _trust_score_for(owner.site_id)
    result = {**today, "label": trust_score.label(today["total"])}

    # Kechagi ball — raqamning yo'nalishi raqamning o'zicha muhim.
    # Kecha ma'lumot bo'lmasa jimgina tashlab ketiladi.
    try:
        yesterday = _trust_score_for(
            owner.site_id, datetime.now(ZoneInfo("Asia/Tashkent")).date() - timedelta(days=1)
        )
        result["yesterday"] = yesterday["total"]
    except Exception:  # noqa: BLE001 — kechagi ball bugungisini yiqitmasin
        logger.exception("Kechagi ballni hisoblab bo'lmadi: %s", owner.site_id)
        result["yesterday"] = None
    return result


@app.get("/api/v1/owner/trend")
async def owner_trend(
    days: int = 7, owner: OwnerPrincipal = Depends(require_active_owner)
) -> Dict[str, Any]:
    """Kunlar bo'yicha kirish oqimi: qaysi kun kuchli, hafta qanday ketdi."""
    return get_event_store().traffic_trend(owner.site_id, days=days)


@app.get("/api/v1/owner/stats")
async def owner_stats(owner: OwnerPrincipal = Depends(require_active_owner)) -> Dict[str, Any]:
    return get_event_store().stats(owner.site_id)


#: Do'kon kompyuteri shu haroratdan oshsa panel ogohlantiradi.
#: `cloud/alerts.py:DEVICE_TEMP_ALERT_C` bilan bir xil — panel va
#: Telegram bir xil chegarada gapirishi kerak, aks holda mijoz
#: "panelda yashil-ku" deb Telegram xabariga ishonmay qo'yadi.
OWNER_DEVICE_HOT_C = 85.0


def _owner_device_health(health: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Eng so'nggi heartbeat'dan egaga ko'rsatiladigan qisqacha holat.

    Faqat O'LCHANGAN ko'rsatkichlar qaytadi.  Windows qurilmalar hozircha
    haroratni umuman yubormaydi (uni administrator huquqisiz o'qib
    bo'lmaydi) — o'shanda kalit ham bo'lmaydi va panel o'sha qatorni
    chizmaydi.  "0°C" yozish yolg'on bo'lardi.

    `None` — hali birorta heartbeat kelmagan; panel kartani umuman
    ko'rsatmaydi.
    """
    records = health.get("devices") or []
    if not records:
        return None
    # `health()` yangidan eskiga qarab qaytaradi — birinchisi eng
    # so'nggisi.  Bir nechta qurilma bo'lsa ham egaga bittasi
    # ko'rsatiladi: uning do'konida odatda bitta kompyuter bo'ladi.
    newest = records[0]
    payload = newest.get("health") or {}

    data: Dict[str, Any] = {"received_at": newest.get("received_at")}
    for key in ("cpu_percent", "ram_percent", "disk_percent", "temperature_c"):
        value = payload.get(key)
        if isinstance(value, (int, float)):
            data[key] = round(float(value), 1)
    uptime = payload.get("uptime_sec")
    if isinstance(uptime, (int, float)):
        data["uptime_sec"] = int(uptime)
    version = payload.get("app_version")
    if version:
        data["app_version"] = str(version)

    free = payload.get("disk_free_bytes")
    if isinstance(free, (int, float)) and free > 0:
        data["free_disk_gb"] = round(float(free) / 1024**3, 1)

    temperature = data.get("temperature_c")
    data["hot"] = isinstance(temperature, float) and temperature >= OWNER_DEVICE_HOT_C
    return data


@app.get("/api/v1/owner/health")
async def owner_health(owner: OwnerPrincipal = Depends(require_active_owner)) -> Dict[str, Any]:
    detail = get_store().site_detail(owner.site_id)
    # `cameras_expected` obyekt yaratilganda qo'lda kiritiladi va o'zi
    # ro'yxatdan o'tgan do'konda u BO'SH qoladi — natijada panel "4 dan 2
    # tasi" o'rniga quruq "Qurilma ulangan" deb turardi.  Ro'yxatdagi
    # kamera soni yaxshiroq zaxira: uni qurilmaning o'zi bildiradi.
    cameras = get_store().list_cameras(owner.site_id)
    registered = len(cameras)
    # Kamera heartbeat'i oxirgi qurilma xabari bilan birga saqlanadi.  Uni
    # alohida "yashil" holat deb qaytarish xato: qurilma 4 soat oldin
    # uzilgan bo'lsa, o'sha eski `connected=true` qiymati kamerani hozir ham
    # ishlayotgandek ko'rsatardi. Owner panel faqat shu normallashtirilgan
    # ro'yxatdan foydalanadi.
    heartbeat_records = get_event_store().health(owner.site_id)
    reported: Dict[str, Dict[str, Any]] = {}
    for record in heartbeat_records:
        for camera in (record.get("health") or {}).get("cameras") or []:
            camera_id = str(camera.get("camera_id") or "")
            if camera_id and camera_id not in reported:
                reported[camera_id] = {**camera, "reported_at": record.get("received_at")}

    connection = str(detail.get("connection") or "offline")
    camera_states = []
    for camera in cameras:
        camera_id = str(camera.get("camera_id") or "")
        item = reported.get(camera_id)
        if connection != "online":
            state = "offline"
            reason = "Qurilma aloqada emas" if connection == "offline" else "Qurilma aloqasi eskirgan"
        elif item is None:
            state = "unknown"
            reason = "Kamera holati hali kelmagan"
        elif bool(item.get("connected")) and not bool(item.get("offline")):
            state = "online"
            reason = "Ishlayapti"
        else:
            state = "offline"
            reason = "Kamera javob bermayapti"
        camera_states.append(
            {
                "camera_id": camera_id,
                "state": state,
                "reason": reason,
                "reported_at": item.get("reported_at") if item else None,
                "reconnects": int(item.get("reconnects") or 0) if item else 0,
            }
        )
    return {
        "devices": heartbeat_records,
        "camera_states": camera_states,
        "cameras_expected": detail["cameras_expected"] or registered or None,
        "connection": connection,
        # Panel sarlavhasi uchun: do'kon nomi va oxirgi aloqadan beri
        # o'tgan vaqt — "Qurilma 2 soatdan beri aloqada emas" kabi oddiy
        # tildagi holat shulardan yasaladi.
        "site_name": detail.get("name"),
        "minutes_since_seen": detail.get("minutes_since_seen"),
        "cameras_active": detail.get("cameras_active"),
        # Tarif — panel qaysi bo'limni ochishini shundan biladi.  `health`
        # baribir hamma tabning bog'liqligida turadi, ya'ni bu qo'shimcha
        # so'rov emas.  Bazadagi kod emas, MIJOZGA ko'rinadigan nom:
        # eski `lite` obyekti ham panelda "Biznes" bo'lib turadi.
        "plan": {
            "code": str(detail.get("plan") or ""),
            "name": plan_display_name(str(detail.get("plan") or "")),
            "max_cameras": get_plan(str(detail["plan"])).max_cameras,
            "max_employees": get_plan(str(detail["plan"])).effective_max_persons(
                int(detail.get("billable_persons") or 0)
            ),
            "panel_features": list(get_plan(str(detail["plan"])).panel_features),
        },
    }


@app.get("/api/v1/owner/cameras")
async def owner_cameras(owner: OwnerPrincipal = Depends(require_active_owner)) -> Dict[str, Any]:
    # RTSP credentiallari owner brauzeriga qaytmaydi.
    return {"cameras": get_store().list_cameras(owner.site_id, include_source=False)}


class DailyRevenueBody(BaseModel):
    #: 0 — "aytmayman".  Chegara `CloudStore.MAX_DAILY_REVENUE_UZS` da ham
    #: bor; bu yerdagisi buzuq so'rovni bazagacha yetkazmaslik uchun.
    amount_uzs: int = Field(ge=0, le=10_000_000_000)


class SpeakBody(BaseModel):
    phrase: str = Field(min_length=1, max_length=32)


def _announce(site_id: str, phrase: str, *, requested_by: str) -> Dict[str, Any]:
    """Ovozni navbatga qo'yadi va qurilmani DARHOL uyg'otadi.

    Uyg'otish `_wake_live_watchers` orqali: qurilma heartbeat'ni ochiq
    ushlab turadi va so'rov ~0.4 soniyada yetadi.  Usiz ovoz keyingi
    odatdagi heartbeat'gacha (60 soniyagacha) kutardi — do'kon egasi
    esa tugmani bosgach darhol natija kutadi.
    """
    if not announcements.is_valid(phrase):
        raise HTTPException(422, "Noma'lum ibora")
    # Cheklov ataylab qattiq: karnay do'konda yangraydi va uni takror
    # bosish xodim uchun ta'qibga aylanishi mumkin.
    ratelimit.check(
        "owner-speak",
        site_id,
        limit=10,
        window_sec=3600,
        message="Soatiga 10 martadan ko'p ovoz berib bo'lmaydi.",
    )
    result = get_store().request_speak(site_id, phrase, requested_by=requested_by)
    _wake_live_watchers(site_id)
    logger.info("Ovoz so'raldi: site=%s phrase=%s by=%s", site_id, phrase, requested_by)
    return result


@app.post("/api/v1/owner/speak")
def owner_speak(
    body: SpeakBody, owner: OwnerPrincipal = Depends(require_active_owner)
) -> Dict[str, Any]:
    """Do'kon karnayidan ibora aytiladi.

    Faqat EGASI: karnay butun do'konda eshitiladi va uni xodim
    ishlatishi noqulay holatlarga olib keladi.
    """
    require_owner_role(owner, "owner", "service_admin")
    return {"ok": True, **_announce(owner.site_id, body.phrase, requested_by=owner.telegram_id)}


@app.get("/api/v1/owner/announcements")
def owner_announcements(_: OwnerPrincipal = Depends(require_active_owner)) -> Dict[str, Any]:
    """Karnaydan aytish mumkin bo'lgan iboralar ro'yxati.

    Panel ro'yxatni o'zi yozmaydi — katalog `chaqimchi_ai/announcements.py`
    da va qurilma ham o'shandan foydalanadi.
    """
    return {
        "announcements": [
            {"code": item.code, "text": item.text, "button": item.button, "hint": item.hint}
            for item in announcements.ANNOUNCEMENTS
        ]
    }


@app.get("/api/v1/owner/revenue")
def owner_get_revenue(owner: OwnerPrincipal = Depends(require_active_owner)) -> Dict[str, Any]:
    """Mijoz aytgan o'rtacha kunlik savdo.

    Panel shu raqam bor-yo'qligiga qarab pul bo'limini ko'rsatadi yoki
    "savdongizni ayting" degan taklifni chiqaradi.
    """
    site = get_store().get_site(owner.site_id) or {}
    return {"amount_uzs": int(site.get("avg_daily_revenue_uzs") or 0)}


@app.put("/api/v1/owner/revenue")
def owner_set_revenue(
    body: DailyRevenueBody, owner: OwnerPrincipal = Depends(require_active_owner)
) -> Dict[str, Any]:
    """Bitta savol — «kuniga taxminan qancha savdo qilasiz?».

    Bu raqamsiz mahsulot faqat hodisa sanog'ini ko'rsatadi; u bilan esa
    hamma narsa so'mga aylanadi.  Faqat egasi o'zgartira oladi: bu
    do'konning moliyaviy ma'lumoti.
    """
    require_owner_role(owner, "owner", "service_admin")
    try:
        get_store().set_avg_daily_revenue(owner.site_id, body.amount_uzs)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "amount_uzs": body.amount_uzs}


@app.get("/api/v1/owner/config")
async def owner_get_config(
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    return get_event_store().get_site_config(owner.site_id)


def _validate_site_config(body: SiteConfigBody) -> None:
    """Do'kon sozlamasining umumiy tekshiruvi.

    Ega ham, o'rnatuvchi ham shu bitta yo'ldan o'tadi — aks holda ikkita
    tekshiruv vaqt o'tib bir-biridan ajralib ketardi.
    """
    allowed_cameras = {f"camera-{number:02d}" for number in range(1, GUARANTEED_CAMERAS + 1)}
    configured_ids = (
        set(body.camera_labels)
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
    cameras_map = (body.floor_map or {}).get("cameras") or {}
    if not isinstance(cameras_map, dict) or len(cameras_map) > GUARANTEED_CAMERAS * 2:
        raise HTTPException(422, "Do'kon plani noto'g'ri formatda")
    for camera_id, item in cameras_map.items():
        quad = (item or {}).get("quad")
        if quad is None:
            continue
        if (
            not isinstance(quad, list)
            or len(quad) != 4
            or any(
                not isinstance(point, list)
                or len(point) != 2
                or any(not isinstance(v, (int, float)) or v < 0 or v > 1 for v in point)
                for point in quad
            )
        ):
            raise HTTPException(
                422, f"{camera_id} pol to'rtburchagi 4 ta [x,y] (0..1) nuqta bo'lsin"
            )


class CameraFromScanBody(BaseModel):
    job_id: str = Field(min_length=6, max_length=40)
    stream_ref: int = Field(ge=0, le=200)
    camera_id: str = Field(default="", max_length=40)
    label: str = Field(min_length=1, max_length=120)


def _owner_camera_saved(site_id: str, camera_id: str, *, label: str, rtsp_url: str, actor: str):
    """Kamerani saqlaydi va qurilmaga xabar beradigan revizyani ko'taradi.

    Tarif chegarasi va Fernet shifrlash `upsert_camera()` ichida —
    bu yerda takrorlanmaydi.  Konfiguratsiyani o'zgarishsiz qayta
    yozish ataylab: uning yagona vazifasi `revision` ni oshirish,
    shundagina qurilma keyingi heartbeat'da o'zgarishni sezadi.
    """
    camera = get_store().upsert_camera(
        site_id, camera_id, label=label, rtsp_url=rtsp_url, enabled=True
    )
    current = get_event_store().get_site_config(site_id)
    desired = dict(current["config"])
    desired["cameras_authoritative"] = True
    updated = get_event_store().update_site_config(site_id, desired)
    get_store().audit_portal_action(
        "owner.camera.saved",
        actor_id=actor,
        target_type="camera",
        target_id=f"{site_id}:{camera_id}",
        detail={"label": label},
    )
    return {"camera": camera, "config_revision": updated["revision"]}


def _next_camera_slot(site_id: str) -> str:
    taken = {item["camera_id"] for item in get_store().list_cameras(site_id)}
    for index in range(1, GUARANTEED_CAMERAS + 1):
        candidate = f"camera-{index:02d}"
        if candidate not in taken:
            return candidate
    raise HTTPException(422, "Barcha kamera o'rinlari band — avval keraksizini o'chiring")


@app.put("/api/v1/owner/cameras/{camera_id}")
async def owner_upsert_camera(
    camera_id: str,
    body: CameraConfigBody,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    """Egasi kamerani o'zi qo'shadi (skaner topmagan holat uchun)."""
    require_owner_role(owner, "owner", "service_admin")
    try:
        return _owner_camera_saved(
            owner.site_id,
            camera_id,
            label=body.label,
            rtsp_url=body.rtsp_url,
            actor=owner.member_id,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/v1/owner/cameras/from-scan")
async def owner_camera_from_scan(
    body: CameraFromScanBody,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    """Skaner topgan oqimni kamera sifatida saqlaydi.

    Panel faqat INDEKS yuboradi; to'liq manzil shifrlangan natijadan
    shu yerda, server tomonda olinadi.  Ya'ni NVR paroli brauzerga
    umuman tushmaydi.
    """
    require_owner_role(owner, "owner", "service_admin")
    job = get_store().get_job(owner.site_id, body.job_id, with_result=True)
    if not job:
        raise HTTPException(404, "Qidiruv natijasi topilmadi")
    result = job.get("result") or {}
    streams = result.get("streams") or result.get("cameras") or []
    if body.stream_ref >= len(streams):
        raise HTTPException(422, "Bunday oqim topilmadi — qidiruvni qaytadan bajaring")
    chosen = streams[body.stream_ref]
    rtsp_url = str(chosen.get("uri") or chosen.get("rtsp_url") or "")
    if not rtsp_url:
        raise HTTPException(422, "Bu oqimda manzil yo'q")
    camera_id = body.camera_id or _next_camera_slot(owner.site_id)
    try:
        return _owner_camera_saved(
            owner.site_id,
            camera_id,
            label=body.label,
            rtsp_url=rtsp_url,
            actor=owner.member_id,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.delete("/api/v1/owner/cameras/{camera_id}")
async def owner_delete_camera(
    camera_id: str,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    require_owner_role(owner, "owner", "service_admin")
    if not get_store().delete_camera(owner.site_id, camera_id):
        raise HTTPException(404, "Kamera topilmadi")
    current = get_event_store().get_site_config(owner.site_id)
    desired = dict(current["config"])
    # Delete ham xuddi save kabi buyruq: bo'sh inventar "bilinmaydi"
    # emas, "cloud tasdiqlagan holda o'chirildi" degani.
    desired["cameras_authoritative"] = True
    updated = get_event_store().update_site_config(owner.site_id, desired)
    get_store().audit_portal_action(
        "owner.camera.deleted",
        actor_id=owner.member_id,
        target_type="camera",
        target_id=f"{owner.site_id}:{camera_id}",
    )
    return {"ok": True, "config_revision": updated["revision"]}


class ScanRequestBody(BaseModel):
    kind: Literal["lan_scan", "onvif", "channels", "probe"]
    host: str = Field(default="", max_length=120)
    port: int = Field(default=0, ge=0, le=65_535)
    username: str = Field(default="", max_length=64)
    password: str = Field(default="", max_length=128)
    xaddr: str = Field(default="", max_length=300)
    channel: int = Field(default=1, ge=1, le=64)
    #: Oldingi qidiruv topgan oqimni sinash uchun: panelda manzil YO'Q
    #: (u parol bilan keladi), faqat indeks bor.  Server manzilni
    #: shifrlangan natijadan o'zi oladi.
    from_job: str = Field(default="", max_length=40)
    stream_ref: int = Field(default=-1, ge=-1, le=200)


@app.post("/api/v1/owner/scan")
async def owner_start_scan(
    body: ScanRequestBody,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    """Do'kon kompyuteridan tarmoqni skanerlashni so'raydi.

    Kamera qidirish do'kon tarmog'idan bajarilishi SHART — bulut
    sahifasi u yerga kira olmaydi.  Shuning uchun bu yerda faqat
    topshiriq yoziladi; qurilma uni heartbeat javobida ko'radi.
    """
    require_owner_role(owner, "owner", "service_admin")
    ratelimit.check(
        "owner-scan",
        owner.site_id,
        limit=20,
        window_sec=3_600,
        message="Juda ko'p qidiruv. Bir soatdan keyin qayta urinib ko'ring.",
    )
    detail = get_store().site_detail(owner.site_id)
    if str(detail.get("connection") or "offline") == "offline":
        # Aks holda foydalanuvchi 2 daqiqa spinnerga qarab, oxirida
        # "javob kelmadi" degan quruq xatoni ko'rardi.
        raise HTTPException(
            409, "Do'kon kompyuteri hozir aloqada emas — uni yoqing va internetni tekshiring."
        )
    params = body.model_dump(exclude={"kind", "from_job", "stream_ref"})
    if body.kind == "probe" and not body.from_job:
        # Xom RTSP manzilini brauzerdan qabul qilmaymiz: unda parol
        # bo'ladi va u sahifadan serverga borishi kerak emas.  Sinash
        # doim oldingi qidiruv natijasiga havola qiladi.
        raise HTTPException(422, "Sinash uchun qidiruv natijasi ko'rsatilishi kerak")
    if body.from_job:
        # Sinaladigan manzil brauzerdan emas, oldingi qidiruv
        # natijasidan olinadi — NVR paroli panelga tushmasligi kerak.
        previous = get_store().get_job(owner.site_id, body.from_job, with_result=True)
        if not previous:
            raise HTTPException(404, "Qidiruv natijasi topilmadi")
        result = previous.get("result") or {}
        streams = result.get("streams") or result.get("cameras") or []
        if not 0 <= body.stream_ref < len(streams):
            raise HTTPException(422, "Bunday oqim topilmadi — qidiruvni qaytadan bajaring")
        chosen = streams[body.stream_ref]
        params["rtsp_url"] = str(chosen.get("uri") or chosen.get("rtsp_url") or "")
        if not params["rtsp_url"]:
            raise HTTPException(422, "Bu oqimda manzil yo'q")
    job = get_store().create_job(
        owner.site_id, kind=body.kind, params=params, requested_by=owner.member_id
    )
    _wake_live_watchers(owner.site_id)
    return {"job": job, "poll_after_sec": 2}


def _scan_view(job: Dict[str, Any]) -> Dict[str, Any]:
    """Topshiriq natijasini brauzerga REDAKSIYALANGAN holda beradi.

    Natijada NVR paroli bilan to'liq RTSP manzillari bo'ladi.  Panelga
    ular o'rniga `safe_url` va `stream_ref` ketadi; kamerani saqlashda
    server manzilni shifrlangan natijadan o'zi oladi.
    """
    view = {key: value for key, value in job.items() if key not in {"result", "frame_key"}}
    result = job.get("result") or {}
    if result:
        cleaned = dict(result)
        if isinstance(result.get("streams"), list):
            cleaned["streams"] = rtsp.safe_streams(result["streams"])
        if isinstance(result.get("cameras"), list):
            cleaned["cameras"] = rtsp.safe_streams(result["cameras"])
        view["result"] = cleaned
    return view


@app.get("/api/v1/owner/scan/{job_id}")
async def owner_scan_status(
    job_id: str, owner: OwnerPrincipal = Depends(require_active_owner)
) -> Dict[str, Any]:
    require_owner_role(owner, "owner", "service_admin")
    job = get_store().get_job(owner.site_id, job_id, with_result=True)
    if not job:
        raise HTTPException(404, "Topshiriq topilmadi")
    return {"ok": True, "job": _scan_view(job)}


@app.get("/api/v1/owner/scan")
async def owner_scan_latest(
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    """Oxirgi topshiriq — sahifa yangilangach qayta ulanish uchun."""
    require_owner_role(owner, "owner", "service_admin")
    job = get_store().latest_job(owner.site_id)
    if not job:
        return {"ok": True, "job": None}
    full = get_store().get_job(owner.site_id, job["job_id"], with_result=True)
    return {"ok": True, "job": _scan_view(full or job)}


@app.get("/api/v1/owner/scan/{job_id}/frame")
async def owner_scan_frame(
    job_id: str, owner: OwnerPrincipal = Depends(require_active_owner)
) -> Response:
    require_owner_role(owner, "owner", "service_admin")
    job = get_store().get_job(owner.site_id, job_id, with_result=True)
    if not job or not job.get("frame_key"):
        raise HTTPException(404, "Kadr hali kelmadi")
    try:
        content = await media_get(str(job["frame_key"]))
    except FileNotFoundError as exc:
        raise HTTPException(404, "Kadr hali kelmadi") from exc
    return Response(content, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.delete("/api/v1/owner/scan/{job_id}")
async def owner_cancel_scan(
    job_id: str, owner: OwnerPrincipal = Depends(require_active_owner)
) -> Dict[str, Any]:
    require_owner_role(owner, "owner", "service_admin")
    if not get_store().cancel_job(owner.site_id, job_id):
        raise HTTPException(404, "Topshiriq topilmadi yoki tugagan")
    return {"ok": True}


@app.put("/api/v1/owner/config")
async def owner_update_config(
    body: SiteConfigBody,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    require_owner_role(owner, "owner", "service_admin")
    _validate_site_config(body)
    return get_event_store().update_site_config(
        owner.site_id, _preserve_server_config_flags(owner.site_id, body.model_dump())
    )


@app.get("/api/v1/owner/employees")
async def owner_employees(
    include_inactive: bool = False,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    require_attendance()
    return {
        "mode": "commercial" if faces.MODELS_LICENSED_FOR_COMMERCIAL_USE else "closed_pilot",
        "employees": get_event_store().list_employees(
            owner.site_id, include_inactive=include_inactive
        ),
    }


def _panel_feature_open(site_id: str, feature: str) -> bool:
    """Shu obyektning tarifida panel bo'limi ochiqmi.

    Bir joyda: xarita, demografiya va navbat kartalari uch xil endpointda
    tekshiriladi va uchtasi bir-biridan uzoqlashib ketmasin.
    """
    site = get_store().get_site(site_id)
    if not site:
        return False
    return feature in get_plan(str(site.get("plan") or "")).panel_features


def _check_employee_limit(site_id: str) -> None:
    """Tarifdagi xodim chegarasi.

    Chegara `plans.py` da yozilgan, ammo bungacha u faqat javoblarda
    qaytardi — hech qayerda majburlanmasdi.  Kamera chegarasi bilan bir
    xil naqsh (`chaqimchi_ai/local/app.py`): sanoq yaratishdan OLDIN
    tekshiriladi.
    """
    site = get_store().get_site(site_id)
    if not site:
        raise HTTPException(404, "Sayt topilmadi")
    limit = get_plan(str(site.get("plan") or "lite")).effective_max_persons(
        int(site.get("billable_persons") or 0)
    )
    if limit <= 0:
        # Boshlang'ich tarifida davomat umuman yo'q.  "Ko'pi bilan 0 ta
        # xodim" degan xabar mijozni chalg'itardi — u chegarani oshirish
        # kerak deb o'ylardi, holbuki tarifni ko'tarish kerak.
        raise HTTPException(
            422,
            "Xodim davomati Biznes tarifidan boshlab ishlaydi. "
            "Tarifni ko'tarish uchun biz bilan bog'laning.",
        )
    current = len(get_event_store().list_employees(site_id))
    if current >= limit:
        raise HTTPException(
            422,
            f"Tarifingizda ko'pi bilan {limit} ta xodim. "
            f"Yangisini qo'shish uchun avval kimnidir ro'yxatdan chiqaring.",
        )


@app.post("/api/v1/owner/employees")
async def owner_create_employee(
    body: EmployeeCreateBody,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    require_attendance()
    require_owner_role(owner, "owner", "service_admin")
    if not body.consent:
        raise HTTPException(422, "Xodimning yozma roziligi qayd etilishi shart")
    _check_employee_limit(owner.site_id)
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


def _month_range(month: Optional[str]) -> tuple[date_type, date_type]:
    """`YYYY-MM` → oyning birinchi va oxirgi kuni.

    Oxirgi kun kalendar bo'yicha: 30/31 ni qo'lda yozish shubhasiz
    fevralda buzilardi.
    """
    today = datetime.now(ZoneInfo("Asia/Tashkent")).date()
    if not month:
        first = today.replace(day=1)
    else:
        try:
            year, mon = month.split("-")
            first = date_type(int(year), int(mon), 1)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, "Oy YYYY-MM ko'rinishida bo'lishi kerak") from exc
    next_month = first.replace(day=28) + timedelta(days=4)
    last = next_month - timedelta(days=next_month.day)
    # Kelajakdagi kunlar hisobotni buzadi: jadval bor, kelish yo'q —
    # hammasi "kelmagan" bo'lib chiqardi.
    return first, min(last, today)


@app.get("/api/v1/owner/shifts")
async def owner_shifts(
    month: Optional[str] = None,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    """Oylik smena hisoboti: kim qancha kechikdi, necha kun kelmadi."""
    require_attendance()
    first, last = _month_range(month)
    return get_event_store().shift_summary(owner.site_id, start=first, end=last)


@app.get("/api/v1/owner/shifts.csv")
async def owner_shifts_csv(
    month: Optional[str] = None,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Response:
    require_attendance()
    first, last = _month_range(month)
    report = get_event_store().shift_summary(owner.site_id, start=first, end=last)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "xodim",
            "tashqi_id",
            "ish_kunlari",
            "kelgan_kunlar",
            "kelmagan_kunlar",
            "kechikkan_kunlar",
            "jami_kechikish_daq",
            "ortacha_kechikish_daq",
            "erta_ketgan_kunlar",
            "jami_erta_ketish_daq",
            "chiqish_aniqlanmadi",
        ]
    )
    for row in report["rows"]:
        writer.writerow(
            [
                row["employee_name"],
                row.get("external_id") or "",
                row["ish_kunlari"],
                row["kelgan_kunlar"],
                row["kelmagan_kunlar"],
                row["kechikkan_kunlar"],
                row["jami_kechikish_daq"],
                row["ortacha_kechikish_daq"],
                row["erta_ketgan_kunlar"],
                row["jami_erta_ketish_daq"],
                row["chiqish_aniqlanmadi"],
            ]
        )
    return Response(
        # BOM: Windows'dagi Excel usiz UTF-8 ni tanimaydi va o'zbekcha
        # harflar krakozyabra bo'lib ochiladi.  Kunlik CSV'da ham shunday.
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="smena-hisoboti-{first:%Y-%m}.csv"'
        },
    )


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


# \u2500\u2500 Yuz tanish: admin enrollment \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
#
# Rasm yuklashning IKKI yo'li bor: admin paneli va mijozning o'z paneli.
#
# Ilgari faqat admin yo'li bor edi ("rozilikni kim olganini bitta qo'lda
# ushlab turish uchun").  Amalda bu shuni anglatardi: har bir xodim uchun
# do'kon egasi operatorga murojaat qilishi kerak — ya'ni funksiya
# ishlamasdi.  Endi mijoz xodimini o'zi qo'shadi va rasmni telefon
# kamerasidan oladi; rozilik esa do'kon egasining zimmasida.

FACE_PHOTO_MAX_BYTES = 2 * 1024 * 1024


def _require_face_service() -> None:
    ok, reason = faces.available()
    if not ok:
        raise HTTPException(503, f"Yuz tanish xizmati tayyor emas: {reason}")


@app.get("/api/v1/admin/sites/{site_id}/faces")
async def admin_site_faces(site_id: str, _: None = Depends(require_admin)) -> Dict[str, Any]:
    require_attendance()
    if not get_store().get_site(site_id):
        raise HTTPException(404, "Sayt topilmadi")
    ok, reason = faces.available()
    store = get_event_store()
    photos: Dict[str, List[Dict[str, Any]]] = {}
    for face in store.list_employee_faces(site_id):
        photos.setdefault(str(face["employee_id"]), []).append(
            {
                "id": face["id"],
                "det_score": face["det_score"],
                "created_at": face["created_at"],
            }
        )
    employees = [
        {**employee, "photos": photos.get(str(employee["id"]), [])}
        for employee in store.list_employees(site_id, include_inactive=True)
    ]
    return {
        "service": {"ok": ok, "reason": reason},
        "threshold": faces.match_threshold(),
        "employees": employees,
    }


@app.post("/api/v1/admin/sites/{site_id}/employees")
async def admin_create_employee(
    site_id: str,
    body: EmployeeCreateBody,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    require_attendance()
    if not get_store().get_site(site_id):
        raise HTTPException(404, "Sayt topilmadi")
    if not body.consent:
        raise HTTPException(422, "Xodimning yozma roziligi qayd etilishi shart")
    _check_employee_limit(site_id)
    try:
        employee = get_event_store().create_employee(
            site_id,
            name=body.name,
            external_id=body.external_id,
            consent_note=body.consent_note,
        )
        get_event_store().touch_site_config(site_id)
        return employee
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/v1/admin/sites/{site_id}/faces/employees/{employee_id}/photos")
async def admin_add_employee_face(
    site_id: str,
    employee_id: str,
    request: Request,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    require_attendance()
    _require_face_service()
    if not get_store().get_site(site_id):
        raise HTTPException(404, "Sayt topilmadi")
    payload = await request.body()
    if not payload:
        raise HTTPException(422, "Rasm bo'sh")
    if len(payload) > FACE_PHOTO_MAX_BYTES:
        raise HTTPException(413, "Rasm 2 MB dan katta")
    # Embedding CPUda ~0.5 s \u2014 event loopni band qilmaslik uchun thread'da.
    embedding = await asyncio.to_thread(faces.get_face_service().embed_jpeg, payload)
    if embedding is None:
        raise HTTPException(422, "Rasmda yuz topilmadi \u2014 yaqinroq, yorug' rasm yuklang")
    face_id = uuid.uuid4().hex[:12]
    photo_key = f"{site_id}/faces/enroll/{employee_id}-{face_id}.jpg"
    try:
        record = get_event_store().add_employee_face(
            site_id,
            employee_id,
            photo_key=photo_key,
            embedding_b64=faces.encrypt_embedding(embedding.vector),
            # O'lcham yozib qo'yiladi: model almashganda eski yozuvlar
            # shu bo'yicha ajratiladi va moslashga qo'shilmaydi.
            embedding_dim=int(embedding.vector.shape[0]),
            det_score=round(float(embedding.det_score), 3),
            photo_bytes=len(payload),
        )
    except ValueError as exc:
        raise HTTPException(404 if "topilmadi" in str(exc) else 422, str(exc)) from exc
    await media_put(photo_key, payload, content_type="image/jpeg")
    get_event_store().touch_site_config(site_id)
    return record


@app.delete("/api/v1/admin/sites/{site_id}/faces/photos/{face_id}")
async def admin_delete_employee_face(
    site_id: str,
    face_id: str,
    admin: Optional[PortalPrincipal] = Depends(require_admin),
) -> Dict[str, Any]:
    require_attendance()
    photo_key = get_event_store().delete_employee_face(site_id, face_id)
    if photo_key is None:
        raise HTTPException(404, "Rasm topilmadi")
    await media_delete(photo_key)
    # Xodimga imzolatilgan rozilik shabloni namunani o'chirishni va'da
    # qiladi — ya'ni o'chirilgani ISBOTLANISHI kerak.  Jurnalsiz "biz
    # o'chirdik" degan gapdan boshqa dalil yo'q.
    get_store().audit_portal_action(
        "biometrics.photo.deleted",
        actor_id=_audit_actor(admin),
        target_type="site",
        target_id=site_id,
        detail={"face_id": face_id},
    )
    return {"ok": True, "id": face_id}


@app.get("/api/v1/admin/sites/{site_id}/faces/photos/{face_id}/image")
async def admin_employee_face_image(
    site_id: str,
    face_id: str,
    _: None = Depends(require_admin),
) -> Response:
    require_attendance()
    face = get_event_store().employee_face(site_id, face_id)
    if face is None:
        raise HTTPException(404, "Rasm topilmadi")
    return await _face_image_response(str(face["photo_key"]))


async def _face_image_response(key: str) -> Response:
    try:
        content = await media_get(key)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Rasm fayli topilmadi") from exc
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/v1/admin/sites/{site_id}/faces/events")
async def admin_face_events(
    site_id: str,
    limit: int = 50,
    _: None = Depends(require_admin),
) -> Dict[str, Any]:
    require_attendance()
    if not get_store().get_site(site_id):
        raise HTTPException(404, "Sayt topilmadi")
    return {"events": get_event_store().list_face_events(site_id, limit=limit)}


@app.get("/api/v1/admin/sites/{site_id}/faces/events/{event_id}/image")
async def admin_face_event_image(
    site_id: str,
    event_id: str,
    _: None = Depends(require_admin),
) -> Response:
    require_attendance()
    event = get_event_store().event(site_id, event_id)
    if not event or event.get("event_type") != "face_captured" or not event.get("snapshot_key"):
        raise HTTPException(404, "Kadr topilmadi")
    return await _face_image_response(str(event["snapshot_key"]))


# ── Yuz tanish: mijoz paneli (faqat o'qish) ──────────────────────────────
#
# Rasm yuklash mijozga berilmaydi — rozilik hujjati bilan birga admin
# nazoratida qoladi.  Mijoz o'z xodimlarini, davomatni va kadrlar
# galereyasini ko'radi.


@app.get("/api/v1/owner/faces")
async def owner_faces(owner: OwnerPrincipal = Depends(require_active_owner)) -> Dict[str, Any]:
    require_attendance()
    store = get_event_store()
    photos: Dict[str, List[Dict[str, Any]]] = {}
    for face in store.list_employee_faces(owner.site_id):
        photos.setdefault(str(face["employee_id"]), []).append(
            {
                "id": face["id"],
                "created_at": face["created_at"],
                # Yuz qanchalik aniq topilgani.  Bazada bor edi, lekin
                # panelga chiqmasdi — mijoz "nega tanimayapti" degan
                # savolga javob topolmasdi.  Past ball = xira yoki
                # yonboshdan olingan rasm; yechim — yana bitta shablon.
                "score": round(float(face.get("det_score") or 0.0), 2),
            }
        )
    ok, _reason = faces.available()
    site = get_store().get_site(owner.site_id) or {}
    return {
        "ready": ok,
        # Panel chegarani ko'rsatadi va tugmani o'chiradi — mijoz 11-xodimni
        # kiritib bo'lgandan keyin "bo'lmaydi" degan javob olmasin.
        "max_employees": get_plan(str(site.get("plan") or "lite")).effective_max_persons(
            int(site.get("billable_persons") or 0)
        ),
        # Xodim boshiga shablon chegarasi.  Bungacha faqat serverda
        # majburlanardi: panel to'rtinchi rasmni ham yuborar, mijoz esa
        # 422 xatosini ko'rardi.
        "max_photos": get_event_store().MAX_FACES_PER_EMPLOYEE,
        "employees": [
            {**employee, "photos": photos.get(str(employee["id"]), [])}
            for employee in store.list_employees(owner.site_id)
        ],
    }


def _owner_employee_or_404(site_id: str, employee_id: str) -> Dict[str, Any]:
    """Xodim shu do'konga tegishlimi.

    Mijoz paneli faqat o'z saytini ko'radi, lekin `employee_id` havolada
    keladi — boshqa do'konning xodimiga rasm yuklab bo'lmasligi shu yerda
    tekshiriladi.
    """
    employee = get_event_store().employee(site_id, employee_id)
    if employee is None:
        raise HTTPException(404, "Xodim topilmadi")
    return employee


@app.post("/api/v1/owner/faces/employees/{employee_id}/photos")
async def owner_add_employee_face(
    employee_id: str,
    request: Request,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    """Mijoz xodimining rasmini yuklaydi (telefon kamerasidan).

    Admin variantidan farqi faqat kirish huquqida: bu yerda sayt
    tokendan olinadi, ya'ni mijoz boshqa do'konga yozolmaydi.
    """
    require_attendance()
    require_biometric_access(owner)
    _require_face_service()
    _owner_employee_or_404(owner.site_id, employee_id)

    # Telefon kamerasi HEIC/PNG ham berishi mumkin; `embed_jpeg` cv2 bilan
    # dekodlaydi, shuning uchun PNG ham qabul qilinadi.  Boshqa turdagi
    # fayl (masalan PDF) bekorga CPU yemasin.
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
    if content_type not in {"image/jpeg", "image/png"}:
        raise HTTPException(415, "Faqat JPEG yoki PNG rasm qabul qilinadi")

    # Har rasm ~0.5 s CPU va bu ochiq (mijoz tokeni bilan) yo'l — kunlik
    # chegara qo'yilmasa bitta mijoz butun serverni band qila olardi.
    ratelimit.check(
        "face-enroll",
        owner.site_id,
        limit=60,
        window_sec=86_400,
        message="Kunlik rasm yuklash chegarasi oshdi — ertaga davom eting",
    )

    payload = await request.body()
    if not payload:
        raise HTTPException(422, "Rasm bo'sh")
    if len(payload) > FACE_PHOTO_MAX_BYTES:
        raise HTTPException(413, "Rasm 2 MB dan katta")
    embedding = await asyncio.to_thread(faces.get_face_service().embed_jpeg, payload)
    if embedding is None:
        raise HTTPException(422, "Rasmda yuz topilmadi — yaqinroq, yorug' rasm oling")

    face_id = uuid.uuid4().hex[:12]
    photo_key = f"{owner.site_id}/faces/enroll/{employee_id}-{face_id}.jpg"
    try:
        record = get_event_store().add_employee_face(
            owner.site_id,
            employee_id,
            photo_key=photo_key,
            embedding_b64=faces.encrypt_embedding(embedding.vector),
            # O'lcham yozib qo'yiladi: model almashganda eski yozuvlar
            # shu bo'yicha ajratiladi va moslashga qo'shilmaydi.
            embedding_dim=int(embedding.vector.shape[0]),
            det_score=round(float(embedding.det_score), 3),
            photo_bytes=len(payload),
        )
    except ValueError as exc:
        raise HTTPException(404 if "topilmadi" in str(exc) else 422, str(exc)) from exc
    await media_put(photo_key, payload, content_type="image/jpeg")
    get_event_store().touch_site_config(owner.site_id)
    return record


@app.post("/api/v1/owner/faces/employees/{employee_id}/photos/from-event/{event_id}")
async def owner_add_face_from_capture(
    employee_id: str,
    event_id: str,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    """Galereyadagi "tanilmagan" kadrni xodimga shablon qilib biriktiradi.

    Panelda "Tanilmagan kadr ko'p bo'lsa — xodimga yana bitta aniqroq
    rasm qo'shing" deb yozilardi, lekin buni qiladigan tugma ham,
    endpoint ham yo'q edi: mijoz telefondan qaytadan rasm olishga majbur
    edi.  Holbuki eng yaxshi shablon aynan shu — do'kondagi haqiqiy
    kamera, haqiqiy yorug'lik va haqiqiy burchak.
    """
    require_attendance()
    require_biometric_access(owner)
    _require_face_service()
    _owner_employee_or_404(owner.site_id, employee_id)

    event = get_event_store().event(owner.site_id, event_id)
    if not event or event.get("event_type") != "face_captured" or not event.get("snapshot_key"):
        raise HTTPException(404, "Kadr topilmadi")
    try:
        payload = await media_get(str(event["snapshot_key"]))
    except FileNotFoundError as exc:
        raise HTTPException(404, "Kadr o'chib ketgan (14 kundan keyin o'chadi)") from exc

    embedding = await asyncio.to_thread(faces.get_face_service().embed_jpeg, payload)
    if embedding is None:
        raise HTTPException(422, "Bu kadrda yuz topilmadi — boshqasini tanlang")

    face_id = uuid.uuid4().hex[:12]
    photo_key = f"{owner.site_id}/faces/enroll/{employee_id}-{face_id}.jpg"
    try:
        record = get_event_store().add_employee_face(
            owner.site_id,
            employee_id,
            photo_key=photo_key,
            embedding_b64=faces.encrypt_embedding(embedding.vector),
            embedding_dim=int(embedding.vector.shape[0]),
            det_score=round(float(embedding.det_score), 3),
            photo_bytes=len(payload),
        )
    except ValueError as exc:
        raise HTTPException(404 if "topilmadi" in str(exc) else 422, str(exc)) from exc
    # Kadr galereyada 14 kun yashaydi va o'chadi — shablon esa qolishi
    # kerak, shuning uchun NUSXA olinadi.
    await media_put(photo_key, payload, content_type="image/jpeg")
    get_event_store().set_face_result(
        owner.site_id, event_id, matched=True, employee_id=employee_id, score=1.0
    )
    get_event_store().touch_site_config(owner.site_id)
    return record


@app.delete("/api/v1/owner/faces/photos/{face_id}")
async def owner_delete_employee_face(
    face_id: str,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    require_attendance()
    require_biometric_access(owner)
    photo_key = get_event_store().delete_employee_face(owner.site_id, face_id)
    if photo_key is None:
        raise HTTPException(404, "Rasm topilmadi")
    await media_delete(photo_key)
    get_event_store().touch_site_config(owner.site_id)
    get_store().audit_portal_action(
        "biometrics.photo.deleted",
        actor_id=f"owner:{owner.member_id}",
        target_type="site",
        target_id=owner.site_id,
        detail={"face_id": face_id},
    )
    return {"ok": True, "id": face_id}


@app.get("/api/v1/owner/faces/events")
async def owner_face_events(
    limit: int = 30, owner: OwnerPrincipal = Depends(require_active_owner)
) -> Dict[str, Any]:
    require_attendance()
    return {"events": get_event_store().list_face_events(owner.site_id, limit=limit)}


@app.get("/api/v1/owner/faces/events/{event_id}/image")
async def owner_face_event_image(
    event_id: str, owner: OwnerPrincipal = Depends(require_active_owner)
) -> Response:
    require_attendance()
    require_biometric_access(owner)
    event = get_event_store().event(owner.site_id, event_id)
    if not event or event.get("event_type") != "face_captured" or not event.get("snapshot_key"):
        raise HTTPException(404, "Kadr topilmadi")
    return await _face_image_response(str(event["snapshot_key"]))


@app.get("/api/v1/owner/faces/photos/{face_id}/image")
async def owner_employee_face_image(
    face_id: str, owner: OwnerPrincipal = Depends(require_active_owner)
) -> Response:
    require_attendance()
    require_biometric_access(owner)
    face = get_event_store().employee_face(owner.site_id, face_id)
    if face is None:
        raise HTTPException(404, "Rasm topilmadi")
    return await _face_image_response(str(face["photo_key"]))


#: Bizning ichki pul ko'rsatkichlarimiz.  Ular admin javoblarida qoladi,
#: mijoz javoblaridan esa OLIB TASHLANADI.  `public_pricing` bu qoidani
#: allaqachon bajaradi; mijoz marshrutlari uni buzardi va do'kon egasi
#: brauzerda biz qancha foyda olayotganimizni o'qiy olardi — aynan narx
#: bo'yicha gaplashayotgan paytda.
_INTERNAL_MONEY_KEYS = ("cost_usd_cents", "cost_total_usd_cents", "gross_margin_percent")


def _without_internal_money(payload: Any) -> Any:
    """Javobning istalgan chuqurligidan ichki narxni olib tashlaydi.

    Rekursiv: `feature_quote` tannarxni ham yuqori darajada, ham har bir
    `features[]` elementida qaytaradi, `site_feature_summary` esa uni
    `assignments`, `drafts` va `active_quote` ichida uchta joyda beradi.
    Bitta joyni unutib qo'yish oson — shuning uchun filtr umumiy.
    """
    if isinstance(payload, dict):
        return {
            key: _without_internal_money(value)
            for key, value in payload.items()
            if key not in _INTERNAL_MONEY_KEYS
        }
    if isinstance(payload, list):
        return [_without_internal_money(item) for item in payload]
    return payload


@app.get("/api/v1/owner/features")
async def owner_features(owner: OwnerPrincipal = Depends(require_active_owner)) -> Dict[str, Any]:
    """Mijoz o'z obunasi va tanlash mumkin bo'lgan funksiyalarni ko'radi."""
    return _without_internal_money(
        {
            "catalog": get_store().list_feature_catalog(),
            "summary": get_store().site_feature_summary(owner.site_id),
        }
    )


@app.post("/api/v1/owner/features/quote")
async def owner_feature_quote(
    body: FeatureDraftBody, owner: OwnerPrincipal = Depends(require_active_owner)
) -> Dict[str, Any]:
    try:
        quote = get_store().feature_quote([item.model_dump() for item in body.selections])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _without_internal_money(quote)


@app.put("/api/v1/owner/features/request")
async def owner_feature_request(
    body: FeatureDraftBody, owner: OwnerPrincipal = Depends(require_active_owner)
) -> Dict[str, Any]:
    """Mijoz so'rovi draft bo'ladi; narx o'zgarishini admin tasdiqlaydi."""
    require_owner_role(owner, "owner", "manager")
    try:
        summary = get_store().replace_feature_draft(
            owner.site_id, [item.model_dump() for item in body.selections]
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _without_internal_money(summary)


@app.get("/api/v1/owner/members")
async def owner_members(owner: OwnerPrincipal = Depends(require_active_owner)) -> Dict[str, Any]:
    # `me` — panel o'z qatorini topib, digest tumblerini to'g'ri ko'rsatishi
    # uchun (token ichidagi member_id brauzerga boshqa yo'l bilan chiqmaydi).
    return {
        "members": get_event_store().list_members(owner.site_id),
        "me": owner.member_id,
        "role": owner.role,
    }


#: `secrets.token_urlsafe(24)` — aynan 32 ta belgi.  Boshqa uzunlikdagi
#: `/start` payload'lari (masalan `register`) taklif emas.
INVITE_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{32}")


class TelegramInviteBody(BaseModel):
    #: `owner` — mijozning o'zi (kirgan hisobiga Telegramni bog'laydi).
    #: `manager` — xodim: hisobot va ogohlantirish oladi, sozlamaga tegmaydi.
    role: Literal["owner", "manager"] = "manager"
    display_name: Optional[str] = Field(default=None, max_length=120)


@app.post("/api/v1/owner/telegram-invite")
async def owner_telegram_invite(
    body: TelegramInviteBody,
    request: Request,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    """Telegramni ulash yoki xodim taklif qilish uchun bir martalik havola.

    Nega kerak: a'zo qo'shish uchun panelda RAQAMLI Telegram ID so'ralardi.
    Do'kon egasi o'z ID sini ham, xodimining ID sini ham bilmaydi va uni
    topish yo'li ko'rsatilmagan edi — ya'ni funksiya amalda ishlamasdi.

    Havola credential: uni bosgan odam panelga kiradi.  Shuning uchun
    bir martalik va 30 daqiqada eskiradi.
    """
    require_owner_role(owner, "owner", "service_admin")
    ratelimit.check(
        "tg-invite",
        owner.site_id,
        limit=10,
        window_sec=3_600,
        message="Juda ko'p havola yaratildi. Bir soatdan keyin urinib ko'ring.",
    )
    bot = os.environ.get("CHAQIMCHI_TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", bot):
        raise HTTPException(503, "Telegram bot sozlanmagan — administrator bilan bog'laning")
    invite = get_event_store().create_telegram_invite(
        owner.site_id,
        secret=_owner_secret(),
        role=body.role,
        display_name=body.display_name,
    )
    return {
        "url": f"https://t.me/{bot}?start={invite['token']}",
        "expires_minutes": invite["expires_minutes"],
        "role": body.role,
    }


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


class DigestPrefBody(BaseModel):
    muted: bool


@app.put("/api/v1/owner/digest")
async def owner_set_digest_pref(
    body: DigestPrefBody,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    """Kunlik hisobotni o'zi uchun yoqadi/o'chiradi.

    Bungacha digest majburiy edi — o'chirishning yagona yo'li a'zolikdan
    chiqish edi.  Sozlama a'zoning o'ziga tegishli: boshqalarga ta'sir
    qilmaydi.
    """
    if owner.auth_kind != "telegram":
        raise HTTPException(400, "Bu sozlama faqat Telegram a'zolari uchun")
    if not get_event_store().set_digest_muted(owner.site_id, owner.member_id, body.muted):
        raise HTTPException(404, "A'zo topilmadi")
    return {"ok": True, "digest_muted": body.muted}


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
    get_store().audit_portal_action(
        "site.member.removed",
        actor_id=f"owner:{owner.member_id}",
        target_type="site",
        target_id=owner.site_id,
        detail={"member_id": member_id},
    )
    return {"ok": True}


@app.get("/api/v1/owner/events/{event_id}/snapshot")
async def owner_snapshot(
    event_id: str,
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Response:
    event = get_event_store().event(owner.site_id, event_id)
    if not event or not event.get("snapshot_key"):
        raise HTTPException(404, "Snapshot topilmadi")
    if event.get("event_type") in {"face_captured", "employee_seen"}:
        require_biometric_access(owner)
    try:
        content = await media_get(event["snapshot_key"])
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
    if event.get("event_type") in {"face_captured", "employee_seen"}:
        require_biometric_access(owner)
    try:
        content = await media_get(event["clip_key"])
    except FileNotFoundError as exc:
        raise HTTPException(404, "Videoklip topilmadi") from exc
    return Response(content=content, media_type="video/mp4")


@app.get("/api/v1/admin/sites/{site_id}/events/{event_id}/snapshot")
async def admin_event_snapshot(
    site_id: str, event_id: str, _: None = Depends(require_admin)
) -> Response:
    event = get_event_store().event(site_id, event_id)
    if not event or not event.get("snapshot_key"):
        raise HTTPException(404, "Snapshot topilmadi")
    try:
        return Response(content=await media_get(event["snapshot_key"]), media_type="image/jpeg")
    except FileNotFoundError as exc:
        raise HTTPException(404, "Snapshot topilmadi") from exc


@app.get("/api/v1/admin/sites/{site_id}/events/{event_id}/clip")
async def admin_event_clip(
    site_id: str, event_id: str, _: None = Depends(require_admin)
) -> Response:
    event = get_event_store().event(site_id, event_id)
    if not event or not event.get("clip_key"):
        raise HTTPException(404, "Videoklip topilmadi")
    try:
        return Response(content=await media_get(event["clip_key"]), media_type="video/mp4")
    except FileNotFoundError as exc:
        raise HTTPException(404, "Videoklip topilmadi") from exc


#: Tugma ma'lumoti — `speak:deter` ko'rinishida.  Telegram `callback_data`
#: uchun 64 baytdan ko'p bermaydi, shuning uchun sayt ID yozilmaydi:
#: sayt bosgan odamning a'zoligidan aniqlanadi.
CALLBACK_SPEAK_PREFIX = "speak:"

#: "Ko'rdim" tugmasi — hodisani o'qilgan deb belgilaydi.  Egasi javob
#: berganini BILISH kerak: aks holda biz uni qayta-qayta bezovta qilamiz.
CALLBACK_ACK = "ack"


async def _handle_callback(callback: Dict[str, Any]) -> Dict[str, Any]:
    """Telegram tugmasi bosilganda ishlaydi.

    Xavfsizlik: `callback_data` ga sayt ID yozilmaydi va u ISHONILMAYDI.
    Sayt bosgan odamning a'zoligidan topiladi — aks holda istalgan odam
    o'z botiga tugma yasab, begona do'kon karnayini yangratardi.
    """
    callback_id = str(callback.get("id") or "")
    data = str(callback.get("data") or "")
    telegram_id = str(((callback.get("from") or {}).get("id")) or "")
    if not callback_id or not telegram_id:
        return {"ok": True}

    members = get_event_store().members_for_telegram(telegram_id)
    if not members:
        await _answer_callback(callback_id, "Sizda do'kon biriktirilmagan.", alert=True)
        return {"ok": True}
    member = members[0]
    site_id = str(member["site_id"])

    if data == CALLBACK_ACK:
        await _answer_callback(callback_id, "Qabul qilindi — rahmat.")
        return {"ok": True}

    if data.startswith(CALLBACK_SPEAK_PREFIX):
        phrase = data[len(CALLBACK_SPEAK_PREFIX) :]
        # Karnay butun do'konda eshitiladi — faqat egasi.
        if str(member.get("role")) not in {"owner", "service_admin"}:
            await _answer_callback(callback_id, "Buni faqat do'kon egasi qila oladi.", alert=True)
            return {"ok": True}
        try:
            _announce(site_id, phrase, requested_by=telegram_id)
        except HTTPException as exc:
            await _answer_callback(callback_id, str(exc.detail), alert=True)
            return {"ok": True}
        item = announcements.BY_CODE.get(phrase)
        spoken = item.text if item else ""
        await _answer_callback(callback_id, f"Do'konda eshitiladi: «{spoken}»")
        return {"ok": True}

    await _answer_callback(callback_id, "Bu tugma endi ishlamaydi.")
    return {"ok": True}


#: Fon tasklariga KUCHLI havola.  `asyncio.create_task` natijasi saqlanmasa
#: GC uni yakunlanmasidan yo'q qilishi mumkin — javob kutayotgan mijoz
#: xabarsiz qolardi.
_background_tasks: set[asyncio.Task[Any]] = set()


def _spawn_background(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _telegram_vision_result(chat_id: str, site_id: str, job_id: str) -> None:
    """Webhookni ushlab turmasdan Agent natijasini keyin yuboradi."""
    for _ in range(90):
        await asyncio.sleep(2)
        # Sync DB chaqiruvi event loopni bloklamasin — har 2 soniyada
        # 3 daqiqagacha davom etadi.
        job = await asyncio.to_thread(get_event_store().vision_job, site_id, job_id)
        if not job or job.get("status") in {"queued", "running"}:
            continue
        if job.get("status") == "failed":
            await _send_owner_telegram(chat_id, "❌ Agent javob bera olmadi. Keyinroq qayta urinib ko'ring.")
            return
        result = job.get("result") or {}
        await _send_owner_telegram(chat_id, f"🤖 <b>Chaqimchi yordamchisi</b>\n\n{botfmt.escape(str(result.get('answer') or 'Javob tayyor.'))}")
        if job.get("audio_reply_key"):
            try:
                await _send_owner_voice(
                    chat_id,
                    await media_get(str(job["audio_reply_key"])),
                    "Chaqimchi yordamchisi javobi",
                    mime=str(result.get("audio_reply_mime") or "audio/wav"),
                )
            except Exception:
                logger.warning("Agent audio javobi Telegramga yuborilmadi", exc_info=True)
        sources = result.get("sources") or []
        if sources:
            event = get_event_store().event(site_id, str(sources[0].get("event_id") or ""))
            # Yuz kadrlari Telegramga KETMAYDI: panel media endpointidagi
            # rol-guard shu yerda ham amal qiladi, aks holda har qanday
            # a'zo xodim yuzini chatda olardi.
            if (
                event
                and event.get("snapshot_key")
                and event.get("event_type") not in {"face_captured", "employee_seen"}
            ):
                try:
                    photo = await media_get(str(event["snapshot_key"]))
                    await _send_owner_photo(chat_id, photo, "Dalil: " + botfmt.escape(str(sources[0].get("label") or "Hodisa")))
                except Exception:
                    logger.warning("Agent dalil rasmi Telegramga yuborilmadi", exc_info=True)
        return
    await _send_owner_telegram(chat_id, "⌛ Agent javobi cho'zildi. Paneldan keyinroq natijani ko'ring.")


async def _telegram_voice_bytes(file_id: str) -> tuple[bytes, str]:
    """Telegram voice faylini faqat Agent jobi uchun vaqtincha oladi."""
    import httpx

    token = (os.environ.get("CHAQIMCHI_OWNER_TELEGRAM_TOKEN", "").strip() or os.environ.get("CHAQIMCHI_CLOUD_TELEGRAM_TOKEN", "").strip())
    if not token:
        raise RuntimeError("Owner Telegram bot tokeni sozlanmagan")
    async with httpx.AsyncClient(timeout=25) as client:
        metadata = await client.get(f"https://api.telegram.org/bot{token}/getFile", params={"file_id": file_id})
        metadata.raise_for_status()
        path = str((metadata.json().get("result") or {}).get("file_path") or "")
        if not path:
            raise RuntimeError("Telegram voice fayli topilmadi")
        response = await client.get(f"https://api.telegram.org/file/bot{token}/{path}")
        response.raise_for_status()
        return response.content, "audio/ogg"


@app.post("/api/v1/telegram/webhook")
async def owner_telegram_webhook(
    request: Request,
    x_telegram_secret: Optional[str] = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> Dict[str, Any]:
    expected = os.environ.get("CHAQIMCHI_TELEGRAM_WEBHOOK_SECRET", "").strip()
    if (
        not expected
        or not x_telegram_secret
        or not secrets.compare_digest(x_telegram_secret, expected)
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

    # ── Tugma bosildi ────────────────────────────────────────────────
    #
    # Bungacha `callback_query` UMUMAN ushlanmasdi: xabarga tugma
    # qo'yilsa ham bosish hech narsa qilmasdi.  Ovoz berish aynan shu
    # yo'ldan ishlaydi.
    callback = update.get("callback_query") or {}
    if callback:
        return await _handle_callback(callback)

    message = update.get("message") or {}
    chat = message.get("chat") or {}
    telegram_id = str(chat.get("id") or "")
    text = str(message.get("text") or "").strip()
    command = text.split()[0].lower().split("@", 1)[0] if text else ""
    # Eski buyruqlar yashaydi — foydalanuvchi yodlab qolgan bo'lishi mumkin.
    command = BOT_COMMAND_ALIASES.get(command, command)
    members = get_event_store().members_for_telegram(telegram_id)
    base = public_url().rstrip("/") or str(request.base_url).rstrip("/")

    # `/start <token>` — panelda yaratilgan taklif havolasi.  Do'kon egasi
    # o'z Telegramini ulaydi yoki xodimini qo'shadi, RAQAM YOZMASDAN.
    # Telegram payload'ni aynan shu ko'rinishda uzatadi.
    #
    # Faqat taklif tokeniga o'xshagan payload ushlanadi.  `/start register`
    # kabi mavjud so'zlar pastdagi odatiy yo'lga o'tishi SHART — aks holda
    # ro'yxatdan o'tish tugmasi ishlamay qoladi.
    payload = text.split(maxsplit=1)[1].strip() if command == "/start" and " " in text else ""
    if not INVITE_TOKEN_RE.fullmatch(payload):
        payload = ""
    if telegram_id and chat.get("type") == "private" and payload:
        if not ratelimit.limiter().hit("tg-invite-use", telegram_id, limit=10, window_sec=600):
            return {"ok": True}
        redeemed = get_event_store().redeem_telegram_invite(
            payload, telegram_id, secret=_owner_secret()
        )
        members = get_event_store().members_for_telegram(telegram_id)
        # Havola ISHLATILGAN, lekin a'zolik allaqachon bor — bu odam
        # ikkinchi marta bosgan yoki Telegram xabarni qayta yuborgan.
        # Unga "eskirgan" deyish yolg'on bo'lardi: u ulangan.
        if redeemed or members:
            site = get_store().get_site(redeemed["site_id"]) if redeemed else {}
            name = str((site or {}).get("name") or "Do‘kon")
            try:
                await _send_owner_telegram(
                    telegram_id,
                    f"✅ <b>{botfmt.escape(name)}</b> ulandi.\n"
                    "Endi kunlik hisobot va muhim ogohlantirishlar shu yerga keladi.",
                    reply_markup=botfmt.panel_button(base),
                )
            except Exception:
                # Xabar ketmasa ham a'zolik saqlanib qoldi.  Bu yerda
                # xato qaytarsak Telegram update'ni qayta yuboradi va
                # o'sha odam "havola eskirgan" degan yolg'on javob oladi.
                logger.warning("taklif tasdig'i yuborilmadi", extra={"telegram_id": telegram_id})
            return {"ok": True}
        try:
            await _send_owner_telegram(
                telegram_id,
                "Havola eskirgan yoki allaqachon ishlatilgan.\n"
                "Do‘kon panelidan yangi havola oling.",
            )
        except Exception:
            logger.warning("taklif rad javobi yuborilmadi", extra={"telegram_id": telegram_id})
        return {"ok": True}

    if (
        telegram_id
        and chat.get("type") == "private"
        and (command == "/start" or (command == "/yordam" and not members))
    ):
        # /start har bosilganda xabar + yangi kirish havolasi yaratiladi —
        # cheklovsiz bu DB'ni ham, chatni ham bo'lar edi.  Oshib ketsa
        # indamay qaytamiz: webhook'ka 429 berish Telegram'ni retry'ga
        # undaydi.
        if not ratelimit.limiter().hit("tg-start", telegram_id, limit=5, window_sec=600):
            return {"ok": True}
        text_out, markup = _bot_welcome(base, telegram_id, members)
        await _send_owner_telegram(telegram_id, text_out, reply_markup=markup)
        return {"ok": True}
    if not telegram_id or not members:
        return {"ok": True}

    # Oddiy Uzbek matn yoki Telegram voice — Agentga savol. Buyruqlar esa
    # avvalgidek o'z yo'lida qoladi, shuning uchun /hisobot va /kamera sinmaydi.
    # FAQAT shaxsiy chat: bot qo'shilgan guruhda har matn kvota yeb yuborardi.
    voice = message.get("voice") or {}
    if chat.get("type") == "private" and (voice or (text and not command.startswith("/"))):
        member = members[0]
        site_id = str(member["site_id"])
        settings = get_event_store().vision_settings(site_id)
        if not settings["consented"]:
            # Avval roziliksiz MATN savoli indamay "Buyruqlar:" ro'yxatiga
            # tushardi — odam Uzbek tilida savol berib buyruq ro'yxati olardi.
            # Endi ikkalasiga ham aniq yo'l ko'rsatiladi (soatiga 2 marta —
            # har bitta matnga javob spam bo'lardi).
            if ratelimit.limiter().hit("tg-agent-consent", telegram_id, limit=2, window_sec=3600):
                await _send_owner_telegram(
                    telegram_id,
                    "Savolga kamera dalillari bilan javob beradigan <b>AI yordamchi</b> "
                    "bu filialda hali yoqilmagan.\n"
                    "Panel → <b>AI yordamchi</b> bo‘limida rozilik berilsa, shu yerga "
                    "oddiy matn yoki ovozli xabar bilan savol bera olasiz.",
                    reply_markup=botfmt.panel_button(urls.app_url() or base),
                )
            return {"ok": True}
        if not vision_agent.configured():
            await _send_owner_telegram(
                telegram_id,
                "AI yordamchi hali texnik sozlanmoqda — tayyor bo'lishi bilan xabar "
                "beramiz. Hozircha /hisobot va /kamera ishlayveradi.",
            )
            return {"ok": True}
        try:
            _check_vision_daily_limit(site_id)
            if voice:
                if int(voice.get("file_size") or 0) > 10 * 1024 * 1024:
                    raise HTTPException(413, "Ovoz 10 MB dan kichik bo'lishi kerak")
                payload, mime = await _telegram_voice_bytes(str(voice.get("file_id") or ""))
                key = f"agent/audio/{site_id}/{uuid.uuid4()}.ogg"
                await media_put(key, payload, content_type=mime)
                job = get_event_store().create_vision_job(
                    site_id, requester_id=telegram_id, requester_kind="telegram", audio_key=key, audio_mime=mime,
                    want_audio_reply=bool(settings["audio_reply_enabled"]),
                )
            else:
                job = get_event_store().create_vision_job(
                    site_id, requester_id=telegram_id, requester_kind="telegram", question=text,
                    want_audio_reply=bool(settings["audio_reply_enabled"]),
                )
            # Ko'p filialli egaga QAYSI filial javob berayotgani aytiladi —
            # savol jimgina birinchi filialga ketishi chalg'itardi.
            branch_note = ""
            if len({str(m["site_id"]) for m in members}) > 1:
                site_row = get_store().get_site(site_id) or {}
                branch_note = f" ({botfmt.escape(str(site_row.get('name') or site_id))} bo'yicha)"
            await _send_owner_telegram(
                telegram_id,
                f"⏳ Savol qabul qilindi{branch_note}. Kamera dalillari tekshirilmoqda…",
            )
            _spawn_background(_telegram_vision_result(telegram_id, site_id, str(job["id"])))
        except HTTPException as exc:
            # Kvota/o'lcham xatosi mijozga TUSHUNARLI aytiladi — "keyinroq
            # urinib ko'ring" hammasini yashirardi.
            await _send_owner_telegram(telegram_id, str(exc.detail))
        except Exception:
            logger.warning("Telegram Vision Agent so'rovi qabul qilinmadi", exc_info=True)
            await _send_owner_telegram(telegram_id, "Savol qabul qilinmadi. Keyinroq qayta urinib ko'ring.")
        return {"ok": True}

    if command == "/yordam":
        await _send_owner_telegram(
            telegram_id,
            "<b>Chaqimchi AI bot buyruqlari</b>\n\n"
            "/hisobot — bugungi hisobot: kirdi-chiqdi, navbat, gavjum soat\n"
            "/kamera — har kameradan oxirgi rasm\n"
            "/panel — mijoz paneliga kirish havolasi\n"
            "/yordam — shu ro'yxat\n"
            "Oddiy matn yoki voice xabar — Vision Agentga savol\n\n"
            "Har kuni kechqurun kunlik, dushanba ertalab haftalik hisobot "
            "avtomatik keladi. Muhim ogohlantirishlar (kamera o'chdi va h.k.) "
            "darhol yuboriladi.",
        )
    elif command == "/panel":
        if not ratelimit.limiter().hit("tg-start", telegram_id, limit=5, window_sec=600):
            return {"ok": True}
        await _send_owner_telegram(
            telegram_id,
            "📊 <b>Mijoz paneli</b> — quyidagi tugma orqali kiring.",
            reply_markup=botfmt.panel_button(urls.app_url() or base),
        )
    elif command == "/kamera":
        # Har bosishda kamera boshiga bitta rasm ketadi — spam bo'lmasin.
        if not ratelimit.limiter().hit("tg-kamera", telegram_id, limit=5, window_sec=600):
            return {"ok": True}
        await _bot_send_camera_photos(telegram_id, members)
    elif command == "/hisobot":
        await _bot_send_report(telegram_id, members, base)
    else:
        await _send_owner_telegram(
            telegram_id,
            "Buyruqlar: /hisobot, /kamera, /panel, /yordam",
        )
    return {"ok": True}


#: Eski buyruqlar → yangi nomlar (foydalanuvchiga sinish yo'q).
BOT_COMMAND_ALIASES = {
    "/today": "/hisobot",
    "/status": "/hisobot",
    "/cameras": "/kamera",
    "/help": "/yordam",
}


def _bot_panel_url(base: str, telegram_id: str, members: List[Dict[str, Any]]) -> Tuple[str, bool]:
    """Eski callerlar uchun owner panelining Mini App URL'i.

    Telegram WebApp imzolangan `initData` yuboradi; URL ichidagi login token
    kerak emas va chat tarixida credential qolmaydi.
    """
    del telegram_id, members
    return f"{urls.app_url() or base}/owner", False


def _bot_welcome(
    base: str, telegram_id: str, members: List[Dict[str, Any]]
) -> Tuple[str, Dict[str, Any]]:
    if members:
        text = (
            "👋 <b>Chaqimchi AI</b> — do'koningiz nazorati.\n\n"
            "Panelga quyidagi tugma orqali kiring.\n\n"
            "Foydali buyruqlar:\n"
            "/hisobot — bugungi hisobot\n"
            "/kamera — kameralardan jonli rasm\n"
            "/yordam — to'liq ro'yxat"
        )
        markup = botfmt.panel_button(urls.app_url() or base)
        return text, markup
    text = (
        "👋 <b>Chaqimchi AI</b> — do'kon uchun aqlli kamera-nazorat.\n\n"
        "Kameralaringiz do'konni o'zi kuzatadi: kirdi-chiqdi hisobi, navbat, "
        "xavfsizlik ogohlantirishlari — hammasi shu botda va panelda. "
        "Tarif bitta: oyiga $20 (so'mda kurs bo'yicha), hammasi ichida.\n\n"
        "Tizim o'rnatilgan bo'lsa, mijoz panelini oching. O'rnatish uchun "
        "kelgan bo'lsangiz — o'rnatuvchi bo'limi."
    )
    markup = {
        "inline_keyboard": [
            [{"text": "🏪 Mijoz paneli", "web_app": {"url": f"{urls.app_url() or base}/owner"}}],
            [{"text": "🛠 O'rnatuvchi bo'limi", "url": f"{urls.partner_url() or base}/installer"}],
            [{"text": "💰 Tarif va narx", "url": f"{urls.public_url() or base}/#narx"}],
        ]
    }
    return text, markup


async def _bot_send_report(telegram_id: str, members: List[Dict[str, Any]], base: str) -> None:
    """/hisobot — bugungi holat, kunlik digest formatida."""
    store_events = get_event_store()
    for member in members:
        site_id = str(member["site_id"])
        site = get_store().get_site(site_id)
        if not site:
            continue
        report = store_events.retail_report(site_id)
        stats = store_events.stats(site_id)
        traffic = report.get("traffic") or {}
        if not stats.get("total") and not traffic.get("entered"):
            await _send_owner_telegram(
                telegram_id,
                f"{botfmt.header(site['name'])}\nBugun hali hodisa yo'q.",
            )
            continue
        try:
            config = store_events.get_site_config(site_id)["config"]
            open_from = config.get("open_from") or None
        except Exception:
            open_from = None
        first_movement = store_events.first_movement_time(site_id) if open_from else None
        text_out = build_digest(
            str(site["name"]),
            str(report["date"]),
            stats,
            report,
            open_from=open_from,
            first_movement=first_movement,
        )
        detail = get_store().site_detail(site_id)
        text_out += (
            f"\n📷 Kamera: {detail['cameras_active']}/{detail['cameras_expected']} "
            f"ishlayapti · aloqa {detail['connection']}"
        )
        await _send_owner_telegram(
            telegram_id, text_out, reply_markup=botfmt.panel_button(urls.app_url() or base)
        )


async def _bot_send_camera_photos(telegram_id: str, members: List[Dict[str, Any]]) -> None:
    """/kamera — har kameradan oxirgi kadr + yangi kadr so'rovi.

    Qurilma jonli strim bermaydi (zaif kompyuter, cloud orqali o'tkazish
    qimmat) — buning o'rniga oxirgi saqlangan kadr darhol yuboriladi va
    keyingi heartbeat'da (≤1 daqiqa) yangisi so'raladi.
    """
    for member in members:
        site_id = str(member["site_id"])
        try:
            cameras = [c for c in get_store().list_cameras(site_id) if c["enabled"]]
        except ValueError:
            continue
        if not cameras:
            await _send_owner_telegram(
                telegram_id,
                "Kameralar hali ulanmagan — o'rnatuvchingiz bilan bog'laning.",
            )
            continue
        missing: List[str] = []
        for camera in cameras:
            label = str(camera.get("label") or camera["camera_id"])
            key = camera.get("preview_key")
            photo: Optional[bytes] = None
            if key:
                try:
                    photo = await media_get(str(key))
                except FileNotFoundError:
                    photo = None
            if photo is None:
                missing.append(label)
            else:
                caption = f"📷 <b>{botfmt.escape(label)}</b>"
                taken = botfmt.stamp(camera.get("preview_at"))
                if taken:
                    caption += f" · {taken}"
                try:
                    await _send_owner_photo(telegram_id, photo, caption)
                except TelegramSendError:
                    logger.warning(
                        "Kamera rasmi yuborilmadi: site=%s camera=%s",
                        site_id,
                        camera["camera_id"],
                        exc_info=True,
                    )
            try:
                get_store().request_camera_preview(site_id, str(camera["camera_id"]))
            except ValueError:
                pass
        tail = "🔄 Yangi rasm so'raldi — 1 daqiqadan keyin /kamera ni qayta bosing."
        if missing:
            tail = (
                "Hali rasm kelmagan: " + ", ".join(botfmt.escape(m) for m in missing) + "\n" + tail
            )
        await _send_owner_telegram(telegram_id, tail)


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


@app.get("/api/v1/owner/subscription")
async def owner_subscription(
    owner: OwnerPrincipal = Depends(require_active_owner),
) -> Dict[str, Any]:
    """Obuna holati va yillik taklif — mijoz paneli uchun.

    `owner_health` tarif cheklovlarini beradi, lekin obuna qachon
    tugashini ham, narxni ham bermaydi.  Yillik taklifni ko'rsatish uchun
    ikkalasi kerak.

    Summalar `plans.py` va `billable_months()` dan HISOBLANADI — panelga
    qo'lda yozilgan raqam hisob-fakturadagidan farq qilib qolardi.
    """
    store = get_store()
    site = store.get_site(owner.site_id)
    if not site:
        raise HTTPException(404, "Do'kon topilmadi")
    status = store.subscription_status(owner.site_id)
    monthly = store.effective_monthly_uzs(owner.site_id)
    charged = YEARLY_MONTHS_CHARGED
    return {
        "status": status["status"],
        "days_left": status["days_left"],
        "message": status.get("message", ""),
        # `_compute_status` sanani qaytarmaydi — u faqat holat hisoblaydi.
        "subscription_until": site["subscription_until"],
        "grace_days": GRACE_DAYS,
        "plan": plan_display_name(str(site.get("plan") or "")),
        "monthly_uzs": monthly,
        "annual_uzs": monthly * charged,
        "annual_saving_uzs": monthly * (12 - charged),
        "free_months": 12 - charged,
    }


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
    admin: Optional[PortalPrincipal] = Depends(require_admin),
) -> Dict[str, Any]:
    """Naqd/bank to'lovi — obuna avtomatik uzayadi."""
    try:
        invoice = get_payments().mark_paid(
            invoice_id, body.provider, provider_txn_id=body.reference
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    # Eng "bahsli" amal: naqd to'lovni odam qo'lda tasdiqlaydi va tashqi
    # provayderdan hech qanday iz qolmaydi.  Kim tasdiqlagani yozilmasa,
    # "to'ladim / to'lamadingiz" bahsida hech kimda dalil yo'q.
    get_store().audit_portal_action(
        "invoice.marked_paid",
        actor_id=_audit_actor(admin),
        target_type="invoice",
        target_id=invoice_id,
        detail={
            "provider": body.provider,
            "reference": body.reference,
            "amount_uzs": invoice.get("amount_uzs"),
            "site_id": invoice.get("site_id"),
        },
    )
    return invoice


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
async def pay_page(invoice_id: str, request: Request) -> HTMLResponse:
    """Mijozga yuboriladigan sahifa: summa + Payme/Click tugmalari.

    `_render_public` orqali beriladi, chunki sahifada Telegram va panel
    havolalari bor: to'lov ishlamay qolgan mijoz shu yerda qolib
    ketmasligi kerak.
    """
    return _render_public("pay.html", request)


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
