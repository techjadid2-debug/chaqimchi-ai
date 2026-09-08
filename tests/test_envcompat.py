"""Eski `CHAQIMCHI_*` env nomlari yangi kodda ham ishlaydi (rebrend ko'priki)."""

from enes import envcompat


def test_legacy_names_are_copied_to_the_new_prefix() -> None:
    env = {"CHAQIMCHI_CLOUD_DB": "/tmp/a.db", "OTHER": "x"}

    adopted = envcompat.adopt_legacy_env(env)

    assert adopted == ["ENES_CLOUD_DB"]
    assert env["ENES_CLOUD_DB"] == "/tmp/a.db"
    assert env["CHAQIMCHI_CLOUD_DB"] == "/tmp/a.db", "eski nom o'chirilmaydi"


def test_the_new_name_wins_when_both_are_set() -> None:
    """Cutoverdan keyin yangi nom qo'yilgach eski qoldiq uni bosmasin."""
    env = {"CHAQIMCHI_ENV": "development", "ENES_ENV": "production"}

    assert envcompat.adopt_legacy_env(env) == []
    assert env["ENES_ENV"] == "production"


def test_the_bridge_runs_on_import(monkeypatch) -> None:
    """`cloud` yoki `enes` import qilinishi bilan ko'prik ishlaydi —
    modul darajasida env o'qiydigan kod yangi nomni topadi."""
    monkeypatch.setenv("CHAQIMCHI_BRIDGE_PROBE", "1")
    monkeypatch.delenv("ENES_BRIDGE_PROBE", raising=False)
    import importlib

    importlib.reload(envcompat)

    import os

    assert os.environ["ENES_BRIDGE_PROBE"] == "1"
    monkeypatch.delenv("ENES_BRIDGE_PROBE", raising=False)
