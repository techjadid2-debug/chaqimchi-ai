"""Bulutdan buyurilgan topshiriqlarni bajarish.

Kamera qidirish do'kon tarmog'idan bajarilishi shart: WS-Discovery
multicast, /24 sweep va xususiy IP ga SOAP.  Bulut sahifasi u yerga
kira olmaydi va kirmasligi ham kerak (lokal API ataylab faqat
`127.0.0.1` ni qabul qiladi).

Shuning uchun bulut heartbeat javobida BUYRUQ yuboradi, bu modul esa
uni shu kompyuterda bajarib, natijani qaytaradi.

Ikki narsa ataylab shunday:

* **Ish alohida oqimda.** Skanerlash 90 soniyagacha cho'zilishi mumkin,
  heartbeat esa 25 soniyada javob berishi kerak.  Bir halqada bo'lsa
  bulut qurilmani "oflayn" deb belgilardi va jonli ko'rish uzilardi.
* **Navbat xotirada, diskda emas.** `live-request.json` fayl orqali
  ketadi, chunki uni BOSHQA jarayon (retail zanjiri) yozadi.  Topshiriq
  esa shu jarayonning o'zida bajariladi — fayl kerak emas va qayta
  ishga tushgach qolib ketgan axlat ham bo'lmaydi (bulut uni muddati
  bilan `failed` qiladi, bu to'g'ri xatti-harakat).
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import httpx

from chaqimchi_ai.local import camera_probe, cloud_link, config_store, onvif_client

logger = logging.getLogger(__name__)

#: Bir vaqtda bitta topshiriq.  Bulut ham bittasiga ruxsat beradi —
#: bu yerdagi chegara faqat ikki tomonlama himoya.
_QUEUE: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=1)

#: Progress xabari shuncha soniyada bir yuboriladi.  Tez-tez yuborish
#: bulutdagi cheklovga urilardi, kamdan-kam yuborish esa foydalanuvchini
#: "qotib qoldi" degan taassurotga qoldirardi.
PROGRESS_EVERY_SEC = 3.0
TIMEOUT_SEC = 20


def enqueue(job: Dict[str, Any]) -> bool:
    """Topshiriqni navbatga qo'yadi.  Navbat to'la bo'lsa `False`."""
    try:
        _QUEUE.put_nowait(job)
        return True
    except queue.Full:
        logger.info("Topshiriq o'tkazib yuborildi — oldingisi hali bajarilmoqda")
        return False


def _headers() -> Optional[Dict[str, str]]:
    raw = config_store.read_raw().get("cloud_sync") or {}
    if not (raw.get("site_id") and raw.get("device_id") and raw.get("device_token")):
        return None
    return {
        "X-Site-Id": str(raw["site_id"]),
        "X-Device-Id": str(raw["device_id"]),
        "X-Device-Token": str(raw["device_token"]),
    }


def _cloud_base() -> str:
    raw = config_store.read_raw().get("cloud_sync") or {}
    return str(raw.get("url") or "").rstrip("/")


def _post(path: str, payload: Dict[str, Any], *, method: str = "POST") -> None:
    headers = _headers()
    base = _cloud_base()
    if not headers or not base:
        return
    try:
        with httpx.Client(timeout=TIMEOUT_SEC) as client:
            client.request(method, f"{base}{path}", json=payload, headers=headers)
    except httpx.HTTPError as exc:
        logger.debug("Topshiriq xabari yuborilmadi: %s", exc)


def _send_frame(job_id: str, jpeg: bytes) -> None:
    headers = _headers()
    base = _cloud_base()
    if not headers or not base or not jpeg:
        return
    try:
        with httpx.Client(timeout=TIMEOUT_SEC) as client:
            client.put(
                f"{base}/api/v1/edge/jobs/{job_id}/frame",
                content=jpeg,
                headers={**headers, "Content-Type": "image/jpeg"},
            )
    except httpx.HTTPError as exc:
        logger.debug("Sinov kadri yuborilmadi: %s", exc)


def _reporter(job_id: str) -> Callable[[int, str], None]:
    """Progressni bulutga yuboradi, lekin juda tez-tez emas."""
    last = {"at": 0.0}

    def report(percent: int, note: str = "") -> None:
        now = time.monotonic()
        if now - last["at"] < PROGRESS_EVERY_SEC and percent < 100:
            return
        last["at"] = now
        _post(f"/api/v1/edge/jobs/{job_id}/progress", {"percent": percent, "note": note})

    return report


