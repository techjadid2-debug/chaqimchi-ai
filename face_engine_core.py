#!/usr/bin/env python3
"""
Chaqimchi AI — yuzni tanish yadrosining yagona kirish nuqtasi.

Ishlatish:
  python face_engine_core.py --camera 0 --frame-skip 2

Asosiy modul: chaqimchi_ai.face_engine
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from chaqimchi_ai.face_engine import FaceCompareResult, FaceEngine, VideoFrameResult

__all__ = ["FaceEngine", "FaceCompareResult", "VideoFrameResult"]


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


async def _demo_camera(camera: int, frame_skip: int, max_frames: int | None) -> None:
    """Oddiy demo: kameradan async oqim va inferens vaqtlari."""
    engine = FaceEngine()
    async for result in engine.process_video_stream(
        video_source=camera,
        frame_skip=frame_skip,
        max_frames=max_frames,
    ):
        if result.skipped:
            logging.getLogger(__name__).debug("skip frame %d", result.frame_index)
            continue
        logging.getLogger(__name__).info(
            "freym %d | yuzlar=%d | inferens=%.2f ms",
            result.frame_index,
            len(result.faces),
            result.inference_ms,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Chaqimchi AI — Face Engine demo")
    parser.add_argument("--camera", type=int, default=0, help="Kamera indeksi (odatda 0)")
    parser.add_argument("--frame-skip", type=int, default=2, help="Har N freymdan bittasini inferens")
    parser.add_argument("--max-frames", type=int, default=None, help="Cheklash (sinov uchun)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Batafsil log")
    args = parser.parse_args()

    _setup_logging(args.verbose)
    try:
        asyncio.run(_demo_camera(args.camera, args.frame_skip, args.max_frames))
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("To‘xtatildi (Ctrl+C).")
        return 0
    except Exception as exc:  # pragma: no cover - CLI
        logging.getLogger(__name__).exception("Xatolik: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
