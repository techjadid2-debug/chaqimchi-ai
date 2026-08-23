"""Do'kon karnayidan ibora aytish — qurilma tomoni.

Ovoz do'konda yangraydi va biz uni eshitmaymiz.  Shuning uchun testlar
ikki narsani qulflaydi: xohlagan matn aytilmasin, va ijro heartbeat
halqasini bloklamasin.
"""

from __future__ import annotations

import time
import wave
from pathlib import Path

import pytest

from chaqimchi_ai import announcements
from chaqimchi_ai.local import audio, cloud_config


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(audio.paths, "data_dir", lambda: tmp_path)
    return tmp_path


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 800)


# ── Faqat katalogdagi ibora ─────────────────────────────────────────────


def test_arbitrary_text_can_never_be_spoken(data_dir: Path) -> None:
    """Erkin matn — xodimni haqoratlash vositasi.  Katalogda yo'q narsa aytilmaydi."""
    assert audio.announce("Sen yomon ishlayapsan") is False
    assert audio.announce("") is False
    assert audio.announce("../../etc/passwd") is False


def test_every_catalog_phrase_is_accepted(data_dir: Path) -> None:
    for item in announcements.ANNOUNCEMENTS:
        assert audio.announce(item.code) is True


# ── Fayl tanlash tartibi ────────────────────────────────────────────────


def test_the_shops_own_recording_wins(data_dir: Path) -> None:
    """Do'kon o'z ovozini yozgan bo'lsa — o'sha ishlatiladi."""
    own = data_dir / "audio" / "deter.wav"
    _write_wav(own)
    assert audio.resolve_file("deter") == own


def test_no_file_means_no_file(data_dir: Path) -> None:
    """Fayl yo'q bo'lsa `None` — chaqiruvchi tizim ovoziga o'tadi."""
    assert audio.resolve_file("deter") is None


# ── Bloklamaslik ────────────────────────────────────────────────────────


def test_playback_never_blocks_the_caller(data_dir: Path, monkeypatch) -> None:
    """Uzun fayl heartbeat halqasini to'xtatib qo'ymasligi kerak."""
    _write_wav(data_dir / "audio" / "deter.wav")

    def slow_play(path: Path) -> bool:
        time.sleep(1.5)
        return True

    monkeypatch.setattr(audio, "_play_file", slow_play)
    started = time.monotonic()
    assert audio.announce("deter") is True
    assert time.monotonic() - started < 0.3, "chaqiruv ijroni kutib qoldi"


# ── Natija ko'rinib tursin ──────────────────────────────────────────────


def _wait_for(key: str, value: int, timeout: float = 3.0) -> int:
    """Ijro alohida oqimda — `sleep` bilan kutish poygaga olib keladi."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if audio.counters()[key] >= value:
            return audio.counters()[key]
        time.sleep(0.02)
    return audio.counters()[key]


def test_a_played_file_is_counted(data_dir: Path, monkeypatch) -> None:
    monkeypatch.setattr(audio, "_counters", {"played_file": 0, "played_tts": 0, "failed": 0})
    monkeypatch.setattr(audio, "_play_file", lambda path: True)
    monkeypatch.setattr(audio, "_speak_with_tts", lambda text: False)
    _write_wav(data_dir / "audio" / "deter.wav")

    audio.announce("deter")
    assert _wait_for("played_file", 1) == 1
    assert audio.counters()["failed"] == 0


def test_silence_is_counted_as_a_failure(data_dir: Path, monkeypatch) -> None:
    """«Bosdim, hech narsa bo'lmadi» shikoyatining sababi topilishi kerak.

    Fayl ham, tizim ovozi ham ishlamasa — bu YO'QOTISH.  Hisoblagichsiz
    karnay o'chiqmi, fayl yo'qmi, TTS ishlamadimi — bilib bo'lmasdi.
    """
    monkeypatch.setattr(audio, "_counters", {"played_file": 0, "played_tts": 0, "failed": 0})
    monkeypatch.setattr(audio, "resolve_file", lambda code: None)
    monkeypatch.setattr(audio, "_speak_with_tts", lambda text: False)

    audio.announce("till")
    assert _wait_for("failed", 1) == 1
    assert audio.counters()["played_file"] == 0


def test_heartbeat_carries_the_counters() -> None:
    assert set(cloud_config._audio_counters()) >= {"played_file", "played_tts", "failed"}


# ── Bulut javobini o'qish ───────────────────────────────────────────────


def test_speak_requests_from_the_heartbeat_answer_are_played(monkeypatch) -> None:
    spoken = []
    monkeypatch.setattr(audio, "announce", lambda code: spoken.append(code) or True)
    cloud_config.apply_speak_requests({"speak_requested": ["deter", "till"]})
    assert spoken == ["deter", "till"]


def test_an_answer_without_speak_is_harmless(monkeypatch) -> None:
    """Eski bulut bu maydonni yubormaydi — qurilma yiqilmasin."""
    cloud_config.apply_speak_requests({})
    cloud_config.apply_speak_requests({"speak_requested": None})
