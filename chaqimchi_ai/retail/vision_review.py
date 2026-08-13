"""Hodisadan keyin kadrni ko'rish agentiga yuborish (8.3).

Do'kon analitikasi "kassada 6 kishi navbat" yoki "kamera yopildi" deydi —
raqam va tur.  Do'kon egasiga esa **jumla** kerak: "kassa oldida ikki kishi
janjallashmoqda", "kamerani qop bilan yopib qo'yishdi".  Shu jumlani ko'rish
agenti yozadi, lekin u har kadrni ko'ra olmaydi: har chaqiruv pul.

Shu sabab bu modul zanjirning **oxirida** turadi va faqat qoida `ai_review`
harakatini so'ragan hodisadan keyin ishga tushadi.  Ya'ni qurilmadagi arzon
model "nimadir bo'ldi" deb topadi, qimmat model esa faqat o'sha lahzani
ko'radi.

## Uch qavatli tormoz

1. **Qoida.**  `ai_review` standart harakatlar ichida yo'q — uni sotuvchi
   ataylab yozishi kerak (odatda `camera_tampered` va `after_hours_presence`
   uchun).
2. **Oraliq.**  Bitta kamera uchun `min_interval_sec` (standart 5 daqiqa).
   Hisob **navbatga qo'yilganda** yangilanadi, javob kelganda emas: aks holda
   ketma-ket kelgan uch hodisa uchta chaqiruv tug'dirardi.
3. **Limit.**  Kunlik va oylik sanoq — `VisionAgent` ning o'z hisobi
   (`data/vision_usage.db`, diskda).

## Nega alohida oqim

`analyze()` — tarmoq chaqiruvi, sekundlar oladi.  Uni inferens halqasidan
chaqirish o'sha vaqtda **hamma** kamerani to'xtatib qo'yardi: navbat, dwell,
kirish-chiqish sanog'i — hammasi AI javobini kutardi.  Shuning uchun kadr
navbatga tushadi va bu yerdagi oqim uni o'z vaqtida yuboradi.

Navbat **chegaralangan** (`queue_size`): AI sekinlashsa yoki tarmoq yiqilsa
kadrlar to'planib xotirani yeb qo'ymasin.  To'lgan navbatda yangi so'rov
tashlanadi va `dropped` da ko'rinadi — kadrni yo'qotgan yaxshi, qurilmani
yo'qotgandan ko'ra.

## Natija qayerga boradi

Xulosa yangi `ai_review` hodisasi bo'lib **outbox**ga tushadi, ya'ni oddiy
yo'ldan cloudga ketadi va u yerdan Telegramga (8.4).  Edge tomonda ikkinchi
Telegram mijozi yo'q — bitta xabar, bitta manba.

`ogohlantirish: false` bo'lsa hodisa `info` bo'lib qoladi: arxivda turadi,
lekin mijozning telefonini bezovta qilmaydi.  Bu ataylab — AI "hammasi
joyida" deganini ham bilish kerak, lekin uni xabar qilib yuborish shovqin.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, Optional

from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.vision_agent import (
    BudgetExceeded,
    VisionAgent,
    VisionAgentError,
    VisionResult,
    encode_frame,
)

logger = logging.getLogger(__name__)

#: Navbatda kutadigan kadrlar soni.  Oraliq allaqachon kamera boshiga 5
#: daqiqada bitta chaqiruvga ruxsat beradi, ya'ni bu navbat 8 kameraning
#: bir vaqtda kelgan hodisasi uchun yetadi.
DEFAULT_QUEUE_SIZE = 8

#: Hodisa turiga qarab beriladigan savol.  Kontekstsiz "nima bo'layapti?"
#: dan ko'ra aniq savol aniqroq javob beradi.
QUESTIONS: Dict[str, str] = {
    "camera_tampered": (
        "Bu kamera yopilgan, burilgan yoki ko'rinishi buzilgan bo'lishi mumkin. "
        "Kadrda nima ko'rinayapti?"
    ),
    "after_hours_presence": (
        "Do'kon yopiq bo'lishi kerak edi, lekin harakat sezildi. "
        "Kadrda kim bor va nima qilyapti?"
    ),
    "queue_threshold_exceeded": "Kassada navbat uzaydi. Kadrda nima bo'layapti?",
    "dwell_exceeded": "Bir odam bitta joyda uzoq turibdi. Kadrda nima bo'layapti?",
    "occupancy_exceeded": "Odam soni odatdagidan ko'p. Kadrda nima bo'layapti?",
    "zone_entered": "Taqiqlangan zonada harakat sezildi. Kadrda nima bo'layapti?",
}

DEFAULT_QUESTION = "Kadrda nima bo'layapti?"

#: Severity tartibi — AI ogohlantirsa hodisa shundan pastga tushmaydi.
_RANK = {"info": 0, "warning": 1, "critical": 2}


def question_for(event_type: str) -> str:
    return QUESTIONS.get(event_type, DEFAULT_QUESTION)


def review_event(source: EdgeEvent, result: VisionResult) -> EdgeEvent:
    """AI xulosasidan cloudga ketadigan hodisa yasaydi.

    Jiddiylik AI qo'lida, lekin **faqat yuqoriga**: manba hodisasi `critical`
    bo'lsa (kamera yopilgan) AI "oddiy holat" deb uni pasaytira olmaydi.
    Model xato qilishi mumkin, buzilgan kamera esa fakt.
    """
    if result.ogohlantirish:
        severity = source.severity if _RANK.get(source.severity, 0) >= 1 else "warning"
    else:
        severity = "info"
    return EdgeEvent(
        event_type="ai_review",
        severity=severity,
        camera_id=source.camera_id,
        track_id=source.track_id,
        zone=source.zone,
        line=source.line,
        occupancy=result.odamlar,
        metadata={
            "tavsif": result.tavsif,
            "sabab": result.sabab,
            "ogohlantirish": result.ogohlantirish,
            "odamlar": result.odamlar,
            "source_event_id": source.event_id,
            "source_event_type": source.event_type,
            "cost_usd": round(result.cost_usd, 6),
            "latency_ms": round(result.latency_ms, 1),
        },
    )


class VisionReviewer:
    """Kadrni navbatga qo'yadi va o'z oqimida AI ga yuboradi.

    `sink` — `RetailPipeline` ishlatadigan bilan **bitta** obyekt
    (`OutboxSink`), shuning uchun xulosa boshqa hodisalar bilan bir yo'ldan
    ketadi: outbox → cloud sync → Telegram.
    """

    def __init__(
        self,
        agent: VisionAgent,
        sink: Callable[[str, EdgeEvent], None],
        *,
        queue_size: int = DEFAULT_QUEUE_SIZE,
        encode: Callable[..., bytes] = encode_frame,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.agent = agent
        self.sink = sink
        self._encode = encode
        self._clock = clock
        self._queue: "queue.Queue[Optional[tuple[EdgeEvent, bytes]]]" = queue.Queue(
            maxsize=max(1, queue_size)
        )
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        #: Kamera bo'yicha keyingi ruxsat vaqti.  Navbatga qo'yishda
        #: yoziladi — javobni kutmaydi.
        self._next_allowed: Dict[str, float] = {}
        self._sent = 0
        self._done = 0
        self._dropped = 0
        self._throttled = 0
        self._over_budget = 0
        self._failed = 0
        self._cost_usd = 0.0

    # ── Hayotiy sikl ─────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._work, name="vision-review", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Navbatni yopadi va oqimni kutadi.

        Ishlab turgan chaqiruv tugatiladi (allaqachon pul to'langan) —
        keyingilari yuborilmaydi.
        """
        thread = self._thread
        if thread is None:
            return
        self._thread = None
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            # Navbat to'la: eng eskisini olib, to'xtash belgisini qo'yamiz.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(None)
            except (queue.Empty, queue.Full):  # pragma: no cover - poyga
                pass
        thread.join(timeout=timeout)

    # ── Navbat ───────────────────────────────────────────────────────────

    def submit(self, event: EdgeEvent, frame: Any, *, now: Optional[float] = None) -> bool:
        """Kadrni navbatga qo'yadi.  `False` — yuborilmadi (sabab hisobda).

        **Bloklamaydi**: inferens halqasidan chaqiriladi.  Kadr shu yerda
        JPEG ga o'giriladi (bir necha millisekund), chunki oqim kadrni
        keyinroq qayta ishlatishi mumkin va navbatda turgan havola
        o'zgarib ketardi.
        """
        now = self._clock() if now is None else now
        camera_id = event.camera_id

        with self._lock:
            allowed_at = self._next_allowed.get(camera_id)
            if allowed_at is not None and now < allowed_at:
                self._throttled += 1
                return False

        try:
            self.agent.check_budget()
        except BudgetExceeded as e:
            with self._lock:
                self._over_budget += 1
            logger.warning("[%s] AI ko'rigi o'tkazib yuborildi: %s", camera_id, e)
            return False

        try:
            jpeg = self._encode(
                frame,
                max_side=self.agent.config.max_side,
                quality=self.agent.config.jpeg_quality,
            )
        except Exception:
            with self._lock:
                self._failed += 1
            logger.exception("[%s] kadrni JPEG ga o'girib bo'lmadi", camera_id)
            return False

        try:
            self._queue.put_nowait((event, jpeg))
        except queue.Full:
            with self._lock:
                self._dropped += 1
            logger.warning("[%s] AI navbati to'la — kadr tashlandi", camera_id)
            return False

        with self._lock:
            # Oraliq **hozir** boshlanadi: javob kelguncha yana bir nechta
            # hodisa chiqishi mumkin va ularning har biri yangi chaqiruv
            # bo'lmasligi kerak.
            self._next_allowed[camera_id] = now + self.agent.config.min_interval_sec
            self._sent += 1
        return True

    # ── Oqim ─────────────────────────────────────────────────────────────

    def _work(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            event, jpeg = item
            try:
                self._review(event, jpeg)
            except Exception:  # pragma: no cover - kutilmagan xato
                with self._lock:
                    self._failed += 1
                logger.exception("[%s] AI ko'rigi xatosi", event.camera_id)

    def _review(self, source: EdgeEvent, jpeg: bytes) -> None:
        try:
            result = self.agent.analyze(
                jpeg,
                camera_id=source.camera_id,
                question=question_for(source.event_type),
            )
        except BudgetExceeded as e:
            # Navbatda turganda limit tugagan bo'lishi mumkin.
            with self._lock:
                self._over_budget += 1
            logger.warning("[%s] AI ko'rigi bekor qilindi: %s", source.camera_id, e)
            return
        except VisionAgentError as e:
            with self._lock:
                self._failed += 1
            logger.warning("[%s] AI javob bermadi: %s", source.camera_id, e)
            return

        event = review_event(source, result)
        event.metadata["model"] = self.agent.config.model
        with self._lock:
            self._done += 1
            self._cost_usd += result.cost_usd
        logger.info(
            "[%s] AI ko'rigi: %s (ogohlantirish=%s, $%.4f)",
            source.camera_id,
            result.tavsif or "—",
            result.ogohlantirish,
            result.cost_usd,
        )
        self.sink("cloud_sync", event)

    # ── Holat ────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "queued": self._sent,
                "completed": self._done,
                "throttled": self._throttled,
                "over_budget": self._over_budget,
                "dropped": self._dropped,
                "failed": self._failed,
                "cost_usd": round(self._cost_usd, 4),
                "pending": self._queue.qsize(),
            }


__all__ = [
    "DEFAULT_QUESTION",
    "DEFAULT_QUEUE_SIZE",
    "QUESTIONS",
    "VisionReviewer",
    "question_for",
    "review_event",
]
