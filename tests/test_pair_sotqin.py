from pathlib import Path

from scripts.pair_sotqin import (
    atomic_write_env,
    default_config_path,
    default_env_file,
    render_env,
    restart_hint,
    validate_cloud_url,
)


def test_render_env_preserves_local_secrets_and_replaces_pairing() -> None:
    existing = """CHAQIMCHI_API_KEY=secret
CHAQIMCHI_SITE_ID=old-site
CHAQIMCHI_DEVICE_TOKEN=old-token
CAMERA_01_RTSP=rtsp://camera/sub
"""
    rendered = render_env(
        existing,
        {
            "CHAQIMCHI_CONFIG": "/opt/chaqimchi/current/config/sotqin.yaml",
            "CHAQIMCHI_CLOUD_URL": "https://cloud.example.uz",
            "CHAQIMCHI_SITE_ID": "new-site",
            "CHAQIMCHI_DEVICE_ID": "device-1",
            "CHAQIMCHI_DEVICE_TOKEN": "new-token",
            "CHAQIMCHI_SOTQIN_MODEL": "Intel N100",
            "CHAQIMCHI_SOTQIN_REVISION": "R1",
            "CHAQIMCHI_SOTQIN_SERIAL": "SQN-R1-1",
        },
    )
    assert "CHAQIMCHI_API_KEY=secret" in rendered
    assert "CAMERA_01_RTSP=rtsp://camera/sub" in rendered
    assert rendered.count("CHAQIMCHI_SITE_ID=") == 1
    assert "CHAQIMCHI_SITE_ID=new-site" in rendered
    assert "CHAQIMCHI_DEVICE_TOKEN=new-token" in rendered


def test_cloud_url_requires_https_except_local() -> None:
    assert validate_cloud_url("https://cloud.example.uz/") == "https://cloud.example.uz"
    assert validate_cloud_url("http://127.0.0.1:8750") == "http://127.0.0.1:8750"
    try:
        validate_cloud_url("http://cloud.example.uz")
        assert False
    except ValueError:
        pass


def test_atomic_write_env_uses_private_permissions(tmp_path: Path) -> None:
    target = tmp_path / "edge.env"
    atomic_write_env(target, "SECRET=value\n")
    assert target.read_text(encoding="utf-8") == "SECRET=value\n"
    assert target.stat().st_mode & 0o777 == 0o600


def test_linux_pairing_defaults_are_stable(monkeypatch) -> None:
    monkeypatch.setattr("scripts.pair_sotqin.os.name", "posix")
    assert default_env_file() == "/etc/chaqimchi/sotqin.env"
    assert default_config_path() == "/opt/chaqimchi/current/config/sotqin.yaml"
    assert restart_hint() == "sudo systemctl restart chaqimchi-sotqin"


def test_windows_pairing_defaults_use_program_data(monkeypatch) -> None:
    monkeypatch.setattr("scripts.pair_sotqin.os.name", "nt")
    monkeypatch.setenv("PROGRAMDATA", r"D:\ProgramData")
    monkeypatch.setenv("PROGRAMFILES", r"D:\Program Files")
    assert default_env_file().replace("\\", "/").endswith("Chaqimchi/Sotqin/sotqin.env")
    assert (
        default_config_path()
        .replace("\\", "/")
        .endswith("Chaqimchi/Sotqin/current/config/sotqin.yaml")
    )
    assert restart_hint() == "Restart-Service ChaqimchiSotqin"
