"""YAML konfiguratsiyasini yuklash (webapp va CLI uchun)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Literal, Optional, Tuple, Union

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class FaceSettings(BaseModel):
    model_name: str = "buffalo_l"
    model_root: Optional[str] = None
    model_version: Optional[str] = None
    det_size: Tuple[int, int] = (640, 640)
    preprocess_max_side: int = Field(default=1024, ge=64, le=4096)
    compare_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    commercial_model_licensed: bool = False

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


class CloudSyncSettings(BaseModel):
    enabled: bool = False
    url: str = "http://127.0.0.1:8750"
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    device_token: Optional[str] = None
    #: Navbatda ish bo'lganda eng tez oraliq.
    interval_sec: int = Field(default=5, ge=1, le=3600)
    #: Navbat bo'sh bo'lganda oraliq shu qiymatgacha ikkilanib boradi.
    #: Har 5 soniyada so'rov yuborish soatiga 720 chaqiruv demak — bu
    #: cloud chegarasini (429) tinch do'konda ham urib yuborardi.
    max_interval_sec: int = Field(default=60, ge=1, le=3600)
    heartbeat_interval_sec: int = Field(default=60, ge=10, le=3600)
    batch_size: int = Field(default=50, ge=1, le=500)
    queue_days: int = Field(default=7, ge=1, le=30)
    queue_max_bytes: int = Field(default=20 * 1024**3, ge=1024**2)

    @model_validator(mode="after")
    def _intervals(self) -> "CloudSyncSettings":
        if self.max_interval_sec < self.interval_sec:
            raise ValueError("max_interval_sec interval_sec dan kichik bo'lmasin")
        return self


class SceneZoneSettings(BaseModel):
    name: str
    camera_id: str
    polygon: List[Tuple[float, float]]
    restricted: bool = False
    #: Navbat zonasi (kassa oldi).  Ichidagi odam soni `scene.queue_limit` dan
    #: oshsa `queue_threshold_exceeded` chiqadi.
    queue: bool = False
    #: Shu zonada shuncha soniyadan uzoq turgan mijoz uchun `dwell_exceeded`.
    #: `None` — zona uchun dwell o'lchanmaydi (yo'lak, kirish maydoni).
    dwell_sec: Optional[int] = Field(default=None, ge=5, le=86400)

    @field_validator("polygon")
    @classmethod
    def _polygon(cls, value: Any) -> List[Tuple[float, float]]:
        if not isinstance(value, (list, tuple)) or len(value) < 3:
            raise ValueError("polygon kamida uchta [x,y] nuqtadan iborat bo'lishi kerak")
        points = [(float(point[0]), float(point[1])) for point in value]
        if any(x < 0 or x > 1 or y < 0 or y > 1 for x, y in points):
            raise ValueError("polygon nuqtalari 0..1 oralig'ida bo'lishi kerak")
        return points


class SceneLineSettings(BaseModel):
    """Kirish/chiqish chizig'i.

    `start`→`end` yo'nalishining chap tomoni "ichkari" hisoblanadi.  O'rnatuvchi
    teskari chizib qo'ysa `swap_direction: true` yetadi — obyektga borib
    chiziqni qayta chizish shart emas.
    """

    name: str
    camera_id: str
    start: Tuple[float, float]
    end: Tuple[float, float]
    swap_direction: bool = False

    @field_validator("start", "end")
    @classmethod
    def _point(cls, value: Any) -> Tuple[float, float]:
        point = (float(value[0]), float(value[1]))
        if any(coordinate < 0 or coordinate > 1 for coordinate in point):
            raise ValueError("chiziq nuqtalari 0..1 oralig'ida bo'lishi kerak")
        return point


class SceneSettings(BaseModel):
    enabled: bool = False
    #: `openvino` — Sotqin (Intel N100) uchun asosiy yo'l.  `onnx` faqat
    #: ishlab chiqish mashinasi uchun qoladi.
    backend: Literal["onnx", "openvino"] = "onnx"
    model_path: Optional[str] = None
    confidence: float = Field(default=0.45, ge=0.05, le=0.99)
    nms_threshold: float = Field(default=0.45, ge=0.05, le=0.99)
    input_size: int = Field(default=640, ge=160, le=1280)
    analyze_fps: float = Field(default=2.0, ge=0.2, le=30.0)
    burst_fps: float = Field(default=5.0, ge=0.2, le=30.0)
    motion_min_area_ratio: float = Field(default=0.01, ge=0.0001, le=1.0)
    loitering_sec: int = Field(default=60, ge=5, le=86400)
    occupancy_limit: int = Field(default=20, ge=1, le=10000)
    event_debounce_sec: int = Field(default=30, ge=1, le=3600)
    #: Navbatdagi odam soni shundan oshsa `queue_threshold_exceeded`.
    queue_limit: int = Field(default=5, ge=1, le=1000)
    zones: List[SceneZoneSettings] = Field(default_factory=list)
    lines: List[SceneLineSettings] = Field(default_factory=list)


class RetailCameraSettings(BaseModel):
    """Do'kon analitikasi uchun bitta kamera.

    Ikkita manzil ikki xil ish uchun: **substream** tahlil qilinadi (yengil,
    640×360 atrofida), **main stream** esa klip uchun xom holda yoziladi.
    Bitta yuqori sifatli oqimni tahlil qilish N100 uchun juda og'ir bo'lardi.
    """

    id: str
    #: Substream manzili.  Kamera cloud inventarida bo'lsa bo'sh qoldiriladi:
    #: manzil o'sha yerdan keladi va bu yozuv faqat sozlama beradi.
    stream_url: str = ""
    #: Berilmasa bu kamerada klip bo'lmaydi — hodisa baribir yuboriladi.
    record_url: Optional[str] = None
    #: `security` — taqiqlangan zona va ish vaqtidan tashqari harakat;
    #: `retail` — sanash, navbat, dwell; `background` — statistika.
    priority: Literal["security", "retail", "background"] = "retail"
    #: Sekundiga shuncha kadr dekodlanadi; qolgani dekodlanmasdan tashlanadi.
    sample_fps: float = Field(default=5.0, gt=0, le=30)
    #: Kafolatlangan eng past tahlil tezligi.  Berilmasa prioritetdan olinadi.
    floor_fps: Optional[float] = Field(default=None, gt=0, le=30)


class RetailSettings(BaseModel):
    enabled: bool = False
    #: Qurilma sekundiga nechta inferens ko'taradi.  Bu **boshlang'ich taxmin**:
    #: byudjet o'lchangan latency bo'yicha o'zini tuzatadi.
    target_fps: float = Field(default=30.0, ge=1, le=240)
    min_fps: float = Field(default=2.0, ge=0.1, le=240)
    max_fps: float = Field(default=45.0, ge=1, le=480)
    clip_dir: str = "data/clips"
    buffer_dir: str = "data/buffer"
    segment_sec: int = Field(default=4, ge=1, le=60)
    #: Hodisa buferi: 3 kun / 40 GB (`sotqin_profile`).  Hajm barcha kameralar
    #: orasida teng bo'linadi.
    buffer_retention_sec: int = Field(default=3 * 24 * 3600, ge=60)
    buffer_max_bytes: int = Field(default=40 * 1024**3, ge=100 * 1024**2)
    pre_sec: float = Field(default=10.0, ge=0, le=300)
    post_sec: float = Field(default=20.0, ge=0, le=300)
    #: Qoidalar fayli (YAML yoki JSON).  Berilmasa hamma hodisa cloudga ketadi.
    rules_path: Optional[str] = None
    housekeeping_sec: float = Field(default=30.0, gt=0, le=3600)
    #: Do'kon ish vaqti ("09:00" / "21:00").  Ikkalasi berilsa, tashqarisida
    #: ko'ringan odam uchun `after_hours_presence` chiqadi.  Berilmasa bu
    #: hodisa umuman bo'lmaydi — noto'g'ri vaqt yolg'on signal beradi.
    open_from: Optional[str] = None
    open_to: Optional[str] = None
    after_hours_debounce_sec: float = Field(default=300.0, ge=10, le=86400)
    #: Kamera yopilgani/burilganini sezish.  Yopilgan kamerada harakat yo'q,
    #: shuning uchun bu tekshiruv harakat filtridan oldin ishlaydi.
    tamper_enabled: bool = True
    tamper_min_duration_sec: float = Field(default=10.0, gt=0, le=600)
    #: Kamera ro'yxati qayerdan olinadi.  `auto` — Sotqin config keshi bo'lsa
    #: undan (cloud inventari), aks holda quyidagi `cameras` dan.  `config` —
    #: faqat lokal ro'yxat (cloud'siz o'rnatish uchun).
    cameras_source: Literal["auto", "config"] = "auto"
    #: Sotqin cloud config keshi.  Bo'sh bo'lsa `CHAQIMCHI_SOTQIN_CONFIG_CACHE`
    #: muhit o'zgaruvchisi, keyin standart yo'l ishlatiladi.
    sotqin_config_path: Optional[str] = None
    #: Zanjir holati yoziladigan fayl (kameralarning **haqiqiy** ulanish
    #: holati).  Sotqin agenti uni heartbeat uchun o'qiydi.  Bo'sh bo'lsa
    #: `CHAQIMCHI_RETAIL_STATUS`, keyin standart yo'l.
    status_path: Optional[str] = None
    #: Cloud'da kamera qo'shilsa/o'chirilsa xizmat o'zini to'xtatadi va
    #: systemd uni qayta ishga tushiradi — yangi ro'yxat shunda kuchga kiradi.
    restart_on_config_change: bool = True
    cameras: List[RetailCameraSettings] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_budget(self) -> "RetailSettings":
        if not (self.min_fps <= self.target_fps <= self.max_fps):
            raise ValueError("retail: min_fps <= target_fps <= max_fps bo'lishi kerak")
        names = [camera.id for camera in self.cameras]
        if len(names) != len(set(names)):
            raise ValueError("retail: kamera id lari takrorlanmasin")
        if bool(self.open_from) != bool(self.open_to):
            raise ValueError("retail: open_from va open_to birga berilishi kerak")
        for value in (self.open_from, self.open_to):
            if value is None:
                continue
            parts = str(value).split(":")
            if len(parts) != 2 or not all(part.isdigit() for part in parts):
                raise ValueError(f"retail: vaqt 'HH:MM' ko'rinishida bo'lsin: {value}")
            hour, minute = int(parts[0]), int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError(f"retail: vaqt noto'g'ri: {value}")
        return self


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
    environment: Literal["development", "test", "production"] = "development"
    license: LicenseSettings = Field(default_factory=LicenseSettings)
    face: FaceSettings = Field(default_factory=FaceSettings)
    paths: PathsSettings = Field(default_factory=PathsSettings)
    events: EventsSettings = Field(default_factory=EventsSettings)
    tracking: TrackingSettings = Field(default_factory=TrackingSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    cloud_sync: CloudSyncSettings = Field(default_factory=CloudSyncSettings)
    scene: SceneSettings = Field(default_factory=SceneSettings)
    retail: RetailSettings = Field(default_factory=RetailSettings)
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

        def expand(value: Any) -> Any:
            if isinstance(value, str):
                return os.path.expandvars(value)
            if isinstance(value, list):
                return [expand(item) for item in value]
            if isinstance(value, dict):
                return {key: expand(item) for key, item in value.items()}
            return value

        cfg = AppSettings.model_validate(expand(raw))
        return cfg

    def resolved_reference_path(self, base_dir: Path) -> Path:
        p = Path(self.paths.reference_image)
        if p.is_absolute():
            return p
        return (base_dir / p).resolve()

    def production_errors(self) -> List[str]:
        """Production ishga tushishidan oldingi fail-closed tekshiruvlar."""
        if self.environment != "production":
            return []
        errors: List[str] = []
        if not self.security.api_key_enabled:
            errors.append("API key autentifikatsiyasi yoqilishi shart")
        if self.security.api_key_enabled and not (
            os.environ.get("CHAQIMCHI_API_KEY", "").strip() or self.security.api_key
        ):
            errors.append("CHAQIMCHI_API_KEY berilishi shart")
        jwt_secret = os.environ.get("CHAQIMCHI_JWT_SECRET", "").strip() or self.security.jwt.secret
        if self.security.jwt.enabled and (not jwt_secret or len(jwt_secret) < 32):
            errors.append("CHAQIMCHI_JWT_SECRET kamida 32 belgidan iborat bo'lishi shart")
        if not self.rate_limit.enabled:
            errors.append("rate_limit productionda yoqilishi shart")
        if not self.storage.encrypt_embeddings:
            errors.append("embedding shifrlash productionda yoqilishi shart")
        if (
            self.storage.encrypt_embeddings
            and not os.environ.get("CHAQIMCHI_EMBEDDING_KEY", "").strip()
        ):
            errors.append("CHAQIMCHI_EMBEDDING_KEY berilishi shart")
        licensed = self.face.commercial_model_licensed or os.environ.get(
            "CHAQIMCHI_FACE_MODEL_LICENSED", ""
        ).lower() in {"1", "true", "yes"}
        attendance_pilot = os.environ.get("CHAQIMCHI_ATTENDANCE_PILOT", "").lower() in {
            "1",
            "true",
            "yes",
        }
        if not licensed and not attendance_pilot:
            errors.append("commercial Face ID model litsenziyasi tasdiqlanishi shart")
        if licensed:
            from chaqimchi_ai.model_bundle import verify_model_manifest

            manifest = os.environ.get("CHAQIMCHI_FACE_MODEL_MANIFEST", "").strip()
            if not manifest:
                errors.append("CHAQIMCHI_FACE_MODEL_MANIFEST berilishi shart")
            else:
                errors.extend(verify_model_manifest(Path(manifest)))
            if self.face.model_name in {"buffalo_l", "buffalo_s", "antelopev2"}:
                errors.append("commercial rejim demo InsightFace model nomidan foydalana olmaydi")
        if attendance_pilot and self.events.save_snapshots:
            errors.append("davomat pilotida biometrik snapshot saqlash o'chirilishi shart")
        if self.cloud_sync.enabled:
            if not self.cloud_sync.url.lower().startswith("https://"):
                errors.append("cloud_sync.url productionda HTTPS bo'lishi shart")
            if not all(
                (self.cloud_sync.site_id, self.cloud_sync.device_id, self.cloud_sync.device_token)
            ):
                errors.append("cloud sync site_id, device_id va device_token talab qiladi")
            elif any(
                "${" in str(value)
                for value in (
                    self.cloud_sync.site_id,
                    self.cloud_sync.device_id,
                    self.cloud_sync.device_token,
                )
            ):
                errors.append("cloud sync muhit o'zgaruvchilari to'liq berilishi shart")
        for camera in self.cameras:
            if isinstance(camera.source, str) and "${" in camera.source:
                errors.append(f"{camera.id} RTSP manzili muhitda berilmagan")
        return errors


def default_config_path(base_dir: Path) -> Path:
    env = os.environ.get("CHAQIMCHI_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    return (base_dir / "config" / "config.yaml").resolve()


def load_app_settings(base_dir: Path) -> AppSettings:
    path = default_config_path(base_dir)
    return AppSettings.load(path, base_dir=base_dir)
