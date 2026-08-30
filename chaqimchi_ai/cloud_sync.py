"""Edge outbox'ini HTTPS orqali cloudga uzatish.

Ikkita narsa ataylab shunday:

1. **429 hodisaning aybi emas.**  Cloud "sekinlash" desa, navbatdagi
   eventlarni muvaffaqiyatsiz deb belgilash noto'g'ri bo'lardi — ular
   yaxshi, faqat vaqti kelmagan.  Shuning uchun 429 da `attempts`
   oshirilmaydi, butun sikl `Retry-After` gacha to'xtaydi.
2. **Bo'sh navbat tez so'ralmaydi.**  Har 5 soniyada so'rov yuborish
   soatiga 720 ta chaqiruv demak; do'kon tinch turganda bu bekorga.
   Navbat bo'shagach oraliq `max_interval_sec` gacha ikkilanadi va
   birinchi yangi hodisada yana 5 soniyaga qaytadi.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Callable, Dict, Optional

import httpx

from chaqimchi_ai.outbox import EventOutbox, failure_reason
from chaqimchi_ai.settings import CloudSyncSettings

logger = logging.getLogger(__name__)

#: Cloud `Retry-After` bermasa shuncha kutamiz.
DEFAULT_RETRY_AFTER_SEC = 60.0

#: `Retry-After` qanchalik katta bo'lsa ham shundan oshmaydi — cloud
#: noto'g'ri sarlavha yuborsa qurilma bir kunga jim bo'lib qolmasin.
MAX_RETRY_AFTER_SEC = 900.0


def parse_retry_after(value: Optional[str]) -> float:
    """`Retry-After` sarlavhasidan soniya.  Noto'g'ri bo'lsa standart qiymat."""
    if not value:
        return DEFAULT_RETRY_AFTER_SEC
    try:
        seconds = float(value.strip())
    except ValueError:
        # HTTP-date shakli ham bo'lishi mumkin; uni tahlil qilishdan ko'ra
        # standart kutishga tushgan xavfsizroq.
        return DEFAULT_RETRY_AFTER_SEC
    if seconds <= 0:
        return DEFAULT_RETRY_AFTER_SEC
    return min(MAX_RETRY_AFTER_SEC, seconds)


def _is_permanent(exc: BaseException) -> bool:
    """Cloud so'rovni QAT'IY rad etdimi.

    4xx — hodisa yoki so'rovning o'zida ayb bor va qayta urinish hech
    narsani o'zgartirmaydi.  Ikkita istisno: 408 (timeout) va 429
    (chegara) — ular vaqt haqida, mazmun haqida emas.  429 yuqorida
    alohida ushlanadi, lekin bu yerda ham to'g'ri turishi kerak: bir
    joyda tekshirilgan qoida ikkinchi yo'l bilan chetlab o'tilmasin.
    """
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if not isinstance(status, int):
        return False
    return 400 <= status < 500 and status not in (408, 429)


