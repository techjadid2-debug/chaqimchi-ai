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

import json
import logging
import os
import platform
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
    """Mijozga ko'rsatiladigan, tuzatib bo'ladigan xato.

    `retryable` — vaqtinchalik muammomi (internet yo'q, server javob
    bermadi) yoki qat'iymi (kod eskirgan, allaqachon ishlatilgan).
    Sehrgar ikkalasini boshqacha ko'rsatadi: birinchisida "biroz kuting",
    ikkinchisida "yangi kod kerak".
    """

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


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


#: Ulanish holati shu faylda: `connect_token` diskda saqlanishi SHART,
#: chunki qurilma tasdiqni daqiqalab kutadi va shu orada qayta ishga
#: tushishi mumkin.  Fayl `config.yaml` bilan bir papkada — o'rnatuvchi
#: uni ACL bilan yopgan.
CONNECT_STATE = "connect.json"

#: Yangi ulanish havolasi shuncha soniyada bir marta so'raladi.
HELLO_RETRY_SEC = 300.0

#: Oxirgi urinish vaqti (monotonik).  Nolinchi qiymat — hali
#: urinilmagan, ya'ni birinchi chaqiruv darhol so'rov yuboradi.
_hello_attempt: Dict[str, float] = {"at": -HELLO_RETRY_SEC}


def _connect_path():
    from chaqimchi_ai.local import paths

    return paths.data_dir() / CONNECT_STATE


def fingerprint() -> str:
    """Qurilmaning barqaror izi.

    Bulut buni ikki narsa uchun ishlatadi: bir xil kompyuter qayta
    ulanganda yangi qator yaratmaslik, va ulanish tokeni sizib ketsa
    uni BOSHQA mashinada ishlatib bo'lmasligi uchun.

    Manbalar ataylab bir nechta: kompyuter nomi o'zgarishi mumkin,
    lekin protsessor va mashina identifikatori bilan birga olinganda
    natija amalda barqaror bo'ladi.
    """
    parts = [platform.node() or "", platform.machine() or "", platform.processor() or ""]
    if os.name == "nt":
        # Windows'da MachineGuid — qayta o'rnatishgacha o'zgarmaydi.
        try:
            import winreg  # type: ignore[import-not-found]

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                parts.append(str(winreg.QueryValueEx(key, "MachineGuid")[0]))
        except Exception:  # noqa: BLE001 - reyestr yopiq bo'lsa nom yetadi
            logger.debug("MachineGuid o'qilmadi — nom bo'yicha iz ishlatiladi")
    import hashlib

    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _read_connect_state() -> Dict[str, Any]:
    path = _connect_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_connect_state(state: Dict[str, Any]) -> None:
    try:
        _connect_path().write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.warning("Ulanish holati saqlanmadi: %s", exc)


