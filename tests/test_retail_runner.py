"""Kamera halqasi: kadr o'qish, dekodlashni tejash, uzilishdan tiklanish.

Kamera ham, ffmpeg ham soxta: `capture_factory` va `spawn` tashqaridan
beriladi, soat ham.  Shu sabab uzilish va qayta ulanish kabi holatlar
sekundlab kutmasdan sinaladi.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Tuple

import numpy as np
import pytest

from chaqimchi_ai.retail.broker import FrameBroker
from chaqimchi_ai.retail.budget import InferenceBudget
from chaqimchi_ai.retail.claims import Priority
from chaqimchi_ai.retail.pipeline import RetailPipeline
from chaqimchi_ai.retail.ringbuffer import RingBuffer
from chaqimchi_ai.retail.rules import RuleEngine
from chaqimchi_ai.retail.runner import MAX_BACKOFF_SEC, CameraSource, RetailRunner

FRAME = np.zeros((8, 8, 3), dtype=np.uint8)


# ── Soxta bo'laklar ──────────────────────────────────────────────────────


class FakeCapture:
    def __init__(self, *, opened: bool = True) -> None:
        self.opened = opened
        self.grabs = 0
        self.retrieves = 0
        self.released = False
        self.alive = True

    def isOpened(self) -> bool:  # noqa: N802 — OpenCV nomi
        return self.opened

    def grab(self) -> bool:
        self.grabs += 1
        return self.alive

    def retrieve(self) -> Tuple[bool, Any]:
        self.retrieves += 1
        return (True, FRAME) if self.alive else (False, None)

    def release(self) -> None:
        self.released = True

    def set(self, *_args) -> None:
        pass


class FakeProcess:
    def __init__(self, command) -> None:
        self.command = command
        self.alive = True
        self.terminated = False

    def poll(self) -> Optional[int]:
        return None if self.alive else 1

    def terminate(self) -> None:
        self.terminated = True
        self.alive = False

    def wait(self, timeout: Optional[float] = None) -> int:
        return 0


class FakeGate:
    def __init__(self) -> None:
        self.min_area_ratio = 0.01
        self.ratio = 1.0

    def motion_ratio(self, _frame) -> float:
        return self.ratio


class FakeAnalyzer:
    def __init__(self) -> None:
        self.motion = FakeGate()
        self.calls = 0

    def analyze(self, _frame, *, now: float):
        self.calls += 1
        return []


def build(
    tmp_path: Path, **source_kwargs
) -> Tuple[RetailRunner, List[FakeCapture], List[FakeProcess]]:
    captures: List[FakeCapture] = []
    processes: List[FakeProcess] = []

    def capture_factory(_url: str) -> FakeCapture:
        capture = FakeCapture()
        captures.append(capture)
        return capture

    def spawn(command, **_kwargs) -> FakeProcess:
        process = FakeProcess(command)
        processes.append(process)
        return process

    broker = FrameBroker(InferenceBudget(target_fps=30.0, min_fps=1.0, max_fps=60.0))
    pipeline = RetailPipeline(
        broker,
        RuleEngine(),
        on_action=lambda _action, _event: None,
        clock=lambda: 0.0,
        local_time=lambda: None,
    )
    runner = RetailRunner(
        pipeline,
        capture_factory=capture_factory,
        spawn=spawn,
        clock=lambda: 0.0,
        sleep=lambda _seconds: None,
    )
    source = CameraSource(
        camera_id="kassa-01",
        stream_url="rtsp://nvr/sub",
        sample_fps=5.0,
        **source_kwargs,
    )
    clips = RingBuffer("kassa-01", tmp_path / "buffer") if source.record_url else None
    runner.add_camera(source, FakeAnalyzer(), clips=clips, now=0.0)  # type: ignore[arg-type]
    return runner, captures, processes


# ── Kadr o'qish ──────────────────────────────────────────────────────────


def test_extra_frames_are_grabbed_but_not_decoded(tmp_path: Path) -> None:
    """Dekodlash eng qimmat ish — kamera 15 FPS bersa ham 5 tasi yetadi.

    Har kadrni dekodlash 8 kamerada N100 ning katta qismini yeb qo'yardi.
    """
    runner, captures, _processes = build(tmp_path)

    # 1 soniya ichida 15 kadr, 5 FPS namuna → 5 tasi dekodlanishi kerak.
    decoded = sum(runner.capture_once("kassa-01", now=index / 15.0) for index in range(15))

    assert captures[0].grabs == 15
    assert captures[0].retrieves == decoded == 5


def test_decoded_frame_reaches_the_pipeline(tmp_path: Path) -> None:
    runner, _captures, _processes = build(tmp_path)

    assert runner.capture_once("kassa-01", now=1.0) is True
    assert runner.stats()["offered"] == 1
    assert runner.stats()["streams"]["kassa-01"]["frames"] == 1


def test_analysis_runs_only_when_the_loop_asks(tmp_path: Path) -> None:
    runner, _captures, _processes = build(tmp_path)
    runner.capture_once("kassa-01", now=1.0)

    assert runner.inference_once(now=1.0) is True
    assert runner.inference_once(now=1.0) is False  # navbat bo'shadi


# ── Uzilish va tiklanish ─────────────────────────────────────────────────


def test_broken_stream_is_retried_with_growing_backoff(tmp_path: Path) -> None:
    runner, captures, _processes = build(tmp_path)
    runner.capture_once("kassa-01", now=1.0)
    captures[0].alive = False

    assert runner.capture_once("kassa-01", now=2.0) is False
    assert captures[0].released is True
    # Kutish tugamaguncha yangi ulanish ochilmaydi.
    assert runner.capture_once("kassa-01", now=2.5) is False
    assert len(captures) == 1

    assert runner.capture_once("kassa-01", now=10.0) is True
    assert len(captures) == 2
    assert runner.stats()["streams"]["kassa-01"]["reconnects"] == 2


def test_backoff_never_grows_past_the_ceiling(tmp_path: Path) -> None:
    """Kechqurun o'chirilgan kamera ertalab yarim daqiqadan ko'p kutmasin.

    Kutish ikki barobardan o'sadi (2, 4, 8, 16 …) — bu log to'ldirmaslik
    uchun.  Lekin cheksiz o'ssa kamera qaytganini soatlab bilmay qolardik.
    """
    broker = FrameBroker(InferenceBudget(target_fps=30.0, min_fps=1.0, max_fps=60.0))
    pipeline = RetailPipeline(
        broker, RuleEngine(), on_action=lambda *_: None, clock=lambda: 0.0, local_time=lambda: None
    )
    runner = RetailRunner(
        pipeline,
        capture_factory=lambda _url: FakeCapture(opened=False),
        clock=lambda: 0.0,
        sleep=lambda _s: None,
    )
    runner.add_camera(
        CameraSource(camera_id="cam", stream_url="rtsp://x"),
        FakeAnalyzer(),
        now=0.0,  # type: ignore[arg-type]
    )

    now = 0.0
    waits = []
    for _attempt in range(8):
        assert runner.capture_once("cam", now=now) is False
        retry_at = runner._streams["cam"].retry_at
        waits.append(retry_at - now)
        now = retry_at

    assert waits[:4] == [2.0, 4.0, 8.0, 16.0]
    assert max(waits) == MAX_BACKOFF_SEC


def test_a_camera_that_will_not_open_does_not_leak(tmp_path: Path) -> None:
    broker = FrameBroker(InferenceBudget(target_fps=30.0, min_fps=1.0, max_fps=60.0))
    pipeline = RetailPipeline(
        broker, RuleEngine(), on_action=lambda *_: None, clock=lambda: 0.0, local_time=lambda: None
    )
    closed: List[FakeCapture] = []

    def capture_factory(_url: str) -> FakeCapture:
        capture = FakeCapture(opened=False)
        closed.append(capture)
        return capture

    runner = RetailRunner(
        pipeline, capture_factory=capture_factory, clock=lambda: 0.0, sleep=lambda _s: None
    )
    runner.add_camera(
        CameraSource(camera_id="cam", stream_url="rtsp://x"),
        FakeAnalyzer(),
        now=0.0,  # type: ignore[arg-type]
    )

    assert runner.capture_once("cam", now=1.0) is False
    assert closed[0].released is True


# ── Segment yozuvchi ─────────────────────────────────────────────────────


def test_recorder_starts_once_and_uses_the_main_stream(tmp_path: Path) -> None:
    runner, _captures, processes = build(tmp_path, record_url="rtsp://nvr/main")

    runner.capture_once("kassa-01", now=1.0)
    runner.capture_once("kassa-01", now=2.0)

    assert len(processes) == 1
    assert "rtsp://nvr/main" in processes[0].command
    assert processes[0].command[processes[0].command.index("-c") + 1] == "copy"


def test_a_dead_recorder_is_restarted(tmp_path: Path) -> None:
    """Yozuvchi o'lsa klip yo'qoladi va buni hech kim sezmaydi — shuning
    uchun har qadamda arzon tekshiruv bor."""
    runner, _captures, processes = build(tmp_path, record_url="rtsp://nvr/main")
    runner.capture_once("kassa-01", now=1.0)
    processes[0].alive = False

    runner.capture_once("kassa-01", now=1.5)  # hali kutish tugamagan
    assert len(processes) == 1

    runner.capture_once("kassa-01", now=10.0)
    assert len(processes) == 2
    assert runner.stats()["streams"]["kassa-01"]["recorder_starts"] == 2


def test_camera_without_record_url_has_no_recorder(tmp_path: Path) -> None:
    runner, _captures, processes = build(tmp_path)
    runner.capture_once("kassa-01", now=1.0)
    assert processes == []


# ── Boshqaruv ────────────────────────────────────────────────────────────


def test_stop_releases_camera_and_recorder(tmp_path: Path) -> None:
    runner, captures, processes = build(tmp_path, record_url="rtsp://nvr/main")
    runner.capture_once("kassa-01", now=1.0)

    runner.stop()

    assert captures[0].released is True
    assert processes[0].terminated is True
    assert runner.running is False


def test_threads_actually_run_and_shut_down(tmp_path: Path) -> None:
    """Yagona oqimli test: halqalar rostdan aylanadi va toza to'xtaydi."""
    import time

    broker = FrameBroker(InferenceBudget(target_fps=30.0, min_fps=1.0, max_fps=60.0))
    pipeline = RetailPipeline(
        broker, RuleEngine(), on_action=lambda *_: None, local_time=lambda: None
    )
    captures: List[FakeCapture] = []

    def capture_factory(_url: str) -> FakeCapture:
        capture = FakeCapture()
        captures.append(capture)
        return capture

    analyzer = FakeAnalyzer()
    runner = RetailRunner(pipeline, capture_factory=capture_factory, housekeeping_sec=0.05)
    runner.add_camera(
        CameraSource(camera_id="cam", stream_url="rtsp://x", sample_fps=50.0),
        analyzer,  # type: ignore[arg-type]
    )

    runner.start()
    assert runner.running is True
    deadline = time.monotonic() + 3.0
    while analyzer.calls == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    runner.stop(timeout=3.0)

    assert analyzer.calls > 0  # kadr o'qildi va tahlil qilindi
    assert runner.running is False
    assert captures[0].released is True


