"""Cloud'da kiritilgan sozlamani qurilmaga olib tushish.

Nima uchun: o'rnatuvchi do'konga borib, sovuq kompyuter oldida turib
kamera manzillarini va chiziqlarni kiritishi shart emas.  U buni oldindan
o'z stolida — cloud panelida — qiladi.  Do'konda esa faqat dasturni
o'rnatadi, qolgani o'zi tushadi.

Yo'l allaqachon qurilgan, biz faqat oxirgi bo'g'inni ulaymiz:

    cloud panel (kamera, chiziq)
      -> `GET /api/v1/edge/config`         (bor edi)
      -> kesh fayli                        (shu modul yozadi)
      -> `retail.cameras_source: auto`     (bor edi)
      -> zanjir kameralarni keshdan oladi  (bor edi)

**Eng muhim qoida: cloud faqat qo'shadi, hech qachon o'chirmaydi.**
Mijoz sehrgarda kamera qo'shgan bo'lishi mumkin, cloudda esa hali hech
narsa yo'q.  Agar biz bo'sh cloud javobini "haqiqat" deb qabul qilsak,
uning ishlab turgan sozlamasini yo'q qilgan bo'lardik.  Shuning uchun
bo'sh bo'lim e'tiborsiz qoldiriladi.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from chaqimchi_ai import __version__
from chaqimchi_ai.local import config_store, paths

logger = logging.getLogger(__name__)

#: Cloud sozlamasini shuncha soniyada bir marta so'raymiz.  Qurilma
#: heartbeat'i ham 60 soniyada — bir xil ritm, cloudga qo'shimcha yuk yo'q.
POLL_INTERVAL_SEC = 60

TIMEOUT_SEC = 20


def cache_path() -> Path:
    """Zanjir kameralarni shu fayldan o'qiydi.

    Yo'l `retail.sotqin_config_path` da ham yoziladi, aks holda
    `read_sotqin_cache` standart Linux yo'lini qidirardi.
    """
    return paths.data_dir() / "sotqin-config.json"


def _headers(cloud: Dict[str, Any]) -> Dict[str, str]:
    return {
        "X-Site-Id": str(cloud["site_id"]),
        "X-Device-Id": str(cloud["device_id"]),
        "X-Device-Token": str(cloud["device_token"]),
    }


def fetch(cloud: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        response = httpx.get(
            f"{str(cloud['url']).rstrip('/')}/api/v1/edge/config",
            headers=_headers(cloud),
            timeout=TIMEOUT_SEC,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("Cloud sozlamasi olinmadi: %s", exc)
        return None
    return payload if isinstance(payload, dict) else None


def _write_cache(payload: Dict[str, Any]) -> None:
    """Keshni atomik yozadi.

    Yarim yozilgan fayl `read_sotqin_cache` da `ValueError` ko'taradi va
    zanjir ishga tushmaydi — tok o'chganda bu real xavf.
    """
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def apply(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Cloud sozlamasini lokal configga qo'llaydi.

    Qaytaradi: nima o'zgargani (panel va log uchun).
    """
    changed: Dict[str, Any] = {"cameras": 0, "lines": 0, "zones": 0, "limits": False}

    cameras = [item for item in (payload.get("cameras") or []) if item.get("source")]
    if cameras:
        _write_cache(payload)
        # Kameralar keshdan olinsin va revizya o'zgarganda zanjir o'zini
        # qayta ishga tushirsin — aks holda cloudda qo'shilgan kamera
        # keyingi qo'lda restartgacha tahlil qilinmasdi.
        config_store.update(
            "retail",
            {
                "cameras_source": "auto",
                "sotqin_config_path": str(cache_path()),
                "restart_on_config_change": True,
            },
        )
        changed["cameras"] = len(cameras)

    site = payload.get("config") or {}
    lines = site.get("lines") or []
    zones = site.get("zones") or []
    if lines or zones:
        config_store.save_geometry(lines, zones)
        changed["lines"] = len(lines)
        changed["zones"] = len(zones)

    limits = {
        key: site[key]
        for key in ("occupancy_limit", "queue_limit", "loitering_sec")
        if site.get(key)
    }
    if limits:
        config_store.update("scene", limits)
        changed["limits"] = True

    # Ish vaqti: ikkalasi ham berilgan bo'lsagina.  Yarmi bo'lsa
    # `AppSettings` validatsiyasi yiqiladi va config umuman o'qilmay qoladi.
    if site.get("open_from") and site.get("open_to"):
        config_store.save_store_hours(site["open_from"], site["open_to"])

    return changed


