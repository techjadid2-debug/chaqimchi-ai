"""Yangilanishni qo'llash: `apply_signed_update.py`.

Bu faylning butun mavjudligi sababi — skriptda **nol test** bo'lgani va
shu sababdan to'qqizta nuqson sezilmay qolgani.  Ulardan uchtasi mijoz
qurilmasini jimgina buzardi:

* import xatosi tufayli skript umuman ishga tushmasdi;
* `models/` bo'sh papkaga symlink qilinib, detektor modeli yo'q bo'lardi;
* faqat agent qayta ishga tushirilar, retail eski kodda qolaverardi.

`tarfile` va symlink **soxtalashtirilmaydi** — `tmp_path` da haqiqiy
arxiv quriladi va haqiqiy symlink yaratiladi.  Qiziq xatolar aynan
o'sha yerda yashaydi.  Faqat `systemctl`, HTTP va `chown` injektsiya
qilinadi.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pytest

from chaqimchi_ai.signed_update import UpdateVerificationError, sha256_file
from scripts import apply_signed_update, generate_update_key, sign_release
from scripts.apply_signed_update import (
    EXIT_OK,
    EXIT_PRECONDITION,
    EXIT_ROLLED_BACK,
    RETAIL,
    SOTQIN,
    Updater,
)

MODEL_XML = b"<net/>"
MODEL_BIN = b"weights"
HEALTH_OK = (200, b'{"product":"Sotqin","version":"0.6.1"}')
HEALTH_503 = (503, b'{"product":"Sotqin","ok":false}')


class Systemctl:
    """`systemctl` o'rniga: chaqiruvlarni yozadi, holatni qaytaradi."""

    def __init__(self, states: Optional[Dict[str, str]] = None) -> None:
        self.calls: List[List[str]] = []
        self.states = states or {SOTQIN: "active", RETAIL: "active"}
        self.fail: Optional[str] = None

    def __call__(self, command, **_kwargs) -> subprocess.CompletedProcess:
        self.calls.append(list(command))
        if command[0] == "systemctl" and command[1] == "is-active":
            return subprocess.CompletedProcess(
                command, 0, self.states.get(command[2], "inactive"), ""
            )
        if self.fail and self.fail in " ".join(map(str, command)):
            return subprocess.CompletedProcess(command, 1, "", "yiqildi")
        return subprocess.CompletedProcess(command, 0, "", "")

    @property
    def restarted(self) -> List[str]:
        for call in self.calls:
            if call[:2] == ["systemctl", "restart"]:
                return call[2:]
        return []

    def restart_count(self) -> int:
        return sum(1 for call in self.calls if call[:2] == ["systemctl", "restart"])


def build_release(
    tmp_path: Path,
    *,
    version: str = "0.6.1",
    requirements: str = "openvino>=2024.4.0\n",
    unit_body: str = "[Service]\nExecStart=/bin/true\n",
) -> Tuple[Path, Path]:
    """Haqiqiy, imzolangan reliz paketi."""
    stage = tmp_path / f"stage-{version}"
    top = stage / f"chaqimchi-sotqin-{version}"
    (top / "chaqimchi_ai").mkdir(parents=True)
    (top / "chaqimchi_ai" / "sotqin_agent.py").write_text("app = None\n", encoding="utf-8")
    (top / "chaqimchi_ai" / "__init__.py").write_text(
        f'__version__ = "{version}"\n', encoding="utf-8"
    )
    (top / "models").mkdir()
    (top / "models" / "retail_manifest.json").write_text(
        json.dumps(
            {
                "files": {
                    "model.xml": {"url": "https://x/model.xml", "sha256": _sha(MODEL_XML)},
                    "model.bin": {"url": "https://x/model.bin", "sha256": _sha(MODEL_BIN)},
                }
            }
        ),
        encoding="utf-8",
    )
    (top / "scripts").mkdir()
    (top / "scripts" / "fetch_retail_model.py").write_text("", encoding="utf-8")
    (top / "deploy").mkdir()
    for unit in (SOTQIN, RETAIL):
        (top / "deploy" / unit).write_text(unit_body, encoding="utf-8")
    (top / "requirements-sotqin.txt").write_text(requirements, encoding="utf-8")

    archive = tmp_path / f"chaqimchi-sotqin-{version}.tar.gz"
    with tarfile.open(archive, "w:gz") as package:
        package.add(top, arcname=top.name)

    private = tmp_path / "maxfiy.pem"
    public = tmp_path / "ochiq.pem"
    if not private.exists():
        generate_update_key.generate(private, public)
    assert (
        sign_release.main(
            [str(archive), "--private-key", str(private), "--public-key", str(public)]
        )
        == 0
    )
    return archive, tmp_path / f"chaqimchi-sotqin-{version}.json"


