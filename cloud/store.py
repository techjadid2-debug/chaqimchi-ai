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
from chaqimchi_ai.sotqin_profile import MAX_CAMERAS

# V1 cloud-AI katalogi. Narxlar sentda saqlanadi: invoice va shartnoma
# snapshotlari floating-point xatodan holi bo'lishi kerak.
#
# Baza narxi Lite obunasining o'zi — ikkita mustaqil konstanta bo'lsa ular
# sekin-asta ajralib ketadi va mijoz saytdagidan boshqa summa to'laydi.
DEFAULT_BASE_FEE_USD_CENTS = LITE_MONTHLY_PRICE_USD_CENTS
DEFAULT_FEATURES = (
    ("person_count", "Odam sanash", "analytics", "batch", 300),
    ("line_crossing", "Kirish-chiqish", "security", "batch", 300),
    ("occupancy", "Occupancy", "analytics", "batch", 300),
    ("heatmap", "Heatmap", "analytics", "batch", 300),
    ("crowd_density", "Crowd density", "security", "batch", 400),
    ("staff_presence", "Xodim mavjudligi", "retail", "batch", 400),
    ("opening_closing", "Ochilish-yopilish", "security", "batch", 400),
    ("vehicle_count", "Avtomobil sanash", "parking", "batch", 400),
    ("parking_occupancy", "Parking bandligi", "parking", "batch", 400),
    ("queue_length", "Navbat uzunligi", "retail", "batch", 500),
    ("wait_time", "Kutish vaqti", "retail", "batch", 500),
    ("loitering", "Uzoq turish", "security", "realtime", 500),
    ("restricted_zone", "Taqiqlangan zona", "security", "realtime", 600),
    ("after_hours", "Ish vaqtidan tashqari kirish", "security", "realtime", 600),
    ("wrong_direction", "Noto'g'ri yo'nalish", "security", "realtime", 600),
    ("empty_shelf", "Bo'sh tokcha", "retail", "batch", 700),
    ("attendance", "Yuz orqali davomat", "office", "batch", 700),
    ("ppe", "PPE nazorati", "safety", "realtime", 800),
    ("abandoned_object", "Tashlab ketilgan buyum", "security", "realtime", 800),
    ("removed_object", "Buyum olib ketilishi", "security", "realtime", 800),
    ("watchlist", "Ruxsatli/begona shaxs", "security", "realtime", 800),
    ("fall_detection", "Yiqilish", "safety", "realtime", 1_000),
    ("smoke_fire", "Tutun/yong'in", "safety", "realtime", 1_000),
    ("anpr", "Avtomobil raqami", "parking", "batch", 1_000),
)

def available_feature_codes() -> frozenset:
    """Hozir rostdan ishlaydigan cloud-AI funksiyalari.

    Katalogda 24 ta funksiya bor, lekin inferens worker'i hali yozilmagan.
    Rasmiy sayt shu ro'yxatga qarab "sotib olish" yoki "tez orada" ko'rsatadi —
    tayyor bo'lmagan narsani sotib qo'yish eng qimmat xato bo'lardi.

    Funksiya ishga tushgach `CHAQIMCHI_AVAILABLE_FEATURES=person_count,...`
    qo'yiladi; deploy kutish shart emas.
    """
    raw = os.environ.get("CHAQIMCHI_AVAILABLE_FEATURES", "").strip()
    if not raw:
        return frozenset()
    return frozenset(code.strip() for code in raw.split(",") if code.strip())


