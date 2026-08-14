"""Internet uzilganda event va snapshotlarni diskda ishonchli navbatlash."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from chaqimchi_ai.event_models import EdgeEvent


class EventOutbox:
    def __init__(self, db_path: Path, *, max_bytes: int, retention_days: int = 7) -> None:
        self.db_path = Path(db_path)
        self.max_bytes = int(max_bytes)
        self.retention_days = int(retention_days)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbox (
                    event_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    snapshot_path TEXT,
                    snapshot_size INTEGER NOT NULL DEFAULT 0,
                    clip_path TEXT,
                    clip_size INTEGER NOT NULL DEFAULT 0,
                    priority INTEGER NOT NULL DEFAULT 10,
                    created_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT
                )
                """
            )
            columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(outbox)").fetchall()
            }
            if "priority" not in columns:
                conn.execute("ALTER TABLE outbox ADD COLUMN priority INTEGER NOT NULL DEFAULT 10")
            if "clip_path" not in columns:
                conn.execute("ALTER TABLE outbox ADD COLUMN clip_path TEXT")
            if "clip_size" not in columns:
                conn.execute(
                    "ALTER TABLE outbox ADD COLUMN clip_size INTEGER NOT NULL DEFAULT 0"
                )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def enqueue(self, event: EdgeEvent) -> None:
        snapshot_size = 0
        if event.snapshot_path:
            path = Path(event.snapshot_path)
            if path.is_file():
                snapshot_size = path.stat().st_size
        clip_size = 0
        if event.clip_path:
            path = Path(event.clip_path)
            if path.is_file():
                clip_size = path.stat().st_size
        payload = json.dumps(event.cloud_payload(), ensure_ascii=False, separators=(",", ":"))
        # Internet uzilganda 8/128 disk avval analytics batch emas, xavfsizlik
        # ogohlantirishlarini saqlashi kerak. Critical > warning > normal.
        priority = {"critical": 30, "warning": 20}.get(event.severity, 10)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO outbox "
                "(event_id,payload,snapshot_path,snapshot_size,clip_path,clip_size,"
                "priority,created_at) VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(event_id) DO UPDATE SET "
                "payload=excluded.payload,"
                "snapshot_path=COALESCE(excluded.snapshot_path,outbox.snapshot_path),"
                "snapshot_size=MAX(excluded.snapshot_size,outbox.snapshot_size),"
                "clip_path=COALESCE(excluded.clip_path,outbox.clip_path),"
                "clip_size=MAX(excluded.clip_size,outbox.clip_size),"
                "priority=MAX(excluded.priority,outbox.priority)",
                (
                    event.event_id,
                    payload,
                    event.snapshot_path,
                    snapshot_size,
                    event.clip_path,
                    clip_size,
                    priority,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        self.prune()

    def pending(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM outbox ORDER BY priority DESC,created_at,event_id LIMIT ?", (int(limit),)
            ).fetchall()
        return [
            {
                **dict(row),
                "payload": json.loads(row["payload"]),
            }
            for row in rows
        ]

    def acknowledge(self, event_ids: List[str]) -> int:
        if not event_ids:
            return 0
        placeholders = ",".join("?" for _ in event_ids)
        with self._connect() as conn:
            cursor = conn.execute(
                f"DELETE FROM outbox WHERE event_id IN ({placeholders})", tuple(event_ids)
            )
            return int(cursor.rowcount)

    def fail(self, event_id: str, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE outbox SET attempts=attempts+1,last_error=? WHERE event_id=?",
                (error[:1000], event_id),
            )

    def stats(self) -> Dict[str, int]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count,"
                "COALESCE(SUM(snapshot_size+clip_size+length(payload)),0) AS bytes "
                "FROM outbox"
            ).fetchone()
        return {"pending": int(row["count"]), "bytes": int(row["bytes"])}

    def prune(self) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat()
        removed = 0
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM outbox WHERE created_at < ?", (cutoff,))
            removed += int(cursor.rowcount)
            total = int(
                conn.execute(
                    "SELECT COALESCE(SUM(snapshot_size+clip_size+length(payload)),0) "
                    "FROM outbox"
                ).fetchone()[0]
            )
            if total > self.max_bytes:
                rows = conn.execute(
                    "SELECT event_id,snapshot_size+clip_size+length(payload) AS size "
                    "FROM outbox "
                    "ORDER BY priority ASC,created_at,event_id"
                ).fetchall()
                for row in rows:
                    if total <= self.max_bytes:
                        break
                    conn.execute("DELETE FROM outbox WHERE event_id=?", (row["event_id"],))
                    total -= int(row["size"])
                    removed += 1
        return removed

    def snapshot_path(self, event_id: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT snapshot_path FROM outbox WHERE event_id=?", (event_id,)
            ).fetchone()
        return str(row[0]) if row and row[0] else None

    def clip_path(self, event_id: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT clip_path FROM outbox WHERE event_id=?", (event_id,)
            ).fetchone()
        return str(row[0]) if row and row[0] else None
