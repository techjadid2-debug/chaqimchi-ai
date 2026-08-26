"""Motion-gated person analytics: person, zona, loitering va occupancy."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, Tuple

import cv2
import numpy as np

from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.retail.lines import CountingLine, DwellTracker, LineCounter
from chaqimchi_ai.retail.shelf import ShelfWatcher, crop_polygon
from chaqimchi_ai.retail.tracker import MotionTracker
from chaqimchi_ai.settings import SceneSettings, SceneZoneSettings

logger = logging.getLogger(__name__)


class PersonDetector(Protocol):
    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]: ...


def _decode_person_output(
    raw: np.ndarray,
    *,
    width: int,
    height: int,
    input_size: int,
    confidence: float,
    nms_threshold: float,
) -> List[Dict[str, Any]]:
    raw = np.asarray(raw).squeeze()
    if raw.ndim != 2:
        return []
    if raw.shape[0] in {84, 85} and raw.shape[1] > raw.shape[0]:
        raw = raw.T
    boxes: List[List[int]] = []
    scores: List[float] = []
    scale_x = width / float(input_size)
    scale_y = height / float(input_size)
    for row in raw:
        if row.shape[0] < 6:
            continue
        score = float(row[4]) if row.shape[0] == 84 else float(row[4] * row[5])
        if score < confidence:
            continue
        cx, cy, bw, bh = (float(value) for value in row[:4])
        x = int((cx - bw / 2) * scale_x)
        y = int((cy - bh / 2) * scale_y)
        boxes.append([x, y, int(bw * scale_x), int(bh * scale_y)])
        scores.append(score)
    if not boxes:
        return []
    indices = cv2.dnn.NMSBoxes(boxes, scores, confidence, nms_threshold)
    detections: List[Dict[str, Any]] = []
    for index in np.asarray(indices).reshape(-1).tolist():
        x, y, bw, bh = boxes[int(index)]
        detections.append(
            {
                "bbox": [
                    float(max(0, x)),
                    float(max(0, y)),
                    float(min(width, x + bw)),
                    float(min(height, y + bh)),
                ],
                "score": scores[int(index)],
            }
        )
    return detections


class OpenCVDnnPersonDetector:
    """COCO YOLOv8/YOLOX ONNX uchun ixcham commercial-backend adapteri."""

    def __init__(
        self,
        model_path: Path,
        *,
        input_size: int = 640,
        confidence: float = 0.45,
        nms_threshold: float = 0.45,
    ) -> None:
        if not model_path.is_file():
            raise FileNotFoundError(f"Person detector modeli topilmadi: {model_path}")
        self.net = cv2.dnn.readNetFromONNX(str(model_path))
        self.input_size = int(input_size)
        self.confidence = float(confidence)
        self.nms_threshold = float(nms_threshold)

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        height, width = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(
            frame,
            scalefactor=1 / 255.0,
            size=(self.input_size, self.input_size),
            swapRB=True,
            crop=False,
        )
        self.net.setInput(blob)
        return _decode_person_output(
            self.net.forward(),
            width=width,
            height=height,
            input_size=self.input_size,
            confidence=self.confidence,
            nms_threshold=self.nms_threshold,
        )


#: Fon modeli o'rganilguncha o'tadigan kadrlar.  Shu oraliqda hamma narsa
#: "harakat" deb qaraladi — aks holda tizim endi yoqilganda birinchi hodisani
#: o'tkazib yuborardi.
WARMUP_FRAMES = 5


class MotionGate:
    def __init__(self, min_area_ratio: float = 0.01) -> None:
        self.min_area_ratio = float(min_area_ratio)
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=300, varThreshold=25, detectShadows=False
        )
        self._frames = 0

    def motion_ratio(self, frame: np.ndarray) -> float:
        """Kadrning necha ulushi o'zgargani (0..1).

        Ha/yo'q javobidan tashqari **miqdor** ham kerak: broker kameralar
        orasida byudjetni taqsimlaganda ko'p harakatli kameraga ko'proq ulush
        beradi.  Hisob baribir bajarilayotgan edi — faqat tashqariga
        chiqarilmasdi.
        """
        self._frames += 1
        small = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
        mask = self._subtractor.apply(small)
        if self._frames <= WARMUP_FRAMES:
            return 1.0
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        return float(cv2.countNonZero(mask)) / float(mask.size)

    def has_motion(self, frame: np.ndarray) -> bool:
        return self.motion_ratio(frame) >= self.min_area_ratio


def _inside(point: Tuple[float, float], polygon: Sequence[Tuple[float, float]]) -> bool:
    contour = np.asarray(polygon, dtype=np.float32)
    return cv2.pointPolygonTest(contour, point, False) >= 0


#: Davomat kadri uchun odam ramkasining minimal balandligi (kadr ulushida).
#: Kichik ramka = uzoqdagi odam = crop ichida yuz o'qib bo'lmaydigan darajada
#: mayda bo'ladi va cloud bekorga ishlaydi.
FACE_MIN_BBOX_RATIO = 0.28
#: Bitta trackdan ko'pi bilan shuncha yuz kadri — odam eshik oldida turib
#: qolsa ham oqim to'lib ketmaydi.
FACE_EMITS_PER_TRACK = 2
#: Ikkinchi kadr kamida shuncha soniyadan keyin (birinchisi sifatsiz chiqsa
#: zaxira bo'ladi).
FACE_DEBOUNCE_SEC = 60.0
#: Bitta KAMERADAN soatiga ko'pi bilan shuncha yuz kadri.
#:
#: Yuqoridagi ikki chegara `track_id` ga bog'langan va aynan shu ularning
#: zaif joyi: tracker odamni yo'qotib qayta topsa YANGI track tug'iladi va
#: byudjet noldan boshlanadi.  2026-08-26 da jonli do'konda oqibati shu
#: bo'ldi — atigi 9 ta tashrifchidan 45 daqiqada 399 ta `face_captured`
#: chiqdi (~200 ta track), cloud'dagi kunlik byudjet tugadi va do'konning
#: HAMMA hodisasi rasmsiz qoldi.
#:
#: Bu shift tracker'ga umuman bog'liq emas: track qanchalik almashsa ham
#: sirpanuvchi oynadagi son o'smaydi.  40 — kunlik 200 lik cloud
#: chegarasiga mos: 5 soatlik gavjum ish kuni to'liq qoplanadi.
FACE_EMITS_PER_HOUR = 40
#: Shift oynasi.
FACE_HOUR_WINDOW_SEC = 3600.0

#: Bosim shundan oshsa demografiya o'tkazib yuboriladi — xavfsizlik va
#: sanash muhimroq (himoya klapani).
DEMOGRAPHY_PRESSURE_LIMIT = 0.85
#: Bitta trek uchun urinishlar (kirish chizig'i kesilgan kadrlarda).
DEMOGRAPHY_ATTEMPTS_PER_TRACK = 2


class SceneAnalyzer:
    def __init__(
        self,
        camera_id: str,
        detector: PersonDetector,
        settings: SceneSettings,
        *,
        attendance: bool = False,
        demography: Optional[Any] = None,
        pressure: Optional[Callable[[], float]] = None,
    ) -> None:
        self.camera_id = camera_id
        self.detector = detector
        self.settings = settings
        #: Davomat kamerasi: odam ko'ringanida yuz crop hodisasi chiqadi.
        #: Qurilma yuzni TANIMAYDI — moslash cloudda (cloud/faces.py).
        self.attendance = bool(attendance)
        self._track_face_emits: Dict[int, int] = {}
        self._track_face_last: Dict[int, float] = {}
        #: Kamera bo'yicha yuborilgan yuz kadrlarining vaqtlari — track
        #: almashuvidan mustaqil shift (`FACE_EMITS_PER_HOUR`).
        self._face_emit_times: List[float] = []
        #: Shift tufayli yuborilmagan kadrlar soni.  Nol bo'lmasa "bu
        #: kamera juda ko'p yuz ko'ryapti" degani — sozlash signali.
        self.face_emits_suppressed = 0
        #: Demografiya (jins/yosh): faqat kirish chizig'i bor kamerada
        #: beriladi; natija anonim raqamlar, rasm saqlanmaydi.
        self.demography = demography
        self.pressure = pressure
        self._track_demography: Dict[int, Dict[str, Any]] = {}
        self._demo_attempts: Dict[int, int] = {}
        #: Issiqlik to'ri: har kadrda oyoq nuqtalari yig'iladi (deyarli
        #: bepul), 10 daqiqada bir cloudga ketadi.
        from chaqimchi_ai.retail.heatmap import HeatmapGrid

        self.heatmap = HeatmapGrid()
        self.motion = MotionGate(settings.motion_min_area_ratio)
        # Yuz uchun mo'ljallangan IoU tracker do'kon eshigida ishlamaydi: normal
        # yurgan odam bir kadrda ramkasining yarmidan ko'p siljiydi va track
        # uziladi — kirish kam sanaladi.  Batafsil `retail/tracker.py` da.
        self.tracker = MotionTracker(iou_threshold=0.2, max_missed_frames=15)
        self.zones: List[SceneZoneSettings] = [
            zone for zone in settings.zones if zone.camera_id == camera_id
        ]
        self.lines = LineCounter(
            [
                CountingLine(
                    name=line.name,
                    camera_id=line.camera_id,
                    start=line.start,
                    end=line.end,
                    swap_direction=line.swap_direction,
                )
                for line in settings.lines
                if line.camera_id == camera_id
            ]
        )
        self.dwell = DwellTracker(
            {zone.name: float(zone.dwell_sec) for zone in self.zones if zone.dwell_sec is not None}
        )
        self._queue_alerted = False
        #: Kassa zonasi qachondan beri bo'sh (zona → monotonik vaqt).
        self._checkout_empty_since: Dict[str, float] = {}
        self._checkout_alerted: Dict[str, bool] = {}
        self._second_till_alerted = False
        self.shelves = ShelfWatcher(
            empty_ratio=settings.shelf_empty_ratio,
            empty_sec=float(settings.shelf_empty_sec),
        )
        self._last_analysis = 0.0
        self._track_first_seen: Dict[int, float] = {}
        self._track_last_seen: Dict[int, float] = {}
        self._track_zones: Dict[int, set[str]] = {}
        self._emitted: Dict[Tuple[str, str], float] = {}
        self._occupancy_alerted = False
        # Faqat xotirada turadigan oxirgi AI ramkalari. Jonli overlay uchun
        # ishlatiladi; DBga, event metadata'ga yoki cloudga koordinata
        # sifatida saqlanmaydi.
        self.last_detections: List[Dict[str, Any]] = []

    def _checkout_events(
        self,
        zone_counts: Dict[str, int],
        queue_zones: List[str],
        people_in_view: int,
        now: float,
    ) -> List[EdgeEvent]:
        """Kassa nazorati: bo'sh kassa va ikkinchi kassa kerakligi.

        **Nima aytiladi va nima aytilmaydi.** Detektor ODAMNI topadi,
        kassirni emas.  "Kassada hech kim yo'q" — o'lchanadigan fakt.
        "Kassir ketib qoldi" — taxmin, va uni sotuv va'dasiga aylantirish
        aynan `FORBIDDEN_CLAIMS` ushlaydigan xato bo'lardi.  Shu sabab
        hamma matnda **kassa**, hech qachon **kassir**.

        Bo'sh kassaning o'zi signal EMAS: mijoz yo'q paytda kassa bo'sh
        bo'lishi normal va bu haqda xabar berish — shovqin.  Signal
        ikkalasi birga bo'lganda chiqadi: kadrda odamlar bor, kassada
        esa yo'q.
        """
        events: List[EdgeEvent] = []
        idle_limit = float(self.settings.checkout_idle_sec)

        for zone_name in queue_zones:
            waiting = zone_counts.get(zone_name, 0)
            if waiting:
                # Kassada odam bor — hisob noldan boshlanadi.
                self._checkout_empty_since.pop(zone_name, None)
                self._checkout_alerted[zone_name] = False
                continue
            if people_in_view < 1:
                # Do'konda umuman odam yo'q: bo'sh kassa kutilgan holat.
                # Hisob ham boshlanmaydi, aks holda kechqurun yopilgandan
                # keyin ertalab birinchi mijoz kelishi bilan signal
                # chiqib ketardi.
                self._checkout_empty_since.pop(zone_name, None)
                continue
            since = self._checkout_empty_since.setdefault(zone_name, now)
            if now - since < idle_limit or self._checkout_alerted.get(zone_name):
                continue
            self._checkout_alerted[zone_name] = True
            events.append(
                EdgeEvent(
                    event_type="checkout_unattended",
                    severity="warning",
                    camera_id=self.camera_id,
                    zone=zone_name,
                    metadata={
                        "idle_sec": round(now - since, 1),
                        "people_in_view": people_in_view,
                    },
                )
            )

        # Ikkinchi kassa: bittasida navbat chegaradan oshgan, boshqasida
        # esa umuman odam yo'q.  Bitta kassali do'konda bu hodisa
        # chiqmaydi — ochadigan ikkinchi kassa yo'q.
        if len(queue_zones) >= 2:
            counts = {zone: zone_counts.get(zone, 0) for zone in queue_zones}
            busiest = max(counts, key=lambda zone: counts[zone])
            idle = [zone for zone, count in counts.items() if count == 0]
            if counts[busiest] >= self.settings.queue_limit and idle:
                if not self._second_till_alerted:
                    self._second_till_alerted = True
                    events.append(
                        EdgeEvent(
                            event_type="checkout_second_till",
                            severity="warning",
                            camera_id=self.camera_id,
                            zone=busiest,
                            queue_length=counts[busiest],
                            metadata={"bosh_kassalar": idle},
                        )
                    )
            else:
                self._second_till_alerted = False
        return events

    def _shelf_events(
        self, frame: np.ndarray, zone_counts: Dict[str, int], now: float
    ) -> List[EdgeEvent]:
        """Javon bo'shab qolganini aytadi.

        Model ishlatilmaydi — sabab va cheklovlar `retail/shelf.py` da.
        Bu yerda faqat ulanish: qaysi zona javon, kim uni yopib turibdi.
        """
        events: List[EdgeEvent] = []
        for zone in self.zones:
            if not zone.shelf:
                continue
            found = self.shelves.observe(
                zone.name,
                crop_polygon(frame, zone.polygon),
                # Zonada odam bor — o'lchov ishonchsiz.  Mijoz javonni
                # yopib turgani ham, uning kiyimi ham chekka zichligini
                # o'zgartiradi va ikkala tomonga ham yolg'on beradi.
                blocked=zone_counts.get(zone.name, 0) > 0,
                now=now,
            )
            if found is None:
                continue
            events.append(
                EdgeEvent(
                    event_type="shelf_empty",
                    severity="warning",
                    camera_id=self.camera_id,
                    zone=zone.name,
                    metadata=found,
                )
            )
        return events

    def _estimate_demography(
        self, frame: np.ndarray, detection: Dict[str, Any], track_id: int
    ) -> Optional[Dict[str, Any]]:
        """Kirish kesishmasida mijozning jins/yoshini baholaydi.

        Trek boshiga ko'pi bilan 2 urinish; bosim yuqorida — o'tkazib
        yuboriladi (xavfsizlik va sanash ustuvor).  Xato tahlilni hech
        qachon to'xtatmaydi.
        """
        if self.demography is None:
            return None
        cached = self._track_demography.get(track_id)
        if cached is not None:
            return cached
        if self.pressure is not None and self.pressure() >= DEMOGRAPHY_PRESSURE_LIMIT:
            return None
        attempts = self._demo_attempts.get(track_id, 0)
        if attempts >= DEMOGRAPHY_ATTEMPTS_PER_TRACK:
            return None
        self._demo_attempts[track_id] = attempts + 1
        try:
            result = self.demography.estimate(frame, detection["bbox"])
        except Exception:
            logger.exception("[%s] demografiya baholanmadi", self.camera_id)
            return None
        if result:
            self._track_demography[track_id] = result
        return result

    def _big_enough(self, detections: List[Dict[str, Any]], height: int) -> List[Dict[str, Any]]:
        """Kadr balandligiga nisbatan juda kichik ramkalarni tashlaydi."""
        ratio = float(getattr(self.settings, "min_person_height_ratio", 0.0) or 0.0)
        if ratio <= 0 or height <= 0:
            return detections
        floor = ratio * height
        return [
            item
            for item in detections
            if (item["bbox"][3] - item["bbox"][1]) >= floor
        ]

    def _emit_allowed(self, kind: str, key: str, now: float) -> bool:
        token = (kind, key)
        previous = self._emitted.get(token, 0.0)
        if now - previous < self.settings.event_debounce_sec:
            return False
        self._emitted[token] = now
        return True

    def process(self, frame: np.ndarray, *, now: float | None = None) -> List[EdgeEvent]:
        """Kadrni filtrlab, kerak bo'lsa tahlil qiladi.

        Bitta kamerali yo'l uchun: harakat filtri va tezlik chegarasi shu
        yerda.  Ko'p kamerali retail yo'lida navbatni `FrameBroker` hal
        qiladi, shuning uchun u to'g'ridan-to'g'ri `analyze()` ni chaqiradi.
        """
        now = time.monotonic() if now is None else float(now)
        if not self.motion.has_motion(frame):
            return []
        min_interval = 1.0 / self.settings.burst_fps
        if now - self._last_analysis < min_interval:
            return []
        return self.analyze(frame, now=now)

    def analyze(self, frame: np.ndarray, *, now: float | None = None) -> List[EdgeEvent]:
        """Kadrni **filtrsiz** tahlil qiladi — kim chaqirsa, o'sha hal qilgan.

        Byudjet allaqachon shu kadrga token bergan bo'lsa, uni yana bir marta
        filtrga solish qo'sh ish bo'lardi.
        """
        now = time.monotonic() if now is None else float(now)
        self._last_analysis = now
        self.heatmap.frame_done()

        height, width = frame.shape[:2]
        # Juda kichik ramkalarni kuzatuvchiga UMUMAN bermaymiz.
        #
        # Bungacha o'lcham filtri yo'q edi va oqibati jonli do'konda
        # o'lchandi (2026-08-21): 6x12 pikselli qimirlamaydigan dog'
        # "odam" bo'lib, bitta track sifatida soatlab yashagan va har
        # sovish oralig'ida "uzoq turish" bergan.  Bir kechada 48 ta
        # yolg'on hodisa — do'kon yopiq bo'lsa ham.
        #
        # Filtr aynan shu yerda: kuzatuvchiga tushsa, u track ochadi va
        # keyingi hamma hisob-kitob (navbat, bandlik, xarita) buziladi.
        detections = self.tracker.update(self._big_enough(self.detector.detect(frame), height))
        self.last_detections = [
            {
                "bbox": [float(value) for value in item.get("bbox", [])[:4]],
                "score": float(item.get("score", 0.0)),
                "track_id": int(item.get("track_id", 0)),
            }
            for item in detections
            if len(item.get("bbox", [])) >= 4
        ]
        events: List[EdgeEvent] = []
        active_ids: set[int] = set()
        #: Shu kadrda har zonada nechta odam bor.  Navbat aynan shundan
        #: hisoblanadi — `_track_zones` da 120 sekundgacha eskirgan tracklar
        #: qolib ketadi va navbat bo'shagan bo'lsa ham to'la ko'rinardi.
        zone_counts: Dict[str, int] = {}

        for detection in detections:
            track_id = int(detection["track_id"])
            active_ids.add(track_id)
            self._track_first_seen.setdefault(track_id, now)
            self._track_last_seen[track_id] = now
            if self._emit_allowed("person", str(track_id), now):
                events.append(
                    EdgeEvent(
                        event_type="person_detected",
                        camera_id=self.camera_id,
                        track_id=track_id,
                        score=float(detection.get("score", 0.0)),
                        metadata={"bbox": detection["bbox"]},
                    )
                )

            x1, y1, x2, y2 = detection["bbox"]

            # Davomat: yetarlicha yaqin kelgan odamdan yuz kadri.
            if self.attendance and (y2 - y1) / height >= FACE_MIN_BBOX_RATIO:
                emits = self._track_face_emits.get(track_id, 0)
                last = self._track_face_last.get(track_id)
                if emits < FACE_EMITS_PER_TRACK and (
                    last is None or now - last >= FACE_DEBOUNCE_SEC
                ):
                    # Kamera shifti track byudjetidan KEYIN tekshiriladi:
                    # shift urilganda track hisobini oshirmaymiz, aks holda
                    # oyna bo'shagach o'sha odamdan kadr olinmay qolardi.
                    self._face_emit_times = [
                        moment
                        for moment in self._face_emit_times
                        if now - moment < FACE_HOUR_WINDOW_SEC
                    ]
                    if len(self._face_emit_times) >= FACE_EMITS_PER_HOUR:
                        # `continue` EMAS: quyida issiqlik xaritasi, zona va
                        # demografiya bor — yuz kadri to'xtagani ular ham
                        # to'xtashi degani emas.
                        self.face_emits_suppressed += 1
                    else:
                        self._face_emit_times.append(now)
                        self._track_face_emits[track_id] = emits + 1
                        self._track_face_last[track_id] = now
                        events.append(
                            EdgeEvent(
                                event_type="face_captured",
                                camera_id=self.camera_id,
                                track_id=track_id,
                                score=float(detection.get("score", 0.0)),
                                metadata={"bbox": detection["bbox"]},
                            )
                        )

            center = ((x1 + x2) / 2 / width, y2 / height)
            self.heatmap.add(center[0], center[1])
            current_zones = {zone.name for zone in self.zones if _inside(center, zone.polygon)}
            for zone_name in current_zones:
                zone_counts[zone_name] = zone_counts.get(zone_name, 0) + 1
            previous_zones = self._track_zones.setdefault(track_id, set())
            for zone_name in current_zones - previous_zones:
                zone = next(item for item in self.zones if item.name == zone_name)
                events.append(
                    EdgeEvent(
                        event_type="zone_entered",
                        severity="warning" if zone.restricted else "info",
                        camera_id=self.camera_id,
                        track_id=track_id,
                        zone=zone_name,
                        score=float(detection.get("score", 0.0)),
                        metadata={"bbox": detection["bbox"], "restricted": zone.restricted},
                    )
                )
            self._track_zones[track_id] = current_zones

            # Kirish/chiqish — konversiya hisobining maxraji.
            for crossing in self.lines.update(track_id, center):
                metadata: Dict[str, Any] = {"bbox": detection["bbox"]}
                if crossing.direction == "in":
                    demography = self._estimate_demography(frame, detection, track_id)
                    if demography:
                        metadata["demografiya"] = demography
                events.append(
                    EdgeEvent(
                        event_type="line_crossed",
                        camera_id=self.camera_id,
                        track_id=track_id,
                        direction=crossing.direction,
                        line=crossing.line,
                        metadata=metadata,
                    )
                )

            # Zonada uzoq turish — "tokcha oldida 3 daqiqa turdi".
            for alert in self.dwell.update(track_id, current_zones, now):
                events.append(
                    EdgeEvent(
                        event_type="dwell_exceeded",
                        camera_id=self.camera_id,
                        track_id=track_id,
                        zone=alert.zone,
                        dwell_sec=round(alert.dwell_sec, 1),
                        metadata={"bbox": detection["bbox"]},
                    )
                )

            elapsed = now - self._track_first_seen[track_id]
            # Qimirlamaydigan obyekt "uzoq turgan odam" emas.
            #
            # `MotionTracker.is_static()` allaqachon yozilgan va sinalgan
            # edi — izohida aynan shu holat ko'rsatilgan: "maneken,
            # plakat".  Lekin u HECH QAYERDA chaqirilmagan, ya'ni himoya
            # amalda yo'q edi.
            #
            # Jonli do'konda oqibati (2026-08-21): `track=3920` bitta
            # joyda 6354 soniya (1 soat 46 daqiqa) "turgan" va har
            # sovish oralig'ida hodisa bergan.
            static_object = self.tracker.is_static(track_id)
            if (
                not static_object
                and elapsed >= self.settings.loitering_sec
                and self._emit_allowed("loitering", str(track_id), now)
            ):
                events.append(
                    EdgeEvent(
                        event_type="loitering",
                        severity="warning",
                        camera_id=self.camera_id,
                        track_id=track_id,
                        zone=next(iter(current_zones), None),
                        metadata={"duration_sec": round(elapsed, 1), "bbox": detection["bbox"]},
                    )
                )

        # Navbat: kassa zonasidagi odam soni.  Bandlik kabi latch bilan —
        # navbat tarqalmaguncha qayta ogohlantirilmaydi.
        queue_zones = [zone.name for zone in self.zones if zone.queue]
        longest_queue = 0
        longest_zone: Optional[str] = None
        for zone_name in queue_zones:
            waiting = zone_counts.get(zone_name, 0)
            if waiting > longest_queue:
                longest_queue, longest_zone = waiting, zone_name
        if queue_zones:
            if longest_queue >= self.settings.queue_limit and not self._queue_alerted:
                self._queue_alerted = True
                events.append(
                    EdgeEvent(
                        event_type="queue_threshold_exceeded",
                        severity="warning",
                        camera_id=self.camera_id,
                        zone=longest_zone,
                        queue_length=longest_queue,
                    )
                )
            elif longest_queue < self.settings.queue_limit:
                self._queue_alerted = False

            events.extend(self._checkout_events(zone_counts, queue_zones, len(detections), now))

        events.extend(self._shelf_events(frame, zone_counts, now))

        occupancy = len(detections)
        if occupancy >= self.settings.occupancy_limit and not self._occupancy_alerted:
            self._occupancy_alerted = True
            events.append(
                EdgeEvent(
                    event_type="occupancy_exceeded",
                    severity="warning",
                    camera_id=self.camera_id,
                    occupancy=occupancy,
                )
            )
        elif occupancy < self.settings.occupancy_limit:
            self._occupancy_alerted = False

        stale = [tid for tid, seen in self._track_last_seen.items() if now - seen > 120]
        for track_id in stale:
            self._track_last_seen.pop(track_id, None)
            self._track_first_seen.pop(track_id, None)
            self._track_zones.pop(track_id, None)
        if stale:
            # Chiziq va dwell holati ham tozalansin — aks holda kun bo'yi
            # o'sib boradigan lug'atlar 8/128 qurilmada xotirani yeydi.
            alive = set(self._track_last_seen)
            self.lines.retain(alive)
            self.dwell.retain(alive)
        return events


def build_person_detector(settings: SceneSettings, base_dir: Path) -> PersonDetector:
    """Konfigga qarab detektor yaratadi.

    Analizatordan ajratilgani — ko'p kamerali retail yo'li uchun: 8 kamera
    **bitta** modelni bo'lishadi.  Har kameraga alohida model yuklash xotirani
    ham, iGPU compile vaqtini ham bekorga sarflardi.  Bir vaqtda faqat bitta
    inferens oqimi `detect()` chaqiradi, shuning uchun bo'lishish xavfsiz.
    """
    if not settings.model_path:
        raise RuntimeError("scene.model_path berilishi shart")
    model_path = Path(settings.model_path)
    if not model_path.is_absolute():
        model_path = base_dir / model_path
    if settings.backend == "openvino":
        # Import shu yerda: OpenVINO faqat qurilmada o'rnatiladi, ishlab
        # chiqish mashinasida yo'q.
        from chaqimchi_ai.retail.detector_ov import OpenVINOPersonDetector

        detector: PersonDetector = OpenVINOPersonDetector(
            model_path, confidence=settings.confidence
        )
    else:
        detector = OpenCVDnnPersonDetector(
            model_path,
            input_size=settings.input_size,
            confidence=settings.confidence,
            nms_threshold=settings.nms_threshold,
        )
    return detector


def build_scene_analyzer(
    camera_id: str, settings: SceneSettings, base_dir: Path
) -> SceneAnalyzer | None:
    if not settings.enabled:
        return None
    return SceneAnalyzer(camera_id, build_person_detector(settings, base_dir), settings)
