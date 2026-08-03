"""Oddiy IoU asosidagi yuz kuzatuvi (track ID)."""

from __future__ import annotations

from typing import Any, Dict, List


def bbox_iou(a: List[float], b: List[float]) -> float:
    """bbox [x1,y1,x2,y2] — intersection over union."""
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


class FaceTracker:
    """Kadrlar bo‘yicha yuzlarga barqaror track_id beradi."""

    def __init__(
        self,
        iou_threshold: float = 0.35,
        max_missed_frames: int = 15,
    ) -> None:
        if not 0.0 < iou_threshold <= 1.0:
            raise ValueError("iou_threshold (0,1] oralig‘ida bo‘lishi kerak")
        if max_missed_frames < 1:
            raise ValueError("max_missed_frames >= 1")
        self.iou_threshold = iou_threshold
        self.max_missed_frames = max_missed_frames
        self._tracks: Dict[int, Dict[str, Any]] = {}
        self._next_id = 1

    def update(self, faces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not faces:
            self._tick_unmatched(set())
            return faces

        pairs: List[tuple[float, int, int]] = []
        for fi, face in enumerate(faces):
            bbox = face.get("bbox")
            if not bbox:
                continue
            for tid, track in self._tracks.items():
                iou = bbox_iou(bbox, track["bbox"])
                if iou >= self.iou_threshold:
                    pairs.append((iou, fi, tid))

        pairs.sort(key=lambda x: x[0], reverse=True)
        used_faces: set[int] = set()
        used_tracks: set[int] = set()

        for _iou, fi, tid in pairs:
            if fi in used_faces or tid in used_tracks:
                continue
            used_faces.add(fi)
            used_tracks.add(tid)
            self._tracks[tid]["bbox"] = faces[fi]["bbox"]
            self._tracks[tid]["missed"] = 0
            faces[fi]["track_id"] = tid

        for fi, face in enumerate(faces):
            if fi in used_faces:
                continue
            tid = self._next_id
            self._next_id += 1
            self._tracks[tid] = {"bbox": face.get("bbox"), "missed": 0}
            face["track_id"] = tid
            used_tracks.add(tid)

        self._tick_unmatched(used_tracks)
        return faces

    def _tick_unmatched(self, matched_tids: set[int]) -> None:
        for tid in list(self._tracks.keys()):
            if tid in matched_tids:
                continue
            self._tracks[tid]["missed"] = self._tracks[tid].get("missed", 0) + 1
            if self._tracks[tid]["missed"] > self.max_missed_frames:
                del self._tracks[tid]
