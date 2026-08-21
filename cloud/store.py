"""Cloud litsenziya bazasi (SQLite)."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken

from chaqimchi_ai.licensing.plans import (
    DEFAULT_USD_RATE_UZS,
    LITE_MONTHLY_PRICE_USD_CENTS,
    PlanTier,
    get_plan,
    usd_rate_uzs,
)
from chaqimchi_ai.pilot_acceptance import pilot_acceptance_status
from chaqimchi_ai.sotqin_profile import GUARANTEED_CAMERAS
from cloud.portal_auth import hash_password, normalize_username, verify_password

# V1 cloud-AI katalogi. Narxlar sentda saqlanadi: invoice va shartnoma
# snapshotlari floating-point xatodan holi bo'lishi kerak.
#
# Baza narxi Lite obunasining o'zi — ikkita mustaqil konstanta bo'lsa ular
# sekin-asta ajralib ketadi va mijoz saytdagidan boshqa summa to'laydi.
DEFAULT_BASE_FEE_USD_CENTS = LITE_MONTHLY_PRICE_USD_CENTS
DEFAULT_FEATURES = (
    ("person_count", "Odam oqimi va bandlik", "retail", "batch", 300),
    ("queue_length", "Navbat va kutish tahlili", "retail", "batch", 500),
    (
        "store_security",
        "Zona, tungi harakat va kamera nazorati",
        "security",
        "realtime",
        600,
    ),
    # Davomat — Lite'ga KIRMAYDIGAN pullik qo'shimcha (category=attendance
    # bo'yicha tarif fallback'idan chiqarib tashlanadi).  Sotuvga litsenziyali
    # yuz modeli kelgach ochiladi; hozir faqat yopiq pilot.
    ("davomat", "Yuz orqali xodim davomati", "attendance", "batch", 800),
)


def available_feature_codes() -> frozenset:
    """Hozir rostdan ishlaydigan cloud-AI funksiyalari.

    Public katalog faqat do'kon MVP paketlarini biladi. Ular ham real N100
    qabul testi tugamaguncha environment gate orqali sotuvga ochilmaydi.

    Funksiya ishga tushgach `CHAQIMCHI_AVAILABLE_FEATURES=person_count,...`
    qo'yiladi; deploy kutish shart emas.
    """
    raw = os.environ.get("CHAQIMCHI_AVAILABLE_FEATURES", "").strip()
    if not raw:
        return frozenset()
    if os.environ.get("CHAQIMCHI_ENV", "development").strip().lower() == "production":
        if not pilot_acceptance_status()["ok"]:
            return frozenset()
    known = {code for code, *_rest in DEFAULT_FEATURES}
    return frozenset(code.strip() for code in raw.split(",") if code.strip() in known)


DEFAULT_TEMPLATES = {
    "retail": (
        "Retail/do'kon MVP",
        ("person_count", "queue_length", "store_security"),
    ),
}


#: Lead xabari shuncha urinishdan keyin tashlab qo'yiladi (holat
#: `abandoned`).  Eksponensial backoff bilan bu ~6 soatlik urinish —
#: undan keyin chat mavjud emasligi aniq va abadiy retry faqat log
#: shovqini bo'lardi.
LEAD_DELIVERY_MAX_ATTEMPTS = 8


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


#: Obuna tugagach necha kun ichida tizim ishlashda davom etadi (grace).
GRACE_DAYS = 14


def subscription_days(months: int) -> int:
    """Obuna necha kunga uzayadi.

    To'liq yil — 365 kun, qolgan oylar — 30 kundan.  Bungacha hamma oy
    30 kun edi, ya'ni 12 oy = 360 kun: yillik to'lagan mijoz har yili
    besh kunini to'lab, olmasdi.

    Nega kalendar oyi EMAS: `reduce_subscription` (to'lov qaytarilganda)
    `extend_subscription` ning ANIQ teskarisi bo'lishi shart.  Kalendar
    arifmetikasida 31-yanvar + 1 oy = 28-fevral, − 1 oy = 28-yanvar —
    ya'ni pulini qaytargan mijoz uch kunini yo'qotardi.  Kun arifmetikasi
    esa teskarilanadi.

    Shakli `billable_months()` (cloud/payments/store.py) bilan ataylab
    bir xil — ikkalasi ham "to'liq yil alohida hisoblanadi" qoidasiga
    tayanadi va yonma-yon o'qilishi kerak.
    """
    years, rest = divmod(max(1, int(months)), 12)
    return years * 365 + rest * 30

# ── Aloqa holati ─────────────────────────────────────────────────────────
#
# Edge har `heartbeat_interval_sec` (standart 1800s = 30 daqiqa) da bir marta
# xabar beradi. Shu sababli:
#   - 1 soatgacha jim  → normal (bitta heartbeat o'tkazib yuborilgan bo'lishi mumkin)
#   - 1–24 soat        → shubhali: internet uzilgan yoki qayta yuklanmoqda
#   - 24 soatdan ortiq → tizim ishlamayapti, mijozga qo'ng'iroq qilish kerak
#
# Bungacha `last_seen` faqat sayt tafsilotida xom matn bo'lib turardi — ya'ni
# mijozning tizimi o'chib qolganini bilish uchun har bir saytni qo'lda ochib
# ko'rish kerak edi.

ONLINE_MINUTES = 60
OFFLINE_HOURS = 24


def _connection_state(
    last_seen: Optional[str], devices: int, now: Optional[datetime] = None
) -> Dict[str, Any]:
    """Aloqa holati: not_paired | online | stale | offline."""
    now = now or _utc_now().replace(tzinfo=None)

    if not devices:
        return {"connection": "not_paired", "minutes_since_seen": None}
    if not last_seen:
        return {"connection": "offline", "minutes_since_seen": None}

    try:
        seen = datetime.strptime(last_seen, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return {"connection": "offline", "minutes_since_seen": None}

    minutes = max(0, int((now - seen).total_seconds() // 60))
    if minutes <= ONLINE_MINUTES:
        state = "online"
    elif minutes <= OFFLINE_HOURS * 60:
        state = "stale"
    else:
        state = "offline"
    return {"connection": state, "minutes_since_seen": minutes}


def _compute_status(site: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """Obuna holatini hisoblaydi: active / grace / expired / suspended.

    Bir joyda hisoblanadi — heartbeat ham, admin paneli ham shu natijani ko‘radi.
    """
    now = now or _utc_now().replace(tzinfo=None)
    until = datetime.strptime(site["subscription_until"], "%Y-%m-%d %H:%M:%S")
    days_left = (until - now).days

    if site["status"] == "suspended":
        return {
            "status": "suspended",
            "days_left": days_left,
            "message": "Obuna to‘xtatilgan (admin).",
        }
    if now > until + timedelta(days=GRACE_DAYS):
        return {"status": "expired", "days_left": days_left, "message": "Obuna muddati tugagan."}
    if now > until:
        return {
            "status": "grace",
            "days_left": days_left,
            "message": "Grace davri: to‘lovni yangilang.",
        }
    return {"status": "active", "days_left": days_left, "message": "Faol."}


class CloudStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Lead, pairing tokeni va shifrlangan kamera credentiallari shu yerda.
        # Fayl 0600 bo'lsa ham parent katalog ochiq qolsa SQLite WAL/SHM fayllari
        # boshqa lokal userlarga ko'rinishi mumkin.
        try:
            self.db_path.parent.chmod(0o700)
        except OSError:
            pass
        self._init_db()
        try:
            self.db_path.chmod(0o600)
        except OSError:
            pass

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
        except Exception:
            pass
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sites (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                plan TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                subscription_until TEXT NOT NULL,
                contact_phone TEXT,
                address TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                site_id TEXT NOT NULL,
                label TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                hardware_id TEXT,
                product_name TEXT NOT NULL DEFAULT 'Sotqin',
                hardware_model TEXT,
                hardware_revision TEXT,
                serial_number TEXT,
                config_revision INTEGER NOT NULL DEFAULT 0,
                config_status TEXT NOT NULL DEFAULT 'pending',
                config_error TEXT,
                config_reported_at TEXT,
                last_seen TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );
            CREATE TABLE IF NOT EXISTS pairing_codes (
                code TEXT PRIMARY KEY,
                site_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );
            CREATE TABLE IF NOT EXISTS site_cameras (
                site_id TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                label TEXT NOT NULL,
                rtsp_ciphertext TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                probe_status TEXT NOT NULL DEFAULT 'pending',
                probe_error TEXT,
                codec TEXT,
                width INTEGER,
                height INTEGER,
                fps REAL,
                last_probed_at TEXT,
                -- O'rnatuvchi "rasmni ko'rsat" desa shu bayroq qo'yiladi va
                -- qurilma keyingi heartbeat'da bitta kadr yuboradi.  Config
                -- revizyasi orqali so'rash mumkin emas edi: uning o'zgarishi
                -- retail xizmatini qayta ishga tushiradi.
                preview_requested INTEGER NOT NULL DEFAULT 0,
                preview_key TEXT,
                preview_at TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (site_id, camera_id),
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );
            -- Telegram ogohlantirishi qaysi holat uchun yuborilganini eslaydi:
            -- shusiz har tekshiruvda o'sha xabar qayta-qayta ketardi.
            -- `kind`: connection | cameras — har bir turi mustaqil kuzatiladi.
            CREATE TABLE IF NOT EXISTS alert_state (
                site_id TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'connection',
                connection TEXT NOT NULL,
                notified_at TEXT NOT NULL,
                PRIMARY KEY (site_id, kind),
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );
            -- Platforma darajasidagi kalitlar.  Hozircha bittasi bor:
            -- `updates_paused` — barcha do'konlarga yangilanish tarqatishni
            -- bir tugma bilan to'xtatish.
            CREATE TABLE IF NOT EXISTS platform_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                company TEXT,
                city TEXT,
                cameras INTEGER NOT NULL DEFAULT 1,
                message TEXT,
                status TEXT NOT NULL DEFAULT 'new',
                admin_note TEXT,
                source_hash TEXT NOT NULL,
                site_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (site_id) REFERENCES sites(id)
            );
            CREATE INDEX IF NOT EXISTS idx_leads_status_created
                ON leads(status, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_leads_source_created
                ON leads(source_hash, created_at DESC);
            -- Leadlar tushadigan ichki Telegram guruhlari. Bu mijozlar
            -- guruhlari emas; faqat sotuv/operatorlar uchun mo'ljallangan.
            CREATE TABLE IF NOT EXISTS telegram_lead_destinations (
                chat_id TEXT PRIMARY KEY,
                chat_type TEXT NOT NULL,
                title TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS lead_notification_deliveries (
                lead_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                -- `abandoned` — yetarlicha urinishdan keyin yopilgan.
                -- U `CHECK` ro'yxatida bo'lishi SHART: bo'lmasa yakuniy
                -- `UPDATE` yiqiladi, qator navbat boshida qolib ketadi va
                -- keyingi har bir aylanish o'sha yerda to'xtaydi.
                state TEXT NOT NULL DEFAULT 'pending'
                    CHECK(state IN ('pending', 'sent', 'failed', 'abandoned')),
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                next_attempt_at TEXT,
                sent_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (lead_id, chat_id),
                FOREIGN KEY (lead_id) REFERENCES leads(id)
            );
            CREATE INDEX IF NOT EXISTS idx_lead_delivery_retry
                ON lead_notification_deliveries(state, next_attempt_at, updated_at);
            CREATE TABLE IF NOT EXISTS feature_definitions (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                queue_kind TEXT NOT NULL CHECK(queue_kind IN ('realtime', 'batch')),
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS price_books (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('draft', 'published', 'retired')),
                base_fee_usd_cents INTEGER NOT NULL,
                usd_rate_uzs INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                published_at TEXT
            );
            CREATE TABLE IF NOT EXISTS feature_prices (
                price_book_id TEXT NOT NULL,
                feature_code TEXT NOT NULL,
                monthly_usd_cents INTEGER NOT NULL,
                cost_usd_cents INTEGER NOT NULL,
                PRIMARY KEY(price_book_id, feature_code),
                FOREIGN KEY(price_book_id) REFERENCES price_books(id),
                FOREIGN KEY(feature_code) REFERENCES feature_definitions(code)
            );
            CREATE TABLE IF NOT EXISTS business_templates (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                feature_codes_json TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS site_feature_assignments (
                id TEXT PRIMARY KEY,
                site_id TEXT NOT NULL,
                feature_code TEXT NOT NULL,
                camera_count INTEGER NOT NULL CHECK(camera_count BETWEEN 1 AND 8),
                price_book_id TEXT NOT NULL,
                monthly_usd_cents INTEGER NOT NULL,
                cost_usd_cents INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('draft', 'active', 'disabled')),
                effective_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(site_id, feature_code),
                FOREIGN KEY(site_id) REFERENCES sites(id),
                FOREIGN KEY(feature_code) REFERENCES feature_definitions(code)
            );
            CREATE INDEX IF NOT EXISTS idx_site_feature_assignments_site
                ON site_feature_assignments(site_id, status);
            CREATE TABLE IF NOT EXISTS site_feature_drafts (
                id TEXT PRIMARY KEY,
                site_id TEXT NOT NULL,
                feature_code TEXT NOT NULL,
                camera_count INTEGER NOT NULL CHECK(camera_count BETWEEN 1 AND 8),
                price_book_id TEXT NOT NULL,
                monthly_usd_cents INTEGER NOT NULL,
                cost_usd_cents INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(site_id, feature_code),
                FOREIGN KEY(site_id) REFERENCES sites(id),
                FOREIGN KEY(feature_code) REFERENCES feature_definitions(code)
            );
            CREATE TABLE IF NOT EXISTS portal_accounts (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'installer', 'customer')),
                status TEXT NOT NULL CHECK(status IN ('pending', 'active', 'disabled')),
                full_name TEXT NOT NULL,
                phone TEXT,
                company TEXT,
                site_id TEXT,
                auth_version INTEGER NOT NULL DEFAULT 1,
                last_login_at TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(site_id) REFERENCES sites(id),
                FOREIGN KEY(created_by) REFERENCES portal_accounts(id)
            );
            CREATE INDEX IF NOT EXISTS idx_portal_accounts_role_status
                ON portal_accounts(role, status, created_at DESC);
            CREATE TABLE IF NOT EXISTS installer_assignments (
                installer_id TEXT NOT NULL,
                site_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'assigned'
                    CHECK(status IN ('assigned', 'in_progress', 'ready', 'completed', 'cancelled')),
                notes TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(installer_id, site_id),
                FOREIGN KEY(installer_id) REFERENCES portal_accounts(id),
                FOREIGN KEY(site_id) REFERENCES sites(id),
                FOREIGN KEY(created_by) REFERENCES portal_accounts(id)
            );
            CREATE TABLE IF NOT EXISTS portal_audit_log (
                id TEXT PRIMARY KEY,
                actor_id TEXT,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT,
                detail_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(actor_id) REFERENCES portal_accounts(id)
            );
            CREATE INDEX IF NOT EXISTS idx_portal_audit_created
                ON portal_audit_log(created_at DESC);
            """
        )
        self._migrate(conn)
        self._seed_feature_catalog(conn)
        conn.commit()
        conn.close()

    @staticmethod
    def _camera_cipher() -> Fernet:
        """RTSP credentiallarini faqat shifrlangan holda DBga yozadi.

        Development testlarda deterministik kalit qulay; productionda esa alohida
        32-byte Fernet kaliti environment orqali majburiy beriladi.
        """
        key = os.environ.get("CHAQIMCHI_CAMERA_SECRET_KEY", "").strip()
        if not key:
            if os.environ.get("CHAQIMCHI_ENV", "development") == "production":
                raise RuntimeError("CHAQIMCHI_CAMERA_SECRET_KEY sozlanmagan")
            key = base64.urlsafe_b64encode(
                hashlib.sha256(b"chaqimchi-development-camera-key").digest()
            ).decode("ascii")
        try:
            return Fernet(key.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise RuntimeError("CHAQIMCHI_CAMERA_SECRET_KEY Fernet kaliti noto'g'ri") from exc

    @staticmethod
    def _camera_id_is_valid(camera_id: str) -> bool:
        return camera_id in {f"camera-{number:02d}" for number in range(1, GUARANTEED_CAMERAS + 1)}

    def list_cameras(self, site_id: str, *, include_source: bool = False) -> List[Dict[str, Any]]:
        if not self.get_site(site_id):
            raise ValueError("Sayt topilmadi")
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM site_cameras WHERE site_id=? ORDER BY camera_id", (site_id,)
        ).fetchall()
        conn.close()
        cipher = self._camera_cipher() if include_source else None
        cameras: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["enabled"] = bool(item["enabled"])
            item["preview_requested"] = bool(item.get("preview_requested"))
            item["has_preview"] = bool(item.get("preview_key"))
            item.pop("rtsp_ciphertext", None)
            if cipher is not None:
                try:
                    encrypted = row["rtsp_ciphertext"].encode("ascii")
                    item["source"] = cipher.decrypt(encrypted).decode("utf-8")
                except (InvalidToken, UnicodeDecodeError) as exc:
                    raise RuntimeError(f"{item['camera_id']} RTSP kaliti o'qilmadi") from exc
            cameras.append(item)
        return cameras

    def upsert_camera(
        self, site_id: str, camera_id: str, *, label: str, rtsp_url: str, enabled: bool = True
    ) -> Dict[str, Any]:
        if not self.get_site(site_id):
            raise ValueError("Sayt topilmadi")
        if not self._camera_id_is_valid(camera_id):
            raise ValueError(
                f"Pilot kamera ID camera-01..camera-{GUARANTEED_CAMERAS:02d} bo'lishi kerak"
            )
        # Tarifdagi kamera SONI.  ID oralig'i emas: 2 kameralik mijoz
        # `camera-01` va `camera-03` ni ulashi mumkin — bu to'g'ri.
        # Chegara nechta kamera borligida.
        #
        # Bu yagona haqiqiy nazorat nuqtasi: qurilmadagi tekshiruv
        # mijozning o'z kompyuterida turadi va tahrirlanishi mumkin,
        # cloud esa bizda.
        existing = self.list_cameras(site_id)
        if camera_id not in {item["camera_id"] for item in existing}:
            limit = get_plan(str(self.get_site(site_id)["plan"])).max_cameras
            if len(existing) >= limit:
                raise ValueError(
                    f"Tarifingizda ko'pi bilan {limit} ta kamera. "
                    "Yana kamera ulash uchun tarifni ko'taring."
                )
        source = rtsp_url.strip()
        if not source.startswith(("rtsp://", "rtsps://")):
            raise ValueError("Kamera manzili rtsp:// yoki rtsps:// bilan boshlanishi kerak")
        clean_label = label.strip()
        if not clean_label:
            raise ValueError("Kamera nomi bo'sh bo'lishi mumkin emas")
        ciphertext = self._camera_cipher().encrypt(source.encode("utf-8")).decode("ascii")
        now = _iso(_utc_now())
        conn = self._connect()
        conn.execute(
            "INSERT INTO site_cameras(site_id,camera_id,label,rtsp_ciphertext,enabled,updated_at) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(site_id,camera_id) DO UPDATE SET "
            "label=excluded.label,rtsp_ciphertext=excluded.rtsp_ciphertext,enabled=excluded.enabled,"
            "probe_status='pending',probe_error=NULL,updated_at=excluded.updated_at",
            (site_id, camera_id, clean_label[:120], ciphertext, int(enabled), now),
        )
        conn.commit()
        conn.close()
        return next(item for item in self.list_cameras(site_id) if item["camera_id"] == camera_id)

    def delete_camera(self, site_id: str, camera_id: str) -> bool:
        conn = self._connect()
        cursor = conn.execute(
            "DELETE FROM site_cameras WHERE site_id=? AND camera_id=?", (site_id, camera_id)
        )
        conn.commit()
        conn.close()
        return bool(cursor.rowcount)

    def request_camera_preview(self, site_id: str, camera_id: str) -> Dict[str, Any]:
        """O'rnatuvchi rasm so'radi — qurilma keyingi heartbeat'da yuboradi."""
        conn = self._connect()
        cursor = conn.execute(
            "UPDATE site_cameras SET preview_requested=1,updated_at=? "
            "WHERE site_id=? AND camera_id=?",
            (_iso(_utc_now()), site_id, camera_id),
        )
        conn.commit()
        conn.close()
        if not cursor.rowcount:
            raise ValueError("Kamera topilmadi")
        return next(item for item in self.list_cameras(site_id) if item["camera_id"] == camera_id)

    def pending_preview_cameras(self, site_id: str) -> List[str]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT camera_id FROM site_cameras "
            "WHERE site_id=? AND preview_requested=1 AND enabled=1 ORDER BY camera_id",
            (site_id,),
        ).fetchall()
        conn.close()
        return [str(row[0]) for row in rows]

    def request_live(self, site_id: str, camera_id: str, *, ttl_sec: int = 90) -> str:
        """Jonli ko'rishni yoqadi/uzaytiradi; muddat (ISO) qaytaradi.

        Bir martalik preview'dan farqi — muddat: panel ochiq turganda
        mijoz tomoni har 60 soniyada qayta chaqiradi va oqim uzilmaydi;
        panel yopilsa muddat o'tib qurilma o'zi to'xtaydi.
        """
        until = _iso(_utc_now() + timedelta(seconds=max(10, ttl_sec)))
        conn = self._connect()
        cursor = conn.execute(
            "UPDATE site_cameras SET live_until=?,updated_at=? "
            "WHERE site_id=? AND camera_id=? AND enabled=1",
            (until, _iso(_utc_now()), site_id, camera_id),
        )
        conn.commit()
        conn.close()
        if not cursor.rowcount:
            raise ValueError("Kamera topilmadi")
        return until

    def live_cameras(self, site_id: str) -> List[Dict[str, Any]]:
        """Hozir jonli rejimda kutilayotgan kameralar (muddat bilan)."""
        now = _iso(_utc_now())
        conn = self._connect()
        rows = conn.execute(
            "SELECT camera_id,live_until FROM site_cameras "
            "WHERE site_id=? AND enabled=1 AND live_until IS NOT NULL AND live_until>? "
            "ORDER BY camera_id",
            (site_id, now),
        ).fetchall()
        conn.close()
        return [{"camera_id": str(row[0]), "until": str(row[1])} for row in rows]

    def live_active(self, site_id: str, camera_id: str) -> bool:
        conn = self._connect()
        row = conn.execute(
            "SELECT live_until FROM site_cameras WHERE site_id=? AND camera_id=?",
            (site_id, camera_id),
        ).fetchone()
        conn.close()
        return bool(row and row[0] and str(row[0]) > _iso(_utc_now()))

    def set_camera_preview(self, site_id: str, camera_id: str, key: str) -> None:
        """Rasm keldi: so'rov bayrog'i o'chadi, kalit saqlanadi."""
        now = _iso(_utc_now())
        conn = self._connect()
        cursor = conn.execute(
            "UPDATE site_cameras SET preview_requested=0,preview_key=?,preview_at=?,"
            "updated_at=? WHERE site_id=? AND camera_id=?",
            (key, now, now, site_id, camera_id),
        )
        conn.commit()
        conn.close()
        if not cursor.rowcount:
            raise ValueError("Kamera topilmadi")

    def camera_preview_key(self, site_id: str, camera_id: str) -> Optional[str]:
        conn = self._connect()
        row = conn.execute(
            "SELECT preview_key FROM site_cameras WHERE site_id=? AND camera_id=?",
            (site_id, camera_id),
        ).fetchone()
        conn.close()
        return str(row[0]) if row and row[0] else None

    def record_camera_probe(
        self,
        site_id: str,
        camera_id: str,
        *,
        status: str,
        error: Optional[str] = None,
        codec: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[float] = None,
    ) -> None:
        if status not in {"online", "offline", "pending"}:
            raise ValueError("Kamera probe holati noto'g'ri")
        conn = self._connect()
        cursor = conn.execute(
            "UPDATE site_cameras SET probe_status=?,probe_error=?,codec=?,width=?,height=?,fps=?,"
            "last_probed_at=?,updated_at=? WHERE site_id=? AND camera_id=?",
            (
                status,
                (error or "")[:500] or None,
                codec,
                width,
                height,
                fps,
                _iso(_utc_now()),
                _iso(_utc_now()),
                site_id,
                camera_id,
            ),
        )
        conn.commit()
        conn.close()
        if not cursor.rowcount:
            raise ValueError("Kamera topilmadi")

    def _seed_feature_catalog(self, conn: sqlite3.Connection) -> None:
        """Bo'sh bazaga sotiladigan katalogning birinchi nashrini yozadi."""
        now = _iso(_utc_now())
        canonical = {item[0] for item in DEFAULT_FEATURES}
        placeholders = ",".join("?" for _ in canonical)
        if canonical:
            conn.execute(
                f"UPDATE feature_definitions SET active=0 WHERE code NOT IN ({placeholders})",
                tuple(sorted(canonical)),
            )
            # Eski katalog funksiyasi edge config va invoice hisobida faol
            # qolmasin. Tarixiy assignment audit uchun `disabled` bo'lib
            # saqlanadi, hali tasdiqlanmagan draft esa tashlanadi.
            conn.execute(
                f"UPDATE site_feature_assignments SET status='disabled' "
                f"WHERE feature_code NOT IN ({placeholders})",
                tuple(sorted(canonical)),
            )
            conn.execute(
                f"DELETE FROM site_feature_drafts WHERE feature_code NOT IN ({placeholders})",
                tuple(sorted(canonical)),
            )
        for code, name, category, queue_kind, _price in DEFAULT_FEATURES:
            conn.execute(
                "INSERT OR IGNORE INTO feature_definitions(code,name,category,queue_kind,active,created_at) VALUES (?,?,?,?,1,?)",
                (code, name, category, queue_kind, now),
            )
            conn.execute(
                "UPDATE feature_definitions SET name=?,category=?,queue_kind=?,active=1 WHERE code=?",
                (name, category, queue_kind, code),
            )
        conn.execute("UPDATE business_templates SET active=0")
        for code, (name, features) in DEFAULT_TEMPLATES.items():
            conn.execute(
                "INSERT OR IGNORE INTO business_templates(code,name,feature_codes_json,active,created_at) VALUES (?,?,?,?,?)",
                (code, name, json.dumps(features), 1, now),
            )
            conn.execute(
                "UPDATE business_templates SET name=?,feature_codes_json=?,active=1 WHERE code=?",
                (name, json.dumps(features), code),
            )
        published = conn.execute(
            "SELECT id FROM price_books WHERE status='published' ORDER BY published_at DESC LIMIT 1"
        ).fetchone()
        book_id = str(published["id"]) if published else "v1-default"
        if not published:
            conn.execute(
                "INSERT OR IGNORE INTO price_books(id,label,status,base_fee_usd_cents,usd_rate_uzs,created_at,published_at) VALUES (?,?, 'published',?,?,?,?)",
                (
                    book_id,
                    "Do'kon MVP katalogi",
                    DEFAULT_BASE_FEE_USD_CENTS,
                    DEFAULT_USD_RATE_UZS,
                    now,
                    now,
                ),
            )
        for code, _name, _category, _queue, price in DEFAULT_FEATURES:
            conn.execute(
                "INSERT OR IGNORE INTO feature_prices(price_book_id,feature_code,monthly_usd_cents,cost_usd_cents) VALUES (?,?,?,?)",
                (book_id, code, price, (price * 35 + 99) // 100),
            )

    # ── Cloud AI funksiyalar katalogi va shartnoma snapshotlari ─────────

    @staticmethod
    def _feature_assignment(row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["monthly_total_usd_cents"] = item["monthly_usd_cents"] * item["camera_count"]
        item["cost_total_usd_cents"] = item["cost_usd_cents"] * item["camera_count"]
        return item

    def active_price_book(self) -> Dict[str, Any]:
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM price_books WHERE status='published' ORDER BY published_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:  # pragma: no cover - seed invariant
            raise RuntimeError("Faol narx katalogi topilmadi")
        return dict(row)

    def list_feature_catalog(self) -> Dict[str, Any]:
        book = self.active_price_book()
        conn = self._connect()
        rows = conn.execute(
            "SELECT f.code,f.name,f.category,f.queue_kind,f.active,p.monthly_usd_cents,p.cost_usd_cents "
            "FROM feature_definitions f JOIN feature_prices p ON p.feature_code=f.code "
            "WHERE p.price_book_id=? ORDER BY f.category,f.name",
            (book["id"],),
        ).fetchall()
        conn.close()
        return {"price_book": book, "features": [dict(row) for row in rows]}

    def list_business_templates(self) -> List[Dict[str, Any]]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM business_templates WHERE active=1 ORDER BY name"
        ).fetchall()
        conn.close()
        result = []
        for row in rows:
            item = dict(row)
            item["feature_codes"] = json.loads(item.pop("feature_codes_json"))
            result.append(item)
        return result

    def feature_quote(self, selections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Tanlangan funksiya × kamera bo'yicha sotuv va tannarx hisoboti."""
        book = self.active_price_book()
        catalog = {item["code"]: item for item in self.list_feature_catalog()["features"]}
        normalized: List[Dict[str, Any]] = []
        seen = set()
        for selection in selections:
            code = str(selection.get("feature_code", "")).strip()
            count = int(selection.get("camera_count", 0))
            if code in seen:
                raise ValueError(f"Funksiya takrorlangan: {code}")
            if code not in catalog or not catalog[code]["active"]:
                raise ValueError(f"Noma'lum yoki o'chirilgan funksiya: {code}")
            if (
                os.environ.get("CHAQIMCHI_ENV", "development").strip().lower() == "production"
                and code not in available_feature_codes()
            ):
                raise ValueError(f"Funksiya N100 qabul testidan o'tmagan: {code}")
            if not 1 <= count <= GUARANTEED_CAMERAS:
                raise ValueError(
                    f"Har funksiya uchun kamera soni 1–{GUARANTEED_CAMERAS} bo'lishi kerak"
                )
            seen.add(code)
            feature = catalog[code]
            normalized.append(
                {
                    "feature_code": code,
                    "feature_name": feature["name"],
                    "queue_kind": feature["queue_kind"],
                    "camera_count": count,
                    "monthly_usd_cents": int(feature["monthly_usd_cents"]),
                    "cost_usd_cents": int(feature["cost_usd_cents"]),
                    "monthly_total_usd_cents": int(feature["monthly_usd_cents"]) * count,
                    "cost_total_usd_cents": int(feature["cost_usd_cents"]) * count,
                }
            )
        feature_total = sum(item["monthly_total_usd_cents"] for item in normalized)
        cost_total = sum(item["cost_total_usd_cents"] for item in normalized)
        base = int(book["base_fee_usd_cents"])
        total = base + feature_total
        # Platformaning ichki tannarxi hozir default narxning 35% gate'ida.
        total_cost = (base * 35 + 99) // 100 + cost_total
        rate = usd_rate_uzs()
        return {
            "price_book_id": book["id"],
            "base_fee_usd_cents": base,
            "features": normalized,
            "monthly_usd_cents": total,
            "monthly_uzs": (total * rate + 99) // 100,
            "cost_usd_cents": total_cost,
            "gross_margin_percent": round((total - total_cost) * 100 / total) if total else 0,
            "usd_rate_uzs": rate,
        }

    def _assignment_quote(self, assignments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aktiv shartnomaning muzlatilgan price-book snapshotidan hisoblaydi."""
        if not assignments:
            return self.feature_quote([])
        book_id = str(assignments[0]["price_book_id"])
        if any(str(item["price_book_id"]) != book_id for item in assignments):
            raise ValueError("Bitta shartnomada bir nechta narx versiyasi aralashgan")
        conn = self._connect()
        row = conn.execute("SELECT * FROM price_books WHERE id=?", (book_id,)).fetchone()
        conn.close()
        if not row:
            raise ValueError("Shartnoma narx katalogi topilmadi")
        book = dict(row)
        base = int(book["base_fee_usd_cents"])
        feature_total = sum(int(item["monthly_total_usd_cents"]) for item in assignments)
        feature_cost = sum(int(item["cost_total_usd_cents"]) for item in assignments)
        total = base + feature_total
        total_cost = (base * 35 + 99) // 100 + feature_cost
        # Shartnoma **dollar** narxini muzlatadi, kursni emas. Aks holda kurs
        # ko'tarilganda eski mijoz o'z-o'zidan arzonlashib ketardi. Ochilgan
        # invoice summasi esa `invoices.amount_uzs` da baribir qotib qoladi.
        rate = usd_rate_uzs()
        return {
            "price_book_id": book_id,
            "base_fee_usd_cents": base,
            "features": assignments,
            "monthly_usd_cents": total,
            "monthly_uzs": (total * rate + 99) // 100,
            "cost_usd_cents": total_cost,
            "gross_margin_percent": round((total - total_cost) * 100 / total),
            "usd_rate_uzs": rate,
        }

    def site_feature_summary(self, site_id: str) -> Dict[str, Any]:
        if not self.get_site(site_id):
            raise ValueError("Sayt topilmadi")
        conn = self._connect()
        rows = conn.execute(
            "SELECT a.*,f.name AS feature_name,f.queue_kind FROM site_feature_assignments a "
            "JOIN feature_definitions f ON f.code=a.feature_code WHERE a.site_id=? "
            "ORDER BY a.status,a.feature_code",
            (site_id,),
        ).fetchall()
        assignments = [self._feature_assignment(row) for row in rows]
        active = [item for item in assignments if item["status"] == "active"]
        draft_rows = conn.execute(
            "SELECT d.*,f.name AS feature_name,f.queue_kind,'draft' AS status FROM site_feature_drafts d "
            "JOIN feature_definitions f ON f.code=d.feature_code WHERE d.site_id=? ORDER BY d.feature_code",
            (site_id,),
        ).fetchall()
        conn.close()
        drafts = [self._feature_assignment(row) for row in draft_rows]
        quote = self._assignment_quote(active)
        return {"assignments": assignments, "drafts": drafts, "active_quote": quote}

    def replace_feature_draft(
        self, site_id: str, selections: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if not self.get_site(site_id):
            raise ValueError("Sayt topilmadi")
        quote = self.feature_quote(selections)
        now = _iso(_utc_now())
        conn = self._connect()
        conn.execute("DELETE FROM site_feature_drafts WHERE site_id=?", (site_id,))
        for item in quote["features"]:
            conn.execute(
                "INSERT INTO site_feature_drafts(id,site_id,feature_code,camera_count,price_book_id,monthly_usd_cents,cost_usd_cents,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    uuid.uuid4().hex[:12],
                    site_id,
                    item["feature_code"],
                    item["camera_count"],
                    quote["price_book_id"],
                    item["monthly_usd_cents"],
                    item["cost_usd_cents"],
                    now,
                ),
            )
        conn.commit()
        conn.close()
        return self.site_feature_summary(site_id)

    def approve_feature_draft(self, site_id: str) -> Dict[str, Any]:
        if not self.get_site(site_id):
            raise ValueError("Sayt topilmadi")
        now = _iso(_utc_now())
        conn = self._connect()
        drafted = conn.execute(
            "SELECT COUNT(*) AS n FROM site_feature_drafts WHERE site_id=?",
            (site_id,),
        ).fetchone()
        if not drafted or not int(drafted["n"]):
            conn.close()
            raise ValueError("Tasdiqlash uchun draft funksiya yo'q")
        rows = conn.execute(
            "SELECT * FROM site_feature_drafts WHERE site_id=?", (site_id,)
        ).fetchall()
        conn.execute("DELETE FROM site_feature_assignments WHERE site_id=?", (site_id,))
        for row in rows:
            conn.execute(
                "INSERT INTO site_feature_assignments(id,site_id,feature_code,camera_count,price_book_id,monthly_usd_cents,cost_usd_cents,status,effective_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,'active',?,?,?)",
                (
                    uuid.uuid4().hex[:12],
                    site_id,
                    row["feature_code"],
                    row["camera_count"],
                    row["price_book_id"],
                    row["monthly_usd_cents"],
                    row["cost_usd_cents"],
                    now,
                    now,
                    now,
                ),
            )
        conn.execute("DELETE FROM site_feature_drafts WHERE site_id=?", (site_id,))
        conn.commit()
        conn.close()
        return self.site_feature_summary(site_id)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Ishlayotgan bazani yangi ustunlar bilan to‘ldiradi.

        `CREATE TABLE IF NOT EXISTS` eski jadvalni o‘zgartirmaydi, shuning uchun
        allaqachon ishlab turgan cloud yangilanganda ustunlar qo‘lda qo‘shiladi.
        """

        def columns(table: str) -> set:
            return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}

        if "active_cameras" not in columns("devices"):
            conn.execute("ALTER TABLE devices ADD COLUMN active_cameras INTEGER")

        device_columns = columns("devices")
        device_additions = {
            "product_name": "TEXT NOT NULL DEFAULT 'Sotqin'",
            "hardware_model": "TEXT",
            "hardware_revision": "TEXT",
            "serial_number": "TEXT",
            "config_revision": "INTEGER NOT NULL DEFAULT 0",
            "config_status": "TEXT NOT NULL DEFAULT 'pending'",
            "config_error": "TEXT",
            "config_reported_at": "TEXT",
            # Qurilmada ishlab turgan dastur versiyasi.  Heartbeat'da
            # allaqachon kelardi, lekin hech qayerda saqlanmasdi — ya'ni
            # yangilanish qaysi do'konga yetganini bilishning iloji yo'q edi.
            "app_version": "TEXT",
        }
        for name, definition in device_additions.items():
            if name not in device_columns:
                conn.execute(f"ALTER TABLE devices ADD COLUMN {name} {definition}")

        if "cameras_expected" not in columns("sites"):
            conn.execute("ALTER TABLE sites ADD COLUMN cameras_expected INTEGER")

        site_columns = columns("sites")
        site_additions = {
            # Yangilanish siyosati.  `auto` — eng yangi imzolangan reliz
            # o'zi o'rnatiladi.  `hold` — obyekt joriy versiyada qoladi
            # (masalan mijozda muhim tadbir bor, yoki yangi versiya shu
            # do'konda muammo bergan).  `pin` — aynan `update_version`.
            "update_channel": "TEXT NOT NULL DEFAULT 'auto'",
            "update_version": "TEXT",
        }
        for name, definition in site_additions.items():
            if name not in site_columns:
                conn.execute(f"ALTER TABLE sites ADD COLUMN {name} {definition}")

        camera_columns = columns("site_cameras")
        camera_additions = {
            "preview_requested": "INTEGER NOT NULL DEFAULT 0",
            "preview_key": "TEXT",
            "preview_at": "TEXT",
            # Jonli ko'rish: shu vaqtgacha qurilma har 2-3 soniyada kadr
            # yuboradi (panel ochiq ekan muddat uzaytirib turiladi).
            "live_until": "TEXT",
        }
        for name, definition in camera_additions.items():
            if name not in camera_columns:
                conn.execute(f"ALTER TABLE site_cameras ADD COLUMN {name} {definition}")

        # Davomat tariflarida oylik to'lov shu songa bog'liq.
        if "billable_persons" not in columns("sites"):
            conn.execute("ALTER TABLE sites ADD COLUMN billable_persons INTEGER NOT NULL DEFAULT 0")

        # Ishlab turgan bazada `lead_notification_deliveries` eski `CHECK`
        # bilan yaratilgan bo'lishi mumkin — u `abandoned` ni rad etadi.
        # SQLite'da `CHECK` ni `ALTER` bilan o'zgartirib bo'lmaydi, shuning
        # uchun jadval qayta quriladi.
        delivery_sql = str(
            conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' "
                "AND name='lead_notification_deliveries'"
            ).fetchone()[0]
            or ""
        )
        if "abandoned" not in delivery_sql:
            conn.executescript(
                """
                ALTER TABLE lead_notification_deliveries RENAME TO lead_delivery_old;
                CREATE TABLE lead_notification_deliveries (
                    lead_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending'
                        CHECK(state IN ('pending', 'sent', 'failed', 'abandoned')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    next_attempt_at TEXT,
                    sent_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (lead_id, chat_id),
                    FOREIGN KEY (lead_id) REFERENCES leads(id)
                );
                INSERT INTO lead_notification_deliveries
                    SELECT lead_id,chat_id,state,attempts,last_error,next_attempt_at,
                           sent_at,created_at,updated_at FROM lead_delivery_old;
                DROP TABLE lead_delivery_old;
                CREATE INDEX IF NOT EXISTS idx_lead_delivery_retry
                    ON lead_notification_deliveries(state, next_attempt_at, updated_at);
                """
            )

        # `alert_state` bir turdan (connection) ikki turga (kind) o'tdi.
        if "kind" not in columns("alert_state"):
            conn.executescript(
                """
                ALTER TABLE alert_state RENAME TO alert_state_old;
                CREATE TABLE alert_state (
                    site_id TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'connection',
                    connection TEXT NOT NULL,
                    notified_at TEXT NOT NULL,
                    PRIMARY KEY (site_id, kind),
                    FOREIGN KEY (site_id) REFERENCES sites(id)
                );
                INSERT INTO alert_state (site_id, kind, connection, notified_at)
                    SELECT site_id, 'connection', connection, notified_at FROM alert_state_old;
                DROP TABLE alert_state_old;
                """
            )

    # ── Portal loginlari va o'rnatuvchi biriktirish ─────────────────────

    @staticmethod
    def _public_account(row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        item = dict(row)
        item.pop("password_hash", None)
        item["auth_version"] = int(item.get("auth_version") or 1)
        return item

    def create_account(
        self,
        *,
        username: str,
        password: str,
        role: str,
        full_name: str,
        status: str = "active",
        phone: Optional[str] = None,
        company: Optional[str] = None,
        site_id: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        if role not in {"admin", "installer", "customer"}:
            raise ValueError("Akkaunt roli noto'g'ri")
        if status not in {"pending", "active", "disabled"}:
            raise ValueError("Akkaunt holati noto'g'ri")
        clean_name = " ".join(full_name.split())
        if len(clean_name) < 2 or len(clean_name) > 120:
            raise ValueError("Ism 2–120 belgi bo'lishi kerak")
        clean_username = normalize_username(username)
        if role == "customer":
            if not site_id or not self.get_site(site_id):
                raise ValueError("Mijoz akkaunti mavjud obyektga bog'lanishi kerak")
        else:
            site_id = None
        now = _iso(_utc_now())
        account_id = str(uuid.uuid4())
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO portal_accounts "
                    "(id,username,password_hash,role,status,full_name,phone,company,site_id,"
                    "auth_version,created_by,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,1,?,?,?)",
                    (
                        account_id,
                        clean_username,
                        hash_password(password),
                        role,
                        status,
                        clean_name,
                        " ".join(phone.split()) if phone else None,
                        " ".join(company.split()) if company else None,
                        site_id,
                        created_by,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if "username" in str(exc).lower() or "unique" in str(exc).lower():
                raise ValueError("Bu login band") from exc
            raise ValueError("Akkaunt yaratilmadi") from exc
        account = self.account_by_id(account_id)
        if account is None:  # pragma: no cover - database invariant
            raise RuntimeError("Akkaunt yozilmadi")
        return account

    # ── Mijozning kirish ma'lumotlari ───────────────────────────────────
    #
    # Do'kon egasi paneliga login va parol bilan kiradi.  Bu ma'lumot
    # unga TELEFON ORQALI aytiladi — SMS shlyuzi yo'q.  Shuning uchun:
    #
    #   login  — o'z telefon raqami: yodlash shart emas, u allaqachon biladi
    #   parol  — ikkita oddiy so'z + to'rt raqam: telefonda aytib berish
    #            mumkin.  `Xk9$mQ2!` ni telefonda aytib bo'lmaydi.
    #
    # Parol xotirada emas, faqat yaratilgan payt bir marta qaytariladi.
    _PASSWORD_WORDS = (
        "olma", "anor", "uzum", "bodom", "shakar", "asal", "chinor", "lola",
        "qaymoq", "gilos", "yong'oq", "nok", "shaftoli", "behi", "tut", "anjir",
    )

    def generate_customer_password(self) -> str:
        first, second = secrets.choice(self._PASSWORD_WORDS), secrets.choice(self._PASSWORD_WORDS)
        while second == first:
            second = secrets.choice(self._PASSWORD_WORDS)
        # `'` faqat "yong'oq" da uchraydi va telefonda aytishda chalkashadi.
        pair = f"{first}{second}".replace("'", "")
        return f"{pair}{secrets.randbelow(9000) + 1000}"

    def suggest_customer_username(self, phone: str) -> str:
        digits = "".join(char for char in str(phone or "") if char.isdigit())
        base = digits[-12:] if len(digits) >= 6 else ""
        if not base:
            base = f"dokon{secrets.randbelow(900000) + 100000}"
        candidate = base
        for attempt in range(2, 60):
            if not self.account_by_username(candidate):
                return candidate
            candidate = f"{base}-{attempt}"
        raise ValueError("Login tanlanmadi — telefon raqamini tekshiring")

    def create_customer_login(
        self,
        site_id: str,
        *,
        full_name: str,
        phone: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Do'kon uchun kirish ma'lumotlarini yaratadi va parolni QAYTARADI.

        Parol shu yerdan boshqa hech qayerda ochiq saqlanmaydi: chaqiruvchi
        uni mijozga yetkazishi shart, aks holda parolni tiklash kerak
        bo'ladi.
        """
        password = self.generate_customer_password()
        account = self.create_account(
            username=self.suggest_customer_username(phone or ""),
            password=password,
            role="customer",
            status="active",
            full_name=full_name,
            phone=phone,
            site_id=site_id,
            created_by=created_by,
        )
        return {"account": account, "username": account["username"], "password": password}

    def customer_account_for_site(self, site_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM portal_accounts WHERE role='customer' AND site_id=? "
                "ORDER BY created_at LIMIT 1",
                (site_id,),
            ).fetchone()
        return self._public_account(row) if row else None

    def ensure_bootstrap_admin(self, username: str, password: str) -> Dict[str, Any]:
        """Birinchi adminni faqat adminlar hali yo'q bo'lsa yaratadi."""
        existing = self.list_accounts(role="admin")
        if existing:
            return existing[0]
        return self.create_account(
            username=username,
            password=password,
            role="admin",
            status="active",
            full_name="Bosh administrator",
        )

    def account_by_id(
        self, account_id: str, *, include_secret: bool = False
    ) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM portal_accounts WHERE id=?", (account_id,)).fetchone()
        if not row:
            return None
        return dict(row) if include_secret else self._public_account(row)

    def account_by_username(
        self, username: str, *, include_secret: bool = False
    ) -> Optional[Dict[str, Any]]:
        try:
            clean_username = normalize_username(username)
        except ValueError:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM portal_accounts WHERE username=?", (clean_username,)
            ).fetchone()
        if not row:
            return None
        return dict(row) if include_secret else self._public_account(row)

    def authenticate_account(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        account = self.account_by_username(username, include_secret=True)
        if not account:
            # Login mavjudligini timing orqali ham oshkor qilmaslik uchun bir xil
            # og'irlikdagi scrypt hisobini bajaramiz.
            hash_password("invalid0000")
            return None
        if not verify_password(password, str(account["password_hash"])):
            return None
        now = _iso(_utc_now())
        with self._connect() as conn:
            conn.execute(
                "UPDATE portal_accounts SET last_login_at=?,updated_at=? WHERE id=?",
                (now, now, account["id"]),
            )
        return self.account_by_id(str(account["id"]))

    def list_accounts(
        self, *, role: Optional[str] = None, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        values: List[Any] = []
        if role:
            clauses.append("role=?")
            values.append(role)
        if status:
            clauses.append("status=?")
            values.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM portal_accounts" + where + " ORDER BY created_at DESC",
                values,
            ).fetchall()
        return [self._public_account(row) for row in rows]

    def update_account(self, account_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        current = self.account_by_id(account_id)
        if not current:
            raise ValueError("Akkaunt topilmadi")
        allowed = {"full_name", "phone", "company", "site_id", "role", "status"}
        clean = {key: value for key, value in changes.items() if key in allowed}
        role = str(clean.get("role", current["role"]))
        status = str(clean.get("status", current["status"]))
        if role not in {"admin", "installer", "customer"}:
            raise ValueError("Akkaunt roli noto'g'ri")
        if status not in {"pending", "active", "disabled"}:
            raise ValueError("Akkaunt holati noto'g'ri")
        site_id = clean.get("site_id", current.get("site_id"))
        if role == "customer":
            if not site_id or not self.get_site(str(site_id)):
                raise ValueError("Mijoz akkaunti mavjud obyektga bog'lanishi kerak")
        else:
            site_id = None
        clean["site_id"] = site_id
        clean["role"] = role
        clean["status"] = status
        if "full_name" in clean:
            clean["full_name"] = " ".join(str(clean["full_name"]).split())
            if len(clean["full_name"]) < 2:
                raise ValueError("Ism juda qisqa")
        for field in ("phone", "company"):
            if field in clean:
                clean[field] = " ".join(str(clean[field]).split()) or None
        # Rol, holat yoki bog'langan obyekt o'zgarsa eski JWT darhol bekor bo'ladi.
        security_changed = any(
            clean.get(key) != current.get(key) for key in ("role", "status", "site_id")
        )
        assignments = ",".join(f"{key}=?" for key in clean)
        values = list(clean.values())
        values.extend([_iso(_utc_now()), account_id])
        version_sql = ",auth_version=auth_version+1" if security_changed else ""
        with self._connect() as conn:
            conn.execute(
                f"UPDATE portal_accounts SET {assignments},updated_at=?{version_sql} WHERE id=?",
                values,
            )
        updated = self.account_by_id(account_id)
        if updated is None:  # pragma: no cover
            raise RuntimeError("Akkaunt yangilanmadi")
        return updated

    def set_account_password(self, account_id: str, password: str) -> Dict[str, Any]:
        if not self.account_by_id(account_id):
            raise ValueError("Akkaunt topilmadi")
        now = _iso(_utc_now())
        with self._connect() as conn:
            conn.execute(
                "UPDATE portal_accounts SET password_hash=?,auth_version=auth_version+1,"
                "updated_at=? WHERE id=?",
                (hash_password(password), now, account_id),
            )
        account = self.account_by_id(account_id)
        if account is None:  # pragma: no cover
            raise RuntimeError("Akkaunt yangilanmadi")
        return account

    def assign_installer(
        self,
        installer_id: str,
        site_id: str,
        *,
        status: str = "assigned",
        notes: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        account = self.account_by_id(installer_id)
        if not account or account["role"] != "installer":
            raise ValueError("O'rnatuvchi akkaunti topilmadi")
        if account["status"] != "active":
            raise ValueError("O'rnatuvchi akkaunti faol emas")
        if not self.get_site(site_id):
            raise ValueError("Obyekt topilmadi")
        if status not in {"assigned", "in_progress", "ready", "completed", "cancelled"}:
            raise ValueError("Biriktirish holati noto'g'ri")
        now = _iso(_utc_now())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO installer_assignments "
                "(installer_id,site_id,status,notes,created_by,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(installer_id,site_id) DO UPDATE SET "
                "status=excluded.status,notes=excluded.notes,updated_at=excluded.updated_at",
                (installer_id, site_id, status, (notes or "")[:1000] or None, created_by, now, now),
            )
        assignment = self.installer_assignment(installer_id, site_id)
        if assignment is None:  # pragma: no cover
            raise RuntimeError("Biriktirish yozilmadi")
        return assignment

    def installer_assignment(self, installer_id: str, site_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT a.*,s.name AS site_name,s.address,s.contact_phone "
                "FROM installer_assignments a JOIN sites s ON s.id=a.site_id "
                "WHERE a.installer_id=? AND a.site_id=?",
                (installer_id, site_id),
            ).fetchone()
        return dict(row) if row else None

    def list_installer_assignments(
        self, *, installer_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        where = " WHERE a.installer_id=?" if installer_id else ""
        values: tuple[Any, ...] = (installer_id,) if installer_id else ()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT a.*,s.name AS site_name,s.address,s.contact_phone,"
                "p.full_name AS installer_name,p.username AS installer_username "
                "FROM installer_assignments a JOIN sites s ON s.id=a.site_id "
                "JOIN portal_accounts p ON p.id=a.installer_id" + where + " "
                "ORDER BY a.updated_at DESC",
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def installer_has_site(self, installer_id: str, site_id: str) -> bool:
        assignment = self.installer_assignment(installer_id, site_id)
        return bool(assignment and assignment["status"] != "cancelled")

    def audit_portal_action(
        self,
        action: str,
        *,
        actor_id: Optional[str] = None,
        target_type: str,
        target_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO portal_audit_log "
                "(id,actor_id,action,target_type,target_id,detail_json,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    actor_id,
                    action,
                    target_type,
                    target_id,
                    json.dumps(detail or {}, ensure_ascii=False),
                    _iso(_utc_now()),
                ),
            )

    def list_portal_audit(self, *, limit: int = 200) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT l.*,a.username AS actor_username FROM portal_audit_log l "
                "LEFT JOIN portal_accounts a ON a.id=l.actor_id "
                "ORDER BY l.created_at DESC LIMIT ?",
                (max(1, min(limit, 1000)),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["detail"] = json.loads(item.pop("detail_json") or "{}")
            result.append(item)
        return result

    def upsert_telegram_lead_destination(
        self, chat_id: str, *, chat_type: str, title: Optional[str] = None
    ) -> None:
        """Bot qo'shilgan ichki sales guruhini lead qabul qiluvchisi qiladi."""
        now = _iso(_utc_now())
        conn = self._connect()
        conn.execute(
            "INSERT INTO telegram_lead_destinations(chat_id,chat_type,title,created_at) "
            "VALUES(?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET "
            "chat_type=excluded.chat_type, title=excluded.title",
            (chat_id, chat_type, title, now),
        )
        conn.commit()
        conn.close()

    def remove_telegram_lead_destination(self, chat_id: str) -> None:
        conn = self._connect()
        conn.execute("DELETE FROM telegram_lead_destinations WHERE chat_id=?", (chat_id,))
        conn.commit()
        conn.close()

    def telegram_lead_destinations(self) -> List[Dict[str, Any]]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT chat_id,chat_type,title,created_at FROM telegram_lead_destinations "
            "ORDER BY created_at ASC"
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def ensure_lead_notification_deliveries(
        self,
        lead_id: str,
        chat_ids: List[str],
        *,
        reset: bool = False,
    ) -> None:
        """Lead xabarini har bir recipient uchun idempotent navbatga qo'yadi."""
        now = _iso(_utc_now())
        recipients = list(
            dict.fromkeys(str(item).strip() for item in chat_ids if str(item).strip())
        )
        if not recipients:
            return
        conn = self._connect()
        for chat_id in recipients:
            if reset:
                conn.execute(
                    "INSERT INTO lead_notification_deliveries "
                    "(lead_id,chat_id,state,attempts,created_at,updated_at) "
                    "VALUES (?,?,'pending',0,?,?) ON CONFLICT(lead_id,chat_id) DO UPDATE SET "
                    "state='pending',attempts=0,last_error=NULL,next_attempt_at=NULL,"
                    "sent_at=NULL,updated_at=excluded.updated_at",
                    (lead_id, chat_id, now, now),
                )
            else:
                conn.execute(
                    "INSERT INTO lead_notification_deliveries "
                    "(lead_id,chat_id,state,attempts,created_at,updated_at) "
                    "VALUES (?,?,'pending',0,?,?) ON CONFLICT(lead_id,chat_id) DO NOTHING",
                    (lead_id, chat_id, now, now),
                )
        conn.commit()
        conn.close()

    def lead_notification_delivery(self, lead_id: str, chat_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM lead_notification_deliveries WHERE lead_id=? AND chat_id=?",
            (lead_id, str(chat_id)),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def pending_lead_notification_deliveries(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        now = _iso(_utc_now())
        conn = self._connect()
        rows = conn.execute(
            "SELECT d.lead_id,d.chat_id,d.attempts,l.full_name,l.phone,l.company,l.city,"
            "l.cameras,l.message,l.created_at FROM lead_notification_deliveries d "
            "JOIN leads l ON l.id=d.lead_id "
            "WHERE d.state IN ('pending','failed') "
            "AND (d.next_attempt_at IS NULL OR d.next_attempt_at<=?) "
            "ORDER BY d.updated_at ASC LIMIT ?",
            (now, max(1, min(int(limit), 500))),
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def recent_leads_without_notifications(
        self, *, hours: int = 24, limit: int = 50
    ) -> List[Dict[str, Any]]:
        cutoff = _iso(_utc_now() - timedelta(hours=max(1, min(int(hours), 168))))
        conn = self._connect()
        rows = conn.execute(
            "SELECT l.* FROM leads l WHERE l.created_at>=? AND NOT EXISTS ("
            "SELECT 1 FROM lead_notification_deliveries d WHERE d.lead_id=l.id) "
            "ORDER BY l.created_at ASC LIMIT ?",
            (cutoff, max(1, min(int(limit), 200))),
        ).fetchall()
        conn.close()
        result = []
        for row in rows:
            lead = dict(row)
            lead.pop("source_hash", None)
            result.append(lead)
        return result

    def mark_lead_notification_delivery(
        self,
        lead_id: str,
        chat_id: str,
        *,
        sent: bool,
        error: Optional[str] = None,
    ) -> None:
        current = self.lead_notification_delivery(lead_id, chat_id)
        if current is None:
            return
        attempts = int(current["attempts"]) + 1
        now = _utc_now()
        conn = self._connect()
        if sent:
            conn.execute(
                "UPDATE lead_notification_deliveries SET state='sent',attempts=?,"
                "last_error=NULL,next_attempt_at=NULL,sent_at=?,updated_at=? "
                "WHERE lead_id=? AND chat_id=?",
                (attempts, _iso(now), _iso(now), lead_id, str(chat_id)),
            )
        elif attempts >= LEAD_DELIVERY_MAX_ATTEMPTS:
            # Abadiy retry — log shovqini: mavjud bo'lmagan chatga soatiga
            # bir marta urinib, jurnal "chat not found" bilan to'lardi.
            # Yetarlicha urinishdan keyin yetkazish yopiladi.
            conn.execute(
                "UPDATE lead_notification_deliveries SET state='abandoned',attempts=?,"
                "last_error=?,next_attempt_at=NULL,updated_at=? WHERE lead_id=? AND chat_id=?",
                (
                    attempts,
                    (error or "Telegram yuborilmadi")[:500],
                    _iso(now),
                    lead_id,
                    str(chat_id),
                ),
            )
        else:
            delay_seconds = min(3600, 60 * (2 ** min(attempts - 1, 6)))
            conn.execute(
                "UPDATE lead_notification_deliveries SET state='failed',attempts=?,"
                "last_error=?,next_attempt_at=?,updated_at=? WHERE lead_id=? AND chat_id=?",
                (
                    attempts,
                    (error or "Telegram yuborilmadi")[:500],
                    _iso(now + timedelta(seconds=delay_seconds)),
                    _iso(now),
                    lead_id,
                    str(chat_id),
                ),
            )
        conn.commit()
        conn.close()

    def create_site(
        self,
        name: str,
        plan: PlanTier,
        *,
        subscription_months: int = 1,
        contact_phone: Optional[str] = None,
        address: Optional[str] = None,
        billable_persons: int = 0,
    ) -> Dict[str, Any]:
        limits = get_plan(plan)
        site_id = str(uuid.uuid4())[:12]
        until = _utc_now() + timedelta(days=subscription_days(subscription_months))
        now = _iso(_utc_now())
        persons = max(0, int(billable_persons))

        conn = self._connect()
        conn.execute(
            """
            INSERT INTO sites (id, name, plan, status, subscription_until,
                               contact_phone, address, created_at, billable_persons)
            VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?)
            """,
            (site_id, name, plan, _iso(until), contact_phone, address, now, persons),
        )

        code, expires = self._insert_pairing_code(conn, site_id)
        conn.commit()
        conn.close()

        return {
            "site_id": site_id,
            "name": name,
            "plan": plan,
            "subscription_until": _iso(until),
            "pairing_code": code,
            "pairing_expires_at": expires,
            "billable_persons": persons,
            "limits": {
                "max_cameras": limits.max_cameras,
                "max_persons": limits.effective_max_persons(persons),
                "monthly_price_uzs": limits.monthly_price(persons),
                "monthly_price_usd": limits.monthly_price_usd,
                "install_price_uzs": limits.install_price_uzs,
                "per_person_uzs": limits.price_per_person_uzs,
            },
        }

    # ── Rasmiy sayt arizalari ───────────────────────────────────────────

    def create_lead(
        self,
        *,
        full_name: str,
        phone: str,
        company: Optional[str],
        city: Optional[str],
        cameras: int,
        message: Optional[str],
        source_hash: str,
    ) -> Dict[str, Any]:
        """Pilot arizani saqlaydi; 24 soatdagi takroriy telefonni birlashtiradi."""
        now = _utc_now()
        conn = self._connect()
        duplicate = conn.execute(
            "SELECT * FROM leads WHERE phone = ? AND created_at >= ? "
            "AND status NOT IN ('converted', 'closed') ORDER BY created_at DESC LIMIT 1",
            (phone, _iso(now - timedelta(hours=24))),
        ).fetchone()
        if duplicate:
            conn.close()
            return {
                "id": duplicate["id"],
                "status": duplicate["status"],
                "duplicate": True,
            }

        hourly = conn.execute(
            "SELECT COUNT(*) AS n FROM leads WHERE source_hash = ? AND created_at >= ?",
            (source_hash, _iso(now - timedelta(hours=1))),
        ).fetchone()
        if int(hourly["n"]) >= 5:
            conn.close()
            raise ValueError("Juda ko'p ariza yuborildi. Bir soatdan keyin qayta urinib ko'ring")

        lead_id = uuid.uuid4().hex[:12]
        now_text = _iso(now)
        conn.execute(
            """
            INSERT INTO leads (
                id, full_name, phone, company, city, cameras, message,
                status, source_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?)
            """,
            (
                lead_id,
                full_name,
                phone,
                company,
                city,
                int(cameras),
                message,
                source_hash,
                now_text,
                now_text,
            ),
        )
        conn.commit()
        conn.close()
        return {"id": lead_id, "status": "new", "duplicate": False}

    def get_lead(self, lead_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        conn.close()
        if not row:
            return None
        lead = dict(row)
        lead.pop("source_hash", None)
        return lead

    def list_leads(self, status: Optional[str] = None, *, limit: int = 200) -> List[Dict[str, Any]]:
        conn = self._connect()
        capped = max(1, min(int(limit), 500))
        if status:
            rows = conn.execute(
                "SELECT * FROM leads WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, capped),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM leads ORDER BY created_at DESC LIMIT ?", (capped,)
            ).fetchall()
        conn.close()
        result: List[Dict[str, Any]] = []
        for row in rows:
            lead = dict(row)
            lead.pop("source_hash", None)
            result.append(lead)
        return result

    def update_lead(
        self,
        lead_id: str,
        *,
        status: str,
        admin_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        allowed = {"new", "contacted", "qualified", "converted", "closed"}
        if status not in allowed:
            raise ValueError("Ariza holati noto'g'ri")
        if not self.get_lead(lead_id):
            raise ValueError("Ariza topilmadi")
        conn = self._connect()
        conn.execute(
            "UPDATE leads SET status = ?, admin_note = ?, updated_at = ? WHERE id = ?",
            (status, admin_note, _iso(_utc_now()), lead_id),
        )
        conn.commit()
        conn.close()
        return self.get_lead(lead_id)  # type: ignore[return-value]

    def link_lead_site(self, lead_id: str, site_id: str) -> Dict[str, Any]:
        lead = self.get_lead(lead_id)
        if not lead:
            raise ValueError("Ariza topilmadi")
        if lead.get("site_id"):
            raise ValueError("Bu ariza allaqachon mijozga aylantirilgan")
        if not self.get_site(site_id):
            raise ValueError("Sayt topilmadi")
        conn = self._connect()
        conn.execute(
            "UPDATE leads SET status = 'converted', site_id = ?, updated_at = ? WHERE id = ?",
            (site_id, _iso(_utc_now()), lead_id),
        )
        conn.commit()
        conn.close()
        return self.get_lead(lead_id)  # type: ignore[return-value]

    def lead_stats(self) -> Dict[str, int]:
        conn = self._connect()
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM leads GROUP BY status").fetchall()
        conn.close()
        by_status = {str(row["status"]): int(row["n"]) for row in rows}
        return {
            "total_leads": sum(by_status.values()),
            "new_leads": by_status.get("new", 0),
            "qualified_leads": by_status.get("qualified", 0),
            "converted_leads": by_status.get("converted", 0),
        }

    def set_billable_persons(self, site_id: str, persons: int) -> Dict[str, Any]:
        """Shartnomadagi xodim sonini o‘zgartirish (davomat tariflari uchun)."""
        if persons < 0:
            raise ValueError("Xodim soni manfiy bo‘lishi mumkin emas")
        if not self.get_site(site_id):
            raise ValueError("Sayt topilmadi")

        conn = self._connect()
        conn.execute("UPDATE sites SET billable_persons = ? WHERE id = ?", (int(persons), site_id))
        conn.commit()
        conn.close()
        return self.site_detail(site_id)

    def set_plan(self, site_id: str, plan: str) -> Dict[str, Any]:
        """Obyektning tarifini almashtiradi.

        Bungacha tarifni o'zgartirishning umuman yo'li yo'q edi — qo'lda
        `UPDATE sites SET plan=...` yozilardi.  Uch tarif bilan bu kundalik
        amal bo'lib qoladi: mijoz Boshlang'ichdan Biznesga ko'tariladi yoki
        eski `lite` mijozi yangi narxga o'z roziligi bilan ko'chadi.

        Config revizyasi ataylab surib qo'yiladi: tarif qurilmadagi
        funksiya to'plamini va kamera chegarasini belgilaydi, qurilma esa
        o'zgarishni faqat revizya raqami bo'yicha sezadi (20 soniyalik
        poll).  Usiz mijoz pul to'lab, funksiyani keyingi qayta ishga
        tushishgacha kutib turardi.
        """
        key = str(plan).lower().strip()
        # `get_plan` noma'lum tarifda ValueError ko'taradi — bazaga faqat
        # hisob-kitob qila oladigan qiymat tushsin.
        get_plan(key)
        if not self.get_site(site_id):
            raise ValueError("Sayt topilmadi")

        conn = self._connect()
        conn.execute("UPDATE sites SET plan = ? WHERE id = ?", (key, site_id))
        conn.commit()
        conn.close()
        return self.site_detail(site_id)

    def _insert_pairing_code(
        self, conn: sqlite3.Connection, site_id: str, *, valid_hours: int = 48
    ) -> tuple[str, str]:
        """Yangi pairing kod yozadi va (kod, tugash vaqti) qaytaradi."""
        code = secrets.token_hex(3).upper()[:6]
        expires = _iso(_utc_now() + timedelta(hours=valid_hours))
        conn.execute(
            "INSERT INTO pairing_codes (code, site_id, expires_at, used) VALUES (?, ?, ?, 0)",
            (code, site_id, expires),
        )
        return code, expires

    def count_sites(self) -> int:
        """Nechta do'kon ochilgan.

        `list_sites()` har sayt uchun qo'shimcha so'rov qiladi — bu yerda
        esa faqat son kerak (self-service chegarasini tekshirish uchun),
        shuning uchun bitta arzon so'rov.
        """
        conn = self._connect()
        try:
            return int(conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0])
        finally:
            conn.close()

    def list_sites(self) -> List[Dict[str, Any]]:
        """Barcha saytlar — har biriga hisoblangan holat, tarif narxi va qurilma soni bilan."""
        conn = self._connect()
        rows = conn.execute("SELECT * FROM sites ORDER BY created_at DESC").fetchall()
        device_rows = conn.execute(
            "SELECT site_id, COUNT(*) AS n, MAX(last_seen) AS last_seen,"
            " SUM(COALESCE(active_cameras, 0)) AS cameras"
            " FROM devices GROUP BY site_id"
        ).fetchall()
        device_counts = {r["site_id"]: r["n"] for r in device_rows}
        last_seen_by_site = {r["site_id"]: r["last_seen"] for r in device_rows}
        cameras_by_site = {r["site_id"]: r["cameras"] for r in device_rows}
        conn.close()

        now = _utc_now().replace(tzinfo=None)
        out: List[Dict[str, Any]] = []
        for row in rows:
            site = dict(row)
            computed = _compute_status(site, now)
            limits = get_plan(site["plan"])
            site["license_status"] = computed["status"]
            site["days_left"] = computed["days_left"]
            site["devices"] = device_counts.get(site["id"], 0)
            site["last_seen"] = last_seen_by_site.get(site["id"])
            site.update(_connection_state(site["last_seen"], site["devices"], now))
            site["cameras_active"] = int(cameras_by_site.get(site["id"]) or 0)
            site["cameras_expected"] = int(site.get("cameras_expected") or 0)
            site["cameras_ok"] = (
                site["cameras_active"] >= site["cameras_expected"]
                if site["cameras_expected"]
                else True
            )
            persons = int(site.get("billable_persons") or 0)
            site["billable_persons"] = persons
            site["monthly_price_uzs"] = limits.monthly_price(persons)
            site["monthly_price_usd"] = limits.monthly_price_usd
            site["per_person_uzs"] = limits.price_per_person_uzs
            site["max_cameras"] = limits.max_cameras
            site["max_persons"] = limits.effective_max_persons(persons)
            feature_summary = self.site_feature_summary(site["id"])
            if feature_summary["assignments"]:
                quote = feature_summary["active_quote"]
                site["monthly_price_uzs"] = quote["monthly_uzs"]
                site["monthly_price_usd"] = quote["monthly_usd_cents"] / 100
                site["cloud_features_active"] = len(feature_summary["assignments"])
            out.append(site)
        return out

    def effective_monthly_uzs(self, site_id: str) -> int:
        """Do'konning haqiqiy oylik summasi — bitta manba.

        Narx ikki yo'ldan chiqadi: funksiya shartnomasi bo'lsa undagi
        muzlatilgan kotirovkadan, aks holda tarifdan (davomatda xodim
        soniga bog'liq).  Shu tarmoq `create_invoice` va `list_sites` da
        allaqachon ikki marta yozilgan; mijozga ko'rsatiladigan yillik
        taklif uchinchi nusxa bo'lsa, mijoz panelda bir raqamni ko'rib,
        hisob-fakturada boshqasini olardi.
        """
        site = self.get_site(site_id)
        if not site:
            raise ValueError("Sayt topilmadi")
        summary = self.site_feature_summary(site_id)
        if summary["assignments"]:
            return int(summary["active_quote"]["monthly_uzs"])
        limits = get_plan(site["plan"])
        return int(limits.monthly_price(int(site.get("billable_persons") or 0)))

    def subscription_status(self, site_id: str) -> Dict[str, Any]:
        """Obuna holati — hisob-kitobsiz, faqat holat.

        `site_detail()` butun obyektni (qurilmalar, kodlar, funksiya
        shartnomasi) yig'adi va u har 20 soniyada chaqiriladigan yo'l
        uchun qimmat.
        """
        site = self.get_site(site_id)
        if not site:
            raise ValueError("Sayt topilmadi")
        return _compute_status(site)

    def site_detail(self, site_id: str) -> Dict[str, Any]:
        """Bitta sayt: holat, tarif cheklovlari, qurilmalar va faol pairing kodlar."""
        site = self.get_site(site_id)
        if not site:
            raise ValueError("Sayt topilmadi")

        conn = self._connect()
        now = _utc_now().replace(tzinfo=None)
        devices = [
            {
                "id": r["id"],
                "label": r["label"],
                "hardware_id": r["hardware_id"],
                "product_name": r["product_name"] or "Sotqin",
                "hardware_model": r["hardware_model"],
                "hardware_revision": r["hardware_revision"],
                "serial_number": r["serial_number"],
                "config_revision": int(r["config_revision"] or 0),
                "config_status": r["config_status"] or "pending",
                "config_error": r["config_error"],
                "config_reported_at": r["config_reported_at"],
                "last_seen": r["last_seen"],
                "created_at": r["created_at"],
                "active_cameras": r["active_cameras"],
                "app_version": r["app_version"],
                **_connection_state(r["last_seen"], 1, now),
            }
            for r in conn.execute(
                "SELECT * FROM devices WHERE site_id = ? ORDER BY created_at", (site_id,)
            ).fetchall()
        ]
        codes = [
            {"code": r["code"], "expires_at": r["expires_at"]}
            for r in conn.execute(
                "SELECT * FROM pairing_codes WHERE site_id = ? AND used = 0 AND expires_at > ?"
                " ORDER BY expires_at DESC",
                (site_id, _iso(_utc_now())),
            ).fetchall()
        ]
        conn.close()

        computed = _compute_status(site)
        limits = get_plan(site["plan"])
        site["license_status"] = computed["status"]
        site["days_left"] = computed["days_left"]
        site["message"] = computed["message"]
        persons = int(site.get("billable_persons") or 0)
        site["billable_persons"] = persons
        site["limits"] = {
            "max_cameras": limits.max_cameras,
            "max_persons": limits.effective_max_persons(persons),
            "retention_days": limits.retention_days,
            "telegram_allowed": limits.telegram_allowed,
            "monthly_price_uzs": limits.monthly_price(persons),
            "monthly_price_usd": limits.monthly_price_usd,
            "install_price_uzs": limits.install_price_uzs,
            "per_person_uzs": limits.price_per_person_uzs,
        }
        features = self.site_feature_summary(site_id)
        site["cloud_features"] = features
        if features["assignments"]:
            quote = features["active_quote"]
            site["limits"]["monthly_price_uzs"] = quote["monthly_uzs"]
            site["limits"]["monthly_price_usd"] = quote["monthly_usd_cents"] / 100
        site["devices"] = devices
        site["last_seen"] = max((d["last_seen"] for d in devices if d["last_seen"]), default=None)
        site.update(_connection_state(site["last_seen"], len(devices), now))
        site["cameras_active"] = sum(int(d["active_cameras"] or 0) for d in devices)
        site["cameras_expected"] = int(site.get("cameras_expected") or 0)
        site["cameras_ok"] = (
            site["cameras_active"] >= site["cameras_expected"] if site["cameras_expected"] else True
        )
        site["active_pairing_codes"] = codes
        return site

    def record_device_version(self, device_id: str, app_version: Optional[str]) -> None:
        """Qurilma o'z versiyasini heartbeat'da aytadi.

        Yozib qo'yilmasa masofadan yangilash "ko'r" bo'lardi: reliz
        chiqariladi-yu, u qaysi do'konga yetganini bilib bo'lmasdi.
        """
        version = (app_version or "").strip()[:64]
        if not version or version == "unknown":
            return
        conn = self._connect()
        conn.execute("UPDATE devices SET app_version = ? WHERE id = ?", (version, device_id))
        conn.commit()
        conn.close()

    def set_update_policy(
        self, site_id: str, *, channel: str, version: Optional[str] = None
    ) -> Dict[str, Any]:
        """Obyektning yangilanish siyosatini belgilaydi.

        Nega kerak: bitta buzuq reliz barcha do'konni birdan yiqitmasligi
        kerak.  Yangi versiya avval bitta obyektda sinaladi (`pin`),
        muammo chiqsa qolganlari `hold` ga o'tkaziladi.
        """
        if channel not in {"auto", "hold", "pin"}:
            raise ValueError("update_channel: auto, hold yoki pin bo'lishi kerak")
        if channel == "pin" and not version:
            raise ValueError("pin uchun versiya ko'rsatilishi shart")
        if not self.get_site(site_id):
            raise ValueError("Sayt topilmadi")

        conn = self._connect()
        conn.execute(
            "UPDATE sites SET update_channel = ?, update_version = ? WHERE id = ?",
            (channel, version if channel == "pin" else None, site_id),
        )
        conn.commit()
        conn.close()
        return self.site_detail(site_id)

    def updates_paused(self) -> bool:
        """Barcha do'konlarga yangilanish tarqatish to'xtatilganmi.

        Nega kerak: relizni nashr qilishning o'zi tarqatish edi.
        Kanareyka ham, bosqichma-bosqich tarqatish ham yo'q — fayl
        papkaga tushgan zahoti har bir do'kon uni 15 daqiqa ichida
        oladi.  Buzuq reliz chiqib ketsa yagona himoya har do'konni
        qo'lda `hold` ga o'tkazish edi, ya'ni mijoz soni qancha bo'lsa
        shuncha so'rov — aynan panika paytida.

        Bu bayroq bitta tugma bilan hammasini to'xtatadi va deploy ham,
        qayta ishga tushirish ham talab qilmaydi.
        """
        conn = self._connect()
        row = conn.execute(
            "SELECT value FROM platform_settings WHERE key='updates_paused'"
        ).fetchone()
        conn.close()
        return bool(row and str(row["value"]) == "1")

    def set_updates_paused(self, paused: bool) -> bool:
        conn = self._connect()
        conn.execute(
            "INSERT INTO platform_settings(key,value,updated_at) VALUES('updates_paused',?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            ("1" if paused else "0", _iso(_utc_now())),
        )
        conn.commit()
        conn.close()
        return bool(paused)

    def update_policy(self, site_id: str) -> Dict[str, Any]:
        site = self.get_site(site_id) or {}
        return {
            "channel": site.get("update_channel") or "auto",
            "version": site.get("update_version"),
        }

    def set_cameras_expected(self, site_id: str, expected: int) -> Dict[str, Any]:
        """O‘rnatilgan kamera sonini qo‘lda belgilash.

        Kamera ataylab olib tashlanganda kerak: aks holda tizim uni abadiy
        “yo‘qolgan” deb hisoblab, har kuni ogohlantirib turadi.
        """
        if expected < 0:
            raise ValueError("Kamera soni manfiy bo‘lishi mumkin emas")
        if not self.get_site(site_id):
            raise ValueError("Sayt topilmadi")

        conn = self._connect()
        conn.execute("UPDATE sites SET cameras_expected = ? WHERE id = ?", (int(expected), site_id))
        conn.commit()
        conn.close()
        self.clear_alert_state(site_id, kind="cameras")
        return self.site_detail(site_id)

    def set_status(self, site_id: str, status: str) -> Dict[str, Any]:
        """Obunani to‘xtatish (`suspended`) yoki qayta yoqish (`active`)."""
        if status not in ("active", "suspended"):
            raise ValueError("Holat faqat 'active' yoki 'suspended' bo‘lishi mumkin")
        if not self.get_site(site_id):
            raise ValueError("Sayt topilmadi")

        conn = self._connect()
        conn.execute("UPDATE sites SET status = ? WHERE id = ?", (status, site_id))
        conn.commit()
        conn.close()
        return self.site_detail(site_id)

    def new_pairing_code(self, site_id: str, *, valid_hours: int = 48) -> Dict[str, str]:
        """Qurilmani qayta juftlash uchun yangi kod (eskisi yo‘qolganda / qurilma almashganda)."""
        if not self.get_site(site_id):
            raise ValueError("Sayt topilmadi")

        conn = self._connect()
        code, expires = self._insert_pairing_code(conn, site_id, valid_hours=valid_hours)
        conn.commit()
        conn.close()
        return {"site_id": site_id, "pairing_code": code, "pairing_expires_at": expires}

    def stats(self) -> Dict[str, Any]:
        """Panel uchun umumiy ko‘rsatkichlar: mijozlar, holatlar, oylik daromad."""
        sites = self.list_sites()
        by_status: Dict[str, int] = {}
        by_connection: Dict[str, int] = {}
        monthly_revenue = 0
        for site in sites:
            by_status[site["license_status"]] = by_status.get(site["license_status"], 0) + 1
            if site["license_status"] in ("active", "grace"):
                monthly_revenue += int(site["monthly_price_uzs"])
                # Aloqa faqat to'lovi joyida bo'lgan mijozlar uchun muhim:
                # o'zimiz to'xtatgan sayt jim turishi — normal holat.
                conn_state = site["connection"]
                by_connection[conn_state] = by_connection.get(conn_state, 0) + 1

        return {
            "total_sites": len(sites),
            "by_status": by_status,
            "active": by_status.get("active", 0),
            "expiring_soon": sum(
                1 for s in sites if s["license_status"] == "active" and s["days_left"] <= 7
            ),
            "total_devices": sum(int(s["devices"]) for s in sites),
            "monthly_revenue_uzs": monthly_revenue,
            "by_connection": by_connection,
            # Panelda qizil raqam: to'lovi joyida, lekin tizimi ishlamayotgan
            # mijozlar. Bularga qo'ng'iroq qilish kerak.
            "offline": by_connection.get("offline", 0),
            "not_paired": by_connection.get("not_paired", 0),
        }

    # ── Ogohlantirish holati ──────────────────────────────────────────────

    def alert_states(self, kind: str = "connection") -> Dict[str, str]:
        """Shu tur bo‘yicha oxirgi xabar berilgan holat (sayt → holat)."""
        conn = self._connect()
        rows = conn.execute(
            "SELECT site_id, connection FROM alert_state WHERE kind = ?", (kind,)
        ).fetchall()
        conn.close()
        return {r["site_id"]: r["connection"] for r in rows}

    def set_alert_state(self, site_id: str, connection: str, *, kind: str = "connection") -> None:
        now = _iso(_utc_now())
        conn = self._connect()
        conn.execute(
            "INSERT INTO alert_state (site_id, kind, connection, notified_at)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(site_id, kind) DO UPDATE SET connection = ?, notified_at = ?",
            (site_id, kind, connection, now, connection, now),
        )
        conn.commit()
        conn.close()

    def alert_throttle_allow(self, site_id: str, key: str, *, window_sec: int = 600) -> bool:
        """Chidamli xabar tormozi: oynada bir marta True, qolganida False.

        `cloud/notify.py` dagi xotiradagi tormoz har deploy'da nolga
        qaytib, hamma sayt uchun bir vaqtda xabar bo'roni berardi.  Bu
        yozuv `alert_state` jadvalida turadi va restartdan omon qoladi.
        """
        kind = f"notify:{key}"[:200]
        now = _utc_now()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT notified_at FROM alert_state WHERE site_id = ? AND kind = ?",
                (site_id, kind),
            ).fetchone()
            if row is not None:
                try:
                    # `_iso` naiv "YYYY-MM-DD HH:MM:SS" yozadi — UTC deb o'qiladi.
                    last = datetime.fromisoformat(str(row["notified_at"])).replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    last = None
                if last is not None and (now - last).total_seconds() < window_sec:
                    return False
            conn.execute(
                "INSERT INTO alert_state (site_id, kind, connection, notified_at)"
                " VALUES (?, ?, 'sent', ?)"
                " ON CONFLICT(site_id, kind) DO UPDATE SET notified_at = ?",
                (site_id, kind, _iso(now), _iso(now)),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def clear_alert_state(self, site_id: str, *, kind: Optional[str] = None) -> None:
        """`kind` berilmasa — saytning barcha ogohlantirish holatlari o‘chadi."""
        conn = self._connect()
        if kind is None:
            conn.execute("DELETE FROM alert_state WHERE site_id = ?", (site_id,))
        else:
            conn.execute("DELETE FROM alert_state WHERE site_id = ? AND kind = ?", (site_id, kind))
        conn.commit()
        conn.close()

    def get_site(self, site_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        row = conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def _hash_token(self, token: str) -> str:
        import hashlib

        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def claim_device(
        self,
        pairing_code: str,
        *,
        hardware_id: Optional[str] = None,
        label: str = "sotqin-1",
        product_name: str = "Sotqin",
        hardware_model: Optional[str] = None,
        hardware_revision: Optional[str] = None,
        serial_number: Optional[str] = None,
    ) -> Dict[str, str]:
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM pairing_codes WHERE code = ?", (pairing_code.upper(),)
        ).fetchone()
        if not row or row["used"]:
            conn.close()
            raise ValueError("Pairing kodi noto‘g‘ri yoki ishlatilgan")
        if _iso(_utc_now()) > row["expires_at"]:
            conn.close()
            raise ValueError("Pairing kodi muddati tugagan")

        site_id = row["site_id"]
        device_token = secrets.token_urlsafe(32)
        device_id = str(uuid.uuid4())[:12]
        now = _iso(_utc_now())

        conn.execute(
            """
            INSERT INTO devices (
                id, site_id, label, token_hash, hardware_id, product_name,
                hardware_model, hardware_revision, serial_number, last_seen, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                site_id,
                label,
                self._hash_token(device_token),
                hardware_id,
                product_name or "Sotqin",
                hardware_model,
                hardware_revision,
                serial_number,
                now,
                now,
            ),
        )
        conn.execute("UPDATE pairing_codes SET used = 1 WHERE code = ?", (pairing_code.upper(),))
        conn.commit()
        conn.close()

        return {"site_id": site_id, "device_id": device_id, "device_token": device_token}

    def record_config_ack(
        self,
        site_id: str,
        device_id: str,
        *,
        revision: int,
        status: str,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        if status not in {"applied", "rejected"}:
            raise ValueError("Config holati applied yoki rejected bo'lishi kerak")
        conn = self._connect()
        row = conn.execute(
            "SELECT id FROM devices WHERE id=? AND site_id=?", (device_id, site_id)
        ).fetchone()
        if not row:
            conn.close()
            raise ValueError("Sotqin topilmadi")
        reported = _iso(_utc_now())
        conn.execute(
            "UPDATE devices SET config_revision=?,config_status=?,config_error=?,"
            "config_reported_at=? WHERE id=?",
            (
                max(0, int(revision)),
                status,
                (error or "")[:500] or None,
                reported,
                device_id,
            ),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
        conn.close()
        return dict(updated)

    def verify_device(self, site_id: str, device_token: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM devices WHERE site_id = ? AND token_hash = ?",
            (site_id, self._hash_token(device_token)),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def heartbeat(
        self,
        site_id: str,
        device_token: str,
        *,
        active_cameras: int = 0,
    ) -> Dict[str, Any]:
        device = self.verify_device(site_id, device_token)
        if not device:
            raise ValueError("Qurilma autentifikatsiyasi muvaffaqiyatsiz")

        site = self.get_site(site_id)
        if not site:
            raise ValueError("Sayt topilmadi")

        now = _utc_now().replace(tzinfo=None)
        limits = get_plan(site["plan"])
        computed = _compute_status(site, now)
        status, msg = computed["status"], computed["message"]

        conn = self._connect()
        conn.execute(
            "UPDATE devices SET last_seen = ?, active_cameras = ? WHERE id = ?",
            (_iso(now), int(active_cameras), device["id"]),
        )
        # `cameras_expected` — shu obyektda ishlagani ma'lum bo'lgan eng katta
        # kamera soni. O'rnatuvchi nechta kamera qo'yganini alohida so'ramaymiz:
        # tizim bir marta 3 kamera bilan ishlagan bo'lsa, keyin 2 ta kelishi —
        # nosozlik. Kamera ataylab olib tashlansa admin qiymatni tushiradi.
        expected = site.get("cameras_expected") or 0
        if int(active_cameras) > int(expected):
            conn.execute(
                "UPDATE sites SET cameras_expected = ? WHERE id = ?",
                (int(active_cameras), site_id),
            )
        conn.commit()
        conn.close()

        return {
            "site_id": site_id,
            "plan": site["plan"],
            "status": status,
            "subscription_until": site["subscription_until"],
            "max_cameras": limits.max_cameras,
            "max_persons": limits.effective_max_persons(int(site.get("billable_persons") or 0)),
            "retention_days": limits.retention_days,
            "telegram_allowed": limits.telegram_allowed,
            "active_cameras_reported": active_cameras,
            "message": msg,
        }

    def extend_subscription(self, site_id: str, months: int) -> Dict[str, Any]:
        site = self.get_site(site_id)
        if not site:
            raise ValueError("Sayt topilmadi")
        base = datetime.strptime(site["subscription_until"], "%Y-%m-%d %H:%M:%S")
        now_naive = _utc_now().replace(tzinfo=None)
        if base < now_naive:
            base = now_naive
        new_until = base + timedelta(days=subscription_days(months))
        conn = self._connect()
        conn.execute(
            "UPDATE sites SET subscription_until = ?, status = 'active' WHERE id = ?",
            (_iso(new_until), site_id),
        )
        conn.commit()
        conn.close()
        return {"site_id": site_id, "subscription_until": _iso(new_until)}

    def reduce_subscription(self, site_id: str, months: int) -> Dict[str, Any]:
        """Obunani qisqartirish — to'lov qaytarilganda (refund) `extend`ning teskarisi."""
        site = self.get_site(site_id)
        if not site:
            raise ValueError("Sayt topilmadi")
        base = datetime.strptime(site["subscription_until"], "%Y-%m-%d %H:%M:%S")
        new_until = base - timedelta(days=subscription_days(months))
        conn = self._connect()
        conn.execute(
            "UPDATE sites SET subscription_until = ? WHERE id = ?", (_iso(new_until), site_id)
        )
        conn.commit()
        conn.close()
        return {"site_id": site_id, "subscription_until": _iso(new_until)}
