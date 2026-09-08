"""Litsenziya holati (edge va cloud)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class LicenseState:
    site_id: str
    plan: str
    status: str  # active | grace | expired | suspended
    subscription_until: str
    max_cameras: int
    max_persons: int
    retention_days: int
    telegram_allowed: bool
    message: str = ""

    @property
    def is_operational(self) -> bool:
        return self.status in ("active", "grace")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "plan": self.plan,
            "status": self.status,
            "subscription_until": self.subscription_until,
            "max_cameras": self.max_cameras,
            "max_persons": self.max_persons,
            "retention_days": self.retention_days,
            "telegram_allowed": self.telegram_allowed,
            "operational": self.is_operational,
            "message": self.message,
        }
