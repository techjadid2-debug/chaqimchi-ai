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
    # ── Kamera sog'ligi ───────────────────────────────────────────────────
    #
    # Bulargacha kamera holati faqat `runner.stats()` ichida yashardi va
    # hech qachon hodisaga aylanmasdi: kamera o'chsa do'kon egasi buni
    # hisobotdagi bo'shliqdan, ya'ni bir necha kundan keyin bilardi.
    #: Kamera ketma-ket bir necha marta ulanmadi (kabel, quvvat, NVR).
    "camera_offline",
    #: Uzilishdan keyin qayta ulandi.  `metadata.downtime_sec` bilan keladi.
    "camera_recovered",
    #: Oqim ochiq, lekin kadr o'zgarmayapti — dekoder yoki NVR qotib qolgan.
    #: Bu eng xavflisi: harakat yo'q degani filtr uni to'sadi va buzilish
    #: tekshiruvi ham "normal" deydi, ya'ni tizim sog'lom ko'rinadi.
    "stream_frozen",
    #: Ko'rish agenti kadrni ko'rib bergan xulosa.  Boshqa hodisadan **keyin**
    #: tug'iladi (`metadata.source_event_type`) va uni odam tilida
    #: tushuntiradi: "kassa oldida ikki kishi janjallashmoqda".
    "ai_review",
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
    clip_path: Optional[str] = None
    has_clip: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    edge_version: str = __version__
    model_version: Optional[str] = None

    def cloud_payload(self) -> Dict[str, Any]:
        # Qurilmaning haqiqiy fayl yo'llari cloudga chiqmaydi. Media alohida
        # autentifikatsiyalangan endpointga yuklanadi.
        data = self.model_dump(exclude={"snapshot_path", "clip_path"})
        data["has_snapshot"] = bool(self.snapshot_path or self.has_snapshot)
        data["has_clip"] = bool(self.clip_path or self.has_clip)
        return data
