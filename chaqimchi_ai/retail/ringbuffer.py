"""Hodisa klipi uchun xom H.264 ring buffer.

Asosiy qoida: **main stream hech qachon dekodlanmaydi.**  FFmpeg oqimni
qanday kelsa shundayligicha (`-c copy`) qisqa segmentlarga bo'lib diskka
yozadi.  Hodisa bo'lganda kerakli segmentlar yana `-c copy` bilan kesiladi.
Ya'ni CPU deyarli sarflanmaydi — bu 8/128 qurilmada 8 kamera uchun shart.

Agar main streamni dekodlab, qayta kodlaganimizda bitta kamera ham N100 ni
to'ldirib qo'yardi va AI uchun quvvat qolmasdi.

To'liq video arxiv NVR da qoladi.  Bu buffer faqat hodisa atrofidagi 30
soniya uchun: `data/buffer` da 3 kun / 40 GB (`sotqin_profile`).
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Sequence

#: Klip nega chiqmagani.  Ikkalasi butunlay boshqa nosozlik va boshqa
#: tuzatishni talab qiladi — bitta `missing` ostida yashirilmasin.
NO_SEGMENTS = "no_segments"
CUT_FAILED = "cut_failed"


@dataclass(frozen=True)
class ClipResult:
    """Kesish natijasi.  `path` bo'lsa muvaffaqiyat, `reason` esa `None`."""

    path: Optional[Path]
    reason: Optional[str] = None
    #: Odam o'qiydigan tafsilot (ffmpeg chiqishi) — logga va diagnostikaga.
    detail: Optional[str] = None


def default_ffmpeg_binary() -> str:
    """ffmpeg qayerda — Windows payload'idagi birga kelgan nusxa birinchi.

    Do'kon kompyuterida PATH'da ffmpeg bo'lmaydi; o'rnatuvchi uni
    `bin/ffmpeg.exe` sifatida dastur papkasiga qo'yadi
    (`scripts/build_windows_payload.py step_ffmpeg`).  Linux Sotqin'da
    esa hostdagi ffmpeg ishlatiladi (PATH).
    """
    override = os.environ.get("CHAQIMCHI_FFMPEG", "").strip()
    if override:
        return override
    bundled = (
        Path(__file__).resolve().parents[2]
        / "bin"
        / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    )
    if bundled.is_file():
        return str(bundled)
    return "ffmpeg"


#: Segment nomi: `camera-01-20260813-142530.mp4`.  Vaqt nomdan o'qiladi —
#: alohida indeks fayli yuritish kerak emas va u buzilib qolmaydi.
SEGMENT_PATTERN = re.compile(r"^(?P<camera>.+)-(?P<stamp>\d{8}-\d{6})\.(?P<ext>mp4|ts)$")
SEGMENT_TIME_FORMAT = "%Y%m%d-%H%M%S"

Runner = Callable[..., subprocess.CompletedProcess]


def _parse_stamp(stamp: str) -> float:
    moment = datetime.strptime(stamp, SEGMENT_TIME_FORMAT).replace(tzinfo=timezone.utc)
    return moment.timestamp()


@dataclass(frozen=True)
class Segment:
    path: Path
    started_at: float
    duration_sec: float
    size_bytes: int

    @property
    def ended_at(self) -> float:
        return self.started_at + self.duration_sec

    def overlaps(self, start: float, end: float) -> bool:
        return self.started_at < end and self.ended_at > start


