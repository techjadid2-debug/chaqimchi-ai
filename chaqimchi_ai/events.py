import json
import sqlite3
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from chaqimchi_ai.event_models import EdgeEvent


class EventLog:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Voqealar jadvali
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id TEXT,
                person_name TEXT,
                camera_id TEXT,
                score REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                image_path TEXT
            )
        ''')

        self._migrate(conn)
        conn.commit()
        conn.close()

    def _migrate(self, conn: sqlite3.Connection) -> None:
        cursor = conn.cursor()
        cols = {row[1] for row in cursor.execute("PRAGMA table_info(events)")}
        if "track_id" not in cols:
            cursor.execute("ALTER TABLE events ADD COLUMN track_id INTEGER")
        additions = {
            "event_uuid": "TEXT",
            "event_type": "TEXT NOT NULL DEFAULT 'employee_seen'",
            "severity": "TEXT NOT NULL DEFAULT 'info'",
            "ended_at": "TEXT",
            "zone": "TEXT",
            "occupancy": "INTEGER",
            "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        for name, definition in additions.items():
            if name not in cols:
                cursor.execute(f"ALTER TABLE events ADD COLUMN {name} {definition}")
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_uuid ON events(event_uuid)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_type_time ON events(event_type,timestamp)"
        )

    def log_event(
        self,
        person_id: str,
        person_name: str,
        camera_id: str,
        score: float,
        image_path: Optional[str] = None,
        track_id: Optional[int] = None,
    ) -> str:
        event_uuid = str(uuid.uuid4())
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO events (event_uuid,event_type,severity,person_id,person_name,
                                camera_id,score,image_path,track_id)
            VALUES (?,'employee_seen','info',?,?,?,?,?,?)
        ''', (event_uuid, person_id, person_name, camera_id, score, image_path, track_id))
        conn.commit()
        conn.close()
        return event_uuid

    def log_edge_event(self, event: "EdgeEvent") -> str:
        from chaqimchi_ai.event_models import EdgeEvent

        if not isinstance(event, EdgeEvent):
            raise TypeError("event EdgeEvent bo'lishi kerak")
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO events (
                    event_uuid,event_type,severity,person_id,person_name,camera_id,score,
                    timestamp,ended_at,image_path,track_id,zone,occupancy,metadata_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    event.event_id,
                    event.event_type,
                    event.severity,
                    event.person_id,
                    event.person_name,
                    event.camera_id,
                    event.score,
                    event.occurred_at,
                    event.ended_at,
                    event.snapshot_path,
                    event.track_id,
                    event.zone,
                    event.occupancy,
                    json.dumps(event.metadata, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return event.event_id

    def purge_older_than(self, days: int) -> tuple[int, List[str]]:
        """`days` kundan eski voqealarni o‘chiradi.

        Tarifdagi "voqea arxivi 30/90/365 kun" va’dasi shu yerda bajariladi.
        Qaytaradi: (o‘chirilgan qatorlar soni, ular ishora qilgan rasm yo‘llari).
        Rasmlarni o‘chirish chaqiruvchining zimmasida — `retention.py` ga qarang.

        `days <= 0` — hech narsa o‘chirilmaydi (arxiv cheksiz).
        """
        if days <= 0:
            return 0, []

        cutoff = f"-{int(days)} days"
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT image_path FROM events "
                "WHERE timestamp < datetime('now', ?) AND image_path IS NOT NULL",
                (cutoff,),
            )
            paths = [row[0] for row in cursor.fetchall() if row[0]]
            cursor.execute("DELETE FROM events WHERE timestamp < datetime('now', ?)", (cutoff,))
            deleted = cursor.rowcount
            conn.commit()
        finally:
            conn.close()
        return deleted, paths

    def count_all(self) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        finally:
            conn.close()

    def oldest_timestamp(self) -> Optional[str]:
        """Arxivdagi eng eski voqea vaqti (UTC) yoki bo‘sh bo‘lsa None."""
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute("SELECT MIN(timestamp) FROM events").fetchone()
        finally:
            conn.close()
        return row[0] if row and row[0] else None

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM events ORDER BY timestamp DESC LIMIT ?', (limit,))
        rows = cursor.fetchall()
        conn.close()
        output: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            raw_meta = item.pop("metadata_json", None)
            try:
                item["metadata"] = json.loads(raw_meta or "{}")
            except (TypeError, json.JSONDecodeError):
                item["metadata"] = {}
            output.append(item)
        return output

    def get_stats_today(self) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Bugungi noyob shaxslar soni
        cursor.execute("SELECT COUNT(DISTINCT person_id) FROM events WHERE date(timestamp) = date('now')")
        unique_today = cursor.fetchone()[0]

        # Jami aniqlashlar soni
        cursor.execute("SELECT COUNT(*) FROM events WHERE date(timestamp) = date('now')")
        total_today = cursor.fetchone()[0]

        conn.close()
        return {
            "unique_today": unique_today,
            "total_today": total_today
        }
