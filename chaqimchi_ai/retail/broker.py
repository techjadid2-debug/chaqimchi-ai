"""Frame Broker — qaysi kamera qachon tahlil qilinishini hal qiladi.

Muammo: 8 kamera × 5 FPS = sekundiga 40 ta inferens, N100 esa ~30 tasini
ulguradi.  "Hammasi bir vaqtda" ishlamaydi.

Yechim: bitta umumiy byudjet va kameralar uning uchun raqobatlashadi.

    kamera → motion gate → submit()  →  ┌─────────────┐
                                        │ FrameBroker │ → acquire() → detektor
    kamera → motion gate → submit()  →  └─────────────┘

Uchta qoida byudjetni taqsimlaydi:

1. **Kredit** — har kamera vaqt o'tishi bilan o'z og'irligiga qarab kredit
   yig'adi va tahlil qilinganda sarflaydi.  Uzoq kutgan kamera oldinga chiqadi.
2. **Ochlik kafolati** — kamera o'z `floor_fps` chegarasidan sekinroq
   ko'rilayotgan bo'lsa, kreditdan qat'i nazar navbatni oladi.  Xavfsizlik
   kamerasi hech qachon butunlay unutilmaydi.
3. **Latest-frame-wins** — har kameradan ko'pi bilan bitta kadr kutadi.  Yangi
   kadr eskisini almashtiradi.  Navbat tabiiy ravishda chegaralangan bo'ladi
   va tizim eskirgan kadrni tahlil qilib vaqt yo'qotmaydi.

Broker qurilma imkoniyatini **oshira olmaydi**.  Agar barcha kameraning
kafolatlangan minimumi byudjetdan katta bo'lsa, u buni yashirmaydi:
`floor_violations` metrikasi o'sadi — bu "qurilma kam quvvatli" degan signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from chaqimchi_ai.retail.budget import InferenceBudget
from chaqimchi_ai.retail.claims import (
    PRIORITY_FLOOR_FPS,
    PRIORITY_WEIGHT,
    Claim,
    Priority,
)

#: Kafolat muddati tugashidan sal oldin navbatni olish uchun chegara.
#:
#: Aynan 1.0 da ishga tushirilsa kamera muddat tugagan paytda navbat oladi,
#: lekin byudjet tokeni bir oz keyin keladi — natijada haqiqiy tezlik
#: kafolatdan past chiqadi (o'lchovda 0.5 FPS o'rniga 0.4 FPS).  0.9 —
#: keyingi tokenni ulgurish uchun zaxira.
RESCUE_LEAD = 0.9


@dataclass
class _Camera:
    camera_id: str
    priority: Priority
    floor_fps: float
    registered_at: float
    credit: float = 0.0
    #: Kutayotgan kadr.  Ko'pi bilan bitta — latest-frame-wins.
    pending_frame: Any = None
    pending_motion: float = 0.0
    pending_at: float = 0.0
    has_pending: bool = False
    #: Kamera **uzluksiz** ko'riladigan narsaga ega bo'lgan payt.  Yangi kadr
    #: eskisini almashtirganda bu **yangilanmaydi** — aks holda 8 FPS yuboradigan
    #: kamera hech qachon "kutmoqda" deb hisoblanmasdi.
    waiting_since: float = 0.0
    #: Hozir tahlil qilinayotgan bo'lsa `True` — bitta kamera ikkita worker'ni
    #: band qilib qo'ymasin.
    in_flight: bool = False
    last_served: float = 0.0
    served: int = 0
    dropped: int = 0
    rescued: int = 0
    floor_violations: int = 0

    def overdue(self, now: float) -> float:
        """Kutayotgan kadr kafolatlangan oraliqdan necha barobar kech qolgani.

        O'lchov **kutish**dan boshlanadi, "oxirgi ko'rilgan"dan emas.  Aks holda
        harakatsiz turgan kamera (masalan kechasi ombor eshigi) harakat
        boshlanishi bilan darhol "kafolat buzildi" deb belgilanardi — holbuki
        qurilma uni o'sha zahoti ko'rgan bo'lardi.  Bunday yolg'on signal
        metrikani ishonchsiz qiladi va haqiqiy yetishmovchilikni yashiradi.
        """
        if not self.has_pending:
            return 0.0
        return (now - self.waiting_since) * self.floor_fps


@dataclass
class _Totals:
    served: int = 0
    dropped: int = 0
    rescued: int = 0
    floor_violations: int = 0
    starved_at_capacity: int = 0
    idle_polls: int = 0
    budget_denied: int = 0
    unknown: Dict[str, int] = field(default_factory=dict)


class FrameBroker:
    def __init__(self, budget: InferenceBudget, *, max_credit: float = 3.0) -> None:
        if max_credit <= 0:
            raise ValueError("max_credit musbat bo'lishi kerak")
        self.budget = budget
        self.max_credit = float(max_credit)
        self._cameras: Dict[str, _Camera] = {}
        self._last_accrual: Optional[float] = None
        self._totals = _Totals()

    # ── Ro'yxat ──────────────────────────────────────────────────────────

    def register(
        self,
        camera_id: str,
        *,
        priority: Priority = Priority.RETAIL,
        floor_fps: Optional[float] = None,
        now: float = 0.0,
    ) -> None:
        """Kamerani byudjetga qo'shadi yoki sozlamasini yangilaydi.

        Qayta chaqirilsa hisoblagichlar va kredit saqlanadi — cloud config
        o'zgarganda kamera navbat boshiga qaytib ketmasin.
        """
        resolved_floor = PRIORITY_FLOOR_FPS[priority] if floor_fps is None else float(floor_fps)
        if resolved_floor <= 0:
            raise ValueError("floor_fps musbat bo'lishi kerak")
        existing = self._cameras.get(camera_id)
        if existing is None:
            self._cameras[camera_id] = _Camera(
                camera_id=camera_id,
                priority=priority,
                floor_fps=resolved_floor,
                registered_at=now,
                # Ro'yxatdan o'tgan payt "oxirgi ko'rilgan" deb olinadi, aks
                # holda yangi kamera darhol "ochlikda" deb hisoblanardi.
                last_served=now,
            )
            return
        existing.priority = priority
        existing.floor_fps = resolved_floor

    def unregister(self, camera_id: str) -> bool:
        return self._cameras.pop(camera_id, None) is not None

    # ── Kadr berish ──────────────────────────────────────────────────────

    def submit(
        self,
        camera_id: str,
        frame: Any,
        *,
        motion_score: float = 1.0,
        now: float,
    ) -> bool:
        """Tahlilga nomzod kadr.  Motion gate o'tgan kadrlargina bu yerga keladi.

        `False` qaytsa — oldingi kadr almashtirildi (tashlab yuborildi).  Bu
        normal holat: eskirgan kadrni tahlil qilishdan foyda yo'q.
        """
        camera = self._cameras.get(camera_id)
        if camera is None:
            self._totals.unknown[camera_id] = self._totals.unknown.get(camera_id, 0) + 1
            raise KeyError(f"Kamera ro'yxatdan o'tmagan: {camera_id}")
        replaced = camera.has_pending
        if replaced:
            camera.dropped += 1
            self._totals.dropped += 1
        else:
            # Bo'sh holatdan kutishga o'tdi — kutish sanog'i shu yerdan boshlanadi.
            camera.waiting_since = now
        camera.pending_frame = frame
        camera.pending_motion = min(1.0, max(0.0, float(motion_score)))
        camera.pending_at = now
        camera.has_pending = True
        return not replaced

    def acquire(self, now: float) -> Optional[Claim]:
        """Keyingi tahlil qilinadigan kadr — yoki byudjet/kadr yo'q bo'lsa `None`."""
        self._accrue(now)
        candidates = [
            camera
            for camera in self._cameras.values()
            if camera.has_pending and not camera.in_flight
        ]
        if not candidates:
            self._totals.idle_polls += 1
            return None

        # Navbatni muddat tugashidan sal oldin beramiz, lekin **buzilish** deb
        # faqat rostdan muddati o'tganini sanaymiz — metrika halol qolsin.
        starved = [camera for camera in candidates if camera.overdue(now) >= RESCUE_LEAD]
        for camera in candidates:
            if camera.overdue(now) >= 1.0:
                camera.floor_violations += 1
                self._totals.floor_violations += 1

        # Token faqat rostdan ish bor bo'lganda sarflanadi.
        if not self.budget.take(now):
            self._totals.budget_denied += 1
            if starved:
                self._totals.starved_at_capacity += 1
            return None

        if starved:
            # Eng ko'p kechikkani birinchi.  Teng bo'lsa muhimrog'i, keyin
            # nomi bo'yicha — natija takrorlanadigan bo'lishi kerak.
            chosen = min(starved, key=lambda c: (-c.overdue(now), c.priority, c.camera_id))
            rescued = True
            chosen.rescued += 1
            self._totals.rescued += 1
        else:
            chosen = min(candidates, key=lambda c: (-c.credit, c.priority, c.camera_id))
            rescued = False

        claim = Claim(
            camera_id=chosen.camera_id,
            frame=chosen.pending_frame,
            priority=chosen.priority,
            motion_score=chosen.pending_motion,
            submitted_at=chosen.pending_at,
            rescued=rescued,
        )
        chosen.credit = max(-self.max_credit, chosen.credit - 1.0)
        chosen.has_pending = False
        chosen.pending_frame = None
        chosen.in_flight = True
        chosen.last_served = now
        chosen.served += 1
        self._totals.served += 1
        return claim

    def complete(self, camera_id: str, *, latency_sec: float, now: float) -> None:
        """Tahlil tugadi.  Byudjet shu o'lchovga qarab o'zini sozlaydi."""
        camera = self._cameras.get(camera_id)
        if camera is None:
            raise KeyError(f"Kamera ro'yxatdan o'tmagan: {camera_id}")
        camera.in_flight = False
        self.budget.observe(latency_sec, now=now)

    # ── Ichki ────────────────────────────────────────────────────────────

    def _weight(self, camera: _Camera) -> float:
        base = PRIORITY_WEIGHT[camera.priority]
        if not camera.has_pending:
            return base
        # Harakat ko'p bo'lgan kamera ko'proq ulush oladi, lekin kam harakatli
        # ham yarim og'irlikni saqlaydi — sekin o'g'irlik tez yurishdan kam
        # muhim emas.
        return base * (0.5 + 0.5 * camera.pending_motion)

    def _accrue(self, now: float) -> None:
        """Kreditni byudjetga **normallashtirib** taqsimlaydi.

        Og'irlik mutlaq tezlik emas, **ulush**: umumiy kredit oqimi aynan
        byudjet tezligiga teng bo'ladi.  Aks holda og'irliklar yig'indisi
        byudjetdan kichik bo'lsa bo'sh quvvat eng muhim kameraga to'liq ketib,
        ulush nisbati buzilardi.
        """
        if self._last_accrual is None:
            self._last_accrual = now
            return
        elapsed = now - self._last_accrual
        if elapsed <= 0:
            return
        self._last_accrual = now
        weights = {camera.camera_id: self._weight(camera) for camera in self._cameras.values()}
        total = sum(weights.values())
        if total <= 0:
            return
        budget_rate = self.budget.target_fps
        for camera in self._cameras.values():
            gain = (weights[camera.camera_id] / total) * budget_rate * elapsed
            camera.credit = min(self.max_credit, camera.credit + gain)

    # ── Holat ────────────────────────────────────────────────────────────

    def camera_ids(self) -> List[str]:
        return sorted(self._cameras)

    def stats(self) -> Dict[str, Any]:
        return {
            "budget": self.budget.stats(),
            "served": self._totals.served,
            "dropped": self._totals.dropped,
            "rescued": self._totals.rescued,
            "floor_violations": self._totals.floor_violations,
            "starved_at_capacity": self._totals.starved_at_capacity,
            "budget_denied": self._totals.budget_denied,
            "idle_polls": self._totals.idle_polls,
            "cameras": {
                camera.camera_id: {
                    "priority": camera.priority.name,
                    "floor_fps": camera.floor_fps,
                    "credit": round(camera.credit, 3),
                    "served": camera.served,
                    "dropped": camera.dropped,
                    "rescued": camera.rescued,
                    "floor_violations": camera.floor_violations,
                    "pending": camera.has_pending,
                    "in_flight": camera.in_flight,
                }
                for camera in sorted(self._cameras.values(), key=lambda c: c.camera_id)
            },
        }
