from pathlib import Path

from chaqimchi_ai.settings import AppSettings


def test_settings_defaults_when_file_missing(tmp_path: Path) -> None:
    cfg = AppSettings.load(tmp_path / "missing.yaml", base_dir=tmp_path)
    assert cfg.face.compare_threshold == 0.4
    assert cfg.face.det_size == (640, 640)


def test_resolved_reference_relative(tmp_path: Path) -> None:
    cfg = AppSettings.model_validate({"paths": {"reference_image": "data/x.png"}})
    p = cfg.resolved_reference_path(tmp_path)
    assert p == (tmp_path / "data" / "x.png").resolve()


def test_camera_source_accepts_int_and_rtsp_string() -> None:
    cfg = AppSettings.model_validate(
        {
            "cameras": [
                {"id": "cam0", "source": 0, "enabled": True},
                {"id": "rtsp", "source": "rtsp://192.168.1.1/live", "enabled": False},
            ]
        }
    )
    assert cfg.cameras[0].source == 0
    assert cfg.cameras[1].source == "rtsp://192.168.1.1/live"


def test_default_config_yaml_loads() -> None:
    base = Path(__file__).resolve().parent.parent
    path = base / "config" / "config.yaml"
    cfg = AppSettings.load(path, base_dir=base)
    assert cfg.face.compare_threshold == 0.4
    assert cfg.events.match_debounce_sec == 30
    assert cfg.events.save_snapshots is True
    assert cfg.tracking.enabled is True
    assert cfg.security.api_key_enabled is False
    assert len(cfg.cameras) >= 1
    assert cfg.cameras[0].source == 0
