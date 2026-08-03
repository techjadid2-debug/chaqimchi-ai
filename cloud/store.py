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
            """
        )
        self._migrate(conn)
        conn.commit()
        conn.close()

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Ishlayotgan bazani yangi ustunlar bilan to‘ldiradi.

        `CREATE TABLE IF NOT EXISTS` eski jadvalni o‘zgartirmaydi, shuning uchun
        allaqachon ishlab turgan cloud yangilanganda ustunlar qo‘lda qo‘shiladi.
        """

        def columns(table: str) -> set:
            return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}

        if "active_cameras" not in columns("devices"):
            conn.execute("ALTER TABLE devices ADD COLUMN active_cameras INTEGER")

        if "cameras_expected" not in columns("sites"):
            conn.execute("ALTER TABLE sites ADD COLUMN cameras_expected INTEGER")

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
        now = _utc_now().replace(tzinfo=None)
        devices = [
            {
                "id": r["id"],
                "label": r["label"],
                "hardware_id": r["hardware_id"],
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
        site["limits"] = {
            "max_cameras": limits.max_cameras,
            "max_persons": limits.max_persons,
            "retention_days": limits.retention_days,
            "telegram_allowed": limits.telegram_allowed,
            "monthly_price_uzs": limits.monthly_price_uzs,
            "install_price_uzs": limits.install_price_uzs,
        }
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
