"""YAML konfiguratsiyasini yuklash (webapp va CLI uchun)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Literal, Optional, Tuple, Union

import yaml
from pydantic import BaseModel, Field, field_validator


class FaceSettings(BaseModel):
    model_name: str = "buffalo_l"
    det_size: Tuple[int, int] = (640, 640)
    preprocess_max_side: int = Field(default=1024, ge=64, le=4096)
    compare_threshold: float = Field(default=0.4, ge=0.0, le=1.0)

    @field_validator("det_size")
    @classmethod
    def _det(cls, v: Any) -> Tuple[int, int]:
        if isinstance(v, (list, tuple)) and len(v) == 2:
            return int(v[0]), int(v[1])
        raise ValueError("det_size [w,h] bo‘lishi kerak")


class PathsSettings(BaseModel):
    reference_image: str = "data/abdulvosit/reference_outdoor.png"
    db_path: str = "data/database"
    events_db: str = "data/events.db"
    snapshots_dir: str = "data/snapshots"
    calibration_dir: str = "data/calibration"
    audit_db: str = "data/audit.db"


class TrackingSettings(BaseModel):
    enabled: bool = True
    iou_threshold: float = Field(default=0.35, ge=0.05, le=0.95)
    max_missed_frames: int = Field(default=15, ge=1, le=300)


class JwtSettings(BaseModel):
    enabled: bool = False
    secret: Optional[str] = None
    algorithm: str = "HS256"
    expire_hours: int = Field(default=24, ge=1, le=720)


class SecuritySettings(BaseModel):
    api_key_enabled: bool = False
    api_key: Optional[str] = None
    jwt: JwtSettings = Field(default_factory=JwtSettings)


class StorageSettings(BaseModel):
    encrypt_embeddings: bool = False
    vector_backend: Literal["numpy", "faiss"] = "numpy"


class RoiSettings(BaseModel):
    enabled: bool = False
    normalized: bool = True
    x1: float = Field(default=0.0, ge=0.0, le=1.0)
    y1: float = Field(default=0.0, ge=0.0, le=1.0)
    x2: float = Field(default=1.0, ge=0.0, le=1.0)
    y2: float = Field(default=1.0, ge=0.0, le=1.0)


class AntispoofSettings(BaseModel):
    enabled: bool = False
    backend: Literal["heuristic", "onnx"] = "heuristic"
    #: ONNX modeli yo‘li (loyiha ildiziga nisbatan). Faqat backend=onnx uchun.
    model_path: Optional[str] = None
    #: Shu balldan past bo‘lsa — soxta deb hisoblanadi.
    min_score: float = Field(default=0.5, ge=0.0, le=1.0)
    #: Heuristika uchun eng kam o‘tkirlik (Laplacian dispersiyasi).
    min_blur_variance: float = Field(default=80.0, ge=0.0)
    #: ONNX chiqishida "tirik" sinf indeksi (MiniFASNet: 1).
    live_index: int = Field(default=1, ge=0)


class RateLimitSettings(BaseModel):
    enabled: bool = False
    requests_per_minute: int = Field(default=60, ge=1, le=10_000)


class CameraRuntimeSettings(BaseModel):
    frame_skip: int = Field(default=5, ge=1, le=60)


class EventsSettings(BaseModel):
    match_debounce_sec: int = Field(default=30, ge=0, le=3600)
    save_snapshots: bool = True
    #: Voqea arxivi necha kun saqlanadi. 0 — cheklanmagan (faqat tarif
    #: cheklaydi). Litsenziya ham muddat bersa, qisqarog‘i ishlaydi.
    retention_days: int = Field(default=0, ge=0, le=3650)
    #: Tozalash qanchalik tez-tez ishlaydi (standart: 6 soat).
    retention_interval_sec: int = Field(default=21_600, ge=60, le=604_800)


class ServerSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8742, ge=1, le=65535)
    # Bo'sh ro'yxat = CORS butunlay o'chiq (dashboard bir xil manbadan
    # xizmat qilinadi, shuning uchun default'da kerak emas). Alohida
    # frontend yoki mobil klient ulaganda shu yerga manba qo'shiladi.
    cors_origins: List[str] = Field(default_factory=list)


class WebcamSettings(BaseModel):
    client_interval_ms: int = Field(default=140, ge=30, le=2000)
    jpeg_quality: float = Field(default=0.82, ge=0.1, le=1.0)

class TelegramSettings(BaseModel):
    token: Optional[str] = None
    chat_id: Optional[str] = None
    enabled: bool = False
    alert_interval_sec: int = 60

class CameraItem(BaseModel):
    id: str
    source: Union[int, str]  # RTSP URL yoki 0, 1 (veb-kamera)
    enabled: bool = True

    @field_validator("source", mode="before")
    @classmethod
    def _normalize_source(cls, v: Any) -> Union[int, str]:
        if isinstance(v, bool):
            raise ValueError("source bool bo‘lishi mumkin emas")
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            s = v.strip()
            if s.isdigit():
                return int(s)
            return s
        raise ValueError("source RTSP URL (str) yoki kamera indeksi (int) bo‘lishi kerak")

class LicenseSettings(BaseModel):
    enabled: bool = False
    cloud_url: str = "http://127.0.0.1:8750"
    site_id: Optional[str] = None
    device_token: Optional[str] = None
    pairing_code: Optional[str] = None
    heartbeat_interval_sec: int = Field(default=1800, ge=60, le=86400)
    offline_grace_days: int = Field(default=7, ge=0, le=30)


class AppSettings(BaseModel):
    license: LicenseSettings = Field(default_factory=LicenseSettings)
    face: FaceSettings = Field(default_factory=FaceSettings)
    paths: PathsSettings = Field(default_factory=PathsSettings)
    events: EventsSettings = Field(default_factory=EventsSettings)
    tracking: TrackingSettings = Field(default_factory=TrackingSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    camera: CameraRuntimeSettings = Field(default_factory=CameraRuntimeSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    roi: RoiSettings = Field(default_factory=RoiSettings)
    antispoof: AntispoofSettings = Field(default_factory=AntispoofSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    webcam: WebcamSettings = Field(default_factory=WebcamSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    cameras: List[CameraItem] = Field(default_factory=list)

    @staticmethod
    def load(path: Path, *, base_dir: Path) -> "AppSettings":
        raw: dict[str, Any]
        if path.is_file():
            with path.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        else:
            raw = {}
        cfg = AppSettings.model_validate(raw)
        return cfg

    def resolved_reference_path(self, base_dir: Path) -> Path:
        p = Path(self.paths.reference_image)
        if p.is_absolute():
            return p
        return (base_dir / p).resolve()


def default_config_path(base_dir: Path) -> Path:
    env = os.environ.get("CHAQIMCHI_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    return (base_dir / "config" / "config.yaml").resolve()


def load_app_settings(base_dir: Path) -> AppSettings:
    path = default_config_path(base_dir)
    return AppSettings.load(path, base_dir=base_dir)