def hello(cloud_url: str) -> Optional[Dict[str, Any]]:
    """Qurilma o'zini bulutga tanishtiradi va ulanish havolasini oladi.

    `None` qaytsa — bulut bu oqimni bilmaydi (eski versiya yoki bayroq
    o'chirilgan).  Bunday holda chaqiruvchi ESKI yo'lga (sehrgar +
    pairing kodi) tushadi; shu tufayli yangi dasturni eski bulut bilan
    ham chiqarish mumkin.
    """
    base = normalise_url(cloud_url)
    body = {
        "fingerprint": fingerprint(),
        "label": device_label(),
        "product_name": "Chaqimchi Windows",
        "app_version": __version__,
        "os_name": f"{platform.system()} {platform.release()}".strip(),
        "local_ip": _local_ip(),
    }
    try:
        with httpx.Client(timeout=TIMEOUT_SEC) as client:
            response = client.post(f"{base}/api/v1/public/device-hello", json=body)
    except httpx.HTTPError as exc:
        logger.info("device-hello yuborilmadi: %s", exc)
        _hello_failure["reason"] = "network"
        return None
    if response.status_code == 404:
        # Bulut bu oqimni bilmaydi (eski versiya/bayroq o'chiq) — bu
        # "internet yo'q" EMAS.
        _hello_failure["reason"] = "unsupported"
        return None
    if response.status_code >= 400:
        logger.info("device-hello rad etildi: %s", response.status_code)
        _hello_failure["reason"] = "rate_limited" if response.status_code == 429 else "unavailable"
        return None
    _hello_failure["reason"] = ""
    payload = response.json()
    lifetime = int(payload.get("expires_in_sec") or 0)
    state = {
        "cloud_url": base,
        "connect_token": payload.get("connect_token", ""),
        "connect_url": payload.get("connect_url", ""),
        "panel_url": payload.get("panel_url", ""),
        "verify_code": payload.get("verify_code", ""),
        # Muddat MUTLAQ vaqtda saqlanadi.  Qolgan soniyalar yozilsa
        # kompyuter bir kecha o'chib turgach fayl hamon "tirik"
        # ko'rinardi va egaga o'lik havola ko'rsatilardi.
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=lifetime)).isoformat(),
        "fingerprint": body["fingerprint"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_connect_state(state)
    return state


def _local_ip() -> str:
    """Do'kon tarmog'idagi manzil — egasi qaysi kompyuter ekanini tanisin.

    Tashqi manzilga UDP soket ochiladi, lekin hech narsa yuborilmaydi:
    bu marshrutlash jadvalidan "qaysi interfeys" degan javobni olishning
    eng ishonchli yo'li.
    """
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.settimeout(0.4)
            probe.connect(("8.8.8.8", 80))
            return str(probe.getsockname()[0])
    except OSError:
        return ""


def handover() -> Optional[PairedSite]:
    """Tasdiqni tekshiradi va hisob ma'lumotlarini oladi.

    `None` — hali tasdiqlanmagan yoki havola eskirgan (bunda holat
    fayli tozalanadi va chaqiruvchi yangi `hello` qiladi).
    """
    state = _read_connect_state()
    token = state.get("connect_token")
    if not token:
        return None
    base = normalise_url(str(state.get("cloud_url") or default_cloud_url()))
    try:
        with httpx.Client(timeout=TIMEOUT_SEC) as client:
            response = client.post(
                f"{base}/api/v1/public/device-handover",
                json={"connect_token": token, "fingerprint": state.get("fingerprint", "")},
            )
    except httpx.HTTPError as exc:
        logger.debug("device-handover yuborilmadi: %s", exc)
        return None
    if response.status_code >= 400:
        # 404 — havola topilmadi; qayta `hello` qilish kerak.
        _connect_path().unlink(missing_ok=True)
        return None
    payload = response.json()
    status_value = payload.get("status")
    if status_value == "pending":
        return None
    if status_value in {"expired", "already_used"}:
        _connect_path().unlink(missing_ok=True)
        return None

    # `PairedSite` da token YO'Q va bo'lmasligi ham kerak: uni panel
    # ham, log ham ko'rmasin — u faqat configga yoziladi.
    site = PairedSite(
        site_id=str(payload["site_id"]),
        device_id=str(payload["device_id"]),
        cloud_url=str(payload.get("cloud_url") or base),
    )
    config_store.update(
        "cloud_sync",
        {
            "enabled": True,
            "url": site.cloud_url,
            "site_id": site.site_id,
            "device_id": site.device_id,
            "device_token": str(payload["device_token"]),
            "panel_url": payload.get("panel_url", ""),
        },
    )
    _connect_path().unlink(missing_ok=True)
    clear_auto_pair_error()
    logger.info("Bulutga ulandi: sayt %s", site.site_id)
    return site


#: Oxirgi `hello` muvaffaqiyatsizligining SABABI.  Panel shu bo'yicha
#: halol matn tanlaydi: avval har qanday 4xx/5xx (rate limit, 503, 404)
#: "Internet yo'q" bo'lib chiqar — internet joyida bo'lgan mijozga
#: internetni tekshirishni maslahat berardik.
_hello_failure: Dict[str, str] = {"reason": ""}


def connect_state() -> Dict[str, Any]:
    """Lokal holat sahifasi uchun: havola va tekshiruv kodi."""
    state = _read_connect_state()
    return {
        "connect_url": state.get("connect_url", ""),
        "verify_code": state.get("verify_code", ""),
        "panel_url": state.get("panel_url", ""),
        "hello_error": _hello_failure.get("reason", ""),
    }


def panel_url() -> str:
    """Bulut panelining manzili.

    Ulangan bo'lsa — bulut aytgan manzil (u `hello` va `/edge/config`
    orqali keladi); aks holda build vaqtidagi API manzilidan tuziladi.
    """
    raw = config_store.read_raw().get("cloud_sync") or {}
    stored = str(raw.get("panel_url") or "")
    if stored.startswith("http"):
        return stored
    # Bulut hali aytmagan bo'lsa API manzilidan chiqaramiz.  Bu holat
    # haqiqiy: pairing kod bilan o'rnatilgan qurilma birinchi
    # `/edge/config` gacha ulangan, lekin panel manzilini bilmaydi.
    base = str(raw.get("url") or default_cloud_url())
    return f"{_panel_host(base)}/owner" if base else ""


def _panel_host(api_base: str) -> str:
    """`https://api.chaqimchi.uz` → `https://app.chaqimchi.uz`.

    Panel API bilan BOSHQA xostda: `api.` faqat `/api/*` ni o'tkazadi va
    `/owner` uchun 404 beradi (`deploy/Caddyfile.chaqimchi`).  Almashuvsiz
    mijozga o'lik havola ko'rsatilardi.

    Tanib bo'lmaydigan manzil (masalan `http://127.0.0.1:8750` — ishlab
    chiqish) o'zgarishsiz qoladi: u yerda panel ham shu xostda.
    """
    base = api_base.rstrip("/")
    parts = urlparse(base)
    host = parts.hostname or ""
    if not host.startswith("api."):
        return base
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://app.{host[4:]}{port}"


def _connect_is_live(state: Dict[str, Any]) -> bool:
    if not state.get("connect_url"):
        return False
    raw = str(state.get("expires_at") or "")
    if not raw:
        return False
    try:
        expires = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    # Bir daqiqalik zaxira: egaga havola berilib, u ochguncha muddati
    # tugab qolmasin.
    return expires - timedelta(seconds=60) > datetime.now(timezone.utc)


def is_connected() -> bool:
    raw = config_store.read_raw().get("cloud_sync") or {}
    return bool(raw.get("enabled") and raw.get("device_token"))


def ensure_connect_state(cloud_url: str = "") -> Dict[str, Any]:
    """Tirik ulanish havolasini qaytaradi, kerak bo'lsa yangisini oladi."""
    if is_connected():
        return {}
    state = _read_connect_state()
    if _connect_is_live(state):
        return connect_state()
    fresh = hello(cloud_url or default_cloud_url())
    return connect_state() if fresh else {}


def poll_connection() -> Optional[PairedSite]:
    """Ulanish oqimini bir qadam oldinga suradi.

    Fon siklidan har 20 soniyada chaqiriladi.  Uchta holat bor:
    ulangan (hech nima qilinmaydi), havola tirik (tasdiq so'raladi),
    havola yo'q yoki eskirgan (yangisi olinadi).

    Egasi tasdiqlagan payt shu yerda "ulandi" ga o'tiladi — mijoz
    do'kon kompyuteriga qaytib borishi shart emas.
    """
    if is_connected():
        return None
    state = _read_connect_state()
    if _connect_is_live(state):
        return handover()
    # Yangi havola so'rash siyrak: bulut bu oqimni bilmasa (bayroq
    # o'chirilgan yoki eski versiya) har 20 soniyada 404 olib turishning
    # ma'nosi yo'q — dastur baribir sehrgar bilan ishlayveradi.
    now = time.monotonic()
    if now - _hello_attempt["at"] < HELLO_RETRY_SEC:
        return None
    _hello_attempt["at"] = now
    hello(default_cloud_url())
    return None


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
            "Cloud serverga ulanib bo'lmadi. Internetni tekshiring va qayta urinib ko'ring.",
            retryable=True,
        ) from exc

    if response.status_code == 400:
        raise PairingError(
            "Bu kod ishlamadi — muddati o'tgan yoki allaqachon ishlatilgan. "
            "Admin paneldan yangi kod oling."
        )
    if response.status_code >= 400:
        logger.warning("Claim rad etildi: %s %s", response.status_code, response.text[:200])
        # 5xx — serverdagi vaqtinchalik muammo, kod aybdor emas.
        raise PairingError(
            f"Cloud so'rovni rad etdi (kod {response.status_code}).",
            retryable=response.status_code >= 500,
        )

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
    clear_auto_pair_error()
    logger.info("Cloudga ulandi: site=%s device=%s", site_id, device_id)
    return PairedSite(site_id=site_id, device_id=device_id, cloud_url=safe_url)