# ── Topshiriq turlari ────────────────────────────────────────────────


def _run_lan_scan(_: Dict[str, Any], report: Callable[[int, str], None]) -> Dict[str, Any]:
    from chaqimchi_ai.discovery import discover_cameras_all

    report(15, "Tarmoq tekshirilmoqda…")
    found = asyncio.run(discover_cameras_all(timeout_sec=3.0))
    report(90, f"{len(found)} ta manzil topildi")
    return {
        "streams": [
            {
                "ip": item.get("ip", ""),
                "vendor_hint": item.get("vendor_hint") or "",
                "has_onvif": bool(item.get("has_onvif")),
                "has_rtsp": bool(item.get("has_rtsp")),
                "rtsp_port": item.get("rtsp_port"),
                "onvif_port": item.get("onvif_port"),
            }
            for item in found
        ]
    }


def _run_onvif(params: Dict[str, Any], report: Callable[[int, str], None]) -> Dict[str, Any]:
    host = str(params.get("host") or "").strip()
    report(20, f"{host} bilan bog'lanilmoqda…")
    answer = onvif_client.describe(
        host,
        username=str(params.get("username") or ""),
        password=str(params.get("password") or ""),
        port=int(params.get("port") or 0),
        xaddr=str(params.get("xaddr") or ""),
    )
    if not answer.ok:
        raise RuntimeError(answer.error or answer.hint or "ONVIF javob bermadi")

    profiles = onvif_client.rank_profiles(answer.profiles)
    report(60, f"{len(profiles)} ta oqim topildi")
    streams: List[Dict[str, Any]] = []
    for index, profile in enumerate(profiles[: camera_probe.MAX_ONVIF_PROFILE_TRIES]):
        uri = onvif_client.with_credentials(
            profile.uri, str(params.get("username") or ""), str(params.get("password") or "")
        )
        probe = camera_probe.grab_frame(uri, timeout_sec=camera_probe.SCAN_TIMEOUT_SEC)
        streams.append(
            {
                "name": profile.name or f"Oqim {index + 1}",
                "encoding": profile.encoding,
                "width": profile.width,
                "height": profile.height,
                "works": bool(probe.ok),
                "warning": "" if probe.ok else (probe.hint or probe.error or ""),
                "uri": uri,
            }
        )
        report(60 + (index + 1) * 12, f"{index + 1}-oqim tekshirildi")
    return {
        "device": {
            "brand": answer.device.get("brand", ""),
            "model": answer.device.get("model", ""),
        },
        "advice": onvif_client.compatibility_note(answer.profiles),
        "streams": streams,
    }


def _run_channels(params: Dict[str, Any], report: Callable[[int, str], None]) -> Dict[str, Any]:
    """NVR kanallarini topadi.

    Mantiq `app.py` dan QAYTA ISHLATILADI: u sehrgarda yillar davomida
    sinalgan va uni ko'chirish ikkita nusxa yaratardi.  Import
    kechiktirilgan — `app.py` bu moduldan foydalanadi, ya'ni yuqorida
    import qilinsa aylanma bog'lanish chiqardi.
    """
    from chaqimchi_ai.local import app as local_app

    body = local_app.ScanChannelsBody(
        host=str(params.get("host") or ""),
        username=str(params.get("username") or ""),
        password=str(params.get("password") or ""),
        port=int(params.get("port") or 554),
    )
    deadline = time.monotonic() + local_app.SCAN_CHANNELS_DEADLINE_SEC
    report(20, "NVR kanallari tekshirilmoqda…")
    found = local_app._scan_via_onvif(body, deadline)
    if not found:
        report(50, "ONVIF javob bermadi — manzil shablonlari sinalmoqda")
        found = local_app._scan_via_templates(body, deadline)
    report(90, f"{len(found)} ta kanal topildi")
    return {
        "streams": [
            {
                "name": item.get("label") or f"Kanal {item.get('channel') or '?'}",
                "channel": item.get("channel"),
                "works": True,
                "uri": item.get("rtsp_url") or item.get("url") or "",
            }
            for item in found
        ]
    }


