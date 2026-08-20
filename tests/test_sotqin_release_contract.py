from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from chaqimchi_ai.event_models import EdgeEvent
from chaqimchi_ai.retail.rules import RuleEngine
from chaqimchi_ai.settings import AppSettings
from scripts import fetch_retail_model

ROOT = Path(__file__).resolve().parent.parent


def test_canonical_sotqin_profile_is_a_four_camera_retail_pilot() -> None:
    config = yaml.safe_load((ROOT / "config" / "sotqin.yaml").read_text())

    assert config["product"]["profile"] == "SOTQIN-N100-8-128-R1"
    assert config["product"]["guaranteed_cameras"] == 4
    assert config["retail"]["enabled"] is True
    assert config["media"]["hardware_decode"] == "software"
    typed = AppSettings.load(ROOT / "config" / "sotqin.yaml", base_dir=ROOT)
    assert typed.environment == "production"
    assert typed.retail.enabled is True
    assert typed.scene.backend == "openvino"


def _requirements(name: str) -> list[str]:
    """Izohsiz, faqat haqiqiy paket qatorlari.

    Izohni ham hisoblash xavfli: "insightface o'rnatilmaydi" degan izoh
    "insightface bor" degan tekshiruvdan o'tib ketardi.
    """
    lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def test_no_face_recognition_stack_anywhere() -> None:
    """Yuz tanish kutubxonalari hech bir to'plamga qaytib kirmasin.

    Davomat to'plami arxivlangan (`archive/attendance-local` tegi); yuz
    tanish keyin **cloud** tomonda quriladi.  Qurilma to'plamlariga
    insightface/onnx qaytsa — bu ~1 GB keraksiz yuk va arxiv qarori
    buzilgani belgisi.
    """
    base = _requirements("requirements-sotqin.txt")
    dev = _requirements("requirements.txt")

    assert any(item.startswith("openvino") for item in base)
    for heavy in ("insightface", "onnxruntime", "onnx"):
        assert not any(item.startswith(heavy) for item in base), heavy
        assert not any(item.startswith(heavy) for item in dev), heavy
    assert not (ROOT / "requirements-attendance.txt").exists()
    assert not (ROOT / "webapp").exists()


def test_installer_refuses_to_fall_back_to_cpu_silently() -> None:
    """iGPU'siz o'rnatish jimgina davom etmasin: detektor CPU'ga tushsa
    tizim 4-8 barobar sekin bo'ladi va buni hech kim sezmaydi."""
    installer = (ROOT / "scripts" / "install_sotqin.sh").read_text()
    unit = (ROOT / "deploy" / "chaqimchi-retail.service").read_text()

    assert "intel-opencl-icd" in installer
    assert "intel-media-va-driver" in installer
    assert "clinfo" in installer and "vainfo" in installer
    assert "exit 3" in installer  # tekshiruv yiqilsa o'rnatish to'xtaydi
    # Drayver bo'lsa ham, guruhsiz /dev/dri ochilmaydi.
    assert "--groups render,video" in installer
    assert "SupplementaryGroups=render video" in unit


def test_services_declare_a_memory_ceiling() -> None:
    """RAM shifti cgroup darajasida — talab: butun qurilma <= 6.5 GB."""
    limits = {
        "chaqimchi-retail.service": "MemoryMax=2560M",
        "chaqimchi-sotqin.service": "MemoryMax=512M",
    }
    for unit, expected in limits.items():
        assert expected in (ROOT / "deploy" / unit).read_text(), unit


def test_release_contains_every_runtime_service_and_verified_model() -> None:
    installer = (ROOT / "scripts" / "install_sotqin.sh").read_text()
    builder = (ROOT / "scripts" / "build_sotqin_release.sh").read_text()
    manifest = json.loads((ROOT / "models" / "retail_manifest.json").read_text())

    assert "chaqimchi-retail.service" in installer
    assert "fetch_retail_model.py" in installer
    assert (ROOT / "scripts" / "soak_n100.py").is_file()
    assert '"$root/models/retail_manifest.json"' in builder
    assert '"$root/config/sotqin.yaml"' in builder
    assert "install_edge.sh" not in builder
    # Davomat to'plami arxivlangan — reliz endi webapp olib yurmaydi.
    assert "webapp" not in builder
    assert "attendance" not in builder
    assert "attendance" not in installer
    assert all(len(item["sha256"]) == 64 for item in manifest["files"].values())


def test_retail_service_resolves_release_assets_from_current_symlink() -> None:
    unit = (ROOT / "deploy" / "chaqimchi-retail.service").read_text()
    service = (ROOT / "chaqimchi_ai" / "retail" / "service.py").read_text()

    assert "--base-dir /opt/chaqimchi/current" in unit
    assert "--base-dir /opt/chaqimchi/shared" not in unit
    assert "CloudEventSync(sync_cfg, outbox)" in service
    assert 'name="retail-cloud-sync"' in service