def send_heartbeat(status: Dict[str, Any]) -> bool:
    """Qurilma holatini cloudga yuboradi.

    Nega lokal ilova yuboradi, zanjir emas: `retail.service` dagi
    `CloudEventSync` `health_provider`siz yaratilgan, ya'ni heartbeat
    **umuman yuborilmasdi**.  Natijada admin panelda versiya `v?` bo'lib
    turardi va kamera holati ko'rinmasdi.

    Bundan tashqari zanjir to'xtab qolsa cloud buni bilishi kerak — agar
    heartbeat faqat zanjirdan kelsa, yiqilgan qurilma shunchaki
    "jim" bo'lib qolardi va sababi noma'lum bo'lardi.  Lokal ilova esa
    doim ishlaydi.
    """
    raw = config_store.read_raw().get("cloud_sync") or {}
    if not raw.get("enabled") or not raw.get("device_token"):
        return False

    try:
        free_bytes = shutil.disk_usage(str(paths.data_dir())).free
    except OSError:
        free_bytes = 0

    payload = {
        "cameras_active": int(status.get("cameras_active") or 0),
        "disk_free_bytes": int(free_bytes),
        "outbox_pending": int(_pending_events() or 0),
        "app_version": __version__,
        "product_name": "Chaqimchi Windows",
    }
    try:
        response = httpx.post(
            f"{str(raw['url']).rstrip('/')}/api/v1/edge/heartbeat",
            headers=_headers(raw),
            json=payload,
            timeout=TIMEOUT_SEC,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.info("Heartbeat yuborilmadi: %s", exc)
        return False
    return True


def _pending_events() -> Optional[int]:
    from chaqimchi_ai.local import cloud_link

    return cloud_link.pending_events()


def sync_once() -> Optional[Dict[str, Any]]:
    """Bir marta so'rab, o'zgargan bo'lsa qo'llaydi.

    Qaytaradi: `None` — o'zgarish yo'q yoki ulanmagan; aks holda nima
    qo'llangani.
    """
    raw = config_store.read_raw().get("cloud_sync") or {}
    if not raw.get("enabled") or not raw.get("device_token"):
        return None

    payload = fetch(raw)
    if payload is None:
        return None

    revision = payload.get("revision")
    if revision == _last_revision.get("value"):
        return None

    changed = apply(payload)
    _last_revision["value"] = revision
    if any(changed.values()):
        logger.info(
            "Cloud sozlamasi qo'llandi (revizya %s): %s kamera, %s chiziq, %s zona",
            revision,
            changed["cameras"],
            changed["lines"],
            changed["zones"],
        )
        return {"revision": revision, **changed}
    return None


#: Oxirgi qo'llangan revizya.  Har siklda faylni qayta yozmaslik uchun:
#: yozish zanjirni qayta ishga tushirar edi va do'kon nazorati har
#: daqiqada bir necha soniyaga uzilardi.
_last_revision: Dict[str, Any] = {"value": None}


def status() -> Dict[str, Any]:
    """Panel uchun: sozlama qayerdan kelgan."""
    raw = config_store.read_raw().get("retail") or {}
    remote = raw.get("cameras_source") == "auto" and cache_path().is_file()
    return {
        "remote_config": remote,
        "revision": _last_revision.get("value"),
    }
