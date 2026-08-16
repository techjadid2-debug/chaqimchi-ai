"""Production event/owner store: PostgreSQL, testda SQLite."""

from __future__ import annotations

import hashlib
import hmac
import json
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
            "CREATE INDEX IF NOT EXISTS idx_prod_events_site_time "
            "ON production_events(site_id,occurred_at)",
            "CREATE INDEX IF NOT EXISTS idx_owner_members_telegram "
            "ON owner_members(telegram_id,active)",
            "CREATE INDEX IF NOT EXISTS idx_owner_login_links_hash "
            "ON owner_login_links(token_hash,revoked)",
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

    @staticmethod
    def _dict(row: Any) -> Dict[str, Any]:
        return dict(row)

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
                        event.occurred_at,
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

        for row in rows:
            kind = row["event_type"]
            local = self._to_local(row["occurred_at"], timezone_tashkent)
            if kind == "line_crossed":
                if row.get("direction") == "in":
                    entered += 1
                    hourly[local.hour]["entered"] += 1
                elif row.get("direction") == "out":
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
        }

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

        Faqat `occurred_at` o'qiladi: 30 kunlik oraliqda bu o'n minglab
        qatorni to'liq yuklashdan ancha yengil.  Kunga bo'lish Python'da,
        chunki vaqt mintaqasi bo'yicha guruhlash SQLite va PostgreSQL'da
        har xil yoziladi.
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
                    "SELECT occurred_at FROM production_events WHERE site_id=? "
                    "AND occurred_at>=? AND occurred_at<? AND event_type='line_crossed' "
                    "AND direction='in'"
                ),
                (site_id, start_utc.isoformat(), end_utc.isoformat()),
            ).fetchall()
        counts: Dict[date, int] = {}
        for row in rows:
            day = self._to_local(dict(row)["occurred_at"], zone).date()
            counts[day] = counts.get(day, 0) + 1
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
        start_local = datetime.combine(day, datetime.min.time(), tzinfo=zone)
        start = start_local.astimezone(timezone.utc).isoformat()
        end = (start_local + timedelta(days=1)).astimezone(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                self._sql(
                    "SELECT COUNT(*) AS count FROM production_events WHERE site_id=? "
                    "AND occurred_at>=? AND occurred_at<? AND event_type='line_crossed' "
                    "AND direction='in'"
                ),
                (site_id, start, end),
            ).fetchone()
        return int(dict(row)["count"]) if row else 0

    @staticmethod
    def _to_local(occurred_at: str, zone: ZoneInfo) -> datetime:
        moment = datetime.fromisoformat(str(occurred_at))
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
                created_day = self._to_local(str(employee["created_at"]), zone).date()
                deactivated_day = (
                    self._to_local(str(employee["deactivated_at"]), zone).date()
                    if employee.get("deactivated_at")
                    else None
                )
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
            if row.get("person_id"):
                grouped.setdefault(str(row["person_id"]), []).append(
                    (
                        self._to_local(str(row["occurred_at"]), zone),
                        str(row["camera_id"]),
                    )
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
                    "SELECT id,site_id,telegram_id,role,display_name,active,created_at "
                    "FROM owner_members WHERE site_id=? AND active=1 ORDER BY created_at"
                ),
                (site_id,),
            ).fetchall()
        return [self._dict(row) for row in rows]

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
