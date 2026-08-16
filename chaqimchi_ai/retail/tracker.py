"""Harakatni bashorat qiluvchi tracker.

Mavjud `FaceTracker` faqat IoU bo'yicha bog'laydi: yangi kadrdagi ramka eski
ramka bilan qanchalik ustma-ust tushishiga qaraydi.  Yuz tanish uchun bu
yetarli — odam kameraga qarab turadi va sekin qimirlaydi.

Do'kon eshigida esa yo'q.  Hisob:

    640×360 substream, odam ramkasi ~60 px keng
    5 FPS tahlil, normal yurish 1.4 m/s → kadrlar orasida ~45 px siljish
    IoU = (60−45) / (60+45) ≈ 0.14  →  0.25 chegarasidan past
    → track uziladi, yangi ID beriladi
    → chiziq kesilgani sezilmaydi  →  KIRISH KAM SANALADI

Kirish soni esa konversiya hisobining maxraji: u xato bo'lsa mijozga
ko'rsatiladigan "savdo konversiyasi" ham xato bo'ladi.

Yechim — **bashorat**: har track o'z tezligini eslab qoladi va keyingi kadrda
qayerda bo'lishi kerakligini oldindan aytadi.  Solishtirish o'sha bashorat
qilingan joy bilan bo'ladi, eski joy bilan emas.  Shu bitta o'zgarish tez
harakatni ham, qisqa panani ham ko'taradi.

To'liq Kalman filtri emas: 8/128 qurilmada 8 kamera uchun doimiy tezlik
modeli yetarli va u kamroq resurs yeydi.  Kerak bo'lsa shu interfeys ortida
almashtiriladi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

Bbox = List[float]


def bbox_iou(a: List[float], b: List[float]) -> float:
    """bbox [x1,y1,x2,y2] — intersection over union.

    Ilgari `chaqimchi_ai/face_tracker.py` da edi; u modul davomat
    to'plami bilan arxivlangach funksiya shu yerga ko'chdi.
    """
    ax1, ay1, ax2, ay2 = a[0], a[1], a[2], a[3]
    bx1, by1, bx2, by2 = b[0], b[1], b[2], b[3]
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0
    inter = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


def _center(bbox: Bbox) -> Tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def _shift(bbox: Bbox, dx: float, dy: float) -> Bbox:
    return [bbox[0] + dx, bbox[1] + dy, bbox[2] + dx, bbox[3] + dy]


@dataclass
class _Track:
    track_id: int
    bbox: Bbox
    velocity: Tuple[float, float] = (0.0, 0.0)
    missed: int = 0
    hits: int = 1
    history: List[Bbox] = field(default_factory=list)
    initial_center: Tuple[float, float] = (0.0, 0.0)
    total_displacement: float = 0.0

    def __post_init__(self) -> None:
        if self.initial_center == (0.0, 0.0) and self.bbox:
            self.initial_center = _center(self.bbox)

    def predict(self) -> Bbox:
        """Keyingi kadrda ramka qayerda bo'lishi kerak."""
        return _shift(self.bbox, *self.velocity)

    def is_static(self, min_hits: int = 40, max_net_movement: float = 8.0) -> bool:
        """Track ko'p kadrlardan beri harakatlanmay turgan bo'lsa (maneken, plakat)."""
        if self.hits < min_hits:
            return False
        curr_cx, curr_cy = _center(self.bbox)
        init_cx, init_cy = self.initial_center
        net_dist = ((curr_cx - init_cx) ** 2 + (curr_cy - init_cy) ** 2) ** 0.5
        return net_dist <= max_net_movement


