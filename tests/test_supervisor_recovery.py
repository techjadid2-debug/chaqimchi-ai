"""Zanjir yiqilganda o'zini tiklashi — "o'chirib yoqish" ni yo'q qilish.

Haqiqiy do'kondan kelgan shikoyat: **svet o'chib yongandan keyin dasturni
o'chirib yoqish kerak.**  Sabablardan biri aynan shu yerda edi: zanjir 20
soniyada uch marta yiqilsa nazoratchi `_auto_restart` ni **abadiy**
o'chirardi va uni faqat odam qayta ko'tarardi.

Tok kelganda kompyuter NVR va routerdan oldin yonadi — kamera hali javob
bermaydi, zanjir yiqiladi.  Bir necha daqiqadan keyin hammasi joyida
bo'ladi, ya'ni to'g'ri javob — kutib, yana urinish.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def supervisor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    from chaqimchi_ai.local import config_store, counters, paths
    from chaqimchi_ai.local import supervisor as module

    for item in (paths, config_store, counters, module):
        importlib.reload(item)
    return module


def test_rapid_crashes_lead_to_a_cooldown_not_a_permanent_stop(supervisor) -> None:
    """Uch marta tez yiqilgach: kutamiz, lekin taslim BO'LMAYMIZ."""
    instance = supervisor.RetailSupervisor()
    now = 1_000.0

    # Birinchi ikkitasi darhol qayta ko'tariladi.
    for _ in range(supervisor.MAX_RAPID_CRASHES - 1):
        assert instance._note_exit(1.0, now=now) is True

    # Uchinchisidan keyin — sovish oralig'i.
    assert instance._note_exit(1.0, now=now) is False
    assert instance._retry_at == now + supervisor.COOLDOWN_STEPS_SEC[0]
    # Eng muhimi: avtomatik ko'tarish O'CHIRILMAYDI.  Ilgari aynan shu
    # yerda `_auto_restart = False` bo'lardi va do'kon egasi dasturni
    # qo'lda o'chirib yoqishga majbur edi.
    assert instance._auto_restart is True
    assert "yana urinadi" in instance._last_error


def test_each_cooldown_is_longer_than_the_previous_one(supervisor) -> None:
    """Kamera butunlay o'chgan bo'lsa har daqiqada urinish foydasiz."""
    instance = supervisor.RetailSupervisor()
    waits = []
    now = 0.0
    for _ in range(4):
        for _ in range(supervisor.MAX_RAPID_CRASHES - 1):
            instance._note_exit(1.0, now=now)
        assert instance._note_exit(1.0, now=now) is False
        waits.append(instance._retry_at - now)

    assert waits == sorted(waits), "kutish faqat o'sishi kerak"
    assert waits[-1] == supervisor.COOLDOWN_STEPS_SEC[-1] <= 900
    assert waits[-1] == waits[-2] or len(supervisor.COOLDOWN_STEPS_SEC) > 3


def test_a_long_run_resets_the_cooldown(supervisor) -> None:
    """Zanjir uzoq ishlab keyin to'xtasa — bu crash-loop emas."""
    instance = supervisor.RetailSupervisor()
    for _ in range(supervisor.MAX_RAPID_CRASHES):
        instance._note_exit(1.0, now=100.0)
    assert instance._retry_at > 0

    assert instance._note_exit(supervisor.CRASH_WINDOW_SEC + 1, now=200.0) is True
    assert instance._retry_at == 0.0
    assert instance._cooldown_step == 0


def test_manual_start_clears_the_cooldown(supervisor, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mijoz "Ishga tushirish" bossa — darhol urinamiz, kutmasdan."""
    from chaqimchi_ai.local import config_store

    instance = supervisor.RetailSupervisor()
    monkeypatch.setattr(supervisor.RetailSupervisor, "_spawn", lambda self: None)
    instance._retry_at = 10_000.0
    instance._cooldown_step = 2
    monkeypatch.setattr(config_store, "model_available", lambda: True)
    monkeypatch.setattr(
        config_store, "cameras", lambda: [{"id": "camera-01", "stream_url": "rtsp://x"}]
    )

    instance.start()

    assert instance._retry_at == 0.0
    assert instance._cooldown_step == 0
    assert instance._auto_restart is True


class _DeadProcess:
    """Ishga tushishi bilan o'ladigan jarayon (kamera yo'q holati)."""

    pid = 4242

    def poll(self) -> int:
        return 1

    def terminate(self) -> None:
        return None

    def wait(self, timeout: int = 0) -> int:
        return 1


def test_the_chain_keeps_being_retried_after_a_power_cut(
    supervisor, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Soatni o'zimiz suramiz va butun tiklanishni kuzatamiz.

    Stsenariy — do'kondagi haqiqiy holat: tok keldi, kompyuter yondi,
    NVR esa hali ko'tarilmagan.  Zanjir har safar darhol yiqiladi.
    Kutilgan xulq: urinishlar SEKINLASHADI, lekin hech qachon
    to'xtamaydi — odam kelib "o'chirib yoqishi" shart emas.
    """
    instance = supervisor.RetailSupervisor()
    clock = {"now": 1_000.0}

    def _spawn(self) -> None:
        self._process = _DeadProcess()
        self._started_at = clock["now"]

    monkeypatch.setattr(supervisor.RetailSupervisor, "_spawn", _spawn)
    instance._auto_restart = True
    instance._spawn()

    waits = []
    # Ikki soatlik "sikl": har qadam 2 soniya (haqiqiy `_watch` bilan bir xil).
    for _ in range(3_600):
        before = instance._retry_at
        assert instance._tick(clock["now"]) is True
        if instance._retry_at and instance._retry_at != before:
            waits.append(round(instance._retry_at - clock["now"]))
        clock["now"] += 2

    assert waits[:3] == [60, 300, 900], "kutish 1 → 5 → 15 daqiqagacha o'sishi kerak"
    assert waits[3:] == [900] * len(waits[3:]), "oxirgi qadamda qotadi, to'xtamaydi"
    # Eng muhimi: ikki soatdan keyin ham avtomatik tiklanish YOQILGAN va
    # keyingi urinish rejalashtirilgan (soat — sinovniki, shuning uchun
    # `status()` emas, ichki qiymat solishtiriladi).
    assert instance._auto_restart is True
    assert instance._retry_at > clock["now"] - supervisor.COOLDOWN_STEPS_SEC[-1]


def test_a_recovered_chain_forgets_the_cooldown(
    supervisor, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NVR ko'tarilgach zanjir ishlaydi va sovish qadami nolga qaytadi."""
    instance = supervisor.RetailSupervisor()
    clock = {"now": 1_000.0}
    alive = {"value": False}

    class _Process:
        pid = 1

        def poll(self):
            return None if alive["value"] else 1

        def terminate(self):
            return None

        def wait(self, timeout: int = 0):
            return 1

    def _spawn(self) -> None:
        self._process = _Process()
        self._started_at = clock["now"]

    monkeypatch.setattr(supervisor.RetailSupervisor, "_spawn", _spawn)
    instance._auto_restart = True
    instance._spawn()

    for _ in range(200):  # kamera yo'q — sovish oralig'iga tushamiz
        instance._tick(clock["now"])
        clock["now"] += 2
    assert instance._cooldown_step > 0

    alive["value"] = True  # NVR ko'tarildi
    for _ in range(500):
        instance._tick(clock["now"])
        clock["now"] += 2

    assert instance._cooldown_step == 0
    assert instance._last_error == ""
