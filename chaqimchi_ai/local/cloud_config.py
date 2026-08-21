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
from chaqimchi_ai.limits import SHOP_MAX_CAMERAS
from chaqimchi_ai.local import config_store, paths

logger = logging.getLogger(__name__)

#: Cloud sozlamasini shuncha soniyada bir marta so'raymiz.  60 emas, 20:
#: mijoz panelda "Jonli ko'rish" bossa qurilma buni keyingi heartbeat'da
#: biladi — kutish 60 soniyadan 20 gacha tushdi.  Har so'rov bir necha yuz
#: bayt — kuniga ~4300 ta yengil so'rov, VPS uchun sezilmas yuk.
POLL_INTERVAL_SEC = 20

TIMEOUT_SEC = 20

#: Server jonli ko'rish so'ralishini shuncha soniya kutib turadi.
#:
#: 25 soniya ataylab `POLL_INTERVAL_SEC` dan katta: kutish tugagach
#: darhol yangi so'rov ketadi, ya'ni qurilma amalda doim "eshitib"
#: turadi va bo'sh aylanish yo'qoladi.  Serverda kutish bazani
#: so'ramaydi — xotiradagi signal.
HEARTBEAT_WAIT_SEC = 25

#: Jonli kadr yuborish qadami (soniya).
LIVE_UPLOAD_INTERVAL_SEC = 2.5


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


