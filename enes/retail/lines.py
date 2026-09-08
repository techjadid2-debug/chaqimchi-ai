"""Kirish/chiqish chizig'i va zonada turish vaqti.

Do'kon analitikasining ikkita asosiy o'lchovi shu yerdan chiqadi:

* **Kirish/chiqish** — konversiya hisobining maxraji ("nechta odam kirdi").
* **Dwell** — mijoz tokcha oldida qancha turgani.

Koordinatalar **0..1 normallashtirilgan**: kamera rezolyutsiyasi o'zgarsa
(substream 640×360 dan 704×576 ga o'tsa) sozlama qayta chizilmasin.  Bu qoida
mavjud `SceneZoneSettings` bilan bir xil.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

Point = Tuple[float, float]


def _cross(origin: Point, first: Point, second: Point) -> float:
    """(first-origin) × (second-origin) vektor ko'paytmasi.

    Belgisi `second` nuqta `origin→first` chizig'ining qaysi tomonida
    turganini aytadi.
    """
    return (first[0] - origin[0]) * (second[1] - origin[1]) - (first[1] - origin[1]) * (
        second[0] - origin[0]
    )


def segments_intersect(a1: Point, a2: Point, b1: Point, b2: Point) -> bool:
    """Ikkita **kesma** kesishadimi.

    Cheksiz chiziq emas, aynan kesma: eshik chizig'ining yonidan o'tgan odam
    kirgan deb hisoblanmasligi kerak.

    Ustma-ust tushgan (kollinear) holat kesishmagan deb qaraladi — chiziq
    ustida turgan odam har kadrda qayta sanalib ketmasin.
    """
    d1 = _cross(b1, b2, a1)
    d2 = _cross(b1, b2, a2)
    d3 = _cross(a1, a2, b1)
    d4 = _cross(a1, a2, b2)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


@dataclass(frozen=True)
class CountingLine:
    """Kirish/chiqish chizig'i.

    `start`→`end` yo'nalishi "ichkari" qayerdaligini belgilaydi: chiziqni
    kesib o'tgan odam vektorning **chap** tomoniga chiqsa `in`, o'ng tomoniga
    chiqsa `out`.  O'rnatuvchi chiziqni do'kon ichkarisi chap tomonda qoladigan
    qilib chizadi; teskari bo'lsa `swap_direction` bilan almashtiriladi.
    """

    name: str
    camera_id: str
    start: Point
    end: Point
    swap_direction: bool = False

    def __post_init__(self) -> None:
        for point in (self.start, self.end):
            if not all(0.0 <= value <= 1.0 for value in point):
                raise ValueError(f"{self.name}: koordinatalar 0..1 oralig'ida bo'lishi kerak")
        if self.start == self.end:
            raise ValueError(f"{self.name}: chiziq uzunligi nol bo'lishi mumkin emas")

    def direction_for(self, moved_to: Point) -> str:
        """Kesib o'tgandan keyingi nuqta bo'yicha yo'nalish."""
        side = _cross(self.start, self.end, moved_to)
        inward = side > 0
        if self.swap_direction:
            inward = not inward
        return "in" if inward else "out"


@dataclass(frozen=True)
class Crossing:
    line: str
    camera_id: str
    track_id: int
    direction: str


class LineCounter:
    """Track harakatini chiziqlar bilan solishtiradi.

    Har track uchun oldingi nuqta saqlanadi; oldingi va yangi nuqta orasidagi
    kesma chiziqni kessa — hodisa.  Bu "chiziqning qaysi tomonidasan" degan
    tekshiruvdan ishonchliroq: kamera bir kadrni tashlab yuborsa ham o'tish
    yo'qolmaydi, va chiziq ustida turgan odam takror sanalmaydi.
    """

    def __init__(self, lines: Sequence[CountingLine]) -> None:
        self.lines = list(lines)
        self._previous: Dict[int, Point] = {}

    def update(self, track_id: int, point: Point) -> List[Crossing]:
        previous = self._previous.get(track_id)
        self._previous[track_id] = point
        if previous is None or previous == point:
            return []
        crossings: List[Crossing] = []
        for line in self.lines:
            if segments_intersect(previous, point, line.start, line.end):
                crossings.append(
                    Crossing(
                        line=line.name,
                        camera_id=line.camera_id,
                        track_id=track_id,
                        direction=line.direction_for(point),
                    )
                )
        return crossings

    def forget(self, track_id: int) -> None:
        self._previous.pop(track_id, None)

    def retain(self, track_ids: Iterable[int]) -> None:
        """Faqat hali tirik tracklarni qoldiradi — xotira cheksiz o'smasin."""
        alive = set(track_ids)
        for track_id in [key for key in self._previous if key not in alive]:
            del self._previous[track_id]

    @property
    def tracked(self) -> int:
        return len(self._previous)


@dataclass(frozen=True)
class DwellAlert:
    zone: str
    track_id: int
    dwell_sec: float


class DwellTracker:
    """Zonada uzoq turishni kuzatadi.

    Mavjud `loitering` hodisasidan farqi: loitering odamning **kadrda** umumiy
    turgan vaqtini o'lchaydi, dwell esa **aniq zonada** — "tokcha-3 oldida 3
    daqiqa turdi" degan retail savoliga javob shu.

    Har (track, zona) juftligi uchun bir marta ogohlantiradi; odam chiqib
    qaytib kirsa hisob noldan boshlanadi.
    """

    def __init__(self, thresholds: Dict[str, float]) -> None:
        for zone, seconds in thresholds.items():
            if seconds <= 0:
                raise ValueError(f"{zone}: dwell chegarasi musbat bo'lishi kerak")
        self.thresholds = dict(thresholds)
        self._entered: Dict[Tuple[int, str], float] = {}
        self._alerted: set = set()

    def update(self, track_id: int, zones: Iterable[str], now: float) -> List[DwellAlert]:
        current = {zone for zone in zones if zone in self.thresholds}
        alerts: List[DwellAlert] = []

        for zone in current:
            key = (track_id, zone)
            entered = self._entered.setdefault(key, now)
            elapsed = now - entered
            if elapsed >= self.thresholds[zone] and key not in self._alerted:
                self._alerted.add(key)
                alerts.append(DwellAlert(zone=zone, track_id=track_id, dwell_sec=elapsed))

        # Zonadan chiqqan bo'lsa hisob tozalanadi — qaytib kirsa yangidan.
        for key in [key for key in self._entered if key[0] == track_id and key[1] not in current]:
            del self._entered[key]
            self._alerted.discard(key)
        return alerts

    def forget(self, track_id: int) -> None:
        for key in [key for key in self._entered if key[0] == track_id]:
            del self._entered[key]
            self._alerted.discard(key)

    def retain(self, track_ids: Iterable[int]) -> None:
        alive = set(track_ids)
        for key in [key for key in self._entered if key[0] not in alive]:
            del self._entered[key]
            self._alerted.discard(key)

    def dwell_of(self, track_id: int, zone: str, now: float) -> Optional[float]:
        entered = self._entered.get((track_id, zone))
        return None if entered is None else now - entered