class RingBuffer:
    def __init__(
        self,
        camera_id: str,
        directory: Path,
        *,
        segment_sec: int = 4,
        retention_sec: int = 180,
        max_bytes: int = 2 * 1024**3,
        container: str = "mp4",
        ffmpeg_binary: Optional[str] = None,
        runner: Runner = subprocess.run,
    ) -> None:
        if segment_sec < 1:
            raise ValueError("segment_sec kamida 1 soniya bo'lishi kerak")
        if retention_sec < segment_sec:
            raise ValueError("retention_sec segment_sec dan kichik bo'lmasin")
        self.camera_id = camera_id
        self.directory = Path(directory)
        self.segment_sec = int(segment_sec)
        self.retention_sec = int(retention_sec)
        self.max_bytes = int(max_bytes)
        self.container = container
        self.ffmpeg_binary = ffmpeg_binary or default_ffmpeg_binary()
        self.runner = runner

    # ── Yozish ───────────────────────────────────────────────────────────

    def record_command(self, rtsp_url: str) -> List[str]:
        """Uzluksiz segment yozish buyrug'i.

        `-c copy` — dekodlash ham, kodlash ham yo'q.  `-rtsp_transport tcp`
        chunki UDP paket yo'qotishi buzuq segment beradi.
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        pattern = str(self.directory / f"{self.camera_id}-%{SEGMENT_TIME_FORMAT}.{self.container}")
        return [
            self.ffmpeg_binary,
            "-nostdin",
            "-loglevel",
            "error",
            "-rtsp_transport",
            "tcp",
            "-i",
            rtsp_url,
            "-c",
            "copy",
            "-f",
            "segment",
            "-segment_time",
            str(self.segment_sec),
            "-segment_format",
            self.container,
            "-strftime",
            "1",
            "-reset_timestamps",
            "1",
            pattern,
        ]

    # ── Segmentlar ───────────────────────────────────────────────────────

    def scan(self) -> List[Segment]:
        """Diskdagi segmentlar, vaqt bo'yicha tartiblangan."""
        if not self.directory.is_dir():
            return []
        segments: List[Segment] = []
        for path in self.directory.iterdir():
            match = SEGMENT_PATTERN.match(path.name)
            if not match or match.group("camera") != self.camera_id:
                continue
            try:
                started = _parse_stamp(match.group("stamp"))
            except ValueError:
                continue
            segments.append(
                Segment(
                    path=path,
                    started_at=started,
                    duration_sec=float(self.segment_sec),
                    size_bytes=path.stat().st_size,
                )
            )
        return sorted(segments, key=lambda item: item.started_at)

    def prune(self, *, now: Optional[float] = None) -> List[Path]:
        """Muddati o'tgan va kvotadan oshgan segmentlarni o'chiradi.

        Ikkita chegara ham kerak: vaqt bo'yicha (eski kadr saqlanmasin) va
        hajm bo'yicha (bitrate kutilganidan yuqori bo'lsa disk to'lmasin).
        Eng eskisi birinchi ketadi.
        """
        now = datetime.now(timezone.utc).timestamp() if now is None else now
        segments = self.scan()
        removed: List[Path] = []

        cutoff = now - self.retention_sec
        keep: List[Segment] = []
        for segment in segments:
            if segment.ended_at < cutoff:
                segment.path.unlink(missing_ok=True)
                removed.append(segment.path)
            else:
                keep.append(segment)

        total = sum(segment.size_bytes for segment in keep)
        index = 0
        while total > self.max_bytes and index < len(keep):
            segment = keep[index]
            segment.path.unlink(missing_ok=True)
            removed.append(segment.path)
            total -= segment.size_bytes
            index += 1
        return removed

    # ── Klip ─────────────────────────────────────────────────────────────

    def segments_for(self, start: float, end: float) -> List[Segment]:
        if end <= start:
            raise ValueError("Klip oxiri boshidan keyin bo'lishi kerak")
        return [segment for segment in self.scan() if segment.overlaps(start, end)]

    def clip_command(
        self, segments: Sequence[Segment], *, offset_sec: float, duration_sec: float, output: Path
    ) -> List[str]:
        """Segmentlarni birlashtirib kesish buyrug'i — yana `-c copy`.

        `-ss` inputdan **keyin** turadi: shunda kesish keyframe'ga emas,
        so'ralgan vaqtga yaqin bo'ladi.  `-c copy` bilan bu keyframe aniqligida
        qoladi, lekin qayta kodlashdan ko'ra bir necha kadr xato afzal.
        """
        listing = "|".join(str(segment.path) for segment in segments)
        return [
            self.ffmpeg_binary,
            "-nostdin",
            "-loglevel",
            "error",
            "-i",
            f"concat:{listing}" if len(segments) > 1 else str(segments[0].path),
            "-ss",
            f"{max(0.0, offset_sec):.3f}",
            "-t",
            f"{duration_sec:.3f}",
            "-c",
            "copy",
            "-y",
            str(output),
        ]

    def extract_detailed(
        self,
        moment: float,
        *,
        output: Path,
        pre_sec: float = 10.0,
        post_sec: float = 20.0,
    ) -> ClipResult:
        """Hodisa atrofidagi klip — sababi bilan.

        Nega sabab kerak.  Ilgari bu metod ikki butunlay boshqa holatda
        bir xil `None` qaytarardi va qurilma ularni bitta `clips.missing`
        hisoblagichiga qo'shardi.  2026-08-28 da jonli do'konda
        `{written: 0, missing: 2}` ko'rindi va bu raqamdan **qaysi**
        nosozlik ekanini aytib bo'lmasdi:

        * `NO_SEGMENTS` — recorder umuman yozmayapti (`record_url` xato,
          ffmpeg o'lgan, disk to'lgan).  Tuzatish: kamera sozlamasi.
        * `CUT_FAILED` — segment bor, lekin ffmpeg kesa olmadi (buzuq
          segment, kodek, joy yo'q).  Tuzatish: butunlay boshqa yo'nalish.

        Ikkalasi ajratilmagani uchun tashxis qo'yish do'konga borishni
        talab qilardi.  Endi javob bitta heartbeat masofasida.

        `NO_SEGMENTS` ba'zan NORMAL: hodisa buffer to'lgunicha yuz bergan
        yoki kamera endi ulangan bo'lishi mumkin.  Hodisaning o'zi
        baribir yuboriladi — klipsiz hodisa hodisasiz qolgandan yaxshi.
        """
        start = moment - pre_sec
        end = moment + post_sec
        segments = self.segments_for(start, end)
        if not segments:
            return ClipResult(None, NO_SEGMENTS, "buferda segment yo'q")
        output.parent.mkdir(parents=True, exist_ok=True)
        completed = self.runner(
            self.clip_command(
                segments,
                offset_sec=start - segments[0].started_at,
                duration_sec=pre_sec + post_sec,
                output=output,
            ),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0 or not output.is_file():
            # ffmpeg nima deganini SAQLAYMIZ.  Ilgari `stderr` jimgina
            # tashlanardi va nosozlikning yagona izi nol hisoblagich edi.
            detail = (getattr(completed, "stderr", "") or "").strip().splitlines()
            return ClipResult(
                None,
                CUT_FAILED,
                f"ffmpeg {completed.returncode}: {detail[-1][:200] if detail else 'sababsiz'}",
            )
        return ClipResult(output, None, None)

    def extract(
        self,
        moment: float,
        *,
        output: Path,
        pre_sec: float = 10.0,
        post_sec: float = 20.0,
    ) -> Optional[Path]:
        """`extract_detailed` ning qisqa shakli — faqat yo'l kerak bo'lganda."""
        return self.extract_detailed(
            moment, output=output, pre_sec=pre_sec, post_sec=post_sec
        ).path

    def stats(self) -> dict:
        segments = self.scan()
        return {
            "segments": len(segments),
            "bytes": sum(segment.size_bytes for segment in segments),
            "seconds": len(segments) * self.segment_sec,
        }
