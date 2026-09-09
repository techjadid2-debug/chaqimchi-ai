"""Hodisa klipi uchun ring buffer.

Kamera va ffmpeg binary'siz sinaladi: segment fayllari soxta yaratiladi,
ffmpeg chaqiruvi esa soxta runner bilan ushlanadi.

DIQQAT — bu faylning eng muhim qoidasi.  Segment nomini **qo'lda**
yasamang: `make_segment` uni `record_command()` bergan patterndan
oladi.  Ilgari nom qo'lda va UTC bilan yasalardi, ya'ni testlar
yozuvchini umuman ko'rmasdi — natijada ffmpegga ortiqcha `%` bilan
pattern berilayotgani (fayl `camera-01-%Y0909-041347.mp4` deb
yozilardi) va nomdagi vaqt UTC emas, MAHALLIY ekani ikki oy davomida
sezilmadi.  Klip esa jonli do'konda hech qachon chiqmadi.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from enes.retail.ringbuffer import SEGMENT_PATTERN, RingBuffer, _parse_stamp

BASE = datetime(2026, 8, 13, 14, 0, 0, tzinfo=timezone.utc).timestamp()


def segment_name(buffer: RingBuffer, moment: float) -> str:
    """Nom AYNAN yozuvchi yasagandek — ffmpeg patternini `strftime` dan o'tkazib.

    Nega shunday: nomni bu yerda qo'lda yozsak, test yozuvchining o'zini
    hech qachon tekshirmaydi va pattern buzilsa ham yashil qolaveradi.
    `time.localtime` — chunki ffmpeg `-strftime` da mahalliy vaqt yozadi.
    """
    pattern = Path(buffer.record_command("rtsp://misol/1")[-1]).name
    return time.strftime(pattern, time.localtime(moment))


def make_segment(buffer: RingBuffer, offset_sec: int, *, size: int = 1024) -> Path:
    path = buffer.directory / segment_name(buffer, BASE + offset_sec)
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


def test_the_writer_and_the_reader_agree_on_the_file_name(tmp_path: Path) -> None:
    """Butun nosozlikning qulfi: ffmpeg yozadigan nomni O'QUVCHI tanisin.

    Aynan shu tekshiruv bo'lmagani uchun ikkita xato ikki oy yashirindi:
    patternda ortiqcha `%` (`%%` → literal `%`) va nomdagi vaqt UTC deb
    o'qilishi.  Test mashina zonasidan mustaqil — u konkret sonni emas,
    "yozib-o'qish aylanasi yopiqmi" xossasini tekshiradi.
    """
    buffer = buffer_at(tmp_path)
    moment = time.time()

    name = Path(buffer.record_command("rtsp://misol/1")[-1]).name
    written = time.strftime(name, time.localtime(moment))
    match = SEGMENT_PATTERN.match(written)

    assert match is not None, f"o'quvchi tanimadi: {written}"
    assert "%" not in written, f"pattern strftime dan o'tmadi: {written}"
    assert abs(_parse_stamp(match.group("stamp")) - moment) <= 1


def test_a_camera_id_with_a_percent_sign_is_rejected(tmp_path: Path) -> None:
    """Butun nom `strftime` dan o'tadi — id dagi `%` nomni jimgina buzardi."""
    with pytest.raises(ValueError):
        RingBuffer("camera-%d", tmp_path)


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


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="tzset faqat POSIX'da")
def test_segments_are_found_when_the_machine_is_not_on_utc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Do'kon kompyuteri UTC+5 da — jonli nosozlikning aynan sharoiti.

    Eski kod nomni UTC deb o'qirdi, ffmpeg esa mahalliy vaqt bilan
    yozadi: har segment besh soat "kelajakda" ko'rinib, hodisa oynasiga
    hech qachon tushmasdi va hisoblagich "buferda segment yo'q" derdi.
    """
    monkeypatch.setenv("TZ", "Asia/Tashkent")
    time.tzset()
    try:
        buffer = buffer_at(tmp_path, retention_sec=600)
        moment = time.time()
        path = buffer.directory / segment_name(buffer, moment)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")

        selected = buffer.segments_for(moment - 10, moment + 20)

        assert [item.path for item in selected] == [path]
        # Nom UTC deb o'qilganda xato aynan +5 soat bo'lardi.
        assert abs(selected[0].started_at - moment) < 60
    finally:
        monkeypatch.undo()
        time.tzset()


def test_a_segment_from_the_future_falls_back_to_the_file_time(tmp_path: Path) -> None:
    """Nom bilan soat yana ajralib qolsa, zanjir to'xtamasin — log aytsin."""
    buffer = buffer_at(tmp_path, retention_sec=600)
    now = time.time()
    path = buffer.directory / segment_name(buffer, now + 5 * 3600)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")

    segments = buffer.scan(now=now)

    assert len(segments) == 1
    # Fayl vaqti bo'yicha ishlanadi, ya'ni klip baribir kesiladi.
    assert abs(segments[0].started_at - (now - buffer.segment_sec)) < 5


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