DEFAULT_TEMPLATES = {
    "retail": ("Retail/do'kon", ("person_count", "heatmap", "queue_length", "wait_time", "staff_presence", "empty_shelf", "after_hours")),
    "office": ("Ofis", ("attendance", "watchlist", "line_crossing", "occupancy", "restricted_zone")),
    "warehouse": ("Ombor/logistika", ("person_count", "vehicle_count", "ppe", "restricted_zone", "removed_object", "wrong_direction")),
    "manufacturing": ("Ishlab chiqarish", ("ppe", "fall_detection", "smoke_fire", "crowd_density", "restricted_zone")),
    "parking": ("Parking", ("vehicle_count", "anpr", "parking_occupancy", "wrong_direction")),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


#: Obuna tugagach nechа kun ichida tizim ishlashda davom etadi (grace).
GRACE_DAYS = 14

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
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
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
        return camera_id in {f"camera-{number:02d}" for number in range(1, MAX_CAMERAS + 1)}

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
            raise ValueError(f"Kamera ID camera-01..camera-{MAX_CAMERAS:02d} bo'lishi kerak")
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
        for code, name, category, queue_kind, _price in DEFAULT_FEATURES:
            conn.execute(
                "INSERT OR IGNORE INTO feature_definitions(code,name,category,queue_kind,active,created_at) VALUES (?,?,?,?,1,?)",
                (code, name, category, queue_kind, now),
            )
        for code, (name, features) in DEFAULT_TEMPLATES.items():
            conn.execute(
                "INSERT OR IGNORE INTO business_templates(code,name,feature_codes_json,active,created_at) VALUES (?,?,?,?,?)",
                (code, name, json.dumps(features), 1, now),
            )
        exists = conn.execute("SELECT id FROM price_books WHERE status='published' LIMIT 1").fetchone()
        if exists:
            return
        book_id = "v1-default"
        conn.execute(
            "INSERT OR IGNORE INTO price_books(id,label,status,base_fee_usd_cents,usd_rate_uzs,created_at,published_at) VALUES (?,?, 'published',?,?,?,?)",
            (book_id, "V1 boshlang'ich katalog", DEFAULT_BASE_FEE_USD_CENTS, DEFAULT_USD_RATE_UZS, now, now),
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
            if not 1 <= count <= MAX_CAMERAS:
                raise ValueError(f"Har funksiya uchun kamera soni 1–{MAX_CAMERAS} bo'lishi kerak")
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

    def replace_feature_draft(self, site_id: str, selections: List[Dict[str, Any]]) -> Dict[str, Any]:
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
                (uuid.uuid4().hex[:12], site_id, item["feature_code"], item["camera_count"], quote["price_book_id"], item["monthly_usd_cents"], item["cost_usd_cents"], now),
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
        rows = conn.execute("SELECT * FROM site_feature_drafts WHERE site_id=?", (site_id,)).fetchall()
        conn.execute("DELETE FROM site_feature_assignments WHERE site_id=?", (site_id,))
        for row in rows:
            conn.execute(
                "INSERT INTO site_feature_assignments(id,site_id,feature_code,camera_count,price_book_id,monthly_usd_cents,cost_usd_cents,status,effective_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,'active',?,?,?)",
                (uuid.uuid4().hex[:12], site_id, row["feature_code"], row["camera_count"], row["price_book_id"], row["monthly_usd_cents"], row["cost_usd_cents"], now, now, now),
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
        }
        for name, definition in device_additions.items():
            if name not in device_columns:
                conn.execute(f"ALTER TABLE devices ADD COLUMN {name} {definition}")

        if "cameras_expected" not in columns("sites"):
            conn.execute("ALTER TABLE sites ADD COLUMN cameras_expected INTEGER")

        # Davomat tariflarida oylik to'lov shu songa bog'liq.
        if "billable_persons" not in columns("sites"):
            conn.execute(
                "ALTER TABLE sites ADD COLUMN billable_persons INTEGER NOT NULL DEFAULT 0"
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
        until = _utc_now() + timedelta(days=30 * max(1, subscription_months))
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
        conn.execute(
            "UPDATE sites SET billable_persons = ? WHERE id = ?", (int(persons), site_id)
        )
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
            site.update(
                _connection_state(site["last_seen"], site["devices"], now)
            )
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
        site["last_seen"] = max(
            (d["last_seen"] for d in devices if d["last_seen"]), default=None
        )
        site.update(_connection_state(site["last_seen"], len(devices), now))
        site["cameras_active"] = sum(int(d["active_cameras"] or 0) for d in devices)
        site["cameras_expected"] = int(site.get("cameras_expected") or 0)
        site["cameras_ok"] = (
            site["cameras_active"] >= site["cameras_expected"]
            if site["cameras_expected"]
            else True
        )
        site["active_pairing_codes"] = codes
        return site

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
        conn.execute(
            "UPDATE sites SET cameras_expected = ? WHERE id = ?", (int(expected), site_id)
        )
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

    def clear_alert_state(self, site_id: str, *, kind: Optional[str] = None) -> None:
        """`kind` berilmasa — saytning barcha ogohlantirish holatlari o‘chadi."""
        conn = self._connect()
        if kind is None:
            conn.execute("DELETE FROM alert_state WHERE site_id = ?", (site_id,))
        else:
            conn.execute(
                "DELETE FROM alert_state WHERE site_id = ? AND kind = ?", (site_id, kind)
            )
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
            "max_persons": limits.effective_max_persons(
                int(site.get("billable_persons") or 0)
            ),
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
        new_until = base + timedelta(days=30 * max(1, months))
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
        new_until = base - timedelta(days=30 * max(1, months))
        conn = self._connect()
        conn.execute(
            "UPDATE sites SET subscription_until = ? WHERE id = ?", (_iso(new_until), site_id)
        )
        conn.commit()
        conn.close()
        return {"site_id": site_id, "subscription_until": _iso(new_until)}
