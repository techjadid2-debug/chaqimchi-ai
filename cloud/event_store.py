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
from typing import Any, Dict, Iterator, List, Optional
from zoneinfo import ZoneInfo

from chaqimchi_ai.event_models import EdgeEvent


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
            "CREATE INDEX IF NOT EXISTS idx_prod_events_site_time "
            "ON production_events(site_id,occurred_at)",
            "CREATE INDEX IF NOT EXISTS idx_owner_members_telegram "
            "ON owner_members(telegram_id,active)",
        ]
        with self._connect() as conn:
            for statement in statements:
                conn.execute(statement)

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
                metadata_json,edge_version,model_version,has_snapshot,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(event_id) DO NOTHING
            """
        )
        with self._connect() as conn:
            for event in events:
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
                        event.person_name,
                        event.score,
                        event.zone,
                        event.occupancy,
                        json.dumps(event.metadata, ensure_ascii=False, separators=(",", ":")),
                        event.edge_version,
                        event.model_version,
                        int(bool(event.snapshot_path or event.has_snapshot)),
                        _now().isoformat(),
                    ),
                )
                # Idempotent qayta yuborilgan event ham accepted hisoblanadi.
                accepted.append(event.event_id)
        return accepted

    def event(self, site_id: str, event_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                self._sql(
                    "SELECT * FROM production_events WHERE site_id=? AND event_id=?"
                ),
                (site_id, event_id),
            ).fetchone()
        return self._decode_event(row) if row else None

    def set_snapshot(self, site_id: str, event_id: str, key: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                self._sql(
                    "UPDATE production_events SET snapshot_key=?,has_snapshot=1 "
                    "WHERE site_id=? AND event_id=?"
                ),
                (key, site_id, event_id),
            )
            return bool(cursor.rowcount)

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
                self._sql(
                    "SELECT * FROM device_health WHERE site_id=? ORDER BY received_at DESC"
                ),
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
                    "occupancy_limit": 20,
                    "loitering_sec": 60,
                    "zones": [],
                },
                "updated_at": None,
            }
        return {
            "site_id": site_id,
            "revision": int(row["revision"]),
            "config": json.loads(row["config_json"]),
            "updated_at": row["updated_at"],
        }

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
                self._sql(
                    "UPDATE owner_otps SET used=1 WHERE telegram_id=? AND used=0"
                ),
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
            conn.execute(
                self._sql("UPDATE owner_otps SET used=1 WHERE id=?"), (row["id"],)
            )
            return True

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
                self._sql(
                    "SELECT 1 FROM daily_digests WHERE site_id=? AND digest_date=?"
                ),
                (site_id, digest_date),
            ).fetchone()
        return row is not None

    def purge(self, retention_days: int = 30) -> List[str]:
        cutoff = (_now() - timedelta(days=max(1, retention_days))).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                self._sql(
                    "SELECT snapshot_key FROM production_events "
                    "WHERE occurred_at<? AND snapshot_key IS NOT NULL"
                ),
                (cutoff,),
            ).fetchall()
            conn.execute(
                self._sql("DELETE FROM production_events WHERE occurred_at<?"), (cutoff,)
            )
        return [str(row["snapshot_key"]) for row in rows]


def event_store_from_env(base_dir: Path) -> EventStore:
    return EventStore(
        os.environ.get("DATABASE_URL", ""),
        sqlite_path=base_dir / "data" / "cloud" / "events.db",
    )
