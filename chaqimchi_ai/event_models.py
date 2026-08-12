"""Edge va cloud orasidagi barqaror event kontrakti."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

from chaqimchi_ai import __version__

EventType = Literal[
    # ── V1 ────────────────────────────────────────────────────────────────
    "person_detected",
    "employee_seen",
    "zone_entered",
    "loitering",
    "occupancy_exceeded",
    # ── Retail (Chaqimchi Retail AI) ──────────────────────────────────────
    #: Kirish/chiqish chizig'i kesildi.  `direction` bilan birga keladi —
    #: mijozlar oqimi va konversiya hisobining asosi.
    "line_crossed",
    #: Mijoz zonada belgilangan vaqtdan uzoq turdi (`dwell_sec`).
    "dwell_exceeded",
    #: Navbatdagi odam soni chegaradan oshdi (`queue_length`).
    "queue_threshold_exceeded",
    #: Ish vaqtidan tashqari harakat.
    "after_hours_presence",
    #: Kamera yopildi, burildi yoki ko'rinishi buzildi.
    "camera_tampered",
]
Severity = Literal["info", "warning", "critical"]

#: Kirish/chiqish yo'nalishi.  Chiziq normalidan qaysi tomonga o'tilgani.
Direction = Literal["in", "out"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EdgeEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType
    severity: Severity = "info"
    camera_id: str
    occurred_at: str = Field(default_factory=utc_now_iso)
    ended_at: Optional[str] = None
    track_id: Optional[int] = None
    person_id: Optional[str] = None
    person_name: Optional[str] = None
    score: Optional[float] = None
    zone: Optional[str] = None
    occupancy: Optional[int] = None
    # ── Retail maydonlari ─────────────────────────────────────────────────
    #
    # Bular `metadata` ichida ham turishi mumkin edi, lekin KPI hisoboti
    # aynan shular bo'yicha guruhlaydi (kuniga nechta kirish, o'rtacha navbat).
    # JSON ichidan qidirish esa indekssiz va sekin bo'lardi.
    #: `line_crossed` uchun: qaysi tomonga o'tildi.
    direction: Optional[Direction] = None
    #: Kesilgan chiziq yoki tegishli zona nomi.
    line: Optional[str] = None
    #: `dwell_exceeded` uchun: zonada necha soniya turgani.
    dwell_sec: Optional[float] = None
    #: `queue_threshold_exceeded` uchun: navbatdagi odam soni.
    queue_length: Optional[int] = None
    snapshot_path: Optional[str] = None
    has_snapshot: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    edge_version: str = __version__
    model_version: Optional[str] = None

    def cloud_payload(self) -> Dict[str, Any]:
        data = self.model_dump(exclude={"snapshot_path"})
        data["has_snapshot"] = bool(self.snapshot_path or self.has_snapshot)
        return data
