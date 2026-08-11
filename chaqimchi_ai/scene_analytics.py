"""Motion-gated person analytics: person, zona, loitering va occupancy."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Protocol, Sequence, Tuple

import cv2
import numpy as np

from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.face_tracker import FaceTracker
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


class RKNNPersonDetector:
    """RK3588 RKNNLite adapteri; single-output YOLOv8/YOLOX exportini qabul qiladi."""

    def __init__(
        self,
        model_path: Path,
        *,
        input_size: int = 640,
        confidence: float = 0.45,
        nms_threshold: float = 0.45,
    ) -> None:
        try:
            from rknnlite.api import RKNNLite
        except ImportError as exc:  # pragma: no cover - faqat RK3588 qurilmada
            raise RuntimeError("RKNNLite2 vendor wheel o'rnatilishi kerak") from exc
        if not model_path.is_file():
            raise FileNotFoundError(f"RKNN modeli topilmadi: {model_path}")
        self._runtime = RKNNLite()
        if self._runtime.load_rknn(str(model_path)) != 0:
            raise RuntimeError("RKNN model yuklanmadi")
        if self._runtime.init_runtime() != 0:
            raise RuntimeError("RKNN runtime ishga tushmadi")
        self.input_size = int(input_size)
        self.confidence = float(confidence)
        self.nms_threshold = float(nms_threshold)

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        height, width = frame.shape[:2]
        resized = cv2.resize(frame, (self.input_size, self.input_size))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        outputs = self._runtime.inference(inputs=[rgb])
        if not outputs or len(outputs) != 1:
            raise RuntimeError("RKNN model single-output YOLO eksport bo'lishi kerak")
        return _decode_person_output(
            outputs[0],
            width=width,
            height=height,
            input_size=self.input_size,
            confidence=self.confidence,
            nms_threshold=self.nms_threshold,
        )

    def close(self) -> None:
        self._runtime.release()


class MotionGate:
    def __init__(self, min_area_ratio: float = 0.01) -> None:
        self.min_area_ratio = float(min_area_ratio)
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=300, varThreshold=25, detectShadows=False
        )
        self._frames = 0

    def has_motion(self, frame: np.ndarray) -> bool:
        self._frames += 1
        small = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
        mask = self._subtractor.apply(small)
        if self._frames <= 5:
            return True
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        changed = float(cv2.countNonZero(mask)) / float(mask.size)
        return changed >= self.min_area_ratio


def _inside(point: Tuple[float, float], polygon: Sequence[Tuple[float, float]]) -> bool:
    contour = np.asarray(polygon, dtype=np.float32)
    return cv2.pointPolygonTest(contour, point, False) >= 0


class SceneAnalyzer:
    def __init__(
        self,
        camera_id: str,
        detector: PersonDetector,
        settings: SceneSettings,
    ) -> None:
        self.camera_id = camera_id
        self.detector = detector
        self.settings = settings
        self.motion = MotionGate(settings.motion_min_area_ratio)
        self.tracker = FaceTracker(iou_threshold=0.25, max_missed_frames=10)
        self.zones: List[SceneZoneSettings] = [
            zone for zone in settings.zones if zone.camera_id == camera_id
        ]
        self._last_analysis = 0.0
        self._track_first_seen: Dict[int, float] = {}
        self._track_last_seen: Dict[int, float] = {}
        self._track_zones: Dict[int, set[str]] = {}
        self._emitted: Dict[Tuple[str, str], float] = {}
        self._occupancy_alerted = False

    def _emit_allowed(self, kind: str, key: str, now: float) -> bool:
        token = (kind, key)
        previous = self._emitted.get(token, 0.0)
        if now - previous < self.settings.event_debounce_sec:
            return False
        self._emitted[token] = now
        return True

    def process(self, frame: np.ndarray, *, now: float | None = None) -> List[EdgeEvent]:
        now = time.monotonic() if now is None else float(now)
        if not self.motion.has_motion(frame):
            return []
        min_interval = 1.0 / self.settings.burst_fps
        if now - self._last_analysis < min_interval:
            return []
        self._last_analysis = now

        detections = self.tracker.update(self.detector.detect(frame))
        events: List[EdgeEvent] = []
        height, width = frame.shape[:2]
        active_ids: set[int] = set()

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
            center = ((x1 + x2) / 2 / width, y2 / height)
            current_zones = {
                zone.name for zone in self.zones if _inside(center, zone.polygon)
            }
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

            elapsed = now - self._track_first_seen[track_id]
            if elapsed >= self.settings.loitering_sec and self._emit_allowed(
                "loitering", str(track_id), now
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
        return events


def build_scene_analyzer(
    camera_id: str, settings: SceneSettings, base_dir: Path
) -> SceneAnalyzer | None:
    if not settings.enabled:
        return None
    if not settings.model_path:
        raise RuntimeError("scene.model_path berilishi shart")
    model_path = Path(settings.model_path)
    if not model_path.is_absolute():
        model_path = base_dir / model_path
    detector_class = RKNNPersonDetector if settings.backend == "rknn" else OpenCVDnnPersonDetector
    detector = detector_class(
        model_path,
        input_size=settings.input_size,
        confidence=settings.confidence,
        nms_threshold=settings.nms_threshold,
    )
    return SceneAnalyzer(camera_id, detector, settings)
