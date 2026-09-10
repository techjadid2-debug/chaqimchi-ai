"""Ma'lumot papkasi qayerdan o'qiladi — eski nomga ko'prik.

2026-09-09: pilot do'kon 15 soat to'xtab qoldi.  Avto-yangilanish
(0.6.25 → 0.6.30) o'tdi, yangi kod esa `%PROGRAMDATA%\\ENES` ni ko'rdi va
u bo'sh edi — sozlama, kamera manzillari, chizmalar va outbox eski
`%PROGRAMDATA%\\Chaqimchi` da qolgan edi.  Dastur o'zini YANGI kompyuter
deb tanishtirdi va sozlash sehrgarini ochdi.

Eng muhim holat — `test_an_empty_new_folder_does_not_win`: papkaning
BORLIGI belgi emas, chunki `data_dir()` uni har chaqiruvda `mkdir` bilan
yaratib qo'yadi.  Belgi — `config.yaml`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from enes.local import paths


@pytest.fixture(autouse=True)
def _no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Testlarni ishga tushiruvchi muhitning `ENES_LOCAL_DIR` idan ajratish."""
    monkeypatch.delenv(paths.ENV_DATA_DIR, raising=False)


def _windows(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """Windows tarmog'ini yoqadi.

    `os.name` ning O'ZI qo'yilmaydi: `Path(...)` unga qarab `WindowsPath`
    tanlaydi va u POSIX mashinada umuman yaratilmaydi.  Shuning uchun
    modul patch qilinadigan `is_windows()` ni chaqiradi — bu naqsh
    `enes/paths.py` da ataylab shunday yozilgan.
    """
    monkeypatch.setattr(paths, "is_windows", lambda: True)
    monkeypatch.setenv("PROGRAMDATA", str(root))


def _installed(directory: Path) -> Path:
    """Haqiqiy o'rnatish: papka + sozlama fayli."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "config.yaml").write_text("cloud_sync: {enabled: true}\n", encoding="utf-8")
    return directory


def test_the_old_folder_is_used_when_only_it_has_a_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _windows(monkeypatch, tmp_path)
    legacy = _installed(tmp_path / "Chaqimchi")

    assert paths.data_dir() == legacy
    assert paths.config_path() == legacy / "config.yaml"


def test_an_empty_new_folder_does_not_win(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aynan pilotni to'xtatgan holat: yangi papka bor, lekin bo'sh.

    `data_dir()` ning o'zi uni `mkdir` bilan yaratadi, ya'ni "papka bor"
    degan tekshiruv har doim rost bo'lib chiqadi va eski papka hech
    qachon tanlanmasdi.
    """
    _windows(monkeypatch, tmp_path)
    (tmp_path / "ENES").mkdir()
    legacy = _installed(tmp_path / "Chaqimchi")

    assert paths.data_dir() == legacy


def test_the_new_folder_wins_when_both_are_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ko'chirilgandan keyin ikkala papka ham qoladi — yangisi ishlaydi."""
    _windows(monkeypatch, tmp_path)
    _installed(tmp_path / "Chaqimchi")
    current = _installed(tmp_path / "ENES")

    assert paths.data_dir() == current


def test_a_fresh_machine_gets_the_new_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _windows(monkeypatch, tmp_path)

    result = paths.data_dir()

    assert result == tmp_path / "ENES"
    assert result.is_dir()


def test_an_old_folder_without_a_config_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Yarim o'chirilgan eski papka (masalan faqat `logs/`) tanlanmaydi."""
    _windows(monkeypatch, tmp_path)
    (tmp_path / "Chaqimchi" / "logs").mkdir(parents=True)

    assert paths.data_dir() == tmp_path / "ENES"


def test_the_override_still_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`ENES_LOCAL_DIR` — testlar va ishlab chiqish uchun, u har doim ustun."""
    _windows(monkeypatch, tmp_path)
    _installed(tmp_path / "Chaqimchi")
    monkeypatch.setenv(paths.ENV_DATA_DIR, str(tmp_path / "boshqa"))

    assert paths.data_dir() == tmp_path / "boshqa"


def test_the_bridge_also_works_on_posix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ishlab chiqish mashinasida ham xuddi shu xato bo'lardi (`~/.chaqimchi`)."""
    monkeypatch.setattr(paths, "is_windows", lambda: False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    legacy = _installed(tmp_path / ".chaqimchi")

    assert paths.data_dir() == legacy


def test_the_two_path_modules_agree_on_the_old_vendor_name() -> None:
    """`enes/paths.py` (Box) va `enes/local/paths.py` (Windows do'kon).

    Ikki modul ikki xil qurilma uchun, lekin eski brend nomi bitta.
    Biri o'zgarib ikkinchisi qolsa, o'sha qurilmada ko'prik jimgina
    uziladi — nosozlik esa faqat mijoz kompyuterida ko'rinadi.
    """
    from enes import paths as device_paths

    assert paths._LEGACY_WINDOWS_DIR == device_paths._LEGACY_WINDOWS_VENDOR[0]


def test_the_box_bridge_stays_safe_because_nothing_creates_its_folders() -> None:
    """`enes/paths.py` papka YARATMASIN — ko'prigi shunga tayanadi.

    U egizak moduldan farqli o'laroq hali `exists()` ga qarab tanlaydi,
    ya'ni yangi nomdagi bo'sh papka paydo bo'lsa eski o'rnatish darhol
    ko'rinmay qoladi.  Bugun bu xavfsiz, chunki papkani hech kim
    yaratmaydi — lekin bu FARAZ, va aynan shu faraz buzilgani do'kon
    dasturida pilotni 15 soatga to'xtatgan edi
    (`enes/local/paths.py` dagi `_MARKER` izohi).

    Shuning uchun tripwire: kimdir bu modulga `mkdir` qo'shsa, test
    ko'prikni belgiga o'tkazish kerakligini aytadi.
    """
    source = (Path(__file__).resolve().parents[1] / "enes" / "paths.py").read_text(
        encoding="utf-8"
    )

    # Izohlarda so'z sifatida uchraydi, shuning uchun CHAQIRUV qidiriladi.
    kod = "\n".join(
        qator for qator in source.splitlines() if not qator.lstrip().startswith("#")
    )
    for chaqiruv in (".mkdir(", "makedirs("):
        assert chaqiruv not in kod, (
            f"enes/paths.py papka yaratyapti ({chaqiruv}) — eski nomdagi "
            "o'rnatish endi topilmay qoladi; ko'prikni `_MARKER` naqshiga "
            "o'tkazing (`enes/local/paths.py`)"
        )
