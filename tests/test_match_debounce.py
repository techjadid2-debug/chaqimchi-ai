import time

from chaqimchi_ai.match_debounce import MatchDebouncer


def test_debounce_blocks_repeat_within_interval() -> None:
    d = MatchDebouncer(10.0)
    assert d.should_emit("cam1", "p1") is True
    assert d.should_emit("cam1", "p1") is False


def test_debounce_allows_after_interval(monkeypatch) -> None:
    d = MatchDebouncer(1.0)
    t = [1000.0]

    def fake_time() -> float:
        return t[0]

    monkeypatch.setattr(time, "time", fake_time)
    assert d.should_emit("cam1", "p1") is True
    t[0] = 1000.5
    assert d.should_emit("cam1", "p1") is False
    t[0] = 1001.1
    assert d.should_emit("cam1", "p1") is True


def test_debounce_independent_per_camera_and_person() -> None:
    d = MatchDebouncer(60.0)
    assert d.should_emit("cam1", "p1") is True
    assert d.should_emit("cam2", "p1") is True
    assert d.should_emit("cam1", "p2") is True


def test_zero_interval_always_emits() -> None:
    d = MatchDebouncer(0)
    assert d.should_emit("c", "p") is True
    assert d.should_emit("c", "p") is True