def _sha(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()


def install_root(tmp_path: Path, *, version: str = "0.6.0", with_model: bool = True) -> Path:
    """Allaqachon o'rnatilgan qurilma holati.

    Idempotent: `updater()` standart qiymatlarni qurayotganda ham, test
    o'z variantini berayotganda ham chaqiriladi.
    """
    root = tmp_path / "opt"
    release = root / "releases" / version
    if (root / "current").exists():
        shutil.rmtree(root)
    (release / "models" / "retail").mkdir(parents=True)
    if with_model:
        (release / "models" / "retail" / "model.xml").write_bytes(MODEL_XML)
        (release / "models" / "retail" / "model.bin").write_bytes(MODEL_BIN)
    (release / "requirements-sotqin.txt").write_text("openvino>=2024.4.0\n", encoding="utf-8")
    (root / "shared" / "data").mkdir(parents=True)
    (root / "current").symlink_to(release, target_is_directory=True)
    return root


def systemd_dir(tmp_path: Path, *, units: Sequence[str] = (SOTQIN, RETAIL)) -> Path:
    path = tmp_path / "systemd"
    if path.exists():
        shutil.rmtree(path)
    path.mkdir()
    for unit in units:
        (path / unit).write_text("[Service]\nExecStart=/bin/old\n", encoding="utf-8")
    return path


def updater(tmp_path: Path, **kwargs) -> Updater:
    """Standart qiymatlar **dangasa** quriladi.

    `install_root()` va `systemd_dir()` diskka yozadi, ya'ni ularni
    ehtiyotsiz chaqirish testning o'z variantini yuvib yuborardi.
    """
    if "root" not in kwargs:
        kwargs["root"] = install_root(tmp_path)
    if "systemd_dir" not in kwargs:
        kwargs["systemd_dir"] = systemd_dir(tmp_path)
    kwargs.setdefault("public_key", tmp_path / "ochiq.pem")
    kwargs.setdefault("venv_python", tmp_path / "python")
    kwargs.setdefault("runner", Systemctl())
    kwargs.setdefault("http_get", lambda _url, _timeout: HEALTH_OK)
    kwargs.setdefault("chown", lambda *_a: None)
    kwargs.setdefault("sleep", lambda _s: None)
    kwargs.setdefault("clock", lambda: 0.0)
    kwargs.setdefault("machine", lambda: "x86_64")
    return Updater(**kwargs)


# ── Muvaffaqiyatli yangilanish ───────────────────────────────────────────


def test_current_points_at_the_new_release(tmp_path: Path) -> None:
    archive, manifest = build_release(tmp_path)
    control = updater(tmp_path)

    assert control.run(archive, manifest) == EXIT_OK

    current = (control.root / "current").resolve()
    assert current.name == "0.6.1"
    assert (current / "chaqimchi_ai" / "sotqin_agent.py").is_file()


def test_data_stays_a_symlink_but_models_does_not(tmp_path: Path) -> None:
    """`data` symlink majburiy: xizmatlar `ProtectSystem=strict` ostida
    faqat `shared/data` ga yoza oladi.  `models` esa faqat o'qiladi va
    relizning o'z papkasida turishi kerak — ilgari u bo'sh papkaga
    ulanib, detektor modelini yo'q qilardi."""
    archive, manifest = build_release(tmp_path)
    control = updater(tmp_path)

    control.run(archive, manifest)

    release = (control.root / "current").resolve()
    assert (release / "data").is_symlink()
    assert (release / "data").resolve() == (control.root / "shared" / "data").resolve()
    assert not (release / "models").is_symlink()


def test_the_detector_model_survives_the_update(tmp_path: Path) -> None:
    """#8 — eng jimgina buzadigan nuqson.  Model yo'qolsa retail keyingi
    qayta yuklashda ishga tushmaydi, ya'ni mijoz obyektida bilinadi."""
    archive, manifest = build_release(tmp_path)
    control = updater(tmp_path)

    control.run(archive, manifest)

    models = (control.root / "current").resolve() / "models" / "retail"
    assert (models / "model.xml").read_bytes() == MODEL_XML
    assert (models / "model.bin").read_bytes() == MODEL_BIN


def test_both_services_are_restarted(tmp_path: Path) -> None:
    """#9 — ilgari faqat agent qayta ishga tushardi va retail eski kodda
    qolaverardi; yangilanish esa "muvaffaqiyatli" deb yozardi."""
    archive, manifest = build_release(tmp_path)
    systemctl = Systemctl()
    control = updater(tmp_path, runner=systemctl)

    control.run(archive, manifest)

    assert set(systemctl.restarted) == {SOTQIN, RETAIL}


def test_the_new_tree_is_handed_to_the_service_user(tmp_path: Path) -> None:
    archive, manifest = build_release(tmp_path)
    owned: List = []
    control = updater(tmp_path, chown=lambda path, user, group: owned.append((path.name, user)))

    control.run(archive, manifest)

    assert owned == [("0.6.1", "chaqimchi")]


# ── Model ololmasa ───────────────────────────────────────────────────────


def test_a_missing_model_stops_the_update_before_anything_changes(tmp_path: Path) -> None:
    """Yuklab olish ham yiqilsa `current` tegilmasin — eski versiya
    ishlab tursin."""
    archive, manifest = build_release(tmp_path)
    systemctl = Systemctl()
    systemctl.fail = "fetch_retail_model"
    control = updater(
        tmp_path,
        root=install_root(tmp_path, with_model=False),
        runner=systemctl,
    )
    before = (control.root / "current").resolve()

    with pytest.raises(UpdateVerificationError, match="Model"):
        control.run(archive, manifest)

    assert (control.root / "current").resolve() == before
    assert systemctl.restart_count() == 0


# ── Health darvozasi ─────────────────────────────────────────────────────


def test_an_unpaired_device_still_counts_as_healthy(tmp_path: Path) -> None:
    """Agent pairing qilinmagan qurilmada 503 qaytaradi.  Bu yangilanish
    xatosi emas — u uvicorn ilovani import qilganini isbotlaydi."""
    archive, manifest = build_release(tmp_path)
    control = updater(tmp_path, http_get=lambda _u, _t: HEALTH_503)

    assert control.run(archive, manifest) == EXIT_OK


def test_a_dead_agent_rolls_back(tmp_path: Path) -> None:
    archive, manifest = build_release(tmp_path)
    systemctl = Systemctl()
    control = updater(
        tmp_path,
        runner=systemctl,
        http_get=lambda _u, _t: (0, b""),
        clock=iter([0.0, 0.0, 200.0, 200.0, 200.0]).__next__,
    )

    assert control.run(archive, manifest) == EXIT_ROLLED_BACK
    assert (control.root / "current").resolve().name == "0.6.0"
    assert systemctl.restart_count() == 2


def test_a_camera_less_retail_does_not_block_the_update(tmp_path: Path) -> None:
    """Bugungi stendda `chaqimchi-retail` kamera yo'qligi sababli umuman
    ishga tushmaydi.  Yangilanish qurilmani oldingidan sog'lomroq
    bo'lishini talab qilmasligi kerak."""
    archive, manifest = build_release(tmp_path)
    systemctl = Systemctl({SOTQIN: "active", RETAIL: "failed"})
    control = updater(tmp_path, runner=systemctl)

    assert control.run(archive, manifest) == EXIT_OK


def test_a_service_that_was_running_and_stops_causes_a_rollback(tmp_path: Path) -> None:
    """Teskarisi: obyektda retail ishlab turgan bo'lsa va yangilanishdan
    keyin to'xtasa — bu haqiqiy regressiya."""
    archive, manifest = build_release(tmp_path)

    class Dying(Systemctl):
        def __init__(self) -> None:
            super().__init__({SOTQIN: "active", RETAIL: "active"})
            self.restarts = 0

        def __call__(self, command, **kwargs):
            if command[:2] == ["systemctl", "restart"]:
                self.restarts += 1
                self.states[RETAIL] = "failed"
            return super().__call__(command, **kwargs)

    control = updater(tmp_path, runner=Dying())

    assert control.run(archive, manifest) == EXIT_ROLLED_BACK


# ── Bog'liqliklar va unitlar ─────────────────────────────────────────────


def test_new_requirements_are_refused_without_pip(tmp_path: Path) -> None:
    """venv reliz tashqarisida va umumiy — `pip install` orqaga qaytmaydi,
    ya'ni `current` ni qaytarish rollback'ni yolg'onga aylantirardi."""
    archive, manifest = build_release(tmp_path, requirements="openvino\nyangi-paket==1.0\n")
    systemctl = Systemctl()
    control = updater(tmp_path, runner=systemctl)

    with pytest.raises(UpdateVerificationError, match="--pip"):
        control.run(archive, manifest)

    assert systemctl.restart_count() == 0


def test_new_requirements_are_installed_before_the_flip_with_pip(tmp_path: Path) -> None:
    archive, manifest = build_release(tmp_path, requirements="openvino\nyangi-paket==1.0\n")
    systemctl = Systemctl()
    control = updater(tmp_path, runner=systemctl, allow_pip=True)

    assert control.run(archive, manifest) == EXIT_OK

    commands = [" ".join(map(str, call)) for call in systemctl.calls]
    pip_at = next(i for i, text in enumerate(commands) if "pip install" in text)
    restart_at = next(i for i, text in enumerate(commands) if "systemctl restart" in text)
    assert pip_at < restart_at


def test_changed_units_are_written_and_restored_on_rollback(tmp_path: Path) -> None:
    archive, manifest = build_release(tmp_path, unit_body="[Service]\nExecStart=/bin/new\n")
    units = systemd_dir(tmp_path)
    original = (units / SOTQIN).read_bytes()
    systemctl = Systemctl()
    control = updater(tmp_path, systemd_dir=units, runner=systemctl)

    assert control.run(archive, manifest) == EXIT_OK
    assert b"/bin/new" in (units / SOTQIN).read_bytes()
    assert any("daemon-reload" in " ".join(map(str, call)) for call in systemctl.calls)

    # Endi health yiqiladigan yangilanish — unitlar tiklanishi kerak.
    archive2, manifest2 = build_release(
        tmp_path, version="0.6.2", unit_body="[Service]\nExecStart=/bin/broken\n"
    )
    broken = updater(
        tmp_path,
        root=control.root,
        systemd_dir=units,
        runner=Systemctl(),
        http_get=lambda _u, _t: (0, b""),
        clock=iter([0.0, 0.0, 200.0, 200.0, 200.0]).__next__,
    )
    assert broken.run(archive2, manifest2) == EXIT_ROLLED_BACK
    assert b"/bin/new" in (units / SOTQIN).read_bytes()
    assert original not in (units / SOTQIN).read_bytes()


def test_a_unit_that_is_not_installed_is_never_enabled(tmp_path: Path) -> None:
    """Yangi unit o'z-o'zidan yoqilmasin — bu operatorning qarori."""
    archive, manifest = build_release(tmp_path)
    units = systemd_dir(tmp_path, units=(SOTQIN,))
    systemctl = Systemctl({SOTQIN: "active"})
    control = updater(tmp_path, systemd_dir=units, runner=systemctl)

    control.run(archive, manifest)

    assert not (units / RETAIL).exists()
    assert systemctl.restarted == [SOTQIN]


# ── Tekshiruv ────────────────────────────────────────────────────────────


def test_a_tampered_archive_is_refused(tmp_path: Path) -> None:
    archive, manifest = build_release(tmp_path)
    archive.write_bytes(archive.read_bytes() + b"buzuq")
    control = updater(tmp_path)

    with pytest.raises(UpdateVerificationError, match="SHA-256"):
        control.run(archive, manifest)


def test_a_foreign_architecture_is_refused(tmp_path: Path) -> None:
    archive, manifest = build_release(tmp_path)
    control = updater(tmp_path, machine=lambda: "aarch64")

    with pytest.raises(UpdateVerificationError, match="arxitekturasi"):
        control.run(archive, manifest)


def test_the_same_version_cannot_be_installed_twice(tmp_path: Path) -> None:
    archive, manifest = build_release(tmp_path)
    control = updater(tmp_path)
    control.run(archive, manifest)

    with pytest.raises(UpdateVerificationError, match="allaqachon"):
        control.run(archive, manifest)


# ── Cloud'dan yuklab olish ───────────────────────────────────────────────


def test_fetch_pulls_both_files_from_the_cloud(tmp_path: Path) -> None:
    archive, manifest = build_release(tmp_path)
    payloads = {
        "https://ai.test/releases/chaqimchi-sotqin-0.6.1.tar.gz": archive.read_bytes(),
        "https://ai.test/releases/chaqimchi-sotqin-0.6.1.json": manifest.read_bytes(),
    }
    control = updater(tmp_path, http_get=lambda url, _t: (200, payloads[url]))
    target = tmp_path / "yuklama"
    target.mkdir()

    got_archive, got_manifest = control.fetch("https://ai.test", "0.6.1", target)

    assert sha256_file(got_archive) == sha256_file(archive)
    assert json.loads(got_manifest.read_text())["version"] == "0.6.1"


def test_fetch_refuses_plain_http(tmp_path: Path) -> None:
    control = updater(tmp_path)

    with pytest.raises(UpdateVerificationError, match="HTTPS"):
        control.fetch("http://ai.test", "0.6.1", tmp_path)


def test_a_missing_release_is_reported_clearly(tmp_path: Path) -> None:
    control = updater(tmp_path, http_get=lambda _u, _t: (404, b"topilmadi"))

    with pytest.raises(UpdateVerificationError, match="404"):
        control.fetch("https://ai.test", "9.9.9", tmp_path)


# ── Skript sifatida ishga tushishi ───────────────────────────────────────


def test_the_script_runs_from_any_directory(tmp_path: Path) -> None:
    """#7 — buni ushlaydigan yagona test.

    Skript `/opt/chaqimchi/current/scripts/` dan ishga tushiriladi, ya'ni
    `sys.path[0]` da `chaqimchi_ai` bo'lmaydi va paket venv'ga hech qachon
    o'rnatilmagan.  Ilgari bu `ModuleNotFoundError` berardi.
    """
    result = subprocess.run(
        [sys_executable(), str(Path(apply_signed_update.__file__)), "--help"],
        capture_output=True,
        text=True,
        cwd="/",
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "ModuleNotFoundError" not in result.stderr


def sys_executable() -> str:
    import sys

    return sys.executable


def test_missing_arguments_are_explained(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        apply_signed_update.main(["--fetch-version", "0.6.1"])  # --cloud yo'q


def test_a_failed_check_leaves_the_device_untouched(tmp_path: Path, capsys) -> None:
    """Exit kodlari avtomatlashtirish uchun ma'noli bo'lishi kerak.

    1 = tekshiruv yiqildi, qurilmada hech nima o'zgarmadi — bu holatda
    qayta urinish xavfsiz.  2 (rollback) va 3 (buzuq) esa boshqa qaror
    talab qiladi.
    """
    archive, manifest = build_release(tmp_path)
    archive.write_bytes(b"bu arxiv emas")
    root = install_root(tmp_path)
    before = (root / "current").resolve()

    code = apply_signed_update.main(
        [
            str(archive),
            str(manifest),
            "--public-key",
            str(tmp_path / "ochiq.pem"),
            "--root",
            str(root),
        ]
    )

    assert code == EXIT_PRECONDITION
    assert (root / "current").resolve() == before
    assert "XATO" in capsys.readouterr().err