def test_camera_cannot_be_added_while_running(tmp_path: Path) -> None:
    runner, _captures, _processes = build(tmp_path)
    runner.start()
    try:
        with pytest.raises(RuntimeError):
            runner.add_camera(
                CameraSource(camera_id="ikkinchi", stream_url="rtsp://y"),
                FakeAnalyzer(),  # type: ignore[arg-type]
            )
    finally:
        runner.stop(timeout=2.0)


def test_pressure_signal_reaches_the_budget(tmp_path: Path) -> None:
    """CPU/harorat chegarada bo'lsa byudjet o'zi tushishi kerak."""
    broker = FrameBroker(InferenceBudget(target_fps=30.0, min_fps=1.0, max_fps=60.0))
    pipeline = RetailPipeline(
        broker, RuleEngine(), on_action=lambda *_: None, clock=lambda: 0.0, local_time=lambda: None
    )
    runner = RetailRunner(
        pipeline,
        capture_factory=lambda _url: FakeCapture(),
        clock=lambda: 0.0,
        sleep=lambda _s: None,
        pressure=lambda: 0.9,
    )
    runner.add_camera(
        CameraSource(camera_id="cam", stream_url="rtsp://x"),
        FakeAnalyzer(),
        now=0.0,  # type: ignore[arg-type]
    )

    runner.housekeeping_once()

    assert broker.budget.stats()["pressure"] == 0.9


def test_housekeeping_prunes_old_segments(tmp_path: Path) -> None:
    runner, _captures, _processes = build(tmp_path, record_url="rtsp://nvr/main")
    buffer = tmp_path / "buffer"
    buffer.mkdir(parents=True, exist_ok=True)
    old = buffer / "kassa-01-20200101-000000.mp4"
    old.write_bytes(b"eski")

    runner.housekeeping_once()

    assert not old.exists()


def test_invalid_sample_rate_is_rejected() -> None:
    with pytest.raises(ValueError):
        CameraSource(camera_id="cam", stream_url="rtsp://x", sample_fps=0)


def test_security_camera_keeps_its_priority(tmp_path: Path) -> None:
    runner, _captures, _processes = build(tmp_path, priority=Priority.SECURITY)
    runner.capture_once("kassa-01", now=1.0)

    cameras = runner.stats()["broker"]["cameras"]
    assert cameras["kassa-01"]["priority"] == "SECURITY"
    assert cameras["kassa-01"]["floor_fps"] == 1.0