#: O'rnatuvchi fayl nomidan olgan pairing kodni shu faylga qoldiradi.
#: Dastur birinchi ishga tushishda uni o'qiydi va **o'chiradi**: kod bir
#: martalik, diskda qolib ketishining ma'nosi yo'q.
PAIRING_HANDOFF = "pairing.txt"

#: Avtomatik ulanish xatosi shu faylda qoladi va sehrgarda ko'rinadi.
#:
#: Bungacha xato faqat log'ga yozilardi: mijoz o'rnatib bo'lgach "ulandi"
#: deb o'ylab qolardi, cloud panelida esa hech narsa paydo bo'lmasdi.
#: Eng ko'p uchraydigan sabab — kod 48 soatda eskirishi (mijoz faylni
#: bugun yuklab, ertaga o'rnatadi).
PAIRING_ERROR_FILE = "pairing-error.json"


def _error_path():
    from chaqimchi_ai.local import paths

    return paths.data_dir() / PAIRING_ERROR_FILE


def record_auto_pair_error(reason: str, *, retryable: bool) -> None:
    try:
        _error_path().write_text(
            json.dumps(
                {
                    "reason": reason,
                    "retryable": retryable,
                    "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError:  # pragma: no cover - diskka yozib bo'lmasa ham ishlash davom etsin
        logger.warning("Ulanish xatosi yozilmadi", exc_info=True)


def clear_auto_pair_error() -> None:
    try:
        _error_path().unlink(missing_ok=True)
    except OSError:  # pragma: no cover
        pass


def auto_pair_error() -> Optional[Dict[str, Any]]:
    """Oxirgi avtomatik ulanish xatosi (bo'lsa)."""
    path = _error_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("reason"):
        return None
    return data


def default_cloud_url() -> str:
    """O'rnatuvchi bilan kelgan cloud manzili.

    Qurish paytida qo'yiladi (`build_windows_payload.py`).  Mijoz uni
    qo'lda yozmasligi kerak — u qaysi serverga ulanishini bilmaydi ham.
    """
    return os.environ.get("CHAQIMCHI_DEFAULT_CLOUD_URL", "").strip()


def auto_pair() -> Optional[PairedSite]:
    """O'rnatuvchi qoldirgan kod bilan avtomatik ulanadi.

    Mijoz 6 ta belgini qo'lda ko'chirmasligi uchun: admin panel
    `...?code=A1B2C3` havolasini beradi, brauzer faylni shu kod bilan
    saqlaydi, o'rnatuvchi esa kodni nomdan ajratib olib shu faylga
    yozadi.

    Xato bo'lsa **jimgina qaytadi**: sehrgar kodni odatdagidek so'raydi.
    Ya'ni bu qulaylik, majburiyat emas — shuning uchun bu yerda hech
    qanday xato mijozga ko'rsatilmaydi.
    """
    from chaqimchi_ai.local import paths

    handoff = paths.data_dir() / PAIRING_HANDOFF
    if not handoff.is_file():
        return None
    if status()["connected"]:
        handoff.unlink(missing_ok=True)
        clear_auto_pair_error()
        return None

    try:
        code = handoff.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return None

    cloud_url = default_cloud_url()
    if not cloud_url:
        logger.info("Avtomatik ulanish o'tkazildi: cloud manzili sozlanmagan")
        record_auto_pair_error(
            "Bu paketda cloud manzili yo'q — dastur qaysi serverga ulanishini bilmaydi. "
            "Yangi o'rnatuvchini saytdan yuklab oling.",
            retryable=False,
        )
        return None

    try:
        site = claim(code, cloud_url)
    except PairingError as exc:
        logger.info("Avtomatik ulanish bajarilmadi (%s) — sehrgar kodni so'raydi", exc)
        # Faylni **qoldiramiz**: internet hali yo'q bo'lishi mumkin,
        # keyingi ishga tushishda qayta urinib ko'ramiz.  Sababni esa
        # sehrgar ko'rsatadi — bungacha u faqat log'da qolardi va mijoz
        # "ulandi" deb o'ylab yurardi.
        record_auto_pair_error(str(exc), retryable=getattr(exc, "retryable", False))
        return None

    handoff.unlink(missing_ok=True)
    logger.info("Avtomatik ulandi: site=%s", site.site_id)
    return site


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
        # Sehrgar maydonini oldindan to'ldiradi: mijoz server manzilini
        # yodda tutmaydi va uni qo'lda yozishi kerak emas.
        "default_cloud_url": default_cloud_url(),
        "cloud_url": raw.get("url") if connected else None,
        "site_id": raw.get("site_id") if connected else None,
        "owner_url": f"{raw.get('url')}/owner" if connected else None,
        "app_version": __version__,
        # Ulanmagan bo'lsa — nega ulanmagani.  Sehrgar shuni ko'rsatadi.
        "auto_pair_error": None if connected else auto_pair_error(),
    }


#: `outbox.priority` — `severity` dan kelib chiqadi (`chaqimchi_ai/outbox.py`):
#: critical=30, warning=20, qolgani=10.  "Yo'qolgan kritik hodisa 0"
#: mezoni aynan shu chegara bilan o'lchanadi.
CRITICAL_PRIORITY = 30


def outbox_stats() -> Dict[str, Any]:
    """Navbat holati: yuborilmaganlar, kritiklar va tashlanganlar.

    Baza **faqat o'qish** rejimida ochiladi: uni retail zanjiri yozadi va
    panel uni qulflab qo'ymasligi kerak.

    Nega alohida funksiya: bungacha bitta `SELECT COUNT(*) FROM outbox`
    ishlatilardi — `WHERE sent_at IS NULL` siz.  `acknowledge()` yozuvni
    o'chirmaydi, `sent_at` qo'yadi va `prune()` uni ikki kun saqlaydi
    (panel kunlik hisobotni shu bazadan o'qiydi).  Natijada muvaffaqiyatli
    yuborilgan hodisalar ham "yuborilmagan" bo'lib sanalardi: panel
    bekordan "N hodisa yuborilmagan — internetni tekshiring" deb
    qo'rqitardi va heartbeat cloudga shishgan raqam yuborardi.
    """
    import sqlite3

    from chaqimchi_ai.local import paths

    empty: Dict[str, Any] = {
        "pending": 0,
        "critical": 0,
        "poisoned": 0,
        "poisoned_reasons": [],
    }
    db = paths.outbox_path()
    if not db.is_file():
        return empty
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)
        try:
            pending, critical = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(priority >= ?), 0) "
                "FROM outbox WHERE sent_at IS NULL",
                (CRITICAL_PRIORITY,),
            ).fetchone()
            # `dead_letter` — umidsiz deb tashlangan hodisalar, ya'ni
            # BUTUNLAY yo'qolganlar.  Jadval eski bazada bo'lmasligi mumkin.
            try:
                poisoned = int(
                    conn.execute("SELECT COUNT(*) FROM dead_letter").fetchone()[0]
                )
                # Sababsiz raqam diagnostika bermaydi: 2730 ta tashlangan
                # hodisa ko'rinardi-yu, NEGA tashlangani na panelda, na
                # cloudda yozilmasdi.  Eng ko'p uchragan uch sabab yetadi.
                reasons = [
                    f"{int(count)}× {str(error or 'sabab yozilmagan')[:120]}"
                    for error, count in conn.execute(
                        "SELECT last_error, COUNT(*) c FROM dead_letter "
                        "GROUP BY last_error ORDER BY c DESC LIMIT 3"
                    )
                ]
            except sqlite3.Error:
                poisoned = 0
                reasons = []
            return {
                "pending": int(pending or 0),
                "critical": int(critical or 0),
                "poisoned": poisoned,
                "poisoned_reasons": reasons,
            }
        finally:
            conn.close()
    except sqlite3.Error:
        return {"pending": None, "critical": None, "poisoned": None, "poisoned_reasons": []}


def pending_events() -> Optional[int]:
    """Cloudga **yuborilmagan** hodisalar soni.

    Bu raqam o'sib borsa — aloqa uzilgan.  Panel shuni ko'rsatadi, chunki
    "ulangan" yozuvi turgani holda hodisalar to'planib qolishi mumkin.
    """
    return outbox_stats()["pending"]
