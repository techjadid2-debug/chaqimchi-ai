"""Internet uzilganda event va snapshotlarni diskda ishonchli navbatlash.

Ikkita narsa ataylab shunday:

1. **Rad etilgan hodisa navbatni to'smaydi.**  `attempts` ilgari yozilardi,
   lekin uni hech kim o'qimasdi: cloud biror hodisani doimiy rad etsa
   (masalan, eski sxema yoki buzuq maydon), u har 5 soniyada qayta
   yuborilar va batch o'rnini egallab turar edi.  Uning ortidagi yaxshi
   hodisalar esa kutib qolardi.  Endi har muvaffaqiyatsizlikdan keyin
   `next_attempt_at` eksponensial ortadi.
2. **Umidsiz hodisa tashlanadi, lekin yo'qolmaydi.**  20 urinishdan keyin
   yozuv `dead_letter` jadvaliga ko'chadi: navbatdan chiqadi, lekin
   diagnostika uchun qoladi va `stats()` da ko'rinadi.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from chaqimchi_ai.event_models import EdgeEvent

#: Qayta urinishlar orasidagi eng uzun kutish.  Cloud yangilanishi yoki
#: tarmoq tiklanishi odatda undan tez bo'ladi, shuning uchun 5 daqiqadan
#: uzun kutish faqat kechikish qo'shadi.
MAX_RETRY_DELAY_SEC = 300.0

#: Boshlang'ich kutish; keyingi urinishlarda ikkilanadi (5, 10, 20 …).
BASE_RETRY_DELAY_SEC = 5.0

#: Shuncha urinishdan keyin hodisa umidsiz deb hisoblanadi.  20 urinish
#: eksponensial kutish bilan ~3 soatga cho'ziladi — vaqtinchalik cloud
#: nosozligi shu vaqt ichida albatta tuzaladi.
MAX_ATTEMPTS = 20

#: Cloudga yuborilgan yozuv shuncha kun bazada qoladi.  U faqat do'kon
#: kompyuteridagi panelning **bugungi** hisoboti uchun kerak, shuning
#: uchun ikki kun yetarli — kechagi kun bilan taqqoslash ham sig'adi.
SENT_KEEP_DAYS = 2


def retry_delay(attempts: int) -> float:
    """Necha soniyadan keyin qayta urinamiz.

    Formula `cloud/store.py` dagi bilan bir xil oiladan: eksponensial,
    shiftga tegib to'xtaydi.
    """
    exponent = min(max(attempts, 1) - 1, 6)
    return min(MAX_RETRY_DELAY_SEC, BASE_RETRY_DELAY_SEC * (2**exponent))


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
                    last_error TEXT,
                    -- Shu vaqtdan oldin qayta urinilmaydi.  `NULL` — hali
                    -- urinilmagan, ya'ni darhol yuboriladi.
                    next_attempt_at TEXT,
                    -- Cloud qabul qilgan vaqt.  `NULL` — hali yuborilmagan.
                    -- Yozuv o'chirilmasligining sababi: do'kon kompyuteridagi
                    -- panel kunlik hisobotni shu bazadan o'qiydi.
                    sent_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dead_letter (
                    event_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    failed_at TEXT NOT NULL
                )
                """
            )
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(outbox)").fetchall()}
            if "priority" not in columns:
                conn.execute("ALTER TABLE outbox ADD COLUMN priority INTEGER NOT NULL DEFAULT 10")
            if "clip_path" not in columns:
                conn.execute("ALTER TABLE outbox ADD COLUMN clip_path TEXT")
            if "clip_size" not in columns:
                conn.execute("ALTER TABLE outbox ADD COLUMN clip_size INTEGER NOT NULL DEFAULT 0")
            if "next_attempt_at" not in columns:
                conn.execute("ALTER TABLE outbox ADD COLUMN next_attempt_at TEXT")
            if "sent_at" not in columns:
                conn.execute("ALTER TABLE outbox ADD COLUMN sent_at TEXT")

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
                "priority=MAX(excluded.priority,outbox.priority),"
                # Payload o'zgardi (masalan klip tayyor bo'ldi) — bu yangi
                # imkoniyat, shuning uchun backoff nolga tushadi.  `attempts`
                # esa saqlanadi: umidsiz hodisa cheksiz qayta urinmasin.
                "next_attempt_at=NULL,"
                # Allaqachon yuborilgan bo'lsa ham qaytadan navbatga tushadi:
                # klip aynan hodisadan keyin tayyor bo'ladi.
                "sent_at=NULL",
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

    def pending(self, limit: int = 50, *, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Yuborishga tayyor yozuvlar.

        Backoff kutayotganlari chiqarilmaydi — aynan shu narsa rad etilgan
        hodisaning batch o'rnini egallab turishini to'xtatadi.
        """
        moment = (now or datetime.now(timezone.utc)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM outbox WHERE sent_at IS NULL "
                "AND (next_attempt_at IS NULL OR next_attempt_at <= ?) "
                "ORDER BY priority DESC,created_at,event_id LIMIT ?",
                (moment, int(limit)),
            ).fetchall()
        return [
            {
                **dict(row),
                "payload": json.loads(row["payload"]),
            }
            for row in rows
        ]

    def acknowledge(self, event_ids: List[str]) -> int:
        """Cloud qabul qildi — navbatdan chiqadi, lekin bazada qoladi.

        Ilgari yozuv darhol o'chirilardi.  Do'kon kompyuteridagi panel esa
        kunlik hisobotni aynan shu bazadan o'qiydi: internet ishlab tursa
        navbat har besh soniyada bo'shar va panelning "Bugun kirdi" raqami
        kun bo'yi nolga yaqin turardi.  Yozuvlar `prune()` bilan
        `SENT_KEEP_DAYS` dan keyin tozalanadi.
        """
        if not event_ids:
            return 0
        placeholders = ",".join("?" for _ in event_ids)
        moment = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE outbox SET sent_at=? WHERE event_id IN ({placeholders}) "
                "AND sent_at IS NULL",
                (moment, *event_ids),
            )
            return int(cursor.rowcount)

    def fail(self, event_id: str, error: str, *, now: Optional[datetime] = None) -> None:
        """Urinish muvaffaqiyatsiz — keyingisini kechiktiradi.

        `MAX_ATTEMPTS` dan oshsa yozuv `dead_letter` ga ko'chadi: navbatdan
        chiqadi (boshqalarni to'smasin), lekin diagnostika uchun qoladi.
        """
        moment = now or datetime.now(timezone.utc)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT attempts,payload,created_at FROM outbox WHERE event_id=?", (event_id,)
            ).fetchone()
            if row is None:
                return
            attempts = int(row["attempts"]) + 1
            if attempts >= MAX_ATTEMPTS:
                conn.execute(
                    "INSERT OR REPLACE INTO dead_letter"
                    "(event_id,payload,attempts,last_error,created_at,failed_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (
                        event_id,
                        row["payload"],
                        attempts,
                        error[:1000],
                        row["created_at"],
                        moment.isoformat(),
                    ),
                )
                conn.execute("DELETE FROM outbox WHERE event_id=?", (event_id,))
                return
            retry_at = moment + timedelta(seconds=retry_delay(attempts))
            conn.execute(
                "UPDATE outbox SET attempts=?,last_error=?,next_attempt_at=? WHERE event_id=?",
                (attempts, error[:1000], retry_at.isoformat(), event_id),
            )

    def stats(self, *, now: Optional[datetime] = None) -> Dict[str, int]:
        moment = (now or datetime.now(timezone.utc)).isoformat()
        with self._connect() as conn:
            # Faqat yuborilmaganlar: bu sonlar "navbat qanchalik uzun"
            # degan savolga javob beradi va heartbeat orqali cloudga
            # ketadi.  Yuborilgan yozuvlar navbat emas — ular panelning
            # bugungi hisoboti uchun qolgan nusxa.
            row = conn.execute(
                "SELECT COUNT(*) AS count,"
                "COALESCE(SUM(snapshot_size+clip_size+length(payload)),0) AS bytes,"
                "COALESCE(SUM(next_attempt_at IS NOT NULL AND next_attempt_at > ?),0) AS waiting "
                "FROM outbox WHERE sent_at IS NULL",
                (moment,),
            ).fetchone()
            poisoned = int(conn.execute("SELECT COUNT(*) FROM dead_letter").fetchone()[0])
        return {
            "pending": int(row["count"]),
            "bytes": int(row["bytes"]),
            # Backoff kutayotganlar: bu son o'sib borsa cloud hodisalarni
            # rad etyapti, tarmoq esa joyida.
            "waiting": int(row["waiting"]),
            # Umidsiz deb tashlanganlar — heartbeat orqali cloudga ko'rinadi.
            "poisoned": poisoned,
        }

    def dead_letters(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Tashlangan hodisalar — nima uchun rad etilganini ko'rish uchun."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM dead_letter ORDER BY failed_at DESC LIMIT ?", (int(limit),)
            ).fetchall()
        return [dict(row) for row in rows]

    def prune(self) -> int:
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=self.retention_days)).isoformat()
        sent_cutoff = (now - timedelta(days=SENT_KEEP_DAYS)).isoformat()
        removed = 0
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM outbox WHERE created_at < ?", (cutoff,))
            removed += int(cursor.rowcount)
            # Yuborilgani cloudda saqlangan — bu yerda faqat panelning
            # bugungi hisoboti uchun turadi, ya'ni tez tozalanadi.
            cursor = conn.execute("DELETE FROM outbox WHERE sent_at < ?", (sent_cutoff,))
            removed += int(cursor.rowcount)
            # Tashlangan hodisalar ham abadiy saqlanmaydi — ular diagnostika
            # uchun, arxiv uchun emas.
            conn.execute("DELETE FROM dead_letter WHERE failed_at < ?", (cutoff,))
            total = int(
                conn.execute(
                    "SELECT COALESCE(SUM(snapshot_size+clip_size+length(payload)),0) "
                    "FROM outbox WHERE sent_at IS NULL"
                ).fetchone()[0]
            )
            if total > self.max_bytes:
                # Disk to'ldi.  Avval yuborilganlar tashlanadi — ular
                # cloudda bor; yuborilmagani esa faqat shu yerda.
                conn.execute("DELETE FROM outbox WHERE sent_at IS NOT NULL")
                rows = conn.execute(
                    "SELECT event_id,snapshot_size+clip_size+length(payload) AS size "
                    "FROM outbox WHERE sent_at IS NULL "
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