def test_canonical_rules_suppress_normal_zone_but_keep_restricted_zone() -> None:
    payload = yaml.safe_load((ROOT / "config" / "rules.yaml").read_text())
    engine = RuleEngine.from_config(payload)
    normal = EdgeEvent(
        event_type="zone_entered", camera_id="camera-01", metadata={"restricted": False}
    )
    restricted = normal.model_copy(update={"metadata": {"restricted": True}})

    assert engine.evaluate(normal, now=1).suppressed is True
    assert engine.evaluate(restricted, now=2).event.severity == "critical"


def test_retail_bundle_is_not_partially_replaced_on_checksum_error(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "retail"
    target.mkdir()
    (target / "model.xml").write_bytes(b"old-xml")
    (target / "model.bin").write_bytes(b"old-bin")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "files": {
                    "model.xml": {
                        "url": "https://example.test/model.xml",
                        "sha256": fetch_retail_model.sha256(b"new-xml"),
                    },
                    "model.bin": {
                        "url": "https://example.test/model.bin",
                        "sha256": "0" * 64,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    payloads = {
        "https://example.test/model.xml": b"new-xml",
        "https://example.test/model.bin": b"new-bin",
    }
    monkeypatch.setattr(fetch_retail_model, "MANIFEST", manifest)
    monkeypatch.setattr(fetch_retail_model, "TARGET_DIR", target)
    monkeypatch.setattr(fetch_retail_model, "download", payloads.__getitem__)
    monkeypatch.setattr(sys, "argv", ["fetch_retail_model.py"])

    assert fetch_retail_model.main() == 1
    assert (target / "model.xml").read_bytes() == b"old-xml"
    assert (target / "model.bin").read_bytes() == b"old-bin"


def test_installer_and_release_ship_the_preflight_script() -> None:
    """O'rnatuvchi obyektda "ishladimi?" savoliga javob bera olsin."""
    installer = (ROOT / "scripts" / "install_sotqin.sh").read_text()
    builder = (ROOT / "scripts" / "build_sotqin_release.sh").read_text()
    bootstrap = (ROOT / "deploy" / "bootstrap_sotqin.sh").read_text()

    assert "sotqin_preflight.py" in installer
    assert "sotqin_preflight.py" in builder
    # Bir buyruqli o'rnatish oxirida ro'yxat chiqadi.
    assert "sotqin_preflight.py" in bootstrap
    # Tekshiruv yiqilsa o'rnatish bekor qilinmasin — qurilma o'rnatilgan,
    # faqat kamera yoki chiziq hali sozlanmagan bo'lishi mumkin.
    assert "sotqin_preflight.py || true" in bootstrap


def test_version_is_declared_in_exactly_one_place() -> None:
    """Ikkita versiya raqami bir-biridan ajralib ketmasin.

    `build_sotqin_release.sh:6` tarball nomini `pyproject.toml` dan oladi,
    qurilma esa heartbeat'da `chaqimchi_ai.__version__` ni yuboradi. Ular
    farq qilsa panelda bitta versiya, faylda boshqasi ko'rinardi — va
    `apply_signed_update.py` "bu versiya allaqachon o'rnatilgan" deb
    to'g'ri relizni rad etardi.
    """
    import tomllib

    from chaqimchi_ai import __version__

    declared = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert declared["project"]["version"] == __version__


def test_version_passes_the_updaters_charset_guard() -> None:
    """Qurilma rad etadigan versiya nomi bilan reliz chiqarib bo'lmasin.

    `signed_update.py` versiyani papka nomi sifatida ishlatadi, shuning
    uchun belgilar ro'yxati qat'iy. Mos kelmasa xato faqat qurilmada,
    o'rnatish paytida chiqardi.
    """
    import re

    from chaqimchi_ai import __version__

    assert re.fullmatch(r"[A-Za-z0-9.\-_]+", __version__), __version__


def test_the_update_key_ships_and_is_never_silently_replaced() -> None:
    """OTA ishonch langari.

    Ochiq kalit reliz paketi ichida qurilmaga boradi va o'rnatishda bir
    marta qotiriladi. Har o'rnatishda ustiga yozilsa, zararli paket o'z
    kalitini qo'yib qo'ya olardi va butun imzo qatlami ma'nosiz bo'lardi.
    """
    installer = (ROOT / "scripts" / "install_sotqin.sh").read_text()
    builder = (ROOT / "scripts" / "build_sotqin_release.sh").read_text()

    assert (ROOT / "deploy" / "update-public.pem").is_file()
    assert '"$root/deploy/update-public.pem"' in builder
    assert "/etc/chaqimchi/update-public.pem" in installer
    # Mavjud kalit faqat ataylab almashtiriladi.
    assert "CHAQIMCHI_ROTATE_UPDATE_KEY" in installer
    assert "cmp -s" in installer


def test_the_release_builder_refuses_a_dirty_worktree() -> None:
    """Commit qilinmagan kod bilan qurilgan paket qaysi kod ekanini hech
    kim ayta olmaydi — va u mijoz qurilmasiga tushadi."""
    builder = (ROOT / "scripts" / "build_sotqin_release.sh").read_text()

    assert "--allow-dirty" in builder
    assert 'git -C "$root" diff --quiet HEAD' in builder
