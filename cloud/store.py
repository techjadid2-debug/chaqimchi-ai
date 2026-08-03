"""Cloud litsenziya bazasi (SQLite)."""

from __future__ import annotations

import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from chaqimchi_ai.licensing.plans import PlanTier, get_plan


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


#: Obuna tugagach nechа kun ichida tizim ishlashda davom etadi (grace).
GRACE_DAYS = 14


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
            """
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
    ) -> Dict[str, Any]:
        limits = get_plan(plan)
        site_id = str(uuid.uuid4())[:12]
        until = _utc_now() + timedelta(days=30 * max(1, subscription_months))
        now = _iso(_utc_now())

        conn = self._connect()
        conn.execute(
            """
            INSERT INTO sites (id, name, plan, status, subscription_until, contact_phone, address, created_at)
            VALUES (?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (site_id, name, plan, _iso(until), contact_phone, address, now),
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
            "limits": {
                "max_cameras": limits.max_cameras,
                "max_persons": limits.max_persons,
                "monthly_price_uzs": limits.monthly_price_uzs,
                "install_price_uzs": limits.install_price_uzs,
            },
        }

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
        device_counts = {
            r["site_id"]: r["n"]
            for r in conn.execute(
                "SELECT site_id, COUNT(*) AS n FROM devices GROUP BY site_id"
            ).fetchall()
        }
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
            site["monthly_price_uzs"] = limits.monthly_price_uzs
            site["max_cameras"] = limits.max_cameras
            site["max_persons"] = limits.max_persons
            out.append(site)
        return out

    def site_detail(self, site_id: str) -> Dict[str, Any]:
        """Bitta sayt: holat, tarif cheklovlari, qurilmalar va faol pairing kodlar."""
        site = self.get_site(site_id)
        if not site:
            raise ValueError("Sayt topilmadi")

        conn = self._connect()
        devices = [
            {
                "id": r["id"],
                "label": r["label"],
                "hardware_id": r["hardware_id"],
                "last_seen": r["last_seen"],
                "created_at": r["created_at"],
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
        site["limits"] = {
            "max_cameras": limits.max_cameras,
            "max_persons": limits.max_persons,
            "retention_days": limits.retention_days,
            "telegram_allowed": limits.telegram_allowed,
            "monthly_price_uzs": limits.monthly_price_uzs,
            "install_price_uzs": limits.install_price_uzs,
        }
        site["devices"] = devices
        site["active_pairing_codes"] = codes
        return site

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
        monthly_revenue = 0
        for site in sites:
            by_status[site["license_status"]] = by_status.get(site["license_status"], 0) + 1
            if site["license_status"] in ("active", "grace"):
                monthly_revenue += int(site["monthly_price_uzs"])

        return {
            "total_sites": len(sites),
            "by_status": by_status,
            "active": by_status.get("active", 0),
            "expiring_soon": sum(
                1 for s in sites if s["license_status"] == "active" and s["days_left"] <= 7
            ),
            "total_devices": sum(int(s["devices"]) for s in sites),
            "monthly_revenue_uzs": monthly_revenue,
        }

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
        label: str = "edge-1",
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
            INSERT INTO devices (id, site_id, label, token_hash, hardware_id, last_seen, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (device_id, site_id, label, self._hash_token(device_token), hardware_id, now, now),
        )
        conn.execute("UPDATE pairing_codes SET used = 1 WHERE code = ?", (pairing_code.upper(),))
        conn.commit()
        conn.close()

        return {"site_id": site_id, "device_id": device_id, "device_token": device_token}

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
            "UPDATE devices SET last_seen = ? WHERE id = ?",
            (_iso(now), device["id"]),
        )
        conn.commit()
        conn.close()

        return {
            "site_id": site_id,
            "plan": site["plan"],
            "status": status,
            "subscription_until": site["subscription_until"],
            "max_cameras": limits.max_cameras,
            "max_persons": limits.max_persons,
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
