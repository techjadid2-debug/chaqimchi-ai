"""Edge → Cloud litsenziya klienti."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from chaqimchi_ai.licensing.models import LicenseState

logger = logging.getLogger(__name__)


def _parse_state(data: Dict[str, Any]) -> LicenseState:
    return LicenseState(
        site_id=str(data["site_id"]),
        plan=str(data["plan"]),
        status=str(data["status"]),
        subscription_until=str(data["subscription_until"]),
        max_cameras=int(data["max_cameras"]),
        max_persons=int(data["max_persons"]),
        retention_days=int(data["retention_days"]),
        telegram_allowed=bool(data.get("telegram_allowed", False)),
        message=str(data.get("message", "")),
    )


class EdgeLicenseClient:
    def __init__(
        self,
        cloud_url: str,
        site_id: str,
        device_token: str,
        cache_path: Path,
        offline_grace_days: int = 7,
    ) -> None:
        self.cloud_url = cloud_url.rstrip("/")
        self.site_id = site_id
        self.device_token = device_token
        self.cache_path = cache_path
        self.offline_grace_days = offline_grace_days

    def _headers(self) -> Dict[str, str]:
        return {
            "X-Site-Id": self.site_id,
            "X-Device-Token": self.device_token,
        }

    def load_cache(self) -> Optional[LicenseState]:
        if not self.cache_path.is_file():
            return None
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return _parse_state(raw)
        except Exception:
            return None

    def save_cache(self, state: LicenseState) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = state.to_dict()
        payload["cached_at"] = datetime.now(timezone.utc).isoformat()
        self.cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def claim_device(
        self,
        pairing_code: str,
        *,
        hardware_id: Optional[str] = None,
        label: str = "edge-1",
    ) -> Dict[str, str]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{self.cloud_url}/api/v1/devices/claim",
                json={
                    "pairing_code": pairing_code,
                    "hardware_id": hardware_id,
                    "label": label,
                },
            )
            r.raise_for_status()
            return r.json()

    async def heartbeat(
        self,
        *,
        active_cameras: int = 0,
        app_version: str = "0.2.0",
    ) -> LicenseState:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{self.cloud_url}/api/v1/license/heartbeat",
                headers=self._headers(),
                json={"active_cameras": active_cameras, "app_version": app_version},
            )
            r.raise_for_status()
            data = r.json()
            state = _parse_state(data)
            self.save_cache(state)
            return state

    async def refresh(self, *, active_cameras: int = 0) -> LicenseState:
        try:
            return await self.heartbeat(active_cameras=active_cameras)
        except Exception as e:
            logger.warning("Cloud heartbeat xato: %s", e)
            cached = self.load_cache()
            if cached and cached.is_operational:
                cached.message = f"Offline rejim (cache). {e}"
                return cached
            raise
