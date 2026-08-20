"""Production event/owner store: PostgreSQL, testda SQLite."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
from zoneinfo import ZoneInfo

from chaqimchi_ai.event_models import EdgeEvent

logger = logging.getLogger(__name__)

#: Kunlik hisobot uchun o'qiladigan turlar.  `person_detected` ataylab yo'q:
#: u eng katta hajmli tur va hisobotda ishlatilmaydi — uni ham o'qish
#: gavjum do'konda so'rovni bir necha barobar og'irlashtirardi.
REPORT_EVENT_TYPES = (
    "line_crossed",
    "dwell_exceeded",
    "queue_threshold_exceeded",
    "occupancy_exceeded",
    "camera_tampered",
    "after_hours_presence",
    "zone_entered",
    "loitering",
)


#: Hafta kunlari — `date.weekday()` tartibida (0 = dushanba).
WEEKDAYS = (
    "Dushanba",
    "Seshanba",
    "Chorshanba",
    "Payshanba",
    "Juma",
    "Shanba",
    "Yakshanba",
)

# Bitta `both` kamerada tracker bir kelishni ketma-ket bir necha marta ko'rishi
# mumkin. Shu qisqa klasterni kelish va ketish deb ikki marta hisoblamaymiz.
MIN_BOTH_CAMERA_DEPARTURE_MINUTES = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _age_bucket(age: Any) -> str:
    """Yosh guruhi — do'kon egasi aniq son emas, guruh bilan ishlaydi."""
    try:
        value = int(age)
    except (TypeError, ValueError):
        return "31-45"
    if value < 18:
        return "<18"
    if value <= 30:
        return "18-30"
    if value <= 45:
        return "31-45"
    if value <= 60:
        return "46-60"
    return "60+"


def _change_percent(today: int, yesterday: int) -> Optional[float]:
    """Kechagiga nisbatan o'zgarish.

    Kecha nol bo'lsa foiz ma'nosiz (cheksizlik) — `None` qaytadi va panelda
    ko'rsatilmaydi.
    """
    if yesterday <= 0:
        return None
    return round((today - yesterday) / yesterday * 100, 1)


