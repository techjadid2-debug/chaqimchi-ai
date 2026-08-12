"""Sotqin uchun RTSP inventar va stream qabul testi.

Bu modul lokal AI qilmaydi. U cloud yuborgan RTSP substreamlarning texnik
yaroqliligini `ffprobe` bilan tekshiradi va keyingi frame/clip worker uchun
xavfsiz, secretsiz health natijasini beradi.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from chaqimchi_ai.sotqin_profile import MAX_CAMERAS


@dataclass(frozen=True)
class StreamProbe:
    camera_id: str
    status: str
    error: Optional[str] = None
    codec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None

    def payload(self) -> Dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "status": self.status,
            "error": self.error,
            "codec": self.codec,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
        }


def _fps(value: str) -> Optional[float]:
    try:
        numerator, denominator = value.split("/", 1)
        result = float(numerator) / float(denominator)
        return round(result, 3) if result > 0 else None
    except (AttributeError, ValueError, ZeroDivisionError):
        return None


def validate_cameras(raw_cameras: object) -> List[Dict[str, Any]]:
    """Cloud config'idan faqat R1 ko'tara oladigan streamlar o'tadi."""
    if not isinstance(raw_cameras, list):
        raise ValueError("Kameralar ro'yxat ko'rinishida bo'lishi kerak")
    if len(raw_cameras) > MAX_CAMERAS:
        raise ValueError(f"Sotqin R1 ko'pi bilan {MAX_CAMERAS} ta kamera qabul qiladi")
    ids: set[str] = set()
    cameras: List[Dict[str, Any]] = []
    for item in raw_cameras:
        if not isinstance(item, Mapping):
            raise ValueError("Kamera config'i noto'g'ri")
        camera_id = str(item.get("camera_id") or "")
        source = str(item.get("source") or "").strip()
        if not camera_id or camera_id in ids:
            raise ValueError("Kamera ID takrorlangan yoki bo'sh")
        if not source.startswith(("rtsp://", "rtsps://")):
            raise ValueError(f"{camera_id} uchun RTSP manzili noto'g'ri")
        ids.add(camera_id)
        cameras.append(
            {
                "camera_id": camera_id,
                "label": str(item.get("label") or camera_id)[:120],
                "source": source,
                "enabled": bool(item.get("enabled", True)),
            }
        )
    return cameras


class SotqinMediaRuntime:
    """Sotqinning media qismi uchun state va qabul testi.

    `runner` inject qilinishi testlarni ffprobe binary yoki kamera talab
    qilmasdan o'tkazadi. Probe xabarlari ichida RTSP URL yoki parol bo'lmaydi.
    """

    def __init__(
        self,
        *,
        ffprobe_binary: str = "ffprobe",
        timeout_sec: int = 12,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.ffprobe_binary = ffprobe_binary
        self.timeout_sec = timeout_sec
        self.runner = runner
        self.cameras: List[Dict[str, Any]] = []
        self.probes: Dict[str, StreamProbe] = {}

    def apply_config(self, payload: Mapping[str, Any]) -> None:
        self.cameras = validate_cameras(payload.get("cameras", []))
        active = {camera["camera_id"] for camera in self.cameras if camera["enabled"]}
        self.probes = {camera_id: probe for camera_id, probe in self.probes.items() if camera_id in active}

    def probe_camera(self, camera: Mapping[str, Any]) -> StreamProbe:
        camera_id = str(camera["camera_id"])
        source = str(camera["source"])
        command = [
            self.ffprobe_binary,
            "-v",
            "error",
            "-rtsp_transport",
            "tcp",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,avg_frame_rate",
            "-of",
            "json",
            source,
        ]
        try:
            completed = self.runner(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                check=False,
            )
            if completed.returncode != 0:
                return StreamProbe(camera_id, "offline", error="RTSP stream ochilmadi")
            data = json.loads(completed.stdout or "{}")
            streams = data.get("streams") or []
            if not streams:
                return StreamProbe(camera_id, "offline", error="Video stream topilmadi")
            stream = streams[0]
            return StreamProbe(
                camera_id,
                "online",
                codec=str(stream.get("codec_name") or "") or None,
                width=int(stream["width"]) if stream.get("width") else None,
                height=int(stream["height"]) if stream.get("height") else None,
                fps=_fps(str(stream.get("avg_frame_rate") or "")),
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return StreamProbe(camera_id, "offline", error="ffprobe yoki RTSP timeout")
        except (json.JSONDecodeError, TypeError, ValueError):
            return StreamProbe(camera_id, "offline", error="RTSP probe javobi noto'g'ri")

    def probe_all(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for camera in self.cameras:
            if not camera["enabled"]:
                continue
            result = self.probe_camera(camera)
            self.probes[result.camera_id] = result
            results.append(result.payload())
        return results

    def health(self) -> Dict[str, int]:
        enabled = [camera for camera in self.cameras if camera["enabled"]]
        online = sum(
            1
            for camera in enabled
            if self.probes.get(camera["camera_id"], StreamProbe("", "pending")).status == "online"
        )
        return {"configured": len(enabled), "online": online}

    def probe_payloads(self) -> Iterable[Dict[str, Any]]:
        return (probe.payload() for probe in self.probes.values())