def _cached_cameras() -> Any:
    """Keshda turgan kamera ro'yxati (bo'lmasa `None`).

    Cloud bo'sh ro'yxat yuborsa keshdagi kameralarni **saqlab qolamiz**:
    `cameras_source: "auto"` bo'lgan qurilmada bo'sh ro'yxat zanjirni
    kamerasiz qoldirardi va do'kon nazoratsiz qolardi.
    """
    try:
        data = json.loads(cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data.get("cameras") if isinstance(data, dict) else None


def apply(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Cloud sozlamasini lokal configga qo'llaydi.

    Qaytaradi: nima o'zgargani (panel va log uchun).
    """
    changed: Dict[str, Any] = {"cameras": 0, "lines": 0, "zones": 0, "limits": False}

    # Keshni HAR DOIM yozamiz va yo'lini configga qo'yamiz.
    #
    # Ilgari ikkalasi ham `if cameras:` ichida edi va bu jimgina nosozlik
    # berardi: mijoz kamerani lokal sehrgarda qo'shsa, cloudda kamera
    # ro'yxati bo'sh qoladi — ya'ni kesh umuman yozilmasdi.  Kesh esa
    # kameralardan tashqari **davomat sozlamasini** ham olib keladi
    # (`attendance.enabled`, `attendance_camera_ids`), demak xodim Face ID
    # bunday do'konda hech qachon ishlamasdi va hech qanday xato ham
    # chiqmasdi.  Yo'l qo'yilmagani esa yana battar edi: `retail/service.py`
    # standart **Linux** yo'lini qidiradi va Windows'da hech narsa topmaydi.
    cameras = [item for item in (payload.get("cameras") or []) if item.get("source")]
    to_cache = dict(payload)
    if not cameras:
        previous = _cached_cameras()
        if previous:
            to_cache["cameras"] = previous
    _write_cache(to_cache)
    config_store.update("retail", {"sotqin_config_path": str(cache_path())})
    if cameras:
        # Kameralar keshdan olinsin va revizya o'zgarganda zanjir o'zini
        # qayta ishga tushirsin — aks holda cloudda qo'shilgan kamera
        # keyingi qo'lda restartgacha tahlil qilinmasdi.
        #
        # `cameras_source: "auto"` faqat SHU YERDA qo'yiladi: cloudda
        # kamera bo'lmasa mijozning lokal ro'yxati yagona haqiqat bo'lib
        # qolishi kerak, aks holda bo'sh cloud javobi ishlab turgan
        # kameralarni o'chirib yuborardi.
        config_store.update(
            "retail",
            {
                "cameras_source": "auto",
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
    # Mijoz daqiqada kiritadi, zanjir soniyada o'ylaydi.  O'girish shu
    # yerda — bitta joyda: ikkala tomonda ham daqiqa/soniya aralashsa
    # sozlama 60 barobar xato ishlardi.
    if site.get("checkout_idle_minutes"):
        limits["checkout_idle_sec"] = int(site["checkout_idle_minutes"]) * 60
    if limits:
        config_store.update("scene", limits)
        changed["limits"] = True

    # Tarifdagi kamera soni.  Bungacha sehrgar har doim 4 ta taklif qilardi
    # va 2 kameralik tarifdagi mijoz uchinchisini qo'sha olardi.
    #
    # `min` ataylab: cloud noto'g'ri (yoki buzilgan) qiymat yuborsa ham
    # chegara apparat profilidan YUQORIGA ko'tarilmaydi.  Nol yoki
    # yo'q qiymat e'tiborsiz qoldiriladi — oflayn qurilma o'zining
    # ishlab turgan chegarasini yo'qotmasin.
    allowed = int((payload.get("product") or {}).get("max_cameras") or 0)
    if allowed > 0:
        config_store.update("retail", {"max_cameras": min(SHOP_MAX_CAMERAS, allowed)})
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

    # Navbat holati bitta so'rovda olinadi: uchta raqamning uchalasi ham
    # cloud modelida allaqachon bor edi, lekin Windows yo'li faqat
    # birinchisini (va uni ham noto'g'ri) yuborardi.
    queue = _outbox_stats()

    # Kamera boshiga holat: qaysi biri tirik, qaysi biri uzilib turibdi.
    # Faqat SON yuborilganda panel qaysi kamera o'chganini ko'rsatolmasdi.
    codecs = {
        str(item.get("id")): item.get("codec")
        for item in (config_store.read_raw().get("retail") or {}).get("cameras") or []
        if item.get("id")
    }
    cameras = [
        {
            "camera_id": str(camera_id),
            "connected": bool(item.get("connected")),
            "offline": bool(item.get("offline")),
            "reconnects": int(item.get("reconnects") or 0),
            # Format sozlamada turadi (sehrgar aniqlagan), holat faylida
            # emas — sekin ishlayotgan kameraning sababi shundan ko'rinadi.
            "codec": codecs.get(str(camera_id)),
        }
        for camera_id, item in (status.get("cameras") or {}).items()
        if isinstance(item, dict)
    ][:16]

    payload = {
        "cameras_active": int(status.get("cameras_active") or 0),
        "cameras": cameras,
        "disk_free_bytes": int(free_bytes),
        "outbox_pending": int(queue.get("pending") or 0),
        # Kritik hodisa navbatda qolib ketsa — bu oddiy kechikish emas.
        "outbox_critical_pending": int(queue.get("critical") or 0),
        # Umidsiz deb tashlanganlar: noldan katta bo'lsa hodisa BUTUNLAY
        # yo'qolgan.  "Yo'qolgan kritik hodisa 0" mezoni shu raqam bilan
        # tekshiriladi.
        "outbox_poisoned": int(queue.get("poisoned") or 0),
        # Sabab bo'lmasa raqamning foydasi yo'q: qaysi xato takrorlanayotgani
        # ko'rinmasa, tashlangan hodisani tuzatib bo'lmaydi.
        "outbox_poisoned_reasons": list(queue.get("poisoned_reasons") or [])[:3],
        # Klip yozilyaptimi: hodisa bor-u klip yo'q bo'lsa sabab shu uchta
        # sondan ko'rinadi (`unavailable` — kamera uchun yozuv manzili yo'q).
        "clips": {
            key: int((status.get("clips") or {}).get(key) or 0)
            for key in ("written", "missing", "dropped", "unavailable", "pending")
        },
        # 72 soatlik sinovning asosiy mezoni: zanjir necha marta o'zi
        # yiqilib qayta ko'tarilgan.  Cloudda bu son umuman ko'rinmasdi.
        "chain_restarts": int(status.get("restart_count") or 0),
        # Jimgina ishlamay qolishni cloud shu uchtasidan biladi:
        # `analyzed`ga nisbatan `analysis_errors` ko'p bo'lsa tahlil
        # zanjiri buzilgan, `queue_errors` noldan katta bo'lsa hodisa
        # umuman saqlanmayapti.  Ularsiz qurilma "sog'lom" ko'rinardi.
        "analyzed": int(status.get("analyzed") or 0),
        "analysis_errors": int(status.get("errors") or 0),
        "queue_errors": int(status.get("action_errors") or 0),
        "app_version": __version__,
        "product_name": "Chaqimchi Windows",
        # Server jonli ko'rish so'ralishini shuncha soniya kutib tursin.
        #
        # Bungacha panel "Jonli" tugmasini bosgach birinchi kadr 14-27
        # soniyada kelardi va eng katta ulush shu yerda edi: buyruq faqat
        # keyingi salomda ko'rinardi (`POLL_INTERVAL_SEC = 20`).  Endi
        # server so'rov kelishi bilan darhol javob beradi.
        #
        # Eski server bu maydonni e'tiborsiz qoldiradi va darhol javob
        # beradi — ya'ni yangi qurilma eski cloud bilan ham ishlayveradi.
        "wait_sec": HEARTBEAT_WAIT_SEC,
    }
    try:
        response = httpx.post(
            f"{str(raw['url']).rstrip('/')}/api/v1/edge/heartbeat",
            headers=_headers(raw),
            json=payload,
            # Kutish vaqti + javob uchun zaxira.  Aks holda o'z
            # so'rovimizni o'zimiz uzib qo'yardik.
            timeout=HEARTBEAT_WAIT_SEC + TIMEOUT_SEC,
        )
        response.raise_for_status()
        answer = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("Heartbeat yuborilmadi: %s", exc)
        return False
    # Javob ilgari umuman o'qilmasdi — shuning uchun `preview_requested`
    # Windows qurilmada ishlamasdi (botdagi /kamera yangi kadr olomasdi).
    if isinstance(answer, dict):
        apply_media_requests(answer)
    return True


#: Oxirgi muvaffaqiyatli yuborilgan ro'yxatning barmoq izi.  Ro'yxat
#: o'zgarmasa har 20 soniyada bir xil so'rov ketmasin.
_published_cameras: Dict[str, Any] = {"value": None}


def publish_cameras() -> bool:
    """Do'kondagi kamera ro'yxatini cloudga bildiradi.

    Kamera oqimi bir tomonlama edi: cloud -> qurilma.  Mijoz kamerani o'z
    kompyuteridagi sehrgarda qo'shsa, cloud ular haqida hech narsa
    bilmasdi va panelda kamera ro'yxati bo'sh qolardi — jonli ko'rish,
    do'kon xaritasi, davomat kamerasini tanlash va kamera rollari,
    to'rttasi ham jimgina ishlamasdi.

    **Manzil yuborilmaydi** — faqat ID va nom.  RTSP ichida NVR
    login/paroli bor va u do'kon tarmog'idan chiqmasligi kerak.
    """
    raw_all = config_store.read_raw()
    cloud = raw_all.get("cloud_sync") or {}
    if not cloud.get("enabled") or not cloud.get("device_token"):
        return False
    cameras = [
        {
            "camera_id": str(item.get("id")),
            "label": str(item.get("label") or item.get("id") or ""),
        }
        for item in ((raw_all.get("retail") or {}).get("cameras") or [])
        if item.get("id")
    ]
    fingerprint = json.dumps(cameras, sort_keys=True, ensure_ascii=False)
    if fingerprint == _published_cameras.get("value"):
        return False
    try:
        response = httpx.post(
            f"{str(cloud['url']).rstrip('/')}/api/v1/edge/cameras",
            headers=_headers(cloud),
            json={"cameras": cameras},
            timeout=TIMEOUT_SEC,
        )
    except httpx.HTTPError as exc:
        # Tarmoq xatosi — xesh yangilanmaydi, keyingi siklda yana urinadi.
        logger.info("Kamera ro'yxati yuborilmadi: %s", exc)
        return False
    if 400 <= response.status_code < 500 and response.status_code != 429:
        # Cloud ATAYLAB rad etdi (masalan tarif chegarasi).  Har 20
        # soniyada qayta yuborish foydasiz: ro'yxat o'zgarmaguncha javob
        # ham o'zgarmaydi.  Xesh yozib qo'yiladi, ya'ni keyingi urinish
        # faqat mijoz kamera qo'shgan/olib tashlaganda bo'ladi.
        _published_cameras["value"] = fingerprint
        logger.warning(
            "Kamera ro'yxati qabul qilinmadi (%s): %s",
            response.status_code,
            response.text[:200],
        )
        return False
    if response.status_code >= 500:
        logger.info("Kamera ro'yxati yuborilmadi: server %s", response.status_code)
        return False
    _published_cameras["value"] = fingerprint
    logger.info("Kamera ro'yxati cloudga yuborildi: %d ta", len(cameras))
    return True


def _pending_events() -> Optional[int]:
    from chaqimchi_ai.local import cloud_link

    return cloud_link.pending_events()


def _outbox_stats() -> Dict[str, Any]:
    from chaqimchi_ai.local import cloud_link

    return cloud_link.outbox_stats()


# ── Jonli ko'rish va preview (media so'rovlari) ──────────────────────────
#
# Ish taqsimoti (jarayonlar chegarasi tufayli fayl orqali):
#   heartbeat javobi     → `live-request.json`     (shu modul yozadi)
#   retail zanjiri       → `data/live/{id}.jpg`    (kadr allaqachon xotirada,
#                          faqat JPEG qilib yoziladi — yangi RTSP ulanish yo'q)
#   yuklovchi sikl       → PUT /live-frame yoki /preview (shu modul)


def live_request_path() -> Path:
    return paths.data_dir() / "live-request.json"


def live_frames_dir() -> Path:
    return paths.data_dir() / "live"


def apply_media_requests(answer: Dict[str, Any]) -> None:
    """Heartbeat javobidagi jonli/preview so'rovlarini faylga yozadi."""
    from datetime import datetime, timedelta, timezone

    requests: Dict[str, Any] = {}
    for item in answer.get("live_requested") or []:
        if isinstance(item, dict) and item.get("camera_id"):
            requests[str(item["camera_id"])] = {
                "until": str(item.get("until") or ""),
                "preview": False,
            }
    # Bir martalik preview — qisqa "jonli" deb qaraladi: bitta mexanizm.
    one_shot_until = (datetime.now(timezone.utc) + timedelta(seconds=8)).isoformat()
    for camera_id in answer.get("preview_requested") or []:
        key = str(camera_id)
        if key not in requests:
            requests[key] = {"until": one_shot_until, "preview": True}

    path = live_request_path()
    if not requests:
        # Bo'sh so'rov — fayl o'chadi; zanjir ham, yuklovchi ham tinchiydi.
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(requests, handle, ensure_ascii=False)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _active_media_requests() -> Dict[str, Dict[str, Any]]:
    from datetime import datetime, timezone

    path = live_request_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    now = datetime.now(timezone.utc)
    active: Dict[str, Dict[str, Any]] = {}
    for camera_id, item in raw.items() if isinstance(raw, dict) else []:
        try:
            until = datetime.fromisoformat(str(item.get("until")))
        except (TypeError, ValueError):
            continue
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        if until > now:
            active[str(camera_id)] = item
    return active


#: Oxirgi yuborilgan kadr fayllarining mtime'lari — o'zgarmagan kadrni
#: qayta yubormaslik uchun.
_uploaded_mtimes: Dict[str, float] = {}


def upload_media_frames() -> int:
    """Zanjir yozgan jonli kadrlarni cloudga yuboradi.  Har 2-3 soniyada.

    Qaytaradi: yuborilgan kadrlar soni.  `continue: false` javobida yoki
    preview yuborilgach kamera so'rovdan chiqariladi.
    """
    requests = _active_media_requests()
    if not requests:
        return 0
    raw = config_store.read_raw().get("cloud_sync") or {}
    if not raw.get("enabled") or not raw.get("device_token"):
        return 0

    sent = 0
    finished: list[str] = []
    for camera_id, item in requests.items():
        frame = live_frames_dir() / f"{camera_id}.jpg"
        if not frame.is_file():
            continue
        try:
            mtime = frame.stat().st_mtime
        except OSError:
            continue
        if _uploaded_mtimes.get(camera_id) == mtime:
            continue  # yangi kadr hali yozilmagan
        try:
            content = frame.read_bytes()
        except OSError:
            continue
        if not content:
            continue
        endpoint = "preview" if item.get("preview") else "live-frame"
        try:
            response = httpx.put(
                f"{str(raw['url']).rstrip('/')}/api/v1/edge/cameras/{camera_id}/{endpoint}",
                headers={**_headers(raw), "Content-Type": "image/jpeg"},
                content=content,
                timeout=TIMEOUT_SEC,
            )
            response.raise_for_status()
            answer = response.json() if response.content else {}
        except (httpx.HTTPError, ValueError) as exc:
            logger.info("Jonli kadr yuborilmadi (%s): %s", camera_id, exc)
            continue
        _uploaded_mtimes[camera_id] = mtime
        sent += 1
        if item.get("preview") or answer.get("continue") is False:
            finished.append(camera_id)

    if finished:
        remaining = {key: value for key, value in requests.items() if key not in finished}
        path = live_request_path()
        if remaining:
            path.write_text(json.dumps(remaining, ensure_ascii=False), encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
    return sent


def heatmap_dir() -> Path:
    return paths.data_dir() / "heatmap"


def upload_heatmaps() -> int:
    """Zanjir yozgan issiqlik to'rlarini cloudga jo'natadi.

    Fayl 200 kelgandagina o'chadi — internet uzilganda ma'lumot diskda
    kutib turadi (soatlik fayllar jamlanib boradi, yo'qolmaydi).
    """
    directory = heatmap_dir()
    if not directory.is_dir():
        return 0
    files = sorted(directory.glob("*.json"))
    if not files:
        return 0
    raw = config_store.read_raw().get("cloud_sync") or {}
    if not raw.get("enabled") or not raw.get("device_token"):
        return 0

    items = []
    consumed: list[Path] = []
    for path in files[:24]:  # bitta so'rovda ko'pi bilan sutkalik to'plam
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            path.unlink(missing_ok=True)  # buzuq fayl qayta-qayta urilmasin
            continue
        items.append(payload)
        consumed.append(path)
    if not items:
        return 0
    try:
        response = httpx.post(
            f"{str(raw['url']).rstrip('/')}/api/v1/edge/heatmap",
            headers=_headers(raw),
            json={"items": items},
            timeout=TIMEOUT_SEC,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.info("Issiqlik to'ri yuborilmadi: %s", exc)
        return 0
    for path in consumed:
        path.unlink(missing_ok=True)
    return len(consumed)


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
