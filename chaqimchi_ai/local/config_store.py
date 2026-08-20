"""Lokal `config.yaml` — sehrgar yozadigan yagona fayl.

Nega alohida modul: sehrgar to'rt xil narsani yozadi (kamera, chiziq/zona,
ish vaqti, Telegram), lekin ularning hammasi **bitta** YAML ga tushishi
kerak.  Har bir endpoint faylni o'zicha ochib yozsa, ikkita so'rov bir vaqtda
kelganda biri ikkinchisini o'chirib yuborardi.

Yozish atomik: avval `.tmp` ga, keyin `os.replace`.  Tok o'chganda yarim
yozilgan config qolmaydi — do'kon kompyuterida bu nazariy xavf emas.

Kamera ro'yxati `retail.cameras_source: config` rejimida turadi: zanjir uni
lokal fayldan oladi va **cloud ulanmasa ham** ishlaydi.  Cloud keyin
ulanganda `auto` ga o'tkaziladi va inventar cloud'dan keladi.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from chaqimchi_ai.local import paths
from chaqimchi_ai.settings import AppSettings

#: Bir vaqtda ikkita so'rov yozmasligi uchun.  Jarayon bitta, shuning uchun
#: oddiy `threading.Lock` yetadi — fayl qulfi ortiqcha murakkablik bo'lardi.
_LOCK = threading.Lock()

#: Do'kon uchun oqilona boshlang'ich qiymatlar.  Mijoz sehrgarda ularni
#: o'zgartira oladi, lekin hech nima kiritmasa ham tizim ishlashi kerak.
#: 20 — cloud standarti bilan bir xil (`cloud/event_store.py`); 30 bitta
#: 640x360 kadrda deyarli hech qachon yig'ilmaydi va hodisa umuman
#: chiqmay qolar edi.
DEFAULT_OCCUPANCY_LIMIT = 20
DEFAULT_QUEUE_LIMIT = 5
DEFAULT_LOITERING_SEC = 300

#: N100 uchun o'lchangan qiymatdan past: mijozning oddiy ofis kompyuteri
#: kuchsizroq bo'lishi mumkin, byudjet esa o'zini latency bo'yicha tuzatadi.
DEFAULT_TARGET_FPS = 12.0


def default_config() -> Dict[str, Any]:
    """Birinchi ishga tushishdagi bo'sh, lekin **to'g'ri** config."""
    root = paths.data_dir()
    return {
        # `production` emas: `AppSettings.production_errors()` fail-closed
        # rejimda API kalit, JWT sirri va shifrlash kalitini talab qiladi —
        # bular do'kon kompyuterida ma'nosiz, chunki xizmat faqat
        # `127.0.0.1` da tinglaydi.
        "environment": "development",
        "paths": {
            "db_path": str(root / "data" / "database"),
            "events_db": str(root / "data" / "events.db"),
            "snapshots_dir": str(root / "data" / "snapshots"),
            "calibration_dir": str(root / "data" / "calibration"),
        },
        "scene": {
            "enabled": True,
            "backend": "openvino",
            "model_path": str(paths.model_path()),
            "confidence": 0.5,
            "occupancy_limit": DEFAULT_OCCUPANCY_LIMIT,
            "queue_limit": DEFAULT_QUEUE_LIMIT,
            "loitering_sec": DEFAULT_LOITERING_SEC,
            "lines": [],
            "zones": [],
        },
        "retail": {
            "enabled": True,
            # Lokal rejimning kaliti: kamera ro'yxati shu fayldan olinadi.
            "cameras_source": "config",
            "target_fps": DEFAULT_TARGET_FPS,
            "min_fps": 2.0,
            "max_fps": 20.0,
            "buffer_dir": str(root / "data" / "buffer"),
            "clip_dir": str(root / "data" / "clips"),
            "status_path": str(paths.status_path()),
            # Cloud keshi yo'q — kesh revizyasini kuzatib qayta ishga
            # tushishning ma'nosi yo'q, aks holda xizmat har 30 soniyada
            # "config o'qilmadi" deb log to'ldirardi.
            "restart_on_config_change": False,
            "tamper_enabled": True,
            # Qoidalar fayli MAJBURIY ulanadi: usiz RuleEngine bo'sh bo'lib,
            # `person_detected` bosilmasdan cloudga oqar, sovutishlar va
            # `save_clip` umuman ishlamas edi (jonli qurilmada bir kunda
            # 394 ta person_detected yig'ilgani shundan).
            "rules_path": str(paths.rules_path()),
            "cameras": [],
        },
        # Cloud ixtiyoriy: mijoz keyin pairing kod bilan ulanishi mumkin.
        "cloud_sync": {"enabled": False},
        "telegram": {"enabled": False},
        "events": {"save_snapshots": True},
        "storage": {"encrypt_embeddings": False},
    }


