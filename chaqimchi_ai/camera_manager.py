"""Kamera oqimlarini boshqarish moduli (Production Edition)."""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

import cv2
import numpy as np

from chaqimchi_ai.antispoof import check_liveness
from chaqimchi_ai.database import FaceDatabase
from chaqimchi_ai.face_engine import FaceEngine
from chaqimchi_ai.face_tracker import FaceTracker
from chaqimchi_ai.match_debounce import MatchDebouncer
from chaqimchi_ai.metrics import get_metrics

logger = logging.getLogger(__name__)


class CameraTask:
    def __init__(
        self,
        camera_id: str,
        source: Union[int, str],
        engine: FaceEngine,
        db: FaceDatabase,
        on_match: Optional[Callable] = None,
        compare_threshold: float = 0.4,
        match_debounce_sec: int = 30,
        save_snapshots: bool = True,
        snapshots_dir: Path = Path("data/snapshots"),
        enable_tracking: bool = True,
        tracking_iou: float = 0.35,
        tracking_max_missed: int = 15,
        frame_skip: int = 5,
        antispoof_enabled: bool = False,
        antispoof_min_blur: float = 80.0,
        antispoof_checker: Optional[Any] = None,
    ):
        self.camera_id = camera_id
        self.source = source
        self.engine = engine
        self.db = db
        self.on_match = on_match
        self.compare_threshold = compare_threshold
        self.save_snapshots = save_snapshots
        self.snapshots_dir = snapshots_dir
        self._debouncer = MatchDebouncer(float(match_debounce_sec))
        self._tracker: Optional[FaceTracker] = (
            FaceTracker(tracking_iou, tracking_max_missed) if enable_tracking else None
        )
        self.frame_skip = max(1, int(frame_skip))
        self.antispoof_enabled = antispoof_enabled
        self.antispoof_min_blur = antispoof_min_blur
        self.antispoof_checker = antispoof_checker
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        self.is_running = True
        self._task = asyncio.create_task(self._run())
        logger.info(f"Kamera vazifasi boshlandi: {self.camera_id} ({self.source})")

    async def stop(self):
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info(f"Kamera vazifasi to'xtatildi: {self.camera_id}")

    def _crop_bbox(self, frame_bgr: np.ndarray, bbox: list) -> np.ndarray:
        h, w = frame_bgr.shape[:2]
        x1 = max(0, int(bbox[0]))
        y1 = max(0, int(bbox[1]))
        x2 = min(w, int(bbox[2]))
        y2 = min(h, int(bbox[3]))
        return frame_bgr[y1:y2, x1:x2]

    def _save_face_snapshot(self, frame_bgr: np.ndarray, bbox: list) -> Optional[str]:
        """Aniqlangan yuz rasmini diskka saqlash; nisbiy yo‘l qaytaradi."""
        try:
            self.snapshots_dir.mkdir(parents=True, exist_ok=True)

            h, w = frame_bgr.shape[:2]
            x1 = max(0, int(bbox[0]))
            y1 = max(0, int(bbox[1]))
            x2 = min(w, int(bbox[2]))
            y2 = min(h, int(bbox[3]))

            margin_x = int((x2 - x1) * 0.2)
            margin_y = int((y2 - y1) * 0.2)
            x1 = max(0, x1 - margin_x)
            y1 = max(0, y1 - margin_y)
            x2 = min(w, x2 + margin_x)
            y2 = min(h, y2 + margin_y)

            crop = frame_bgr[y1:y2, x1:x2]
            if crop.size == 0:
                return None

            filename = f"{self.camera_id}_{int(time.time() * 1000)}.jpg"
            filepath = self.snapshots_dir / filename
            cv2.imwrite(str(filepath), crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return str(filepath)
        except Exception as e:
            logger.warning(f"Snapshot saqlashda xato: {e}")
            return None

    async def _run(self):
        backoff = 5
        max_backoff = 60

        while self.is_running:
            try:
                async for result in self.engine.process_video_stream(
                    self.source, frame_skip=self.frame_skip
                ):
                    if not self.is_running:
                        break

                    if result.skipped or not result.faces:
                        continue

                    get_metrics().record_inference(
                        self.camera_id,
                        result.inference_ms,
                        faces=len(result.faces),
                    )

                    faces = result.faces
                    if self._tracker is not None:
                        faces = self._tracker.update(faces)

                    for face in faces:
                        emb = face["embedding"]
                        matches = self.db.search(emb, threshold=self.compare_threshold)

                        if not matches:
                            continue

                        best = matches[0]
                        person_id = str(best["id"])
                        if not self._debouncer.should_emit(self.camera_id, person_id):
                            continue

                        if (
                            self.antispoof_enabled
                            and result.frame is not None
                            and face.get("bbox")
                        ):
                            crop = self._crop_bbox(result.frame, face["bbox"])
                            live = check_liveness(
                                crop,
                                min_blur_variance=self.antispoof_min_blur,
                                checker=self.antispoof_checker,
                            )
                            if not live.get("live"):
                                get_metrics().record_spoof(self.camera_id)
                                logger.info(
                                    "[%s] Anti-spoof rad etdi (%s): %s",
                                    self.camera_id,
                                    best["name"],
                                    live.get("reason") or live,
                                )
                                continue

                        get_metrics().record_match(self.camera_id)

                        image_path: Optional[str] = None
                        if (
                            self.save_snapshots
                            and result.frame is not None
                            and face.get("bbox")
                        ):
                            image_path = self._save_face_snapshot(
                                result.frame, face["bbox"]
                            )

                        logger.info(
                            f"[{self.camera_id}] MOS KELDI: {best['name']} ({best['score']:.2f})"
                        )
                        if self.on_match:
                            await self.on_match(
                                self.camera_id,
                                best,
                                face,
                                image_path=image_path,
                            )

                if self.is_running:
                    logger.warning(
                        f"[{self.camera_id}] Oqim uzildi, {backoff}s dan keyin qayta ulanish..."
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)

            except asyncio.CancelledError:
                logger.info(f"[{self.camera_id}] Task bekor qilindi.")
                break
            except Exception as e:
                logger.error(f"[{self.camera_id}] Xato: {e}")
                if self.is_running:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)