def _run_probe(params: Dict[str, Any], report: Callable[[int, str], None], job_id: str) -> Dict[str, Any]:
    url = str(params.get("rtsp_url") or "")
    if not url:
        raise RuntimeError("Sinash uchun manzil berilmadi")
    report(30, "Kamera ochilmoqda…")
    probe = camera_probe.grab_frame(url)
    if not probe.ok:
        raise RuntimeError(probe.hint or probe.error or "Kadr olinmadi")
    _send_frame(job_id, probe.jpeg or b"")
    return {"width": probe.width, "height": probe.height}


def _run_clean_chains(report: Callable[[int, str], None]) -> Dict[str, Any]:
    """Yetim AI zanjirlarini to'xtatadi (masofadan yuborilgan topshiriq).

    Nega masofadan kerak: yetim jarayonlar ESKI kodda ishlaydi va
    o'zlarini to'xtatishni bilmaydi.  Ularni faqat tashqaridan
    o'ldirish mumkin.  Bu topshiriqni esa DASTUR bajaradi — u
    yangilangan, ya'ni yetimlar hech narsani tushunishi shart emas.

    2026-08-26: do'kon kompyuterida beshta zanjir bir vaqtda ishlab
    turgan edi va ularning to'rttasi eski versiyalardan qolgan.
    """
    from chaqimchi_ai.local import chain_processes

    report(20, "Ishlab turgan zanjirlar qidirilmoqda")
    result = chain_processes.kill_chains()
    report(90, f"{result['killed']} ta to'xtatildi")
    if result["remaining"]:
        # Xato EMAS, lekin javobda ko'rinadi: qolganini admin biladi.
        logger.warning("Tozalashdan keyin %s ta zanjir qoldi", result["remaining"])
    return result


def run_one(job: Dict[str, Any]) -> None:
    """Bitta topshiriqni bajarib, natijani bulutga yuboradi."""
    job_id = str(job.get("job_id") or "")
    kind = str(job.get("kind") or "")
    params = dict(job.get("params") or {})
    report = _reporter(job_id)
    try:
        if kind == "lan_scan":
            result = _run_lan_scan(params, report)
        elif kind == "onvif":
            result = _run_onvif(params, report)
        elif kind == "channels":
            result = _run_channels(params, report)
        elif kind == "probe":
            result = _run_probe(params, report, job_id)
        elif kind == "clean_chains":
            result = _run_clean_chains(report)
        else:
            raise RuntimeError(f"Noma'lum topshiriq turi: {kind}")
    except Exception as exc:  # noqa: BLE001 - har qanday xato bulutga yetsin
        logger.info("Topshiriq bajarilmadi (%s): %s", kind, exc)
        _post(
            f"/api/v1/edge/jobs/{job_id}/result",
            {"ok": False, "error": str(exc)[:300], "result": {}},
            method="PUT",
        )
        return
    _post(f"/api/v1/edge/jobs/{job_id}/result", {"ok": True, "result": result}, method="PUT")


def run_pending() -> None:
    """Navbatni kuzatuvchi oqim (`app.py` ishga tushiradi).

    Xato USHLANADI, garchi `run_one` o'zi ham ushlasa ham: bu yerdagi
    tutqich `run_one` ning O'ZIDAGI xato (masalan kutilmagan javob
    formati) uchun.  Usiz oqim jimgina o'lib qolardi va shundan
    keyingi hamma topshiriq — egasi panelda bosgan har bir "Qidirish"
    tugmasi — javobsiz qolardi.
    """
    while True:
        job = _QUEUE.get()
        try:
            run_one(job)
        except Exception:  # noqa: BLE001 — oqim tirik qolsin
            logger.exception("Topshiriq oqimida kutilmagan xato")
        finally:
            _QUEUE.task_done()


def apply_job_requests(answer: Dict[str, Any]) -> None:
    """Heartbeat javobidagi topshiriqlarni navbatga qo'yadi."""
    for job in answer.get("job_requested") or []:
        if isinstance(job, dict):
            enqueue(job)


def start(daemon: bool = True) -> threading.Thread:
    thread = threading.Thread(target=run_pending, name="cloud-job-runner", daemon=daemon)
    thread.start()
    return thread


__all__ = ["apply_job_requests", "enqueue", "run_one", "run_pending", "start", "cloud_link"]
