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


def test_release_contains_every_runtime_service_and_verified_model() -> None:
    requirements = (ROOT / "requirements-sotqin.txt").read_text()
    installer = (ROOT / "scripts" / "install_sotqin.sh").read_text()
    builder = (ROOT / "scripts" / "build_sotqin_release.sh").read_text()
    manifest = json.loads((ROOT / "models" / "retail_manifest.json").read_text())

    assert "openvino" in requirements
    assert "insightface" in requirements
    assert "chaqimchi-retail.service" in installer
    assert "chaqimchi-attendance.service" in installer
    assert "fetch_retail_model.py" in installer
    assert (ROOT / "scripts" / "soak_n100.py").is_file()
    assert '"$root/models/retail_manifest.json"' in builder
    assert '"$root/webapp"' in builder
    assert '"$root/config/sotqin.yaml"' in builder
    assert '"$root/config/lite.yaml"' not in builder
    assert "benchmark_streams.py" not in builder
    assert "install_edge.sh" not in builder
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
