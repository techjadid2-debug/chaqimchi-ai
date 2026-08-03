"""
Chaqimchi Cloud — mijozlar, litsenziya, o‘rnatish juftlash.

Ishga tushirish: make run-cloud  (port 8750)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from chaqimchi_ai.licensing.plans import PLANS, PlanTier, cheapest_plan_for
from cloud.alerts import AlertService, test_message
from cloud.payments import PaymentStore, click_config, payme_config, public_url
from cloud.payments import click as click_api
from cloud.payments import payme as payme_api
from cloud.store import CloudStore

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "cloud" / "cloud.db"
STATIC_DIR = Path(__file__).resolve().parent / "static"

_store: Optional[CloudStore] = None
_payments: Optional[PaymentStore] = None
_alerts: Optional[AlertService] = None


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


def require_admin(
    x_cloud_admin_key: Optional[str] = Header(None, alias="X-Cloud-Admin-Key"),
) -> None:
    expected = os.environ.get("CHAQIMCHI_CLOUD_ADMIN_KEY", "").strip()
    if not expected:
        raise HTTPException(503, "CHAQIMCHI_CLOUD_ADMIN_KEY sozlanmagan")
    if not x_cloud_admin_key or x_cloud_admin_key.strip() != expected:
        raise HTTPException(401, "Admin kalit noto‘g‘ri")


class CreateSiteBody(BaseModel):
    name: str
    plan: PlanTier = "business"
    subscription_months: int = Field(default=1, ge=1, le=60)
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    #: Davomat tariflarida shartnomadagi xodim soni — oylik to‘lov shunga bog‘liq.
    billable_persons: int = Field(default=0, ge=0, le=100_000)


class ClaimDeviceBody(BaseModel):
    pairing_code: str
    label: str = "edge-1"
    hardware_id: Optional[str] = None


class HeartbeatBody(BaseModel):
    active_cameras: int = 0
    app_version: str = "0.2.0"


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


def get_alerts() -> AlertService:
    """Aloqa ogohlantirishi xizmati. `_store` almashsa qayta quriladi."""
    global _alerts
    store = get_store()
    if _alerts is None or _alerts.store is not store:
        _alerts = AlertService(store)
    return _alerts


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_payments()
    alerts = get_alerts()
    alerts.start()
    try:
        yield
    finally:
        await alerts.stop()


app = FastAPI(title="Chaqimchi Cloud", lifespan=lifespan)


if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"ok": True, "service": "chaqimchi-cloud"}


@app.get("/admin", include_in_schema=False)
async def admin_panel() -> FileResponse:
    """Admin paneli. Kirish admin kalit bilan — brauzerda so‘raladi va API ga yuboriladi."""
    page = STATIC_DIR / "admin.html"
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
                "monthly_price_uzs": v.monthly_price_uzs,
                "install_price_uzs": v.install_price_uzs,
                "per_person_uzs": v.price_per_person_uzs,
                "billing": "per_person" if v.is_per_person else "flat",
            }
            for k, v in PLANS.items()
        }
    }


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


@app.get("/api/v1/admin/stats")
async def admin_stats(_: None = Depends(require_admin)) -> Dict[str, Any]:
    return {**get_store().stats(), **get_payments().invoice_stats()}


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
    expected: int = Field(ge=0, le=64)


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
async def claim_device(body: ClaimDeviceBody) -> Dict[str, str]:
    try:
        return get_store().claim_device(
            body.pairing_code,
            hardware_id=body.hardware_id,
            label=body.label,
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
