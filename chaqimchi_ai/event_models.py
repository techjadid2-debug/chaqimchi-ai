"""Edge va cloud orasidagi barqaror event kontrakti."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

EventType = Literal[
    "person_detected",
    "employee_seen",
    "zone_entered",
    "loitering",
    "occupancy_exceeded",
]
Severity = Literal["info", "warning", "critical"]


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
    snapshot_path: Optional[str] = None
    has_snapshot: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    edge_version: str = "0.3.0"
    model_version: Optional[str] = None

    def cloud_payload(self) -> Dict[str, Any]:
        data = self.model_dump(exclude={"snapshot_path"})
        data["has_snapshot"] = bool(self.snapshot_path or self.has_snapshot)
        return data