def test_names_nobody_recognises_are_cleaned_up(tmp_path: Path) -> None:
    """0.6.31 gacha yozilgan `%Y…` fayllarni yangi kod ko'rmaydi.

    Ularni hech kim o'chirmasa papka disk to'lguncha o'saveradi — pilotda
    aynan shunday bo'lgan.  Qo'shni kamera va hali yozilayotgan fayl esa
    tegilmasin.
    """
    buffer = buffer_at(tmp_path, retention_sec=600)
    buffer.directory.mkdir(parents=True, exist_ok=True)
    eski = buffer.directory / "camera-01-%Y0909-041347.mp4"  # pilotdagi aynan nom
    qoshni = buffer.directory / "camera-02-%Y0909-041347.mp4"
    begona = buffer.directory / "camera-01-eslatma.txt"
    yangi = buffer.directory / "camera-01-%Y0909-041351.mp4"
    for path in (eski, qoshni, begona, yangi):
        path.write_bytes(b"x")
    eskirgan = time.time() - 3600
    for path in (eski, qoshni, begona):
        import os

        os.utime(path, (eskirgan, eskirgan))

    buffer.prune()

    assert not eski.exists()
    assert qoshni.exists(), "qo'shni kameraning fayliga tegilmasin"
    assert begona.exists(), "video bo'lmagan faylga tegilmasin"
    assert yangi.exists(), "hali yozilayotgan fayl tortib olinmasin"


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


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg o'rnatilmagan")
def test_a_real_ffmpeg_writes_names_the_scanner_can_read(tmp_path: Path) -> None:
    """Yagona test HAQIQIY ffmpeg bilan — soxta runner buni ko'ra olmaydi.

    Kamera kerak emas: kirish sifatida oldindan tayyorlangan fayl beriladi,
    tekshirilayotgani esa NOM — u `-strftime` va pattern bilan hal bo'ladi.
    Aynan shu yo'l bilan `%%` xatosi productionda tug'ilgan edi.
    """
    manba = tmp_path / "manba.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x120:rate=10",
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(manba),
        ],
        check=True,
        timeout=60,
    )

    buffer = buffer_at(tmp_path, segment_sec=1, retention_sec=600)
    command = buffer.record_command(str(manba))
    # RTSP transportini olib tashlaymiz — fayl kirishi uni tushunmaydi.
    # Qolgan hammasi (pattern, `-strftime`, `-c copy`) production'dagidek.
    transport = command.index("-rtsp_transport")
    command = command[:transport] + command[transport + 2 :]
    subprocess.run(command, check=True, timeout=60)

    segments = buffer.scan()
    assert segments, (
        f"ffmpeg yozgan nomni scan() tanimadi: {sorted(p.name for p in buffer.directory.iterdir())}"
    )
    assert abs(segments[-1].started_at - time.time()) < 120


def test_bundled_ffmpeg_is_preferred(tmp_path, monkeypatch) -> None:
    """Do'kon kompyuterida PATH'da ffmpeg yo'q — birga kelgani ishlatiladi."""
    from enes.retail.ringbuffer import default_ffmpeg_binary

    monkeypatch.setenv("ENES_FFMPEG", str(tmp_path / "maxsus-ffmpeg"))
    assert default_ffmpeg_binary() == str(tmp_path / "maxsus-ffmpeg")

    monkeypatch.delenv("ENES_FFMPEG", raising=False)
    # Birga kelgan fayl yo'q (dev muhit) — PATH'dagi "ffmpeg" ga tushadi.
    assert default_ffmpeg_binary() in ("ffmpeg",) or default_ffmpeg_binary().endswith("ffmpeg")