def read_raw() -> Dict[str, Any]:
    """Configni lug'at ko'rinishida o'qiydi; fayl yo'q bo'lsa yaratadi."""
    path = paths.config_path()
    if not path.is_file():
        raw = default_config()
        _write_raw_unlocked(raw)
        return raw
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return _heal(raw)


def _heal(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Eski o'rnatishlardagi config'ni yangi majburiy maydonlar bilan to'ldiradi.

    `rules_path` keyin qo'shildi: usiz ishlab turgan qurilmalarda qoidalar
    (suppression, sovutish, save_clip) o'lik edi.  Yangilanish o'rnatilgach
    dastur birinchi o'qishdayoq yo'lni to'ldirib qo'yadi — mijozdan hech
    narsa talab qilinmaydi.
    """
    retail = raw.get("retail")
    if isinstance(retail, dict) and not retail.get("rules_path"):
        rules = paths.rules_path()
        if rules.is_file():
            retail["rules_path"] = str(rules)
            _write_raw_unlocked(raw)
    return raw


def _write_raw_unlocked(raw: Dict[str, Any]) -> None:
    path = paths.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(raw, handle, allow_unicode=True, sort_keys=False)
    os.replace(tmp, path)


def update(section: str, values: Dict[str, Any]) -> Dict[str, Any]:
    """Bitta bo'limni yangilaydi va butun configni qaytaradi.

    O'qish→o'zgartirish→yozish qulf ostida bajariladi, aks holda kamera
    saqlash va chiziq saqlash bir vaqtda kelsa biri yo'qolardi.
    """
    with _LOCK:
        raw = read_raw()
        current = raw.get(section)
        if not isinstance(current, dict):
            current = {}
        current.update(values)
        raw[section] = current
        _write_raw_unlocked(raw)
        return raw


def load_settings() -> AppSettings:
    """Validatsiyadan o'tgan sozlama.  Xato bo'lsa `ValidationError` beradi."""
    return AppSettings.load(paths.config_path(), base_dir=paths.data_dir())


# ── Sehrgar yozadigan bo'limlar ──────────────────────────────────────────


def cameras() -> List[Dict[str, Any]]:
    raw = read_raw()
    retail = raw.get("retail") or {}
    return list(retail.get("cameras") or [])


def save_camera(
    *,
    camera_id: str,
    stream_url: str,
    label: str = "",
    record_url: Optional[str] = None,
    priority: str = "retail",
) -> List[Dict[str, Any]]:
    """Kamerani qo'shadi yoki mavjudini almashtiradi (id bo'yicha).

    `label` — faqat panel va sehrgar uchun ("Kirish eshigi").  `RetailCameraSettings`
    da bunday maydon yo'q va pydantic uni e'tiborsiz qoldiradi; fayl esa xom
    YAML sifatida o'qib-yozilgani uchun nom yo'qolmaydi.  Ya'ni bu ataylab —
    zanjir sxemasini mijoz uchun chiroyli nom deb kengaytirish shart emas.
    """
    entry: Dict[str, Any] = {
        "id": camera_id,
        "stream_url": stream_url,
        "priority": priority,
    }
    if label:
        entry["label"] = label
    if record_url:
        entry["record_url"] = record_url

    with _LOCK:
        raw = read_raw()
        retail = raw.get("retail") or {}
        existing = [item for item in (retail.get("cameras") or []) if item.get("id") != camera_id]
        existing.append(entry)
        existing.sort(key=lambda item: str(item.get("id")))
        retail["cameras"] = existing
        raw["retail"] = retail
        _write_raw_unlocked(raw)
        return existing


def delete_camera(camera_id: str) -> List[Dict[str, Any]]:
    """Kamerani va unga tegishli chiziq/zonalarni birga o'chiradi.

    Alohida o'chirilsa, kamerasiz qolgan chiziq zanjirda jimgina e'tiborsiz
    qolardi va mijoz "chizdim, lekin sanamayapti" degan holatga tushardi.
    """
    with _LOCK:
        raw = read_raw()
        retail = raw.get("retail") or {}
        retail["cameras"] = [
            item for item in (retail.get("cameras") or []) if item.get("id") != camera_id
        ]
        raw["retail"] = retail

        scene = raw.get("scene") or {}
        scene["lines"] = [
            item for item in (scene.get("lines") or []) if item.get("camera_id") != camera_id
        ]
        scene["zones"] = [
            item for item in (scene.get("zones") or []) if item.get("camera_id") != camera_id
        ]
        raw["scene"] = scene

        _write_raw_unlocked(raw)
        return list(retail["cameras"])


def geometry() -> Dict[str, List[Dict[str, Any]]]:
    scene = read_raw().get("scene") or {}
    return {"lines": list(scene.get("lines") or []), "zones": list(scene.get("zones") or [])}


def save_geometry(lines: List[Dict[str, Any]], zones: List[Dict[str, Any]]) -> Dict[str, Any]:
    return update("scene", {"lines": lines, "zones": zones})


def save_store_hours(open_from: Optional[str], open_to: Optional[str]) -> Dict[str, Any]:
    """Ish vaqti — `after_hours_presence` hodisasi shunga qarab chiqadi."""
    return update("retail", {"open_from": open_from, "open_to": open_to})


def save_telegram(token: Optional[str], chat_id: Optional[str]) -> Dict[str, Any]:
    enabled = bool(token and chat_id)
    return update("telegram", {"token": token, "chat_id": chat_id, "enabled": enabled})


def save_limits(*, occupancy_limit: int, queue_limit: int, loitering_sec: int) -> Dict[str, Any]:
    return update(
        "scene",
        {
            "occupancy_limit": occupancy_limit,
            "queue_limit": queue_limit,
            "loitering_sec": loitering_sec,
        },
    )


def is_ready() -> bool:
    """Zanjirni ishga tushirish mantiqiymi.

    Kamerasiz xizmat `RuntimeError` bilan darhol to'xtaydi; chiziqsiz esa
    ishlaydi-yu, hech narsa sanamaydi.  Ikkalasi ham sehrgarning tugash
    sharti — panelga "tayyor" deb ko'rsatilishidan oldin tekshiriladi.
    """
    raw = read_raw()
    has_camera = bool((raw.get("retail") or {}).get("cameras"))
    scene = raw.get("scene") or {}
    has_shape = bool(scene.get("lines") or scene.get("zones"))
    return has_camera and has_shape


def model_available() -> bool:
    """AI modeli o'rnatilganmi.

    O'rnatuvchi uni birga olib keladi.  Ishlab chiqish mashinasida esa
    `python scripts/fetch_retail_model.py` bilan yuklab olinadi — sehrgar
    buni aniq aytishi kerak, aks holda mijoz "ishga tushirish" tugmasini
    bosib, tushunarsiz xatoga duch kelardi.
    """
    xml = paths.model_path()
    return xml.is_file() and xml.with_suffix(".bin").is_file()


def summary() -> Dict[str, Any]:
    """Sehrgar va panel uchun qisqacha holat.

    Kamera manzili **qaytarilmaydi**: u ichida NVR foydalanuvchi nomi va
    parolini olib yuradi, ya'ni kameraga to'liq kirish huquqi.  Brauzerga
    faqat ID va nom ketadi; manzil kerak bo'lsa `/api/setup/cameras` uni
    paroli o'chirilgan holda beradi.
    """
    raw = read_raw()
    scene = raw.get("scene") or {}
    telegram = raw.get("telegram") or {}
    saved = list((raw.get("retail") or {}).get("cameras") or [])
    return {
        "cameras": [
            {"camera_id": item.get("id"), "label": item.get("label") or item.get("id")}
            for item in saved
        ],
        "lines": len(scene.get("lines") or []),
        "zones": len(scene.get("zones") or []),
        "telegram_enabled": bool(telegram.get("enabled")),
        "model_available": model_available(),
        "ready": is_ready(),
        "config_path": str(paths.config_path()),
        "data_dir": str(paths.data_dir()),
    }


def feature_status() -> List[Dict[str, Any]]:
    """Har funksiya: yoqilganmi va bo'lmasa — NIMA yetishmayapti.

    "Yashil chiroq yolg'oni"ga qarshi asosiy qurol: ilgari zona-only yoki
    soatlari kiritilmagan o'rnatish panelda yashil ko'rinar, mijoz esa
    "navbat funksiyasi ishlayapti" deb yurar edi — aslida u hech qachon
    hodisa chiqarmagan.  Bu ro'yxat panel va sehrgar yakunida ko'rinadi.
    """
    raw = read_raw()
    scene = raw.get("scene") or {}
    retail = raw.get("retail") or {}
    lines = list(scene.get("lines") or [])
    zones = list(scene.get("zones") or [])
    cameras = list(retail.get("cameras") or [])
    queue_zones = [zone for zone in zones if zone.get("queue")]
    restricted_zones = [zone for zone in zones if zone.get("restricted")]
    dwell_zones = [zone for zone in zones if zone.get("dwell_sec")]
    hours_set = bool(retail.get("open_from") and retail.get("open_to"))
    clip_source = any(camera.get("record_url") for camera in cameras)

    def item(code: str, name: str, active: bool, reason: str) -> Dict[str, Any]:
        return {"code": code, "name": name, "active": active, "reason": None if active else reason}

    return [
        item(
            "line_count",
            "Kirish-chiqish sanash",
            bool(lines),
            "Kirish chizig'i chizilmagan — sozlamalarda eshik ustiga chizing",
        ),
        item(
            "queue",
            "Kassa navbati",
            bool(queue_zones),
            "Navbat zonasi belgilanmagan — kassa oldiga zona chizib, «navbat» ni belgilang",
        ),
        item(
            "restricted",
            "Taqiqlangan zona",
            bool(restricted_zones),
            "Taqiqlangan zona chizilmagan (masalan ombor eshigi)",
        ),
        item(
            "dwell",
            "Zonada uzoq turish",
            bool(dwell_zones),
            "Hech bir zonada «uzoq turish» vaqti kiritilmagan",
        ),
        item(
            "after_hours",
            "Ish vaqtidan tashqari nazorat",
            hours_set,
            "Ochilish va yopilish soatlari kiritilmagan",
        ),
        item(
            "tamper",
            "Kamera buzilishi nazorati",
            bool(retail.get("tamper_enabled", True)),
            "Sozlamada o'chirilgan",
        ),
        item(
            "clips",
            "Hodisa videosi (klip)",
            clip_source,
            "Asosiy oqim manzili topilmadi — kamera sozlamasida kiriting",
        ),
    ]


def config_file() -> Path:
    return paths.config_path()
