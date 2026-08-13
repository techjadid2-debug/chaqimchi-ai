"""Hodisa klipi uchun ring buffer.

Kamera va ffmpeg binary'siz sinaladi: segment fayllari qo'lda yaratiladi,
ffmpeg chaqiruvi esa soxta runner bilan ushlanadi.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from chaqimchi_ai.retail.ringbuffer import RingBuffer

BASE = datetime(2026, 8, 13, 14, 0, 0, tzinfo=timezone.utc).timestamp()


def make_segment(buffer: RingBuffer, offset_sec: int, *, size: int = 1024) -> Path:
    stamp = datetime.fromtimestamp(BASE + offset_sec, tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = buffer.directory / f"{buffer.camera_id}-{stamp}.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def buffer_at(tmp_path: Path, **overrides) -> RingBuffer:
    defaults = dict(segment_sec=4, retention_sec=60, max_bytes=10_000)
    defaults.update(overrides)
    return RingBuffer("camera-01", tmp_path / "buffer", **defaults)  # type: ignore[arg-type]


# ── Yozish buyrug'i ──────────────────────────────────────────────────────


def test_recording_never_decodes_the_stream(tmp_path: Path) -> None:
    """Butun dizaynning asosi: `-c copy`, dekodlash yo'q."""
    command = buffer_at(tmp_path).record_command("rtsp://nvr/1")

    assert "-c" in command and command[command.index("-c") + 1] == "copy"
    # Qayta kodlash bayroqlari umuman bo'lmasligi kerak.
    assert not {"-c:v", "-vcodec", "-crf", "-preset"} & set(command)
    # UDP paket yo'qotishi buzuq segment beradi.
    assert command[command.index("-rtsp_transport") + 1] == "tcp"
    assert command[command.index("-segment_time") + 1] == "4"


# ── Segmentlarni topish ──────────────────────────────────────────────────


def test_segments_are_read_from_their_file_names(tmp_path: Path) -> None:
    buffer = buffer_at(tmp_path)
    for offset in (0, 4, 8):
        make_segment(buffer, offset)

    segments = buffer.scan()

    assert [segment.started_at - BASE for segment in segments] == [0, 4, 8]
    assert segments[0].ended_at - BASE == 4


def test_other_cameras_and_junk_files_are_ignored(tmp_path: Path) -> None:
    buffer = buffer_at(tmp_path)
    make_segment(buffer, 0)
    (buffer.directory / "camera-02-20260813-140000.mp4").write_bytes(b"x")
    (buffer.directory / "notes.txt").write_bytes(b"x")
    (buffer.directory / "camera-01-buzuq.mp4").write_bytes(b"x")

    assert len(buffer.scan()) == 1


def test_only_segments_overlapping_the_window_are_selected(tmp_path: Path) -> None:
    buffer = buffer_at(tmp_path)
    for offset in range(0, 40, 4):
        make_segment(buffer, offset)

    # Hodisa 20-soniyada; 10 oldin, 20 keyin → [10, 40)
    selected = buffer.segments_for(BASE + 10, BASE + 40)

    assert [segment.started_at - BASE for segment in selected] == [8, 12, 16, 20, 24, 28, 32, 36]


def test_window_must_be_forward_in_time(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        buffer_at(tmp_path).segments_for(BASE + 10, BASE)


# ── Tozalash ─────────────────────────────────────────────────────────────


def test_old_segments_are_deleted_by_time(tmp_path: Path) -> None:
    buffer = buffer_at(tmp_path, retention_sec=20)
    for offset in range(0, 40, 4):
        make_segment(buffer, offset)

    buffer.prune(now=BASE + 40)

    remaining = [segment.started_at - BASE for segment in buffer.scan()]
    assert remaining == [16, 20, 24, 28, 32, 36]  # oxirgi 20 soniya + joriy


def test_quota_deletes_the_oldest_first(tmp_path: Path) -> None:
    buffer = buffer_at(tmp_path, retention_sec=3600, max_bytes=3_000)
    for offset in range(0, 20, 4):
        make_segment(buffer, offset, size=1_000)

    buffer.prune(now=BASE + 20)

    remaining = [segment.started_at - BASE for segment in buffer.scan()]
    assert remaining == [8, 12, 16]  # 5 tadan 3 tasi qoldi (3 KB kvota)


def test_pruning_an_empty_directory_is_safe(tmp_path: Path) -> None:
    assert buffer_at(tmp_path).prune(now=BASE) == []
    assert buffer_at(tmp_path).stats() == {"segments": 0, "bytes": 0, "seconds": 0}


# ── Klip kesish ──────────────────────────────────────────────────────────


class FakeFFmpeg:
    def __init__(self, *, returncode: int = 0, write: bool = True) -> None:
        self.returncode = returncode
        self.write = write
        self.commands: list = []

    def __call__(self, command, **_kwargs):
        self.commands.append(command)
        if self.write:
            Path(command[-1]).write_bytes(b"klip")
        return subprocess.CompletedProcess(command, self.returncode, "", "")


def test_clip_is_cut_without_re_encoding(tmp_path: Path) -> None:
    runner = FakeFFmpeg()
    buffer = buffer_at(tmp_path, runner=runner)
    for offset in range(0, 40, 4):
        make_segment(buffer, offset)
    output = tmp_path / "clip.mp4"

    result = buffer.extract(BASE + 20, output=output, pre_sec=10, post_sec=20)

    assert result == output
    command = runner.commands[0]
    assert command[command.index("-c") + 1] == "copy"
    assert command[command.index("-t") + 1] == "30.000"
    # Klip 10-soniyadan boshlanadi, birinchi segment esa 8-da → siljish 2 s.
    assert command[command.index("-ss") + 1] == "2.000"


def test_single_segment_is_not_wrapped_in_concat(tmp_path: Path) -> None:
    runner = FakeFFmpeg()
    buffer = buffer_at(tmp_path, segment_sec=60, retention_sec=600, runner=runner)
    make_segment(buffer, 0)

    buffer.extract(BASE + 30, output=tmp_path / "clip.mp4", pre_sec=5, post_sec=5)

    assert "concat:" not in runner.commands[0][runner.commands[0].index("-i") + 1]


def test_missing_footage_returns_none_instead_of_failing(tmp_path: Path) -> None:
    """Hodisa buffer to'lgunicha bo'lsa klip yo'q — lekin hodisa yo'qolmaydi."""
    buffer = buffer_at(tmp_path, runner=FakeFFmpeg())
    assert buffer.extract(BASE, output=tmp_path / "clip.mp4") is None


def test_ffmpeg_failure_is_reported_as_no_clip(tmp_path: Path) -> None:
    buffer = buffer_at(tmp_path, runner=FakeFFmpeg(returncode=1, write=False))
    for offset in range(0, 40, 4):
        make_segment(buffer, offset)

    assert buffer.extract(BASE + 20, output=tmp_path / "clip.mp4") is None


def test_invalid_configuration_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        RingBuffer("c", tmp_path, segment_sec=0)
    with pytest.raises(ValueError):
        RingBuffer("c", tmp_path, segment_sec=10, retention_sec=5)