class CameraManager:
    def __init__(
        self,
        engine: FaceEngine,
        db: FaceDatabase,
        compare_threshold: float = 0.4,
        match_debounce_sec: int = 30,
        save_snapshots: bool = True,
        snapshots_dir: Optional[Path] = None,
        enable_tracking: bool = True,
        tracking_iou: float = 0.35,
        tracking_max_missed: int = 15,
        frame_skip: int = 5,
        antispoof_enabled: bool = False,
        antispoof_min_blur: float = 80.0,
        antispoof_checker: Optional[Any] = None,
    ):
        self.engine = engine
        self.db = db
        self.compare_threshold = compare_threshold
        self.match_debounce_sec = match_debounce_sec
        self.save_snapshots = save_snapshots
        self.snapshots_dir = snapshots_dir or Path("data/snapshots")
        self.enable_tracking = enable_tracking
        self.tracking_iou = tracking_iou
        self.tracking_max_missed = tracking_max_missed
        self.frame_skip = max(1, int(frame_skip))
        self.antispoof_enabled = antispoof_enabled
        self.antispoof_min_blur = antispoof_min_blur
        self.antispoof_checker = antispoof_checker
        self.cameras: Dict[str, CameraTask] = {}

    async def add_camera(
        self,
        camera_id: str,
        source: Union[int, str],
        on_match: Optional[Callable] = None,
    ):
        if camera_id in self.cameras:
            await self.cameras[camera_id].stop()

        task = CameraTask(
            camera_id,
            source,
            self.engine,
            self.db,
            on_match,
            compare_threshold=self.compare_threshold,
            match_debounce_sec=self.match_debounce_sec,
            save_snapshots=self.save_snapshots,
            snapshots_dir=self.snapshots_dir,
            enable_tracking=self.enable_tracking,
            tracking_iou=self.tracking_iou,
            tracking_max_missed=self.tracking_max_missed,
            frame_skip=self.frame_skip,
            antispoof_enabled=self.antispoof_enabled,
            antispoof_min_blur=self.antispoof_min_blur,
            antispoof_checker=self.antispoof_checker,
        )
        self.cameras[camera_id] = task
        await task.start()

    async def remove_camera(self, camera_id: str) -> bool:
        if camera_id in self.cameras:
            await self.cameras[camera_id].stop()
            del self.cameras[camera_id]
            return True
        return False

    async def stop_all(self):
        tasks = [task.stop() for task in self.cameras.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.cameras.clear()
