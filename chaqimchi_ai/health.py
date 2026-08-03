"""Sog‘liq tekshiruvi yordamchilari."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from chaqimchi_ai.face_engine import FaceEngine


def engine_status(engine: "FaceEngine") -> Dict[str, Any]:
    providers = []
    for p in engine.providers:
        providers.append(p if isinstance(p, str) else p[0])
    return {
        "model_name": engine.model_name,
        "det_size": list(engine.det_size),
        "providers": providers,
        "recognition_loaded": engine.recognition_ready,
    }
