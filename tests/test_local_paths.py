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


def test_the_box_bridge_ignores_an_empty_new_folder(tmp_path: Path) -> None:
    """Box ko'prigi ham endi BO'SHLIKKA qaraydi, borlikka emas.

    Ilgari `enes/paths.py` `exists()` bilan tanlardi va bu faqat bitta
    FARAZ ustida turardi: papkani hech kim yaratmaydi.  Faraz esa
    tekshirib bo'lmaydigan joyda buzilishi mumkin — `mkdir -p` qiladigan
    deploy skripti, yarim uzilgan o'rnatuvchi yoki ochilgan arxiv.  Xuddi
    shu faraz do'kon dasturida buzilgani pilotni 15 soatga to'xtatgan edi
    (`enes/local/paths.py` dagi `_MARKER` izohi).
    """
    from enes import paths as device_paths

    current = tmp_path / "enes"
    legacy = tmp_path / "chaqimchi"
    current.mkdir()
    (legacy / "current").mkdir(parents=True)

    assert device_paths._has_installation(current) is False
    assert device_paths._has_installation(legacy) is True


def test_the_box_bridge_prefers_the_new_folder_once_it_is_installed(tmp_path: Path) -> None:
    """Ko'chirilgandan keyin ikkala papka ham qoladi — yangisi ishlaydi."""
    from enes import paths as device_paths

    current = tmp_path / "enes"
    legacy = tmp_path / "chaqimchi"
    (current / "current").mkdir(parents=True)
    (legacy / "current").mkdir(parents=True)

    monkey = {str(current): str(legacy)}
    original = device_paths._LINUX_LEGACY
    device_paths._LINUX_LEGACY = monkey
    try:
        assert device_paths._linux_dir(str(current)) == current
    finally:
        device_paths._LINUX_LEGACY = original


def test_the_box_bridge_falls_back_to_the_old_folder(tmp_path: Path) -> None:
    """Yangi nomdagi papka bo'sh — eski o'rnatish tanlansin."""
    from enes import paths as device_paths

    current = tmp_path / "enes"
    legacy = tmp_path / "chaqimchi"
    current.mkdir()
    (legacy / "current").mkdir(parents=True)

    original = device_paths._LINUX_LEGACY
    device_paths._LINUX_LEGACY = {str(current): str(legacy)}
    try:
        assert device_paths._linux_dir(str(current)) == legacy
    finally:
        device_paths._LINUX_LEGACY = original


def test_the_box_bridge_survives_an_unreadable_folder(tmp_path: Path) -> None:
    """Huquq yo'q bo'lsa "o'rnatish yo'q" deyiladi, xato tashlanmaydi.

    `iterdir()` `exists()` dan farqli o'laroq `PermissionError` tashlashi
    mumkin — va u yo'l hisoblashda ushlanmasa butun zanjir ko'tarilmaydi.
    """
    from enes import paths as device_paths

    closed = tmp_path / "yopiq"
    closed.mkdir()
    closed.chmod(0o000)
    try:
        assert device_paths._has_installation(closed) is False
    finally:
        closed.chmod(0o755)


def test_the_box_path_module_still_creates_no_folders() -> None:
    """Yo'lni HISOBLAYDIGAN modul yon ta'sir qilmasin.

    Ko'prik endi bo'shlikka qaragani uchun bu hayot-mamot emas, lekin
    papka yaratish baribir bu modulning ishi emas: `data_dir()` ni
    tashxis uchun chaqirgan skript diskda papka qoldirib ketmasin.
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
            f"enes/paths.py papka yaratyapti ({chaqiruv}) — yo'l hisoblash "
            "yon ta'sirsiz bo'lsin"
        )
