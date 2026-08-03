"""Tarif cheklovlarini edge serverda qo‘llash."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from chaqimchi_ai.settings import CameraItem


def filter_cameras(cameras: List["CameraItem"], max_cameras: int) -> List["CameraItem"]:
    enabled = [c for c in cameras if c.enabled]
    if len(enabled) <= max_cameras:
        return cameras
    allowed_ids = {c.id for c in enabled[:max_cameras]}
    out: List["CameraItem"] = []
    for cam in cameras:
        if cam.enabled and cam.id not in allowed_ids:
            copy = cam.model_copy(update={"enabled": False})
            out.append(copy)
        else:
            out.append(cam)
    return out