class CloudEventSync:
    def __init__(
        self,
        settings: CloudSyncSettings,
        outbox: EventOutbox,
        *,
        client: Optional[httpx.AsyncClient] = None,
        health_provider: Optional[Callable[[], Dict[str, object]]] = None,
        config_applier: Optional[Callable[[Dict[str, object]], None]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.outbox = outbox
        self.client = client
        self._owns_client = client is None
        self.health_provider = health_provider
        self.config_applier = config_applier
        self._clock = clock
        self._last_heartbeat = 0.0
        #: Cloud 429 bergan bo'lsa shu vaqtgacha umuman so'rov yubormaymiz.
        self._blocked_until = 0.0
        #: Bo'sh navbatda o'sadigan kutish oralig'i.
        self._idle_interval = float(settings.interval_sec)
        #: Cloud rad etgani uchun rasmsiz/klipsiz qolgan hodisalar soni.
        #:
        #: Bu — shu jarayonning ichki hisobi (log va test uchun).  Mijozga
        #: ko'rsatiladigan raqam CLOUD tomonda sanaladi
        #: (`cloud/ratelimit.py` rad etish hisoblagichi): qurilma o'zi
        #: yiqilgan holatda ham u haqiqatni ko'rsatishda davom etadi.
        self.media_dropped = 0

    @property
    def blocked_for(self) -> float:
        """429 tufayli qancha vaqt qolgani (0 — bloklanmagan)."""
        return max(0.0, self._blocked_until - self._clock())

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "X-Site-Id": self.settings.site_id or "",
            "X-Device-Id": self.settings.device_id or "",
            "X-Device-Token": self.settings.device_token or "",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=30)
        return self.client

    async def sync_once(self) -> Dict[str, int]:
        if self.blocked_for > 0:
            return {"sent": 0, "failed": 0, "pending": len(self.outbox.pending(1))}
        rows = self.outbox.pending(self.settings.batch_size)
        if not rows:
            return {"sent": 0, "failed": 0, "pending": 0}
        client = await self._get_client()
        base = self.settings.url.rstrip("/")
        try:
            response = await client.post(
                f"{base}/api/v1/edge/events/batch",
                headers=self.headers,
                json={"events": [row["payload"] for row in rows]},
            )
            if response.status_code == 429:
                # Cloud chegarani oshirdi dedi. Eventlar aybdor emas —
                # `attempts` ni oshirsak ular keraksiz backoff'ga tushardi
                # va oxir-oqibat dead-letter'ga o'tib ketardi.
                wait = parse_retry_after(response.headers.get("Retry-After"))
                self._blocked_until = self._clock() + wait
                logger.warning("Cloud chegarasi oshdi (429) — %.0f soniyaga to'xtaymiz", wait)
                return {"sent": 0, "failed": 0, "pending": len(rows), "throttled": 1}
            response.raise_for_status()
            accepted = set(response.json().get("accepted", []))
        except Exception as exc:  # noqa: BLE001 - navbat keyingi siklda qayta urinadi
            # Tarmoq va 5xx — VAQTINCHALIK: hodisa urinishlar hisobini
            # yemasin (`outbox.fail` izohiga qarang).  Faqat cloud
            # so'rovning o'zini rad etgan bo'lsa (4xx) hodisa aybdor.
            permanent = _is_permanent(exc)
            for row in rows:
                self.outbox.fail(row["event_id"], failure_reason(exc), permanent=permanent)
            logger.warning("Cloud event sync muvaffaqiyatsiz: %s", exc)
            return {"sent": 0, "failed": len(rows), "pending": len(rows)}

        completed = []
        failed = 0
        for row in rows:
            event_id = row["event_id"]
            if event_id not in accepted:
                # Cloud butun batchni qabul qildi, LEKIN shu hodisani
                # ro'yxatga qo'shmadi — ya'ni ayb hodisada (sxema, tarif
                # filtri, buzuq maydon).  Qayta urinish uni tuzatmaydi.
                self.outbox.fail(event_id, "cloud eventni qabul qilmadi", permanent=True)
                failed += 1
                continue
            verdict = await self._upload_media(client, base, event_id, row)
            if verdict == "retry":
                failed += 1
                continue
            completed.append(event_id)
        self.outbox.acknowledge(completed)
        return {"sent": len(completed), "failed": failed, "pending": len(rows)}

    async def _upload_media(
        self,
        client: httpx.AsyncClient,
        base: str,
        event_id: str,
        row: Dict[str, object],
    ) -> str:
        """Hodisaning rasmi va klipini yuboradi.

        Qaytaradi: `"ok"` — yuborildi yoki yuboradigan narsa yo'q;
        `"dropped"` — media yo'qoldi, lekin **hodisa saqlanadi**;
        `"retry"` — vaqtinchalik xato, hodisa navbatda qolsin.

        Nega media xatosi hodisani o'ldirmasligi kerak: bu joyga kelganda
        cloud hodisani ALLAQACHON qabul qilgan (u `accepted` ro'yxatida).
        Ilgari har qanday yuklash xatosi `outbox.fail()` ga ketardi va
        butun hodisa qayta yuborilardi — cloud esa uni qayta qabul qilib,
        rasmni yana rad etardi.  2026-08-26 da shu halqa jonli do'konda
        3 soatda 6 315 ta bekor so'rov berdi va do'konning HAMMA rasmi
        yo'qoldi: kunlik snapshot byudjeti tugagach har urinish 429 edi.

        Shuning uchun xato ikkiga bo'linadi:

        * **4xx — qat'iy.**  429 (chegara), 403 (taqiq), 413 (hajm),
          415 (format) — qayta urinishdan hech biri o'zgarmaydi.  Media
          yo'qoladi, hodisaning o'zi esa saqlanib qoladi: raqam rasmdan
          muhimroq.
        * **5xx va tarmoq — vaqtinchalik.**  Server tiklanadi, shuning
          uchun hodisa navbatda qoladi va keyingi siklda qayta urinadi.
        """
        verdict = "ok"
        for path_key, endpoint, mime in (
            ("snapshot_path", "snapshot", "image/jpeg"),
            ("clip_path", "clip", "video/mp4"),
        ):
            raw = row.get(path_key)
            if not raw or not Path(str(raw)).is_file():
                continue
            try:
                with Path(str(raw)).open("rb") as handle:
                    upload = await client.put(
                        f"{base}/api/v1/edge/events/{event_id}/{endpoint}",
                        headers={**self.headers, "Content-Type": mime},
                        content=handle.read(),
                    )
                upload.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if 400 <= exc.response.status_code < 500:
                    self.media_dropped += 1
                    # `warning`, `info` emas: rasmsiz qolgan hodisa mijoz
                    # ko'radigan kamchilik, jimgina o'tmasligi kerak.
                    logger.warning(
                        "Media qabul qilinmadi (%s %s) — hodisa rasmsiz saqlanadi: %s",
                        endpoint,
                        exc.response.status_code,
                        event_id,
                    )
                    verdict = "dropped"
                    continue
                # 5xx — server tiklanadi, hodisa aybdor emas.
                self.outbox.fail(event_id, failure_reason(exc))
                return "retry"
            except Exception as exc:  # noqa: BLE001 — tarmoq: keyingi siklda
                self.outbox.fail(event_id, failure_reason(exc))
                return "retry"
        return verdict

    async def heartbeat_once(self) -> None:
        if self.health_provider is None:
            return
        client = await self._get_client()
        response = await client.post(
            f"{self.settings.url.rstrip('/')}/api/v1/edge/heartbeat",
            headers=self.headers,
            json=self.health_provider(),
        )
        response.raise_for_status()

    async def config_once(self) -> None:
        if self.config_applier is None:
            return
        client = await self._get_client()
        response = await client.get(
            f"{self.settings.url.rstrip('/')}/api/v1/edge/config", headers=self.headers
        )
        response.raise_for_status()
        self.config_applier(response.json())

    def next_interval(self, result: Dict[str, int]) -> float:
        """Keyingi siklgacha qancha kutish.

        Navbatda ish bo'lsa — eng tez oraliq (hodisa kech kelmasin).
        Bo'sh bo'lsa — oraliq ikkilanib boradi: tinch do'kon cloudni
        bekorga bezovta qilmasin.  429 bo'lsa blok tugagunicha kutamiz.
        """
        blocked = self.blocked_for
        if blocked > 0:
            return blocked
        floor = float(self.settings.interval_sec)
        if result.get("pending"):
            self._idle_interval = floor
        else:
            self._idle_interval = min(
                float(self.settings.max_interval_sec), max(floor, self._idle_interval) * 2
            )
        return self._idle_interval

    async def run(self, stop_requested: Optional[Callable[[], bool]] = None) -> None:
        try:
            while not (stop_requested and stop_requested()):
                delay = float(self.settings.interval_sec)
                try:
                    delay = self.next_interval(await self.sync_once())
                    now = self._clock()
                    if now - self._last_heartbeat >= self.settings.heartbeat_interval_sec:
                        # Heartbeat navbatdan mustaqil: qurilma tirikligini
                        # cloud bilishi kerak, hodisa bo'lmasa ham.
                        await self.heartbeat_once()
                        await self.config_once()
                        self._last_heartbeat = now
                        delay = min(delay, float(self.settings.heartbeat_interval_sec))
                except asyncio.CancelledError:
                    break
                except Exception:  # pragma: no cover - mustaqil fon sikli
                    logger.exception("Cloud sync siklida kutilmagan xato")
                await asyncio.sleep(delay)
        finally:
            await self.close()

    async def close(self) -> None:
        if self._owns_client and self.client is not None:
            await self.client.aclose()
        self.client = None
