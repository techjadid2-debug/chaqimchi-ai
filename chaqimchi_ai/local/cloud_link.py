"""Windows dasturini Chaqimchi Cloud'ga ulash.

Nima uchun kerak: ulanmagan dastur to'liq ishlaydi, lekin **yolg'iz**
qoladi — hodisalar `outbox.db` da to'planadi, mijoz cloud panelida hech
nima ko'rmaydi va Telegram xabar kelmaydi.  Ulangandan keyin uch narsa
o'z-o'zidan ishga tushadi (ular cloudda allaqachon yozilgan):

* `CloudEventSync` navbatni cloudga uzatadi (`chaqimchi_ai/cloud_sync.py`);
* cloud hodisani qabul qilib obyekt a'zolariga Telegram yuboradi;
* mijoz owner panelida o'sha raqamlarni ko'radi.

`scripts/pair_sotqin.py` bilan farqi faqat **natijani qayerga yozishda**:
u Linux qurilmasida `/etc/chaqimchi/sotqin.env` ga yozadi, bu yerda esa
lokal `config.yaml` ning `cloud_sync` bo'limiga tushadi.  Claim so'rovi
va uning maydonlari bir xil — cloud ikkalasini ham farq qilmaydi.
"""

from __future__ import annotations

import logging
import platform
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

from chaqimchi_ai import __version__
from chaqimchi_ai.local import config_store

logger = logging.getLogger(__name__)

#: Pairing kod — `secrets.token_hex(3).upper()`, ya'ni 6 ta hex belgi
#: (`cloud/store.py:_insert_pairing_code`).
CODE_PATTERN = re.compile(r"^[0-9A-F]{6}$")

#: Cloud sekin javob bersa ham mijoz "osilib qoldi" deb o'ylamasligi kerak.
TIMEOUT_SEC = 20


class PairingError(Exception):
    """Mijozga ko'rsatiladigan, tuzatib bo'ladigan xato."""


@dataclass(frozen=True)
class PairedSite:
    site_id: str
    device_id: str
    cloud_url: str


def normalise_code(value: str) -> str:
    code = value.strip().upper().replace(" ", "").replace("-", "")
    if not CODE_PATTERN.match(code):
        raise PairingError(
            "Pairing kod 6 ta belgidan iborat bo'lishi kerak (0-9 va A-F). "
            "Kodni admin panelidan qayta ko'chiring."
        )
    return code


def normalise_url(value: str) -> str:
    """Cloud manzilini tekshiradi.

    HTTPS majburiy: qurilma tokeni shu ulanish orqali uzatiladi va ochiq
    HTTP'da uni yo'lda o'qib olish mumkin.  Faqat `localhost` istisno —
    ishlab chiqish va test uchun.
    """
    url = value.strip().rstrip("/")
    if not url:
        raise PairingError("Cloud manzili kiritilmagan")
    if "://" not in url:
        url = f"https://{url}"
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PairingError(f"Cloud manzili noto'g'ri: {value}")
    is_local = parsed.hostname in {"127.0.0.1", "localhost"}
    if parsed.scheme != "https" and not is_local:
        raise PairingError("Cloud manzili https:// bilan boshlanishi kerak")
    return url


def device_label() -> str:
    """Admin panelda ko'rinadigan nom — kompyuter nomi."""
    return (platform.node() or "windows-pc")[:64]


def hardware_id() -> str:
    """Qurilmani ajratib turadigan barqaror identifikator.

    Windows'da `platform.node()` — kompyuter nomi.  U o'zgarishi mumkin,
    lekin cloud uni faqat ma'lumot uchun saqlaydi: haqiqiy autentifikatsiya
    `device_token` orqali bo'ladi.
    """
    return (platform.node() or "windows-pc")[:120]


def claim(code: str, cloud_url: str) -> PairedSite:
    """Pairing kodni qurilma tokeniga almashtiradi va configga yozadi.

    Muvaffaqiyatsiz bo'lsa config **umuman o'zgarmaydi** — yarim ulangan
    holat eng yomon variant bo'lardi: dastur cloudga urinaveradi, lekin
    hech qachon ulanmaydi va sababi hech qayerda ko'rinmaydi.
    """
    safe_code = normalise_code(code)
    safe_url = normalise_url(cloud_url)

    try:
        response = httpx.post(
            f"{safe_url}/api/v1/devices/claim",
            json={
                "pairing_code": safe_code,
                "label": device_label(),
                "hardware_id": hardware_id(),
                "product_name": "Chaqimchi Windows",
                "hardware_model": platform.processor()[:120] or "Windows PC",
                "hardware_revision": "W1",
                "serial_number": hardware_id(),
            },
            timeout=TIMEOUT_SEC,
        )
    except httpx.HTTPError as exc:
        logger.warning("Cloud bilan ulanish xatosi: %s", exc)
        raise PairingError(
            "Cloud serverga ulanib bo'lmadi. Internetni tekshiring "
            "va qayta urinib ko'ring."
        ) from exc

    if response.status_code == 400:
        raise PairingError(
            "Bu kod ishlamadi — muddati o'tgan yoki allaqachon ishlatilgan. "
            "Admin paneldan yangi kod oling."
        )
    if response.status_code >= 400:
        logger.warning("Claim rad etildi: %s %s", response.status_code, response.text[:200])
        raise PairingError(f"Cloud so'rovni rad etdi (kod {response.status_code}).")

    try:
        device = response.json()
        site_id = str(device["site_id"])
        device_id = str(device["device_id"])
        device_token = str(device["device_token"])
    except (ValueError, KeyError) as exc:
        raise PairingError("Cloud kutilmagan javob qaytardi.") from exc

    config_store.update(
        "cloud_sync",
        {
            "enabled": True,
            "url": safe_url,
            "site_id": site_id,
            "device_id": device_id,
            "device_token": device_token,
        },
    )
    logger.info("Cloudga ulandi: site=%s device=%s", site_id, device_id)
    return PairedSite(site_id=site_id, device_id=device_id, cloud_url=safe_url)


def unlink() -> None:
    """Ulanishni uzadi.

    Token va identifikatorlar **o'chiriladi**: dastur boshqa kompyuterga
    ko'chirilsa yoki mijoz almashsa, eski obyektga hodisa yuborib
    qo'ymasligi kerak.
    """
    config_store.update(
        "cloud_sync",
        {"enabled": False, "site_id": None, "device_id": None, "device_token": None},
    )
    logger.info("Cloud ulanishi uzildi")


def status() -> Dict[str, Any]:
    """Panel va sehrgar uchun ulanish holati.

    `device_token` **qaytarilmaydi** — u brauzerga chiqsa qurilma nomidan
    hodisa yuborish mumkin bo'lardi.
    """
    raw = config_store.read_raw().get("cloud_sync") or {}
    connected = bool(raw.get("enabled") and raw.get("device_token"))
    return {
        "connected": connected,
        "cloud_url": raw.get("url") if connected else None,
        "site_id": raw.get("site_id") if connected else None,
        "owner_url": f"{raw.get('url')}/owner" if connected else None,
        "app_version": __version__,
    }


def pending_events() -> Optional[int]:
    """Cloudga yuborilmagan hodisalar soni.

    Bu raqam o'sib borsa — aloqa uzilgan.  Panel shuni ko'rsatadi, chunki
    "ulangan" yozuvi turgani holda hodisalar to'planib qolishi mumkin.
    """
    import sqlite3

    from chaqimchi_ai.local import paths

    db = paths.outbox_path()
    if not db.is_file():
        return 0
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)
        try:
            return int(conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0])
        finally:
            conn.close()
    except sqlite3.Error:
        return None