class EventStore:
    def __init__(self, database_url: str = "", *, sqlite_path: Optional[Path] = None) -> None:
        self.database_url = database_url.strip()
        self.sqlite_path = sqlite_path or Path("data/cloud/events.db")
        self.postgres = self.database_url.startswith(("postgres://", "postgresql://"))
        if not self.postgres:
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        if self.postgres:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:  # pragma: no cover - production dependency
                raise RuntimeError("PostgreSQL uchun psycopg[binary] o'rnatilishi kerak") from exc
            with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
                yield conn
            return
        conn = sqlite3.connect(self.sqlite_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _sql(self, query: str) -> str:
        return query.replace("?", "%s") if self.postgres else query

    def _init_db(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS production_events (
                event_id TEXT PRIMARY KEY,
                site_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                ended_at TEXT,
                track_id INTEGER,
                person_id TEXT,
                person_name TEXT,
                score REAL,
                zone TEXT,
                occupancy INTEGER,
                metadata_json TEXT NOT NULL,
                edge_version TEXT NOT NULL,
                model_version TEXT,
                has_snapshot INTEGER NOT NULL DEFAULT 0,
                snapshot_key TEXT,
                has_clip INTEGER NOT NULL DEFAULT 0,
                clip_key TEXT,
                snapshot_bytes INTEGER NOT NULL DEFAULT 0,
                clip_bytes INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS owner_members (
                id TEXT PRIMARY KEY,
                site_id TEXT NOT NULL,
                telegram_id TEXT NOT NULL,
                role TEXT NOT NULL,
                display_name TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                digest_muted INTEGER NOT NULL DEFAULT 0,
                notify_failures INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(site_id, telegram_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS owner_otps (
                id TEXT PRIMARY KEY,
                telegram_id TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                used INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS owner_login_links (
                id TEXT PRIMARY KEY,
                site_id TEXT NOT NULL,
                telegram_id TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_used_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS telegram_invites (
                id TEXT PRIMARY KEY,
                site_id TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                display_name TEXT,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                used_by TEXT,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS daily_digests (
                site_id TEXT NOT NULL,
                digest_date TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY(site_id, digest_date)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS device_health (
                device_id TEXT PRIMARY KEY,
                site_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                received_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS site_configs (
                site_id TEXT PRIMARY KEY,
                revision INTEGER NOT NULL,
                config_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS employees (
                id TEXT PRIMARY KEY,
                site_id TEXT NOT NULL,
                name TEXT NOT NULL,
                external_id TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                consent_recorded_at TEXT NOT NULL,
                consent_note TEXT,
                enrollment_status TEXT NOT NULL DEFAULT 'pending',
                deactivated_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(site_id, external_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS employee_schedules (
                employee_id TEXT NOT NULL,
                weekday INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                grace_minutes INTEGER NOT NULL DEFAULT 5,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(employee_id, weekday),
                FOREIGN KEY(employee_id) REFERENCES employees(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS attendance_daily (
                site_id TEXT NOT NULL,
                employee_id TEXT NOT NULL,
                work_date TEXT NOT NULL,
                scheduled_start TEXT,
                scheduled_end TEXT,
                first_seen TEXT,
                last_seen TEXT,
                status TEXT NOT NULL,
                late_minutes INTEGER NOT NULL DEFAULT 0,
                early_leave_minutes INTEGER NOT NULL DEFAULT 0,
                checkout_missing INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(site_id, employee_id, work_date),
                FOREIGN KEY(employee_id) REFERENCES employees(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS employee_faces (
                id TEXT PRIMARY KEY,
                site_id TEXT NOT NULL,
                employee_id TEXT NOT NULL,
                photo_key TEXT NOT NULL,
                embedding_b64 TEXT NOT NULL,
                embedding_dim INTEGER NOT NULL DEFAULT 512,
                det_score REAL,
                photo_bytes INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(employee_id) REFERENCES employees(id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_employee_faces_site "
            "ON employee_faces(site_id,employee_id)",
            """
            CREATE TABLE IF NOT EXISTS heatmap_hourly (
                site_id TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                bucket_hour TEXT NOT NULL,
                grid_json TEXT NOT NULL,
                frames INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(site_id, camera_id, bucket_hour)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_prod_events_site_time "
            "ON production_events(site_id,occurred_at)",
            "CREATE INDEX IF NOT EXISTS idx_owner_members_telegram "
            "ON owner_members(telegram_id,active)",
            "CREATE INDEX IF NOT EXISTS idx_owner_login_links_hash "
            "ON owner_login_links(token_hash,revoked)",
            "CREATE INDEX IF NOT EXISTS idx_telegram_invites_hash "
            "ON telegram_invites(token_hash,used_at)",
            "CREATE INDEX IF NOT EXISTS idx_employees_site_active ON employees(site_id,active)",
            "CREATE INDEX IF NOT EXISTS idx_attendance_site_date "
            "ON attendance_daily(site_id,work_date)",
        ]
        with self._connect() as conn:
            for statement in statements:
                conn.execute(statement)
            self._migrate(conn)

    def _existing_columns(self, conn: Any, table: str) -> set:
        """Jadvaldagi ustunlar.  Ikkala dialekt uchun ham ishlaydi."""
        if self.postgres:
            rows = conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name=%s",
                (table,),
            ).fetchall()
            return {str(self._dict(row)["column_name"]) for row in rows}
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(row["name"]) for row in rows}

    def _migrate(self, conn: Any) -> None:
        """Retail ustunlarini mavjud bazaga qo'shadi.

        `ADD COLUMN` ni sinab ko'rib xatoni yutish mumkin emas: PostgreSQL'da
        muvaffaqiyatsiz statement butun tranzaksiyani bekor qiladi.  Shu sabab
        avval ustun bor-yo'qligi tekshiriladi.
        """
        existing = self._existing_columns(conn, "production_events")
        retail_columns = (
            ("direction", "TEXT"),
            ("line_name", "TEXT"),
            ("dwell_sec", "REAL"),
            ("queue_length", "INTEGER"),
            ("has_clip", "INTEGER NOT NULL DEFAULT 0"),
            ("clip_key", "TEXT"),
            # Hajm kvotasi uchun: qaysi hodisa qancha media saqlayotgani.
            ("snapshot_bytes", "INTEGER NOT NULL DEFAULT 0"),
            ("clip_bytes", "INTEGER NOT NULL DEFAULT 0"),
        )
        for name, column_type in retail_columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE production_events ADD COLUMN {name} {column_type}")
        employee_columns = self._existing_columns(conn, "employees")
        if "deactivated_at" not in employee_columns:
            conn.execute("ALTER TABLE employees ADD COLUMN deactivated_at TEXT")
        member_columns = self._existing_columns(conn, "owner_members")
        for name in ("digest_muted", "notify_failures"):
            if name not in member_columns:
                conn.execute(
                    f"ALTER TABLE owner_members ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0"
                )

    @staticmethod
    def _dict(row: Any) -> Dict[str, Any]:
        return dict(row)

    #: Qurilma soati serverdan shuncha oldinda bo'lishi mumkin.  Bir necha
    #: daqiqalik farq normal va uni "tuzatish" hodisani noto'g'ri soatga
    #: surib qo'yardi.
    CLOCK_FUTURE_TOLERANCE = timedelta(minutes=5)

    #: Shundan orqada qolgan soat — deyarli aniq BIOS batareyasi o'lgan
    #: (o'sha davr kompyuterlari 2010-2016 ga tushadi).  Bunday hodisa
    #: **surilmaydi**, faqat jurnalga yoziladi: quyidagi izohga qarang.
    CLOCK_PAST_WARN = timedelta(days=730)

    def _normalise_occurred_at(self, raw: Any, *, now: Optional[datetime] = None) -> str:
        """Qurilma vaqtini ishonchli holga keltiradi.

        `occurred_at` do'kon kompyuterining devor soatidan olinadi.  U
        2014-yilgi kompyuter, CMOS batareyasi o'lishi odatiy hol va NTP
        hech qayerda majburiy emas.  Bu qiymat esa **retention**, kunlik
        hisobot va grafikni boshqaradi:

        * kelajakdagi sana hech qachon o'chmaydi va ro'yxat boshida
          abadiy turib oladi — u **serverning vaqtiga tortiladi**;
        * ochib bo'lmaydigan satr hisobotni butunlay yiqitadi — unda
          hech qanday ma'lumot yo'q, shuning uchun server vaqti qo'yiladi.

        Orqada qolgan soat esa ATAYLAB surilmaydi.  Bir yillik arxiv
        sotilgan mijozda eski hodisa qonuniy holat (`enterprise` tarifi
        365 kun), va butun kunlik yuklamani "hozir" ga surish do'kon
        egasiga **soxta mijozlar** ko'rsatardi: soatlik grafik yuklash
        daqiqasiga yig'ilib qolardi.  Buzuq soat jurnalga yoziladi.

        Internet bir hafta yo'q bo'lgandan keyingi kechikkan yuklash ham
        shu sabab haqiqiy vaqtini saqlaydi.
        """
        moment = (now or _now()).astimezone(timezone.utc)
        try:
            parsed = datetime.fromisoformat(str(raw))
        except (TypeError, ValueError):
            logger.warning("Qurilma vaqti o'qilmadi (%r) — server vaqti qo'yildi", raw)
            return moment.isoformat()
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
        if parsed > moment + self.CLOCK_FUTURE_TOLERANCE:
            logger.warning("Qurilma soati oldinda (%s) — server vaqti qo'yildi", parsed)
            return moment.isoformat()
        if parsed < moment - self.CLOCK_PAST_WARN:
            logger.warning(
                "Qurilma soati juda orqada (%s) — hodisa o'z vaqtida saqlandi, "
                "lekin do'kon kompyuterining soatini to'g'rilash kerak",
                parsed,
            )
        return parsed.isoformat()

    def ingest(self, site_id: str, device_id: str, events: List[EdgeEvent]) -> List[str]:
        accepted: List[str] = []
        query = self._sql(
            """
            INSERT INTO production_events (
                event_id,site_id,device_id,event_type,severity,camera_id,occurred_at,
                ended_at,track_id,person_id,person_name,score,zone,occupancy,
                direction,line_name,dwell_sec,queue_length,
                metadata_json,edge_version,model_version,has_snapshot,has_clip,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(event_id) DO NOTHING
            """
        )
        with self._connect() as conn:
            for event in events:
                employee_name = event.person_name
                if event.event_type == "employee_seen":
                    # Edge yuborgan ismga ishonilmaydi. Cloud faqat shu
                    # obyektga tegishli, roziligi yozilgan faol xodimni
                    # davomatga qo'shadi. Noma'lum ID audit uchun event bo'lib
                    # qoladi, ammo PII va attendance hisobiga kirmaydi.
                    employee = conn.execute(
                        self._sql(
                            "SELECT name FROM employees WHERE site_id=? AND id=? AND active=1"
                        ),
                        (site_id, event.person_id or ""),
                    ).fetchone()
                    employee_name = str(employee["name"]) if employee else None
                conn.execute(
                    query,
                    (
                        event.event_id,
                        site_id,
                        device_id,
                        event.event_type,
                        event.severity,
                        event.camera_id,
                        self._normalise_occurred_at(event.occurred_at),
                        event.ended_at,
                        event.track_id,
                        event.person_id,
                        employee_name,
                        event.score,
                        event.zone,
                        event.occupancy,
                        event.direction,
                        event.line,
                        event.dwell_sec,
                        event.queue_length,
                        json.dumps(event.metadata, ensure_ascii=False, separators=(",", ":")),
                        event.edge_version,
                        event.model_version,
                        int(bool(event.snapshot_path or event.has_snapshot)),
                        int(bool(event.clip_path or event.has_clip)),
                        _now().isoformat(),
                    ),
                )
                # Idempotent qayta yuborilgan event ham accepted hisoblanadi.
                accepted.append(event.event_id)
        return accepted

    def existing_event_ids(self, site_id: str, event_ids: List[str]) -> set[str]:
        """Idempotent retry yangi Telegram alert deb hisoblanmasligi uchun."""
        unique = list(dict.fromkeys(str(item) for item in event_ids if item))
        if not unique:
            return set()
        placeholders = ",".join("?" for _ in unique)
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    f"SELECT event_id FROM production_events WHERE site_id=? "
                    f"AND event_id IN ({placeholders})"
                ),
                (site_id, *unique),
            ).fetchall()
        return {str(row["event_id"]) for row in rows}

    def event(self, site_id: str, event_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                self._sql("SELECT * FROM production_events WHERE site_id=? AND event_id=?"),
                (site_id, event_id),
            ).fetchone()
        return self._decode_event(row) if row else None

    def set_snapshot(self, site_id: str, event_id: str, key: str, *, size_bytes: int = 0) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                self._sql(
                    "UPDATE production_events SET snapshot_key=?,has_snapshot=1,"
                    "snapshot_bytes=? WHERE site_id=? AND event_id=?"
                ),
                (key, int(size_bytes), site_id, event_id),
            )
            return bool(cursor.rowcount)

    def set_clip(self, site_id: str, event_id: str, key: str, *, size_bytes: int = 0) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                self._sql(
                    "UPDATE production_events SET clip_key=?,has_clip=1,"
                    "clip_bytes=? WHERE site_id=? AND event_id=?"
                ),
                (key, int(size_bytes), site_id, event_id),
            )
            return bool(cursor.rowcount)

    def set_face_result(
        self,
        site_id: str,
        event_id: str,
        *,
        matched: bool,
        employee_id: Optional[str] = None,
        score: Optional[float] = None,
        note: Optional[str] = None,
    ) -> bool:
        """`face_captured` kadriga moslash natijasini yozadi.

        Ism `employees`dan olinadi — qurilma yuborgan matnga ishonilmaydi
        (ingest'dagi qoida bilan bir xil).
        """
        person_name = None
        if matched and employee_id:
            employee = self.employee(site_id, employee_id)
            person_name = employee["name"] if employee else None
        with self._connect() as conn:
            row = conn.execute(
                self._sql(
                    "SELECT metadata_json FROM production_events "
                    "WHERE site_id=? AND event_id=? AND event_type='face_captured'"
                ),
                (site_id, event_id),
            ).fetchone()
            if not row:
                return False
            try:
                metadata = json.loads(self._dict(row)["metadata_json"] or "{}")
            except ValueError:
                metadata = {}
            metadata["face"] = {
                "matched": bool(matched),
                **({"note": note} if note else {}),
            }
            cursor = conn.execute(
                self._sql(
                    "UPDATE production_events SET person_id=?,person_name=?,score=?,"
                    "metadata_json=? WHERE site_id=? AND event_id=?"
                ),
                (
                    employee_id if matched else None,
                    person_name,
                    score,
                    json.dumps(metadata, ensure_ascii=False),
                    site_id,
                    event_id,
                ),
            )
            return bool(cursor.rowcount)

    def list_face_events(self, site_id: str, *, limit: int = 50) -> List[Dict[str, Any]]:
        """Galereya uchun so'nggi yuz kadrlari (yangi birinchi)."""
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT event_id,camera_id,occurred_at,person_id,person_name,"
                    "score,snapshot_key,metadata_json FROM production_events "
                    "WHERE site_id=? AND event_type='face_captured' "
                    "ORDER BY occurred_at DESC LIMIT ?"
                ),
                (site_id, max(1, min(int(limit), 200))),
            ).fetchall()
        events = []
        for raw in rows:
            row = self._dict(raw)
            try:
                metadata = json.loads(row.pop("metadata_json") or "{}")
            except ValueError:
                metadata = {}
            row["face"] = metadata.get("face") or {}
            events.append(row)
        return events

    def purge_face_media(self, site_id: str, *, retention_days: int) -> List[str]:
        """Muddati o'tgan yuz kadrlarini butunlay o'chiradi.

        Oddiy hodisalardan farqi: yozuvning O'ZI ham o'chadi — biometrik iz
        (kim qachon ko'ringani rasm bilan) kerak bo'lgandan uzoq yashamasligi
        kerak.  Davomat statistikasi `employee_seen`da — u qoladi.
        """
        cutoff = (_now() - timedelta(days=max(1, retention_days))).isoformat()
        keys: List[str] = []
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT event_id,snapshot_key FROM production_events "
                    "WHERE site_id=? AND event_type='face_captured' AND occurred_at<?"
                ),
                (site_id, cutoff),
            ).fetchall()
            for raw in rows:
                row = self._dict(raw)
                if row["snapshot_key"]:
                    keys.append(str(row["snapshot_key"]))
                conn.execute(
                    self._sql("DELETE FROM production_events WHERE site_id=? AND event_id=?"),
                    (site_id, row["event_id"]),
                )
        return keys

    def purge_inactive_employee_faces(self, site_id: str) -> List[str]:
        """Ro'yxatdan chiqarilgan xodimlarning yuz namunalarini o'chiradi.

        Maxfiylik va'dasi: xodim ketdi — biometrikasi ham ketadi.  Har 6
        soatlik maintenance shu yerni chaqiradi, ya'ni kechikish ko'pi
        bilan yarim kun.
        """
        keys: List[str] = []
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT f.id,f.photo_key FROM employee_faces f "
                    "JOIN employees e ON e.id=f.employee_id "
                    "WHERE f.site_id=? AND e.active=0"
                ),
                (site_id,),
            ).fetchall()
            for raw in rows:
                row = self._dict(raw)
                keys.append(str(row["photo_key"]))
                conn.execute(
                    self._sql("DELETE FROM employee_faces WHERE id=?"),
                    (row["id"],),
                )
        return keys

    def media_usage_bytes(self, site_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                self._sql(
                    "SELECT COALESCE(SUM(COALESCE(snapshot_bytes,0)+COALESCE(clip_bytes,0)),0) "
                    "AS total FROM production_events WHERE site_id=?"
                ),
                (site_id,),
            ).fetchone()
        return int(self._dict(row)["total"] or 0)

    def purge_site_media_over_quota(self, site_id: str, max_bytes: int) -> List[str]:
        """Obyekt media hajmi kvotadan oshsa **eng eski** medialarni bo'shatadi.

        Muddat bo'yicha tozalash (`purge_site`) yetarli emas: kuniga 500
        snapshot + 100 klip ruxsat etilgan, ya'ni bitta shovqinli sayt 30
        kunlik tarifda ham VPS diskini to'ldira oladi.  Hodisa yozuvining
        o'zi qoladi (statistika buzilmaydi) — faqat media o'chadi, xuddi
        edge'dagi `outbox.prune` kabi.
        """
        usage = self.media_usage_bytes(site_id)
        if usage <= max_bytes:
            return []
        keys: List[str] = []
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT event_id,snapshot_key,clip_key,"
                    "COALESCE(snapshot_bytes,0)+COALESCE(clip_bytes,0) AS media_bytes "
                    "FROM production_events WHERE site_id=? AND "
                    "(snapshot_key IS NOT NULL OR clip_key IS NOT NULL) "
                    "ORDER BY occurred_at"
                ),
                (site_id,),
            ).fetchall()
            freed = 0
            for raw in rows:
                if usage - freed <= max_bytes:
                    break
                row = self._dict(raw)
                keys.extend(key for key in (row["snapshot_key"], row["clip_key"]) if key)
                freed += int(row["media_bytes"] or 0)
                conn.execute(
                    self._sql(
                        "UPDATE production_events SET snapshot_key=NULL,has_snapshot=0,"
                        "snapshot_bytes=0,clip_key=NULL,has_clip=0,clip_bytes=0 "
                        "WHERE site_id=? AND event_id=?"
                    ),
                    (site_id, row["event_id"]),
                )
        return keys

    def list_events(
        self,
        site_id: str,
        *,
        limit: int = 100,
        event_type: Optional[str] = None,
        camera_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        where = ["site_id=?"]
        params: List[Any] = [site_id]
        if event_type:
            where.append("event_type=?")
            params.append(event_type)
        if camera_id:
            where.append("camera_id=?")
            params.append(camera_id)
        params.append(max(1, min(int(limit), 500)))
        query = self._sql(
            "SELECT * FROM production_events WHERE "
            + " AND ".join(where)
            + " ORDER BY occurred_at DESC LIMIT ?"
        )
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._decode_event(row) for row in rows]

    def _decode_event(self, row: Any) -> Dict[str, Any]:
        item = self._dict(row)
        try:
            item["metadata"] = json.loads(item.pop("metadata_json", "{}"))
        except json.JSONDecodeError:
            item["metadata"] = {}
        item["has_snapshot"] = bool(item.get("has_snapshot"))
        item["has_clip"] = bool(item.get("has_clip"))
        return item

    def stats(self, site_id: str, *, day: Optional[date] = None) -> Dict[str, Any]:
        timezone_tashkent = ZoneInfo("Asia/Tashkent")
        day = day or datetime.now(timezone_tashkent).date()
        start_local = datetime.combine(day, datetime.min.time(), tzinfo=timezone_tashkent)
        start = start_local.astimezone(timezone.utc).isoformat()
        end = (start_local + timedelta(days=1)).astimezone(timezone.utc).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT event_type,COUNT(*) AS count FROM production_events "
                    "WHERE site_id=? AND occurred_at>=? AND occurred_at<? GROUP BY event_type"
                ),
                (site_id, start, end),
            ).fetchall()
        by_type = {row["event_type"]: int(row["count"]) for row in rows}
        return {"date": day.isoformat(), "total": sum(by_type.values()), "by_type": by_type}

    #: "Ochilish vaqti" uchun hisobga olinadigan harakat turlari — kamera
    #: sog'ligi hodisalari emas (ular odam kelganini bildirmaydi).
    MOVEMENT_TYPES = (
        "line_crossed",
        "person_detected",
        "zone_entered",
        "loitering",
        "queue_threshold_exceeded",
    )

    def first_movement_time(self, site_id: str, *, day: Optional[date] = None) -> Optional[str]:
        """Kunning birinchi harakat hodisasi (Toshkent kuni bo'yicha).

        Kunlik hisobotdagi "Ochilish: 09:05" satri uchun — do'kon
        jadvaldagidan kech ochilsa ega buni hisobotdan ko'radi.
        """
        timezone_tashkent = ZoneInfo("Asia/Tashkent")
        day = day or datetime.now(timezone_tashkent).date()
        start_local = datetime.combine(day, datetime.min.time(), tzinfo=timezone_tashkent)
        start = start_local.astimezone(timezone.utc).isoformat()
        end = (start_local + timedelta(days=1)).astimezone(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in self.MOVEMENT_TYPES)
        with self._connect() as conn:
            row = conn.execute(
                self._sql(
                    "SELECT MIN(occurred_at) AS first FROM production_events "
                    f"WHERE site_id=? AND occurred_at>=? AND occurred_at<? "
                    f"AND event_type IN ({placeholders})"
                ),
                (site_id, start, end, *self.MOVEMENT_TYPES),
            ).fetchone()
        value = self._dict(row).get("first") if row else None
        return str(value) if value else None

    def camera_uptime_percent(self, site_id: str, *, start: date, end: date) -> Optional[float]:
        """Davr bo'yicha kamera ishlash foizi (offline/recovered juftlaridan).

        Haftalik hisobot uchun: "kameralar 98% vaqt ishladi".  Hodisa
        umuman bo'lmasa (uzilish qayd etilmagan) — 100%.  Ma'lumot yo'q
        davr uchun None emas, 100 qaytadi: uzilish hodisasi bor-yo'qligi
        yagona ishonchli signalimiz.
        """
        timezone_tashkent = ZoneInfo("Asia/Tashkent")
        start_local = datetime.combine(start, datetime.min.time(), tzinfo=timezone_tashkent)
        end_local = datetime.combine(
            end, datetime.min.time(), tzinfo=timezone_tashkent
        ) + timedelta(days=1)
        period_start = start_local.astimezone(timezone.utc)
        period_end = end_local.astimezone(timezone.utc)
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT camera_id,event_type,occurred_at FROM production_events "
                    "WHERE site_id=? AND occurred_at>=? AND occurred_at<? "
                    "AND event_type IN ('camera_offline','camera_recovered') "
                    "ORDER BY camera_id,occurred_at"
                ),
                (site_id, period_start.isoformat(), period_end.isoformat()),
            ).fetchall()
        events = [self._dict(row) for row in rows]
        if not events:
            return 100.0
        total_seconds = (period_end - period_start).total_seconds()
        downtime = 0.0
        cameras = {item["camera_id"] for item in events}
        for camera_id in cameras:
            offline_since: Optional[datetime] = None
            for item in (e for e in events if e["camera_id"] == camera_id):
                try:
                    moment = datetime.fromisoformat(str(item["occurred_at"]))
                except ValueError:
                    continue
                if moment.tzinfo is None:
                    moment = moment.replace(tzinfo=timezone.utc)
                if item["event_type"] == "camera_offline" and offline_since is None:
                    offline_since = moment
                elif item["event_type"] == "camera_recovered" and offline_since is not None:
                    downtime += (moment - offline_since).total_seconds()
                    offline_since = None
            if offline_since is not None:
                # Davr oxirigacha tiklanmagan.
                downtime += (period_end - offline_since).total_seconds()
        if not cameras or total_seconds <= 0:
            return 100.0
        # O'rtacha: umumiy downtime kamera-davrlar yig'indisiga nisbatan.
        ratio = downtime / (total_seconds * len(cameras))
        return round(max(0.0, min(1.0, 1 - ratio)) * 100, 1)

    def retail_report(self, site_id: str, *, day: Optional[date] = None) -> Dict[str, Any]:
        """Do'kon egasi uchun kunlik hisobot.

        Xom hodisa sanog'i ("line_crossed: 680") mijozga hech narsa aytmaydi:
        u kirish va chiqishning yig'indisi.  Do'kon egasining savollari
        boshqacha — nechta odam **kirdi**, qaysi soat gavjum, kassada navbat
        qancha bo'ldi, qaysi tokcha oldida uzoq turishadi.

        Hisob Python'da yig'iladi, SQL'da emas: vaqt mintaqasi (Asia/Tashkent)
        bo'yicha soatlarga bo'lish SQLite va PostgreSQL'da har xil yoziladi,
        kunlik hodisa hajmi esa buni talab qilmaydi.  `person_detected`
        umuman o'qilmaydi — u eng katta hajmli tur va hisobotga kirmaydi.
        """
        timezone_tashkent = ZoneInfo("Asia/Tashkent")
        day = day or datetime.now(timezone_tashkent).date()
        rows = self._events_of_day(site_id, day, timezone_tashkent)

        hourly: Dict[int, Dict[str, int]] = {
            hour: {"hour": hour, "entered": 0, "exited": 0} for hour in range(24)
        }
        entered = exited = 0
        queue_lengths: List[Tuple[int, str]] = []
        dwell: Dict[str, List[float]] = {}
        security = {
            "camera_tampered": 0,
            "after_hours_presence": 0,
            "restricted_zone": 0,
            "loitering": 0,
        }
        # Do'kon egasi sotib olgan raqam — «bugun nechta MIJOZ kirdi».  Xodim
        # kuniga o'n martalab eshikdan o'tadi, shuning uchun uning o'tishlari
        # kirdi-chiqdi sonidan ham, soatlik grafikdan ham, demografiyadan ham
        # butunlay chiqariladi.  Xodimni `employee_seen` (kamera, trek)
        # juftligi belgilaydi — uni cloud tomondagi yuz moslash yozadi.
        employee_marks = self._employee_marks_of_day(site_id, day, timezone_tashkent)
        gender_counts = {"ayol": 0, "erkak": 0}
        age_buckets = {"<18": 0, "18-30": 0, "31-45": 0, "46-60": 0, "60+": 0}
        demo_total = 0
        staff_crossings = 0

        for row in rows:
            kind = row["event_type"]
            local = self._to_local(row["occurred_at"], timezone_tashkent)
            if local is None:
                continue  # yaroqsiz vaqt — bitta qator hisobotni yiqitmasin
            if kind == "line_crossed":
                direction = row.get("direction")
                if direction not in ("in", "out"):
                    continue
                if self._matches_employee(row, employee_marks):
                    staff_crossings += 1
                    continue
                if direction == "in":
                    entered += 1
                    hourly[local.hour]["entered"] += 1
                    demo = (row.get("metadata") or {}).get("demografiya") or {}
                    if demo.get("jins") in gender_counts:
                        demo_total += 1
                        gender_counts[str(demo["jins"])] += 1
                        age_buckets[_age_bucket(demo.get("yosh"))] += 1
                else:
                    exited += 1
                    hourly[local.hour]["exited"] += 1
            elif kind == "dwell_exceeded" and row.get("dwell_sec") is not None:
                dwell.setdefault(row.get("zone") or "—", []).append(float(row["dwell_sec"]))
            elif kind == "queue_threshold_exceeded" and row.get("queue_length") is not None:
                queue_lengths.append((int(row["queue_length"]), local.strftime("%H:%M")))
            elif kind in security:
                security[kind] += 1
            elif kind == "zone_entered" and (row.get("metadata") or {}).get("restricted"):
                security["restricted_zone"] += 1

        busiest = max(hourly.values(), key=lambda item: (item["entered"], -item["hour"]))
        longest = max(queue_lengths, default=None, key=lambda item: item[0])
        yesterday = self._entered_count(site_id, day - timedelta(days=1), timezone_tashkent)

        return {
            "date": day.isoformat(),
            "traffic": {
                "entered": entered,
                "exited": exited,
                # Kirish va chiqish har doim ham teng bo'lmaydi (kamera
                # ko'rmay qolishi mumkin), shuning uchun bu **taxminiy**.
                "inside_estimate": max(0, entered - exited),
                "entered_yesterday": yesterday,
                "change_percent": _change_percent(entered, yesterday),
                "busiest_hour": busiest if busiest["entered"] else None,
                "hourly": [hourly[hour] for hour in range(24)],
                #: Yuz tanish xodim deb topgan va sanoqdan chiqarilgan
                #: o'tishlar.  Ko'rsatiladi, chunki "kecha 210 edi, bugun 190"
                #: degan farq xodim jadvalidan ham kelib chiqishi mumkin.
                "xodim_chiqarilgan": staff_crossings,
            },
            "queue": {
                "alerts": len(queue_lengths),
                "longest": longest[0] if longest else 0,
                "longest_at": longest[1] if longest else None,
                "average": (
                    round(sum(item[0] for item in queue_lengths) / len(queue_lengths), 1)
                    if queue_lengths
                    else 0
                ),
            },
            "dwell": sorted(
                (
                    {
                        "zone": zone,
                        "count": len(values),
                        "average_sec": round(sum(values) / len(values), 1),
                        "longest_sec": round(max(values), 1),
                    }
                    for zone, values in dwell.items()
                ),
                key=lambda item: (-item["count"], item["zone"]),
            ),
            "security": security,
            "demografiya": {
                "hisoblangan": demo_total,
                "jins": (
                    {
                        "ayol": round(gender_counts["ayol"] * 100 / demo_total),
                        "erkak": round(gender_counts["erkak"] * 100 / demo_total),
                    }
                    if demo_total
                    else {}
                ),
                "yosh": age_buckets,
            },
        }

    # ── Issiqlik xaritasi ────────────────────────────────────────────────

    #: To'r o'lchami — qurilmadagi chaqimchi_ai/retail/heatmap.py bilan mos.
    HEATMAP_COLS = 48
    HEATMAP_ROWS = 27

    def add_heatmap(
        self, site_id: str, camera_id: str, bucket_hour: str, grid: List[List[int]], frames: int
    ) -> None:
        """Soatlik to'rni JAMLAB yozadi (qurilma bir soat uchun bir necha
        marta yuborishi mumkin — internet uzilib qayta ulanganda)."""
        with self._connect() as conn:
            row = conn.execute(
                self._sql(
                    "SELECT grid_json,frames FROM heatmap_hourly "
                    "WHERE site_id=? AND camera_id=? AND bucket_hour=?"
                ),
                (site_id, camera_id, bucket_hour),
            ).fetchone()
            total_frames = int(frames)
            if row:
                existing = self._dict(row)
                try:
                    old = json.loads(existing["grid_json"])
                    for row_index in range(min(len(old), self.HEATMAP_ROWS)):
                        for col_index in range(min(len(old[row_index]), self.HEATMAP_COLS)):
                            grid[row_index][col_index] += int(old[row_index][col_index])
                except (ValueError, TypeError):
                    pass
                total_frames += int(existing["frames"] or 0)
                conn.execute(
                    self._sql(
                        "UPDATE heatmap_hourly SET grid_json=?,frames=?,updated_at=? "
                        "WHERE site_id=? AND camera_id=? AND bucket_hour=?"
                    ),
                    (
                        json.dumps(grid, separators=(",", ":")),
                        total_frames,
                        _now().isoformat(),
                        site_id,
                        camera_id,
                        bucket_hour,
                    ),
                )
            else:
                conn.execute(
                    self._sql(
                        "INSERT INTO heatmap_hourly "
                        "(site_id,camera_id,bucket_hour,grid_json,frames,updated_at) "
                        "VALUES (?,?,?,?,?,?)"
                    ),
                    (
                        site_id,
                        camera_id,
                        bucket_hour,
                        json.dumps(grid, separators=(",", ":")),
                        total_frames,
                        _now().isoformat(),
                    ),
                )

    def heatmap(
        self,
        site_id: str,
        camera_id: str,
        *,
        day: date,
        hour: Optional[int] = None,
        days: int = 1,
    ) -> Dict[str, Any]:
        """Toshkent kuni (ixtiyoriy soati) bo'yicha jamlangan to'r.

        Bucket'lar UTC'da saqlanadi — lokal soat oralig'i UTC bucket
        satrlariga o'girilib yig'iladi.  `days > 1` — `day` bilan tugaydigan
        bir necha kun jamlanadi (do'kon plani "o'zi chizilishi" uchun:
        haftalik yig'indida odam yurmagan joylar jihoz bo'lib ko'rinadi).
        """
        zone = ZoneInfo("Asia/Tashkent")
        hours = [hour] if hour is not None else list(range(24))
        buckets = []
        for offset in range(max(1, min(int(days), 30))):
            target_day = day - timedelta(days=offset)
            for local_hour in hours:
                local = datetime.combine(target_day, datetime.min.time(), tzinfo=zone) + timedelta(
                    hours=local_hour
                )
                buckets.append(local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H"))
        placeholders = ",".join("?" for _ in buckets)
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT grid_json,frames FROM heatmap_hourly "
                    f"WHERE site_id=? AND camera_id=? AND bucket_hour IN ({placeholders})"
                ),
                (site_id, camera_id, *buckets),
            ).fetchall()
        total = [[0] * self.HEATMAP_COLS for _ in range(self.HEATMAP_ROWS)]
        frames = 0
        for raw in rows:
            row = self._dict(raw)
            try:
                cells = json.loads(row["grid_json"])
            except (ValueError, TypeError):
                continue
            frames += int(row["frames"] or 0)
            for row_index in range(min(len(cells), self.HEATMAP_ROWS)):
                for col_index in range(min(len(cells[row_index]), self.HEATMAP_COLS)):
                    total[row_index][col_index] += int(cells[row_index][col_index])
        return {
            "camera_id": camera_id,
            "date": day.isoformat(),
            "hour": hour,
            "cols": self.HEATMAP_COLS,
            "rows": self.HEATMAP_ROWS,
            "grid": total,
            "frames": frames,
            "points": sum(sum(row) for row in total),
        }

    def purge_heatmaps(self, site_id: str, *, retention_days: int = 90) -> int:
        cutoff = (_now() - timedelta(days=max(1, retention_days))).strftime("%Y-%m-%dT%H")
        with self._connect() as conn:
            cursor = conn.execute(
                self._sql("DELETE FROM heatmap_hourly WHERE site_id=? AND bucket_hour<?"),
                (site_id, cutoff),
            )
            return int(cursor.rowcount or 0)

    #: Xodim treki bilan kirish kesishmasi orasidagi ruxsat etilgan farq.
    #: Trek raqamlari restartdan keyin qayta ishlatiladi — vaqt oynasi
    #: eski trekni yangi mijoz bilan adashtirishning oldini oladi.
    EMPLOYEE_MATCH_WINDOW_SEC = 600

    def _employee_marks_between(
        self, site_id: str, start: str, end: str
    ) -> List[Dict[str, Any]]:
        """Oraliqdagi `employee_seen` belgilari (kamera, trek, vaqt).

        `employee_seen` `line_crossed`ga qaraganda o'nlab marta kam — kun
        yoki hafta bo'yicha to'liq o'qish arzon.
        """
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT camera_id,track_id,occurred_at FROM production_events "
                    "WHERE site_id=? AND occurred_at>=? AND occurred_at<? "
                    "AND event_type='employee_seen' AND track_id IS NOT NULL"
                ),
                (site_id, start, end),
            ).fetchall()
        return [self._dict(row) for row in rows]

    def _employee_marks_of_day(
        self, site_id: str, day: date, zone: ZoneInfo
    ) -> List[Dict[str, Any]]:
        """Kun ichidagi `employee_seen` belgilari (kamera, trek, vaqt)."""
        start_local = datetime.combine(day, datetime.min.time(), tzinfo=zone)
        return self._employee_marks_between(
            site_id,
            start_local.astimezone(timezone.utc).isoformat(),
            (start_local + timedelta(days=1)).astimezone(timezone.utc).isoformat(),
        )

    def _matches_employee(self, row: Dict[str, Any], marks: List[Dict[str, Any]]) -> bool:
        if not marks or row.get("track_id") is None:
            return False
        try:
            moment = datetime.fromisoformat(str(row["occurred_at"]))
        except (TypeError, ValueError):
            return False
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        for mark in marks:
            if str(mark["camera_id"]) != str(row.get("camera_id")):
                continue
            if int(mark["track_id"]) != int(row["track_id"]):
                continue
            try:
                seen_at = datetime.fromisoformat(str(mark["occurred_at"]))
            except (TypeError, ValueError):
                continue
            if seen_at.tzinfo is None:
                seen_at = seen_at.replace(tzinfo=timezone.utc)
            if abs((seen_at - moment).total_seconds()) <= self.EMPLOYEE_MATCH_WINDOW_SEC:
                return True
        return False

    def traffic_trend(
        self, site_id: str, *, days: int = 7, until: Optional[date] = None
    ) -> Dict[str, Any]:
        """Kunlar bo'yicha kirish oqimi.

        Kunlik hisobot "bugun 340 kishi kirdi" deydi, lekin do'kon egasining
        ikkinchi savoli boshqacha: **shu hafta qanday ketdi va qaysi kun
        kuchli?**  Dam olish kunlari savdo ikki barobar bo'lsa xodim jadvali
        ham shunga qarab tuziladi.

        Taqqoslash oldingi **shuncha kunlik** oraliq bilan bo'ladi (7 kun ↔
        oldingi 7 kun), aks holda o'sish bayram kuni tufayli ekanini bilib
        bo'lmasdi.
        """
        timezone_tashkent = ZoneInfo("Asia/Tashkent")
        days = max(1, min(int(days), 90))
        until = until or datetime.now(timezone_tashkent).date()
        start = until - timedelta(days=days - 1)

        counts = self._entered_by_day(site_id, start, until, timezone_tashkent)
        daily = [
            {
                "date": (start + timedelta(days=offset)).isoformat(),
                "weekday": WEEKDAYS[(start + timedelta(days=offset)).weekday()],
                "entered": counts.get(start + timedelta(days=offset), 0),
            }
            for offset in range(days)
        ]
        total = sum(item["entered"] for item in daily)
        previous_end = start - timedelta(days=1)
        previous = sum(
            self._entered_by_day(
                site_id, previous_end - timedelta(days=days - 1), previous_end, timezone_tashkent
            ).values()
        )
        active = [item for item in daily if item["entered"]]
        return {
            "from": start.isoformat(),
            "to": until.isoformat(),
            "days": days,
            "daily": daily,
            "total": total,
            "average": round(total / days, 1),
            "busiest_day": max(active, key=lambda item: item["entered"]) if active else None,
            "quietest_day": min(active, key=lambda item: item["entered"]) if active else None,
            "previous_total": previous,
            "change_percent": _change_percent(total, previous),
        }

    def _entered_by_day(
        self, site_id: str, start: date, end: date, zone: ZoneInfo
    ) -> Dict[date, int]:
        """Oraliqdagi kunlar bo'yicha kirish soni.

        Faqat kerakli ustunlar o'qiladi: 30 kunlik oraliqda bu qatorni
        to'liq yuklashdan ancha yengil.  Kunga bo'lish Python'da, chunki
        vaqt mintaqasi bo'yicha guruhlash SQLite va PostgreSQL'da har xil
        yoziladi.  Xodim o'tishlari kunlik hisobotdagi bilan **bir xil**
        qoida bo'yicha chiqariladi — aks holda grafik va hisobot bir-biriga
        zid raqam ko'rsatardi.
        """
        start_utc = datetime.combine(start, datetime.min.time(), tzinfo=zone).astimezone(
            timezone.utc
        )
        end_utc = datetime.combine(
            end + timedelta(days=1), datetime.min.time(), tzinfo=zone
        ).astimezone(timezone.utc)
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT camera_id,track_id,occurred_at FROM production_events "
                    "WHERE site_id=? AND occurred_at>=? AND occurred_at<? "
                    "AND event_type='line_crossed' AND direction='in'"
                ),
                (site_id, start_utc.isoformat(), end_utc.isoformat()),
            ).fetchall()
        marks = self._employee_marks_between(
            site_id, start_utc.isoformat(), end_utc.isoformat()
        )
        counts: Dict[date, int] = {}
        for row in rows:
            item = self._dict(row)
            if self._matches_employee(item, marks):
                continue
            local = self._to_local(item["occurred_at"], zone)
            if local is None:
                continue
            counts[local.date()] = counts.get(local.date(), 0) + 1
        return counts

    def _events_of_day(self, site_id: str, day: date, zone: ZoneInfo) -> List[Dict[str, Any]]:
        start_local = datetime.combine(day, datetime.min.time(), tzinfo=zone)
        start = start_local.astimezone(timezone.utc).isoformat()
        end = (start_local + timedelta(days=1)).astimezone(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in REPORT_EVENT_TYPES)
        query = self._sql(
            "SELECT * FROM production_events WHERE site_id=? AND occurred_at>=? "
            f"AND occurred_at<? AND event_type IN ({placeholders}) ORDER BY occurred_at"
        )
        with self._connect() as conn:
            rows = conn.execute(query, (site_id, start, end, *REPORT_EVENT_TYPES)).fetchall()
        return [self._decode_event(row) for row in rows]

    def _entered_count(self, site_id: str, day: date, zone: ZoneInfo) -> int:
        """Bir kunlik mijoz kirishi — «kechaga nisbatan» taqqoslash uchun.

        `COUNT(*)` emas: xodim o'tishlari kunlik hisobotdagi bilan bir xil
        qoida bo'yicha chiqarilishi kerak, aks holda "bugun 50% kam" degan
        yolg'on farq chiqadi.
        """
        start_local = datetime.combine(day, datetime.min.time(), tzinfo=zone)
        start = start_local.astimezone(timezone.utc).isoformat()
        end = (start_local + timedelta(days=1)).astimezone(timezone.utc).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT camera_id,track_id,occurred_at FROM production_events "
                    "WHERE site_id=? AND occurred_at>=? AND occurred_at<? "
                    "AND event_type='line_crossed' AND direction='in'"
                ),
                (site_id, start, end),
            ).fetchall()
        marks = self._employee_marks_between(site_id, start, end)
        return sum(
            1 for row in rows if not self._matches_employee(self._dict(row), marks)
        )

    @staticmethod
    def _to_local(occurred_at: str, zone: ZoneInfo) -> Optional[datetime]:
        """Mahalliy vaqtga o'giradi; ochib bo'lmasa `None`.

        Ilgari bu yerda himoya yo'q edi va bitta yaroqsiz qator butun
        do'konning kunlik hisobotini va grafigini 500 qilardi.  Yangi
        yozuvlar `_normalise_occurred_at` bilan kirishda to'g'rilanadi,
        bu esa bazada allaqachon turgan qatorlar uchun.
        """
        try:
            moment = datetime.fromisoformat(str(occurred_at))
        except (TypeError, ValueError):
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(zone)

    def record_health(self, site_id: str, device_id: str, payload: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    "INSERT INTO device_health(device_id,site_id,payload_json,received_at) "
                    "VALUES (?,?,?,?) ON CONFLICT(device_id) DO UPDATE SET "
                    "site_id=excluded.site_id,payload_json=excluded.payload_json,"
                    "received_at=excluded.received_at"
                ),
                (
                    device_id,
                    site_id,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    _now().isoformat(),
                ),
            )

    def health(self, site_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                self._sql("SELECT * FROM device_health WHERE site_id=? ORDER BY received_at DESC"),
                (site_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = self._dict(row)
            item["health"] = json.loads(item.pop("payload_json"))
            result.append(item)
        return result

    def latest_health_by_site(self) -> Dict[str, Dict[str, Any]]:
        """Har sayt uchun oxirgi heartbeat — bitta so'rovda.

        Ogohlantirish tsikli har 15 daqiqada barcha saytlarni ko'radi;
        har biri uchun alohida so'rov yuborish qimmat bo'lardi.  Bir
        saytda bir necha qurilma bo'lsa eng yomon ko'rsatkich olinadi:
        bitta qurilma sog'lom bo'lgani boshqasining yiqilganini
        yashirmasligi kerak.
        """
        with self._connect() as conn:
            rows = conn.execute(
                self._sql("SELECT site_id,payload_json,received_at FROM device_health")
            ).fetchall()
        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            item = self._dict(row)
            try:
                payload = json.loads(item["payload_json"])
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            current = result.get(item["site_id"])
            if current is None:
                result[item["site_id"]] = payload
                continue
            for key in ("analysis_errors", "queue_errors"):
                current[key] = max(int(current.get(key) or 0), int(payload.get(key) or 0))
            current["analyzed"] = max(
                int(current.get("analyzed") or 0), int(payload.get("analyzed") or 0)
            )
            free_values = [
                int(value or 0)
                for value in (current.get("disk_free_bytes"), payload.get("disk_free_bytes"))
                if value
            ]
            if free_values:
                current["disk_free_bytes"] = min(free_values)
        return result

    def get_site_config(self, site_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                self._sql("SELECT * FROM site_configs WHERE site_id=?"), (site_id,)
            ).fetchone()
        if not row:
            return {
                "site_id": site_id,
                "revision": 0,
                "config": {
                    "camera_labels": {},
                    "camera_roles": {},
                    "occupancy_limit": 20,
                    # 60 s juda tajovuzkor edi: band do'konda deyarli har
                    # xaridor "uzoq turish" bo'lib chiqar va shovqin
                    # yaratar edi.  5 daqiqa — haqiqatan g'ayrioddiy holat.
                    "loitering_sec": 300,
                    "queue_limit": 5,
                    "checkout_idle_minutes": 5,
                    "open_from": None,
                    "open_to": None,
                    "attendance_camera_ids": [],
                    "attendance_camera_roles": {},
                    "zones": [],
                    "lines": [],
                },
                "updated_at": None,
            }
        return {
            "site_id": site_id,
            "revision": int(row["revision"]),
            "config": json.loads(row["config_json"]),
            "updated_at": row["updated_at"],
        }

    def config_revision(self, site_id: str) -> int:
        """Faqat revision — heartbeat har daqiqada shuni so'raydi.

        To'liq `get_site_config()` JSON parse qiladi, `/config` marshruti esa
        ustiga funksiya narxini hisoblab, har kameraning RTSP parolini
        deshifrlaydi. Qurilma o'zgarish bor-yo'qligini shu bitta sondan biladi.
        """
        with self._connect() as conn:
            row = conn.execute(
                self._sql("SELECT revision FROM site_configs WHERE site_id=?"), (site_id,)
            ).fetchone()
        return int(row["revision"]) if row else 0

    def update_site_config(self, site_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        current = self.get_site_config(site_id)
        revision = int(current["revision"]) + 1
        updated_at = _now().isoformat()
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    "INSERT INTO site_configs(site_id,revision,config_json,updated_at) "
                    "VALUES (?,?,?,?) ON CONFLICT(site_id) DO UPDATE SET "
                    "revision=excluded.revision,config_json=excluded.config_json,"
                    "updated_at=excluded.updated_at"
                ),
                (
                    site_id,
                    revision,
                    json.dumps(config, ensure_ascii=False, separators=(",", ":")),
                    updated_at,
                ),
            )
        return self.get_site_config(site_id)

    def touch_site_config(self, site_id: str) -> int:
        """Config tashqarisidagi edge metadata (masalan xodim) o'zgarganini bildiradi."""
        current = self.get_site_config(site_id)
        return int(self.update_site_config(site_id, current["config"])["revision"])

    # ── Xodimlar va davomat ─────────────────────────────────────────────

    def create_employee(
        self,
        site_id: str,
        *,
        name: str,
        external_id: Optional[str] = None,
        consent_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cloud profilini yaratadi; yuz rasmi va embedding bu bazaga kirmaydi."""
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Xodim ismi bo'sh bo'lishi mumkin emas")
        clean_external = (external_id or "").strip() or None
        employee_id = str(uuid.uuid4())
        now = _now().isoformat()
        try:
            with self._connect() as conn:
                conn.execute(
                    self._sql(
                        "INSERT INTO employees "
                        "(id,site_id,name,external_id,active,consent_recorded_at,"
                        "consent_note,enrollment_status,created_at,updated_at) "
                        "VALUES (?,?,?,?,1,?,?,'pending',?,?)"
                    ),
                    (
                        employee_id,
                        site_id,
                        clean_name[:160],
                        clean_external[:80] if clean_external else None,
                        now,
                        (consent_note or "").strip()[:500] or None,
                        now,
                        now,
                    ),
                )
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise ValueError("Bu tashqi xodim ID allaqachon ishlatilgan") from exc
            raise
        employee = self.employee(site_id, employee_id)
        if employee is None:  # pragma: no cover - database invariant
            raise RuntimeError("Xodim yozilmadi")
        return employee

    def employee(self, site_id: str, employee_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                self._sql("SELECT * FROM employees WHERE site_id=? AND id=?"),
                (site_id, employee_id),
            ).fetchone()
        return self._decode_employee(row) if row else None

    def list_employees(
        self, site_id: str, *, include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        where = "site_id=?" if include_inactive else "site_id=? AND active=1"
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(f"SELECT * FROM employees WHERE {where} ORDER BY name,id"),
                (site_id,),
            ).fetchall()
        return [self._decode_employee(row) for row in rows]

    def _decode_employee(self, row: Any) -> Dict[str, Any]:
        item = self._dict(row)
        item["active"] = bool(item.get("active"))
        item["consent_recorded"] = bool(item.get("consent_recorded_at"))
        item["schedules"] = self.employee_schedules(str(item["id"]))
        return item

    def update_employee(
        self,
        site_id: str,
        employee_id: str,
        *,
        name: Optional[str] = None,
        external_id: Optional[str] = None,
        active: Optional[bool] = None,
        enrollment_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        current = self.employee(site_id, employee_id)
        if current is None:
            raise ValueError("Xodim topilmadi")
        clean_name = current["name"] if name is None else name.strip()
        if not clean_name:
            raise ValueError("Xodim ismi bo'sh bo'lishi mumkin emas")
        clean_external = (
            current.get("external_id") if external_id is None else external_id.strip() or None
        )
        clean_status = enrollment_status or str(current.get("enrollment_status") or "pending")
        if clean_status not in {"pending", "enrolled", "failed", "removed"}:
            raise ValueError("Enrollment holati noto'g'ri")
        next_active = bool(current["active"] if active is None else active)
        if active is None:
            deactivated_at = current.get("deactivated_at")
        else:
            deactivated_at = None if next_active else _now().isoformat()
        try:
            with self._connect() as conn:
                conn.execute(
                    self._sql(
                        "UPDATE employees SET name=?,external_id=?,active=?,"
                        "enrollment_status=?,deactivated_at=?,updated_at=? "
                        "WHERE site_id=? AND id=?"
                    ),
                    (
                        clean_name[:160],
                        clean_external[:80] if clean_external else None,
                        int(next_active),
                        clean_status,
                        deactivated_at,
                        _now().isoformat(),
                        site_id,
                        employee_id,
                    ),
                )
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise ValueError("Bu tashqi xodim ID allaqachon ishlatilgan") from exc
            raise
        updated = self.employee(site_id, employee_id)
        if updated is None:  # pragma: no cover
            raise RuntimeError("Xodim yangilanmadi")
        return updated

    def employee_schedules(self, employee_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT weekday,start_time,end_time,grace_minutes,enabled,updated_at "
                    "FROM employee_schedules WHERE employee_id=? ORDER BY weekday"
                ),
                (employee_id,),
            ).fetchall()
        result = [self._dict(row) for row in rows]
        for item in result:
            item["enabled"] = bool(item["enabled"])
        return result

    def replace_employee_schedules(
        self, site_id: str, employee_id: str, schedules: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        if self.employee(site_id, employee_id) is None:
            raise ValueError("Xodim topilmadi")
        weekdays = [int(item["weekday"]) for item in schedules]
        if any(day < 0 or day > 6 for day in weekdays) or len(weekdays) != len(set(weekdays)):
            raise ValueError("Hafta kuni 0..6 va takrorlanmas bo'lishi kerak")
        now = _now().isoformat()
        with self._connect() as conn:
            conn.execute(
                self._sql("DELETE FROM employee_schedules WHERE employee_id=?"),
                (employee_id,),
            )
            for item in schedules:
                conn.execute(
                    self._sql(
                        "INSERT INTO employee_schedules "
                        "(employee_id,weekday,start_time,end_time,grace_minutes,enabled,updated_at) "
                        "VALUES (?,?,?,?,?,?,?)"
                    ),
                    (
                        employee_id,
                        int(item["weekday"]),
                        str(item["start_time"]),
                        str(item["end_time"]),
                        int(item.get("grace_minutes", 5)),
                        int(bool(item.get("enabled", True))),
                        now,
                    ),
                )
        return self.employee_schedules(employee_id)

    def edge_employees(self, site_id: str) -> List[Dict[str, Any]]:
        """Edge enrollment uchun PII'ning minimal, biometrikasiz nusxasi."""
        return [
            {
                "id": employee["id"],
                "name": employee["name"],
                "active": employee["active"],
                "consent_recorded_at": employee["consent_recorded_at"],
                "enrollment_status": employee["enrollment_status"],
                "updated_at": employee["updated_at"],
            }
            for employee in self.list_employees(site_id)
        ]

    # ── Yuz namunalari (cloud enrollment) ────────────────────────────────
    #
    # Embedding hech qachon ochiq saqlanmaydi: `embedding_b64` — Fernet
    # bilan shifrlangan vektor.  Kalit (`CHAQIMCHI_EMBEDDING_KEY`) faqat
    # environmentda, bazada emas — baza nusxasi o'g'irlansa ham biometrik
    # ma'lumot ochilmaydi.

    #: Bitta xodimga rasm limiti: 1-3 rasm yetadi, ko'pi shovqin.
    MAX_FACES_PER_EMPLOYEE = 3

    def add_employee_face(
        self,
        site_id: str,
        employee_id: str,
        *,
        photo_key: str,
        embedding_b64: str,
        embedding_dim: int,
        det_score: Optional[float] = None,
        photo_bytes: int = 0,
    ) -> Dict[str, Any]:
        employee = self.employee(site_id, employee_id)
        if employee is None:
            raise ValueError("Xodim topilmadi")
        existing = self.list_employee_faces(site_id, employee_id=employee_id)
        if len(existing) >= self.MAX_FACES_PER_EMPLOYEE:
            raise ValueError(f"Bitta xodimga ko'pi bilan {self.MAX_FACES_PER_EMPLOYEE} ta rasm")
        face_id = uuid.uuid4().hex[:12]
        now = _now().isoformat()
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    "INSERT INTO employee_faces "
                    "(id,site_id,employee_id,photo_key,embedding_b64,embedding_dim,"
                    "det_score,photo_bytes,created_at) VALUES (?,?,?,?,?,?,?,?,?)"
                ),
                (
                    face_id,
                    site_id,
                    employee_id,
                    photo_key,
                    embedding_b64,
                    int(embedding_dim),
                    det_score,
                    int(photo_bytes),
                    now,
                ),
            )
            # Birinchi yaroqli rasm — xodim ro'yxatga olindi.
            conn.execute(
                self._sql(
                    "UPDATE employees SET enrollment_status='enrolled',updated_at=? "
                    "WHERE site_id=? AND id=?"
                ),
                (now, site_id, employee_id),
            )
        return {
            "id": face_id,
            "employee_id": employee_id,
            "photo_key": photo_key,
            "det_score": det_score,
            "created_at": now,
        }

    def list_employee_faces(
        self, site_id: str, *, employee_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Rasm ro'yxati — embedding QAYTARILMAYDI (faqat moslash o'qiydi)."""
        query = (
            "SELECT id,employee_id,photo_key,det_score,photo_bytes,created_at "
            "FROM employee_faces WHERE site_id=?"
        )
        params: List[Any] = [site_id]
        if employee_id is not None:
            query += " AND employee_id=?"
            params.append(employee_id)
        query += " ORDER BY created_at"
        with self._connect() as conn:
            rows = conn.execute(self._sql(query), tuple(params)).fetchall()
        return [self._dict(row) for row in rows]

    def all_employee_faces(self, *, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Barcha obyektlardagi rasm yozuvlari — model migratsiyasi uchun.

        `list_employee_faces` ataylab bitta obyekt bilan cheklangan va
        embedding qaytarmaydi (panel uchun).  Bu yerda esa aksincha:
        `scripts/reembed_faces.py` butun bazani aylanib chiqishi kerak.
        """
        query = (
            "SELECT id,site_id,employee_id,photo_key,embedding_dim,created_at "
            "FROM employee_faces"
        )
        params: List[Any] = []
        if site_id is not None:
            query += " WHERE site_id=?"
            params.append(site_id)
        query += " ORDER BY site_id,created_at"
        with self._connect() as conn:
            rows = conn.execute(self._sql(query), tuple(params)).fetchall()
        return [self._dict(row) for row in rows]

    def update_employee_face_embedding(
        self,
        face_id: str,
        *,
        embedding_b64: str,
        embedding_dim: int,
        det_score: Optional[float] = None,
    ) -> bool:
        """Rasmni qayta hisoblangan vektor bilan yangilaydi.

        Rasm o'chirilib qayta qo'shilmaydi: `photo_key` va `created_at`
        o'z joyida qoladi, ya'ni retensiya hisobi va galereya tartibi
        buzilmaydi.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                self._sql(
                    "UPDATE employee_faces SET embedding_b64=?,embedding_dim=?,det_score=? "
                    "WHERE id=?"
                ),
                (embedding_b64, int(embedding_dim), det_score, face_id),
            )
        return bool(cursor.rowcount)

    def employee_face(self, site_id: str, face_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                self._sql(
                    "SELECT id,employee_id,photo_key,det_score,photo_bytes,created_at "
                    "FROM employee_faces WHERE site_id=? AND id=?"
                ),
                (site_id, face_id),
            ).fetchone()
        return self._dict(row) if row else None

    def delete_employee_face(self, site_id: str, face_id: str) -> Optional[str]:
        """Rasmni o'chiradi, blob kalitini qaytaradi (chaqiruvchi blobni o'chiradi)."""
        face = self.employee_face(site_id, face_id)
        if face is None:
            return None
        with self._connect() as conn:
            conn.execute(
                self._sql("DELETE FROM employee_faces WHERE site_id=? AND id=?"),
                (site_id, face_id),
            )
            remaining = conn.execute(
                self._sql(
                    "SELECT COUNT(*) AS total FROM employee_faces WHERE site_id=? AND employee_id=?"
                ),
                (site_id, face["employee_id"]),
            ).fetchone()
            if not int(self._dict(remaining)["total"] or 0):
                # Oxirgi rasm o'chdi — xodim yana ro'yxatga olinmagan holatda.
                conn.execute(
                    self._sql(
                        "UPDATE employees SET enrollment_status='pending',updated_at=? "
                        "WHERE site_id=? AND id=?"
                    ),
                    (_now().isoformat(), site_id, face["employee_id"]),
                )
        return str(face["photo_key"])

    def face_embeddings(self, site_id: str) -> List[Dict[str, Any]]:
        """Moslash uchun faol xodimlarning shifrlangan embeddinglari.

        `embedding_dim` ham qaytariladi: model almashganda eski yozuvlar
        boshqa o'lchamda qoladi va ularni moslashga qo'shib bo'lmaydi.
        """
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT f.employee_id,f.embedding_b64,f.embedding_dim,e.name "
                    "FROM employee_faces f JOIN employees e ON e.id=f.employee_id "
                    "WHERE f.site_id=? AND e.active=1"
                ),
                (site_id,),
            ).fetchall()
        return [self._dict(row) for row in rows]

    def attendance_report(
        self,
        site_id: str,
        *,
        start: date,
        end: date,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        if end < start:
            raise ValueError("Tugash sanasi boshlanishdan oldin")
        if (end - start).days > 366:
            raise ValueError("Davomat oralig'i 367 kundan oshmasin")
        zone = ZoneInfo("Asia/Tashkent")
        local_now = now or datetime.now(zone)
        if local_now.tzinfo is None:
            local_now = local_now.replace(tzinfo=zone)
        employees = self.list_employees(site_id, include_inactive=True)
        attendance_roles = dict(
            self.get_site_config(site_id)["config"].get("attendance_camera_roles") or {}
        )
        schedule_map = {
            (employee["id"], int(item["weekday"])): item
            for employee in employees
            for item in employee["schedules"]
        }
        rows: List[Dict[str, Any]] = []
        cursor = start
        while cursor <= end:
            day_events = self._employee_events_of_day(site_id, cursor, zone)
            for employee in employees:
                # Bu vaqtlarni server o'zi yozadi, ya'ni ular doim to'g'ri;
                # `or cursor` faqat sxema buzilgan holat uchun himoya.
                created_local = self._to_local(str(employee["created_at"]), zone)
                created_day = created_local.date() if created_local else cursor
                deactivated_local = (
                    self._to_local(str(employee["deactivated_at"]), zone)
                    if employee.get("deactivated_at")
                    else None
                )
                deactivated_day = deactivated_local.date() if deactivated_local else None
                if cursor < created_day or (
                    deactivated_day is not None and cursor > deactivated_day
                ):
                    continue
                rows.append(
                    self._attendance_row(
                        employee,
                        cursor,
                        schedule_map.get((employee["id"], cursor.weekday())),
                        day_events.get(employee["id"], []),
                        attendance_roles,
                        local_now,
                        zone,
                    )
                )
            cursor += timedelta(days=1)
        self._cache_attendance_rows(site_id, rows)
        counts: Dict[str, int] = {
            "present": 0,
            "absent": 0,
            "late": 0,
            "early_leave": 0,
            "checkout_missing": 0,
            "unscheduled": 0,
        }
        for row in rows:
            if row["first_seen"]:
                counts["present"] += 1
            if row["status"] == "absent":
                counts["absent"] += 1
            if row["status"] == "unscheduled":
                counts["unscheduled"] += 1
            if row["late_minutes"]:
                counts["late"] += 1
            if row["early_leave_minutes"]:
                counts["early_leave"] += 1
            if row["checkout_missing"]:
                counts["checkout_missing"] += 1
        return {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "employees": len({row["employee_id"] for row in rows}),
            "summary": counts,
            "rows": rows,
        }

    def shift_summary(
        self,
        site_id: str,
        *,
        start: date,
        end: date,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Oylik smena hisoboti — xodim kesimida.

        Kunlik jadval allaqachon bor (`attendance_report`), lekin do'kon
        egasining savoli boshqacha: "kim qancha kechikdi va bu menga
        necha pulga tushdi".  Kunma-kun 30 qatorni ko'zdan kechirib
        chiqib, uni qo'lda qo'shib hisoblash — hech kim qilmaydigan ish.

        Hisob `attendance_report` ustiga quriladi, chunki kechikish
        daqiqalari faqat o'sha yerda jadval bilan solishtirib
        aniqlanadi.  Kunlik natijalar `attendance_daily` ga keshlanadi,
        ya'ni ikkinchi chaqiruv qimmat emas.
        """
        report = self.attendance_report(site_id, start=start, end=end, now=now)
        people: Dict[str, Dict[str, Any]] = {}
        for row in report["rows"]:
            item = people.setdefault(
                str(row["employee_id"]),
                {
                    "employee_id": row["employee_id"],
                    "employee_name": row["employee_name"],
                    "external_id": row.get("external_id"),
                    "ish_kunlari": 0,
                    "kelgan_kunlar": 0,
                    "kelmagan_kunlar": 0,
                    "kechikkan_kunlar": 0,
                    "jami_kechikish_daq": 0,
                    "erta_ketgan_kunlar": 0,
                    "jami_erta_ketish_daq": 0,
                    "chiqish_aniqlanmadi": 0,
                },
            )
            # `unscheduled` — jadvalda yo'q kun (dam olish).  U "ish
            # kuni" ham, "kelmagan kun" ham emas: aks holda haftada ikki
            # kun dam oladigan xodim eng yomon ko'rsatkichga chiqib
            # qolardi.
            if row["status"] in {"present", "late", "absent", "early_leave"}:
                item["ish_kunlari"] += 1
            if row.get("first_seen"):
                item["kelgan_kunlar"] += 1
            if row["status"] == "absent":
                item["kelmagan_kunlar"] += 1
            if row["late_minutes"]:
                item["kechikkan_kunlar"] += 1
                item["jami_kechikish_daq"] += int(row["late_minutes"])
            if row["early_leave_minutes"]:
                item["erta_ketgan_kunlar"] += 1
                item["jami_erta_ketish_daq"] += int(row["early_leave_minutes"])
            if row["checkout_missing"]:
                item["chiqish_aniqlanmadi"] += 1

        rows = []
        for item in people.values():
            kechikkan = item["kechikkan_kunlar"]
            item["ortacha_kechikish_daq"] = (
                round(item["jami_kechikish_daq"] / kechikkan, 1) if kechikkan else 0.0
            )
            rows.append(item)
        # Eng ko'p kechikkan tepada — hisobot aynan shu savolga javob
        # beradi va do'kon egasi pastga qarab qidirmasin.
        rows.sort(key=lambda item: (-item["jami_kechikish_daq"], item["employee_name"]))

        return {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "employees": len(rows),
            "jami": {
                "kechikish_daq": sum(item["jami_kechikish_daq"] for item in rows),
                "kelmagan_kunlar": sum(item["kelmagan_kunlar"] for item in rows),
                "erta_ketish_daq": sum(item["jami_erta_ketish_daq"] for item in rows),
            },
            "rows": rows,
        }

    def _employee_events_of_day(
        self, site_id: str, day: date, zone: ZoneInfo
    ) -> Dict[str, List[Tuple[datetime, str]]]:
        start_local = datetime.combine(day, datetime.min.time(), tzinfo=zone)
        start = start_local.astimezone(timezone.utc).isoformat()
        end = (start_local + timedelta(days=1)).astimezone(timezone.utc).isoformat()
        with self._connect() as conn:
            raw = conn.execute(
                self._sql(
                    "SELECT person_id,occurred_at,camera_id FROM production_events "
                    "WHERE site_id=? AND event_type='employee_seen' AND person_name IS NOT NULL "
                    "AND occurred_at>=? AND occurred_at<? ORDER BY occurred_at"
                ),
                (site_id, start, end),
            ).fetchall()
        grouped: Dict[str, List[Tuple[datetime, str]]] = {}
        for item in raw:
            row = self._dict(item)
            local = self._to_local(str(row["occurred_at"]), zone)
            if row.get("person_id") and local is not None:
                grouped.setdefault(str(row["person_id"]), []).append(
                    (local, str(row["camera_id"]))
                )
        return grouped

    @staticmethod
    def _attendance_row(
        employee: Dict[str, Any],
        day: date,
        schedule: Optional[Dict[str, Any]],
        seen: List[Tuple[datetime, str]],
        attendance_roles: Dict[str, str],
        now: datetime,
        zone: ZoneInfo,
    ) -> Dict[str, Any]:
        moments = [moment for moment, _camera_id in seen]
        explicit_roles = bool(attendance_roles)
        arrival_observed = False
        if explicit_roles:
            arrival_events = [
                (moment, camera_id)
                for moment, camera_id in seen
                if attendance_roles.get(camera_id) in {"arrival", "both"}
            ]
            departure_events = [
                (moment, camera_id)
                for moment, camera_id in seen
                if attendance_roles.get(camera_id) in {"departure", "both"}
            ]
            # Chiqish kamerasi odamni ko'rgan bo'lsa ham "kelmadi" deyish
            # noto'g'ri. Arrival yo'qolgan holatda birinchi umumiy ko'rish
            # present bo'lish uchun fallback, lekin checkout alohida qoladi.
            first_event = arrival_events[0] if arrival_events else (seen[0] if seen else None)
            first = first_event[0] if first_event else None
            arrival_observed = bool(arrival_events)
            valid_departures = [
                item
                for item in departure_events
                # `both` kameradagi kelish atrofidagi takroriy match ketish
                # emas. Alohida departure kamera esa vaqt farqisiz valid.
                if attendance_roles.get(item[1]) == "departure"
                or (
                    first_event is not None
                    and item[0] - first_event[0]
                    >= timedelta(minutes=MIN_BOTH_CAMERA_DEPARTURE_MINUTES)
                )
            ]
            last = valid_departures[-1][0] if valid_departures else None
        else:
            first = moments[0] if moments else None
            last = moments[-1] if moments else None
            arrival_observed = bool(moments)
        scheduled_start = scheduled_end = None
        late_minutes = early_minutes = 0
        checkout_missing = False

        if not schedule or not schedule.get("enabled"):
            status = "unscheduled" if seen else "off"
        else:
            start_hour, start_minute = map(int, str(schedule["start_time"]).split(":"))
            end_hour, end_minute = map(int, str(schedule["end_time"]).split(":"))
            scheduled_start = datetime.combine(day, datetime.min.time(), tzinfo=zone).replace(
                hour=start_hour, minute=start_minute
            )
            scheduled_end = datetime.combine(day, datetime.min.time(), tzinfo=zone).replace(
                hour=end_hour, minute=end_minute
            )
            if not moments:
                absent_after = scheduled_start + timedelta(minutes=int(schedule["grace_minutes"]))
                status = "absent" if now >= absent_after else "pending"
            else:
                allowed = scheduled_start + timedelta(minutes=int(schedule["grace_minutes"]))
                late_minutes = (
                    max(0, int(((first or allowed) - allowed).total_seconds() // 60))
                    if arrival_observed
                    else 0
                )
                shift_finished = now >= scheduled_end or day < now.date()
                checkout_missing = bool(
                    shift_finished and (last is None if explicit_roles else first == last)
                )
                if shift_finished and not checkout_missing and last is not None:
                    early_minutes = max(0, int((scheduled_end - last).total_seconds() // 60))
                status = "late" if late_minutes else "present"

        return {
            "employee_id": employee["id"],
            "employee_name": employee["name"],
            "external_id": employee.get("external_id"),
            "date": day.isoformat(),
            "scheduled_start": scheduled_start.isoformat() if scheduled_start else None,
            "scheduled_end": scheduled_end.isoformat() if scheduled_end else None,
            "first_seen": first.isoformat() if first else None,
            "last_seen": last.isoformat() if last else None,
            "status": status,
            "late_minutes": late_minutes,
            "early_leave_minutes": early_minutes,
            "checkout_missing": checkout_missing,
        }

    def _cache_attendance_rows(self, site_id: str, rows: List[Dict[str, Any]]) -> None:
        query = self._sql(
            "INSERT INTO attendance_daily "
            "(site_id,employee_id,work_date,scheduled_start,scheduled_end,first_seen,last_seen,"
            "status,late_minutes,early_leave_minutes,checkout_missing,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(site_id,employee_id,work_date) "
            "DO UPDATE SET scheduled_start=excluded.scheduled_start,scheduled_end=excluded.scheduled_end,"
            "first_seen=excluded.first_seen,last_seen=excluded.last_seen,status=excluded.status,"
            "late_minutes=excluded.late_minutes,early_leave_minutes=excluded.early_leave_minutes,"
            "checkout_missing=excluded.checkout_missing,updated_at=excluded.updated_at"
        )
        now = _now().isoformat()
        with self._connect() as conn:
            for row in rows:
                conn.execute(
                    query,
                    (
                        site_id,
                        row["employee_id"],
                        row["date"],
                        row["scheduled_start"],
                        row["scheduled_end"],
                        row["first_seen"],
                        row["last_seen"],
                        row["status"],
                        row["late_minutes"],
                        row["early_leave_minutes"],
                        int(row["checkout_missing"]),
                        now,
                    ),
                )

    def add_member(
        self,
        site_id: str,
        telegram_id: str,
        *,
        role: str,
        display_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        if role not in {"owner", "manager", "service_admin"}:
            raise ValueError("Noto'g'ri rol")
        member_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    "INSERT INTO owner_members "
                    "(id,site_id,telegram_id,role,display_name,active,created_at) "
                    "VALUES (?,?,?,?,?,1,?) "
                    "ON CONFLICT(site_id,telegram_id) DO UPDATE SET "
                    "role=excluded.role,display_name=excluded.display_name,active=1"
                ),
                (member_id, site_id, str(telegram_id), role, display_name, _now().isoformat()),
            )
        member = self.member_for_site(site_id, str(telegram_id))
        if member is None:  # pragma: no cover - database invariant
            raise RuntimeError("Member yozilmadi")
        return member

    def member_for_site(self, site_id: str, telegram_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                self._sql(
                    "SELECT * FROM owner_members WHERE site_id=? AND telegram_id=? AND active=1"
                ),
                (site_id, str(telegram_id)),
            ).fetchone()
        return self._dict(row) if row else None

    def members_for_telegram(self, telegram_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT * FROM owner_members WHERE telegram_id=? AND active=1 "
                    "ORDER BY created_at"
                ),
                (str(telegram_id),),
            ).fetchall()
        return [self._dict(row) for row in rows]

    def list_members(self, site_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT id,site_id,telegram_id,role,display_name,active,"
                    "digest_muted,notify_failures,created_at "
                    "FROM owner_members WHERE site_id=? AND active=1 ORDER BY created_at"
                ),
                (site_id,),
            ).fetchall()
        return [self._dict(row) for row in rows]

    def set_digest_muted(self, site_id: str, member_id: str, muted: bool) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                self._sql("UPDATE owner_members SET digest_muted=? WHERE site_id=? AND id=?"),
                (1 if muted else 0, site_id, member_id),
            )
            return bool(cursor.rowcount)

    def record_notify_failure(self, site_id: str, member_id: str) -> int:
        """Yuborish muvaffaqiyatsizligini sanaydi; yangi qiymatni qaytaradi.

        "Chat not found" — a'zo botga hech qachon /start bosmagani belgisi;
        bir necha urinishdan keyin unga yuborish to'xtatiladi, aks holda
        har batch'da log xatoga to'lardi.
        """
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    "UPDATE owner_members SET notify_failures=notify_failures+1 "
                    "WHERE site_id=? AND id=?"
                ),
                (site_id, member_id),
            )
            row = conn.execute(
                self._sql("SELECT notify_failures FROM owner_members WHERE site_id=? AND id=?"),
                (site_id, member_id),
            ).fetchone()
        return int(self._dict(row)["notify_failures"]) if row else 0

    def reset_notify_failures(self, site_id: str, member_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                self._sql("UPDATE owner_members SET notify_failures=0 WHERE site_id=? AND id=?"),
                (site_id, member_id),
            )

    def disable_member(self, site_id: str, member_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                self._sql("UPDATE owner_members SET active=0 WHERE site_id=? AND id=?"),
                (site_id, member_id),
            )
            return bool(cursor.rowcount)

    def create_otp(self, telegram_id: str, *, secret: str, code: Optional[str] = None) -> str:
        code = code or f"{secrets.randbelow(1_000_000):06d}"
        digest = hmac.new(
            secret.encode(), f"{telegram_id}:{code}".encode(), hashlib.sha256
        ).hexdigest()
        now = _now()
        with self._connect() as conn:
            conn.execute(
                self._sql("UPDATE owner_otps SET used=1 WHERE telegram_id=? AND used=0"),
                (str(telegram_id),),
            )
            conn.execute(
                self._sql(
                    "INSERT INTO owner_otps "
                    "(id,telegram_id,code_hash,expires_at,attempts,used,created_at) "
                    "VALUES (?,?,?,?,0,0,?)"
                ),
                (
                    str(uuid.uuid4()),
                    str(telegram_id),
                    digest,
                    (now + timedelta(minutes=5)).isoformat(),
                    now.isoformat(),
                ),
            )
        return code

    def verify_otp(self, telegram_id: str, code: str, *, secret: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                self._sql(
                    "SELECT * FROM owner_otps WHERE telegram_id=? AND used=0 "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                (str(telegram_id),),
            ).fetchone()
            if not row:
                return False
            conn.execute(
                self._sql("UPDATE owner_otps SET attempts=attempts+1 WHERE id=?"),
                (row["id"],),
            )
            if int(row["attempts"]) >= 5 or row["expires_at"] < _now().isoformat():
                return False
            digest = hmac.new(
                secret.encode(), f"{telegram_id}:{code}".encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(digest, row["code_hash"]):
                return False
            conn.execute(self._sql("UPDATE owner_otps SET used=1 WHERE id=?"), (row["id"],))
            return True

    # ── Kirish havolalari ────────────────────────────────────────────────
    #
    # `?key=<token>` havolasi — OTP o'rnini bosadigan qulaylik.  Token
    # `secrets.token_urlsafe(32)` (taxmin qilib bo'lmaydi), bazada faqat
    # HMAC hash turadi (baza sizib chiqsa ham havola tiklanmaydi), va har
    # a'zoda bitta faol havola bo'ladi: yangisini yaratish eskisini bekor
    # qiladi — "havola tarqalib ketdi" muammosi bitta tugma bilan yopiladi.

    def _login_link_digest(self, token: str, secret: str) -> str:
        # "login-link:" prefiksi — OTP hash'lari bilan domen ajratish.
        return hmac.new(secret.encode(), f"login-link:{token}".encode(), hashlib.sha256).hexdigest()

    # ── Telegramni bir bosishda ulash ───────────────────────────────────
    #
    # Mijozdan Telegram ID raqamini so'rash ishlamaydi: u raqamni bilmaydi
    # va topish yo'lini ham bilmaydi.  Buning o'rniga panel havola beradi
    # (`t.me/bot?start=<token>`), odam uni bosadi va bot uni a'zo qiladi.
    # Xuddi shu mexanizm xodim taklif qilish uchun ham ishlatiladi.
    #
    # Havola — CREDENTIAL: uni bosgan odam do'kon paneliga kiradi.
    # Shuning uchun muddati qisqa va bir martalik.  (Taqqoslash uchun:
    # `owner_login_links` 30 kun yashaydi, chunki u aniq bir a'zo uchun
    # yaratiladi; bu esa "kim bossa o'sha" turidan.)
    INVITE_TTL_MINUTES = 30

    def _invite_digest(self, token: str, secret: str) -> str:
        return hmac.new(secret.encode(), f"tg-invite:{token}".encode(), hashlib.sha256).hexdigest()

    def create_telegram_invite(
        self,
        site_id: str,
        *,
        secret: str,
        role: str = "manager",
        display_name: Optional[str] = None,
        ttl_minutes: Optional[int] = None,
    ) -> Dict[str, Any]:
        token = secrets.token_urlsafe(24)
        now = _now()
        minutes = int(ttl_minutes or self.INVITE_TTL_MINUTES)
        expires = now + timedelta(minutes=minutes)
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    "INSERT INTO telegram_invites "
                    "(id,site_id,token_hash,role,display_name,expires_at,created_at) "
                    "VALUES (?,?,?,?,?,?,?)"
                ),
                (
                    str(uuid.uuid4()),
                    site_id,
                    self._invite_digest(token, secret),
                    role,
                    display_name,
                    expires.isoformat(),
                    now.isoformat(),
                ),
            )
        return {"token": token, "expires_at": expires.isoformat(), "expires_minutes": minutes}

    def redeem_telegram_invite(
        self, token: str, telegram_id: str, *, secret: str
    ) -> Optional[Dict[str, Any]]:
        """Havolani a'zolikka aylantiradi.  Muddati o'tgan yoki ishlatilgan
        bo'lsa `None` — chaqiruvchi buni "havola eskirgan" deb aytadi."""
        digest = self._invite_digest(token, secret)
        now = _now()
        with self._connect() as conn:
            row = conn.execute(
                self._sql(
                    "SELECT * FROM telegram_invites WHERE token_hash=? AND used_at IS NULL"
                ),
                (digest,),
            ).fetchone()
            if not row:
                return None
            invite = self._dict(row)
            try:
                if datetime.fromisoformat(str(invite["expires_at"])) < now:
                    return None
            except (TypeError, ValueError):
                return None
            conn.execute(
                self._sql("UPDATE telegram_invites SET used_at=?,used_by=? WHERE id=?"),
                (now.isoformat(), str(telegram_id), invite["id"]),
            )
        self.add_member(
            invite["site_id"],
            str(telegram_id),
            role=str(invite["role"] or "manager"),
            display_name=invite.get("display_name") or None,
        )
        return {"site_id": invite["site_id"], "role": invite["role"]}

    def create_login_link(
        self, site_id: str, telegram_id: str, *, secret: str, ttl_days: int = 30
    ) -> str:
        token = secrets.token_urlsafe(32)
        now = _now()
        with self._connect() as conn:
            conn.execute(
                self._sql(
                    "UPDATE owner_login_links SET revoked=1 "
                    "WHERE site_id=? AND telegram_id=? AND revoked=0"
                ),
                (site_id, str(telegram_id)),
            )
            conn.execute(
                self._sql(
                    "INSERT INTO owner_login_links "
                    "(id,site_id,telegram_id,token_hash,expires_at,revoked,created_at) "
                    "VALUES (?,?,?,?,?,0,?)"
                ),
                (
                    str(uuid.uuid4()),
                    site_id,
                    str(telegram_id),
                    self._login_link_digest(token, secret),
                    (now + timedelta(days=ttl_days)).isoformat(),
                    now.isoformat(),
                ),
            )
        return token

    def member_for_login_token(self, token: str, *, secret: str) -> Optional[Dict[str, Any]]:
        """Havola tokeni → faol a'zo, yoki None.

        A'zolik har safar qayta tekshiriladi: a'zo o'chirilsa uning eski
        havolasi ham darhol ishlamay qoladi.
        """
        digest = self._login_link_digest(token, secret)
        with self._connect() as conn:
            row = conn.execute(
                self._sql("SELECT * FROM owner_login_links WHERE token_hash=? AND revoked=0"),
                (digest,),
            ).fetchone()
            if not row:
                return None
            data = self._dict(row)
            if data["expires_at"] < _now().isoformat():
                return None
            conn.execute(
                self._sql("UPDATE owner_login_links SET last_used_at=? WHERE id=?"),
                (_now().isoformat(), data["id"]),
            )
        return self.member_for_site(data["site_id"], data["telegram_id"])

    def revoke_login_links(self, site_id: str, telegram_id: Optional[str] = None) -> int:
        query = "UPDATE owner_login_links SET revoked=1 WHERE site_id=? AND revoked=0"
        params: List[Any] = [site_id]
        if telegram_id is not None:
            query += " AND telegram_id=?"
            params.append(str(telegram_id))
        with self._connect() as conn:
            cursor = conn.execute(self._sql(query), tuple(params))
            return int(cursor.rowcount or 0)

    def mark_digest_sent(self, site_id: str, digest_date: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                self._sql(
                    "INSERT INTO daily_digests(site_id,digest_date,sent_at) VALUES (?,?,?) "
                    "ON CONFLICT(site_id,digest_date) DO NOTHING"
                ),
                (site_id, digest_date, _now().isoformat()),
            )
            return bool(cursor.rowcount)

    def digest_was_sent(self, site_id: str, digest_date: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                self._sql("SELECT 1 FROM daily_digests WHERE site_id=? AND digest_date=?"),
                (site_id, digest_date),
            ).fetchone()
        return row is not None

    def purge(self, retention_days: int = 30) -> List[str]:
        cutoff = (_now() - timedelta(days=max(1, retention_days))).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT snapshot_key,clip_key FROM production_events "
                    "WHERE occurred_at<? AND "
                    "(snapshot_key IS NOT NULL OR clip_key IS NOT NULL)"
                ),
                (cutoff,),
            ).fetchall()
            conn.execute(self._sql("DELETE FROM production_events WHERE occurred_at<?"), (cutoff,))
        return [str(key) for row in rows for key in (row["snapshot_key"], row["clip_key"]) if key]

    def purge_site(self, site_id: str, retention_days: int) -> List[str]:
        """Bitta obyektni **o'z tarifi** muddati bo'yicha tozalaydi.

        Umumiy `purge()` hammaga bitta muddat qo'llaydi — 365 kun to'lagan
        mijozning arxivi 30 kunda o'chib ketardi.
        """
        cutoff = (_now() - timedelta(days=max(1, retention_days))).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT snapshot_key,clip_key FROM production_events "
                    "WHERE site_id=? AND occurred_at<? AND "
                    "(snapshot_key IS NOT NULL OR clip_key IS NOT NULL)"
                ),
                (site_id, cutoff),
            ).fetchall()
            conn.execute(
                self._sql("DELETE FROM production_events WHERE site_id=? AND occurred_at<?"),
                (site_id, cutoff),
            )
        return [str(key) for row in rows for key in (row["snapshot_key"], row["clip_key"]) if key]


def event_store_from_env(base_dir: Path) -> EventStore:
    return EventStore(
        os.environ.get("DATABASE_URL", ""),
        sqlite_path=base_dir / "data" / "cloud" / "events.db",
    )
