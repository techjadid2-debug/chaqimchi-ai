"""Chaqimchi AI paketi; og'ir vision importlari lazy yuklanadi."""

from typing import Any

__version__ = "0.5.0"
__all__ = ["FaceEngine", "FaceCompareResult", "VideoFrameResult", "__version__"]


def __getattr__(name: str) -> Any:
    if name in {"FaceEngine", "FaceCompareResult", "VideoFrameResult"}:
        from chaqimchi_ai.face_engine import FaceCompareResult, FaceEngine, VideoFrameResult

        return {
            "FaceEngine": FaceEngine,
            "FaceCompareResult": FaceCompareResult,
            "VideoFrameResult": VideoFrameResult,
        }[name]
    raise AttributeError(name)
