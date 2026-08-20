"""Sotqin uchun RTSP inventar, stream qabul testi va bitta kadr rasmi.

Bu modul lokal AI qilmaydi. U cloud yuborgan RTSP substreamlarning texnik
yaroqliligini `ffprobe` bilan tekshiradi va keyingi frame/clip worker uchun
xavfsiz, secretsiz health natijasini beradi.

Bundan tashqari o'rnatuvchi uchun **bitta kadr rasmi** oladi. Sababi: hozir
o'rnatuvchi kamerani ko'rmaydi — `ffprobe` unga faqat "h264 640x360 15fps"
deb aytadi. Kamera to'g'ri joyga qaratilganini, linza tozaligini yoki
umuman qaysi kamera ekanini bilishning yagona yo'li — rasmni ko'rish.
O'sha rasm ayni paytda chiziq va zona chizish uchun ham asos bo'ladi.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from chaqimchi_ai.sotqin_profile import MAX_CAMERAS

#: Preview rasm eni (balandlik nisbat bo'yicha). 640 px — brauzerda chiziq
#: chizish uchun yetarli va bitta kadr ~50-80 KB bo'ladi.
PREVIEW_WIDTH = 640

#: JPEG sifati (ffmpeg `-q:v`, 2 eng yaxshi ... 31 eng yomon).
PREVIEW_QUALITY = 6

#: Cloud tomon ham shu chegarani qo'yadi; undan kattasi yuborilmaydi.
PREVIEW_MAX_BYTES = 2 * 1024 * 1024


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
        ffmpeg_binary: str = "ffmpeg",
        timeout_sec: int = 12,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.ffprobe_binary = ffprobe_binary
        self.ffmpeg_binary = ffmpeg_binary
        self.timeout_sec = timeout_sec
        self.runner = runner
        self.cameras: List[Dict[str, Any]] = []
        self.probes: Dict[str, StreamProbe] = {}

    def camera(self, camera_id: str) -> Optional[Dict[str, Any]]:
        for item in self.cameras:
            if item["camera_id"] == camera_id:
                return item
        return None

    def apply_config(self, payload: Mapping[str, Any]) -> None:
        self.cameras = validate_cameras(payload.get("cameras", []))
        active = {camera["camera_id"] for camera in self.cameras if camera["enabled"]}
        self.probes = {
            camera_id: probe for camera_id, probe in self.probes.items() if camera_id in active
        }

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

    def grab_preview(self, camera: Mapping[str, Any]) -> Optional[bytes]:
        """Kameradan bitta kadr — JPEG bayt.  Olinmasa `None`.

        Xato holatida `None` qaytariladi va sabab log'ga ham chiqmaydi:
        chiqishda RTSP manzili bo'lishi mumkin, u esa parol bilan keladi.
        Nima bo'lganini o'rnatuvchi `probe_camera()` natijasidan biladi.
        """
        source = str(camera["source"])
        command = [
            self.ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-rtsp_transport",
            "tcp",
            "-i",
            source,
            "-frames:v",
            "1",
            "-vf",
            f"scale={PREVIEW_WIDTH}:-2",
            "-q:v",
            str(PREVIEW_QUALITY),
            "-f",
            "image2",
            "-",
        ]
        try:
            completed = self.runner(
                command,
                capture_output=True,
                timeout=self.timeout_sec,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None
        if completed.returncode != 0:
            return None
        data = completed.stdout
        if not isinstance(data, (bytes, bytearray)):
            return None
        data = bytes(data)
        # JPEG SOI markeri — ffmpeg xato matnini stdout'ga yozib qo'ymaganiga
        # ishonch hosil qilamiz.
        if not data.startswith(b"\xff\xd8") or len(data) > PREVIEW_MAX_BYTES:
            return None
        return data

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