class MotionTracker:
    """`FaceTracker` bilan bir xil kontrakt: `update(detections)`.

    Kirish: `[{"bbox": [x1,y1,x2,y2], "score": float}, ...]`
    Chiqish: o'sha ro'yxat, har elementga `track_id` qo'shilgan holda.
    """

    def __init__(
        self,
        *,
        iou_threshold: float = 0.2,
        max_missed_frames: int = 15,
        velocity_smoothing: float = 0.6,
        max_velocity_frames: int = 3,
        max_center_shift: float = 1.0,
        max_size_ratio: float = 2.0,
    ) -> None:
        if not 0.0 < iou_threshold < 1.0:
            raise ValueError("iou_threshold 0 va 1 orasida bo'lishi kerak")
        if max_missed_frames < 1:
            raise ValueError("max_missed_frames kamida 1 bo'lishi kerak")
        if not 0.0 < velocity_smoothing <= 1.0:
            raise ValueError("velocity_smoothing 0 va 1 orasida bo'lishi kerak")
        self.iou_threshold = float(iou_threshold)
        self.max_missed_frames = int(max_missed_frames)
        self.velocity_smoothing = float(velocity_smoothing)
        # Ko'rinmagan track bashoratini cheksiz davom ettirish xavfli: odam
        # to'xtagan bo'lsa ham ramka uchib ketardi va begona odamga yopishardi.
        self.max_velocity_frames = int(max_velocity_frames)
        self.max_center_shift = float(max_center_shift)
        self.max_size_ratio = float(max_size_ratio)
        self._tracks: Dict[int, _Track] = {}
        self._next_id = 1

    def update(self, detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        predictions = {track_id: track.predict() for track_id, track in self._tracks.items()}
        used_detections: set = set()
        used_tracks: set = set()

        # ── 1-bosqich: bashorat qilingan ramka bilan IoU ──────────────────
        pairs: List[Tuple[float, int, int]] = []
        for index, detection in enumerate(detections):
            for track_id, predicted in predictions.items():
                score = bbox_iou(detection["bbox"], predicted)
                if score >= self.iou_threshold:
                    pairs.append((score, index, track_id))
        # Eng ishonchli moslik birinchi bog'lanadi.  Teng IoU da tartib
        # barqaror bo'lishi uchun indeks va ID ham kalitga kiradi.
        pairs.sort(key=lambda item: (-item[0], item[1], item[2]))
        for _score, index, track_id in pairs:
            if index in used_detections or track_id in used_tracks:
                continue
            used_detections.add(index)
            used_tracks.add(track_id)
            self._attach(self._tracks[track_id], detections[index])

        # ── 2-bosqich: markaz masofasi bo'yicha ───────────────────────────
        #
        # Birinchi harakatda tezlik hali noma'lum, shuning uchun bashorat
        # yordam bermaydi va IoU tushib ketadi.  Aynan shu paytda track
        # uzilsa, u hech qachon tezlikni o'rganmaydi — tovuq va tuxum.
        # Shu sabab ustma-ust tushmagan, lekin **yaqin va o'lchamdosh**
        # ramkalar ham bog'lanadi.
        distances: List[Tuple[float, int, int]] = []
        for index, detection in enumerate(detections):
            if index in used_detections:
                continue
            for track_id, predicted in predictions.items():
                if track_id in used_tracks:
                    continue
                gap = self._center_gap(detection["bbox"], predicted)
                if gap is not None:
                    distances.append((gap, index, track_id))
        distances.sort(key=lambda item: (item[0], item[1], item[2]))
        for _gap, index, track_id in distances:
            if index in used_detections or track_id in used_tracks:
                continue
            used_detections.add(index)
            used_tracks.add(track_id)
            self._attach(self._tracks[track_id], detections[index])

        for index, detection in enumerate(detections):
            if index in used_detections:
                continue
            track = _Track(track_id=self._next_id, bbox=list(detection["bbox"]))
            self._tracks[track.track_id] = track
            self._next_id += 1
            detection["track_id"] = track.track_id

        self._age(used_tracks)
        return detections

    def _center_gap(self, bbox: Bbox, predicted: Bbox) -> float | None:
        """Markazlar orasidagi masofa — chegaradan chiqsa `None`.

        Chegara ramka kengligiga nisbatan olinadi: uzoqdagi kichik odam kam
        siljiydi, yaqindagi katta odam ko'p — bitta piksel chegarasi ikkalasiga
        ham to'g'ri kelmaydi.
        """
        width = max(1.0, predicted[2] - predicted[0])
        height = max(1.0, predicted[3] - predicted[1])
        detected_width = max(1.0, bbox[2] - bbox[0])
        detected_height = max(1.0, bbox[3] - bbox[1])

        # O'lchami keskin farq qilsa bu boshqa odam (yoki noto'g'ri deteksiya).
        ratio = max(detected_width / width, width / detected_width)
        ratio = max(ratio, max(detected_height / height, height / detected_height))
        if ratio > self.max_size_ratio:
            return None

        old_x, old_y = _center(predicted)
        new_x, new_y = _center(bbox)
        gap = ((new_x - old_x) ** 2 + (new_y - old_y) ** 2) ** 0.5
        return gap if gap <= self.max_center_shift * width else None

    def _attach(self, track: _Track, detection: Dict[str, Any]) -> None:
        bbox = [float(value) for value in detection["bbox"]]
        old_x, old_y = _center(track.bbox)
        new_x, new_y = _center(bbox)
        alpha = self.velocity_smoothing
        track.velocity = (
            alpha * (new_x - old_x) + (1 - alpha) * track.velocity[0],
            alpha * (new_y - old_y) + (1 - alpha) * track.velocity[1],
        )
        track.bbox = bbox
        track.missed = 0
        track.hits += 1
        detection["track_id"] = track.track_id

    def _age(self, matched: set) -> None:
        for track_id in list(self._tracks):
            if track_id in matched:
                continue
            track = self._tracks[track_id]
            track.missed += 1
            if track.missed > self.max_missed_frames:
                del self._tracks[track_id]
                continue
            if track.missed <= self.max_velocity_frames:
                # Ko'rinmagan kadrda ham harakatni davom ettiramiz (dead
                # reckoning) — qisqa pana ortidan chiqqan odam o'z ID sini
                # saqlab qoladi.
                track.bbox = track.predict()
            else:
                # Uzoq ko'rinmasa bashoratni to'xtatamiz: aks holda ramka
                # kadrdan uchib chiqib, begona odamga yopishishi mumkin.
                track.velocity = (0.0, 0.0)

    def is_static(self, track_id: int, min_hits: int = 40, max_net_movement: float = 8.0) -> bool:
        """Berilgan track_id statik obyekt (maneken/plakat) ekanligini aytadi."""
        track = self._tracks.get(track_id)
        if track is None:
            return False
        return track.is_static(min_hits=min_hits, max_net_movement=max_net_movement)

    @property
    def active(self) -> int:
        return len(self._tracks)

    def track_ids(self) -> List[int]:
        return sorted(self._tracks)
