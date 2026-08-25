"""Demografiya model yo'llarining resolutioni.

Bu regressiya sinfi uchun hozirgacha BITTA ham test yo'q edi — barcha
demografiya testlari FakeDemography bilan ishlab, haqiqiy yo'l xatosini
(modellar Program Files'da, izlash ProgramData'da) yashirib kelgan.
Natijada jins/yosh Windows'da chiqarilgan kundan beri o'lik edi.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml


@pytest.fixture()
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    from chaqimchi_ai.local import config_store, paths

    importlib.reload(paths)
    importlib.reload(config_store)
    return paths, config_store, tmp_path


def test_default_config_writes_absolute_demography_paths(isolated) -> None:
    """Yangi o'rnatish darhol to'g'ri: yo'llar app_root ostida, absolyut."""
    paths, config_store, _tmp = isolated
    scene = config_store.default_config()["scene"]
    for key in ("face_model_path", "age_gender_model_path"):
        value = Path(scene[key])
        assert value.is_absolute(), f"{key} absolyut bo'lishi shart"
        assert str(value).startswith(str(paths.app_root())), (
            f"{key} o'rnatish papkasida izlanishi kerak, data_dir'da emas"
        )


def test_heal_upgrades_relative_paths_from_old_installs(isolated) -> None:
    """Eski configdagi nisbiy yo'l OTA'dan keyin birinchi o'qishda tuzaladi.

    Nisbiy yo'l xizmatning `--base-dir`iga (ProgramData) nisbatan izlanib
    hech qachon topilmasdi — mijozdan hech narsa talab qilmasdan
    to'g'rilash shart.
    """
    paths, config_store, tmp = isolated
    legacy = config_store.default_config()
    legacy["scene"]["face_model_path"] = "models/retail/face-detection-retail-0004.xml"
    legacy["scene"].pop("age_gender_model_path", None)
    (tmp / "config.yaml").parent.mkdir(parents=True, exist_ok=True)
    config_path = paths.config_path()
    config_path.write_text(yaml.safe_dump(legacy, allow_unicode=True), encoding="utf-8")

    healed = config_store.read_raw()["scene"]
    assert Path(healed["face_model_path"]).is_absolute()
    assert Path(healed["age_gender_model_path"]).is_absolute()
    # Tuzatilgan qiymat DISKKA ham yozildi — keyingi o'qish ham to'g'ri.
    on_disk = yaml.safe_load(config_path.read_text(encoding="utf-8"))["scene"]
    assert Path(on_disk["face_model_path"]).is_absolute()


def test_resolver_keeps_absolute_paths_untouched(tmp_path: Path) -> None:
    from chaqimchi_ai.retail.demography import resolve_demography_paths

    face = tmp_path / "install" / "models" / "retail" / "face.xml"
    age = tmp_path / "install" / "models" / "retail" / "age.xml"
    scene = SimpleNamespace(face_model_path=str(face), age_gender_model_path=str(age))
    resolved = resolve_demography_paths(scene, base_dir=tmp_path / "programdata")
    assert resolved == (face, age)


def test_resolver_relative_paths_land_in_base_dir(tmp_path: Path) -> None:
    """Nisbiy yo'l base_dir'ga tushishi — aynan Windows'dagi tuzoq.

    Bu xatti-harakat schema'da qoladi (dev configlar uchun), lekin
    production config uni hech qachon ishlatmasligini yuqoridagi ikki
    test kafolatlaydi.
    """
    from chaqimchi_ai.retail.demography import resolve_demography_paths

    scene = SimpleNamespace(
        face_model_path="models/retail/face.xml",
        age_gender_model_path="models/retail/age.xml",
    )
    base = tmp_path / "programdata"
    resolved = resolve_demography_paths(scene, base_dir=base)
    assert resolved is not None
    assert resolved[0] == base / "models/retail/face.xml"


def test_model_available_checks_demography_models(isolated) -> None:
    """Supervisor demografiyasiz zanjirni "hammasi joyida" deb ko'rsatmasin."""
    paths, config_store, _tmp = isolated
    assert config_store.demography_models_available() is False

    models = paths.app_root() / "models" / "retail"
    # app_root repo ildizi bo'lishi mumkin — haqiqiy fayllarga tegmaymiz,
    # borligini tekshiramiz xolos.
    face = paths.face_model_path()
    age = paths.age_gender_model_path()
    if face.is_file() and face.with_suffix(".bin").is_file() and age.is_file():
        assert config_store.demography_models_available() is (
            age.with_suffix(".bin").is_file()
        )
    else:
        assert config_store.demography_models_available() is False
    assert models == face.parent
