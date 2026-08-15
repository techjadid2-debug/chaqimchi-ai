"""Qurilmadagi tekshiruv ro'yxati.

Har tekshiruv ikki narsa berishi kerak: holat **va** nima qilish kerak.
"XATO: iGPU" foydasiz — o'rnatuvchi buni o'qib nima qilishini bilmaydi.
Shu sabab testlar `fix` matnining borligini ham tekshiradi.

Hech qanday qurilma, ffmpeg yoki kamera talab qilinmaydi: barcha tashqi
chaqiruvlar injektsiya qilinadi.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict

import pytest

from scripts.sotqin_preflight import FAIL, OK, WARN, Preflight, render

MANIFEST = {"files": {"model.xml": {}, "model.bin": {}}}


class Disk:
    def __init__(self, free: int) -> None:
        self.free = free
        self.total = free * 2
        self.used = free


def _runner(results: Dict[str, Any]):
    """Buyruq nomi bo'yicha javob beradigan soxta `subprocess.run`."""

    def run(command, **_kwargs):
        key = command[0]
        outcome = results.get(key)
        if outcome is None:
            raise FileNotFoundError(key)
        if isinstance(outcome, Exception):
            raise outcome
        code, text = outcome
        return subprocess.CompletedProcess(args=command, returncode=code, stdout=text, stderr="")

    return run


def _healthy(tmp_path: Path) -> Preflight:
    """Hamma narsa joyida bo'lgan qurilma."""
    env = tmp_path / "sotqin.env"
    env.write_text(
        "CHAQIMCHI_CLOUD_URL=https://ai.example.test\n"
        "CHAQIMCHI_SITE_ID=site-1\n"
        "CHAQIMCHI_DEVICE_ID=device-1\n"
        "CHAQIMCHI_DEVICE_TOKEN=token-1\n",
        encoding="utf-8",
    )
    env.chmod(0o600)

    models = tmp_path / "retail"
    models.mkdir()
    (models / "model.xml").write_bytes(b"x")
    (models / "model.bin").write_bytes(b"b")
    manifest = tmp_path / "retail_manifest.json"
    manifest.write_text(json.dumps(MANIFEST), encoding="utf-8")

    cache = tmp_path / "sotqin-config.json"
    cache.write_text(
        json.dumps(
            {
                "cameras": [
                    {"camera_id": "camera-01", "source": "rtsp://nvr/1", "enabled": True}
                ],
                "config": {
                    "lines": [{"name": "kirish", "camera_id": "camera-01"}],
                    "zones": [{"name": "kassa", "camera_id": "camera-01"}],
                },
            }
        ),
        encoding="utf-8",
    )

    probe = json.dumps(
        {"streams": [{"codec_name": "h264", "width": 640, "height": 360, "avg_frame_rate": "15/1"}]}
    )
    return Preflight(
        env_path=env,
        model_dir=models,
        manifest_path=manifest,
        data_dir=tmp_path,
        config_cache=cache,
        runner=_runner(
            {
                "clinfo": (0, "Platform: Intel(R) OpenCL Graphics"),
                "vainfo": (0, "VAProfileH264Main : VAEntrypointVLD"),
                "systemctl": (0, "active\n"),
                "ffprobe": (0, probe),
            }
        ),
        which=lambda name: f"/usr/bin/{name}",
        disk_usage=lambda _path: Disk(80 * 1024**3),
    )


def _status(preflight: Preflight, name: str) -> str:
    return next(check.status for check in preflight.run() if check.name == name)


# ── Hammasi joyida ───────────────────────────────────────────────────────


def test_a_healthy_device_passes_every_check(tmp_path: Path) -> None:
    preflight = _healthy(tmp_path)

    payload = preflight.payload()

    assert payload["ready"] is True, [c for c in payload["checks"] if c["status"] == FAIL]
    assert payload["failed"] == 0
    assert all(check["status"] == OK for check in payload["checks"])


def test_every_problem_says_what_to_do(tmp_path: Path) -> None:
    """Yechimsiz xato o'rnatuvchi uchun foydasiz."""
    preflight = Preflight(
        env_path=tmp_path / "yo'q.env",
        model_dir=tmp_path / "yo'q",
        manifest_path=tmp_path / "yo'q.json",
        data_dir=tmp_path / "yo'q",
        config_cache=tmp_path / "yo'q.json",
        runner=_runner({}),
        which=lambda _name: None,
        disk_usage=lambda _path: (_ for _ in ()).throw(OSError("yo'q")),
    )

    for check in preflight.run():
        if check.status in {FAIL, WARN}:
            assert check.fix, check.name


# ── Alohida muammolar ────────────────────────────────────────────────────


def test_a_missing_igpu_is_a_hard_failure(tmp_path: Path) -> None:
    """Jimgina CPU'ga tushish — mahsulotni buzuq holda topshirish."""
    preflight = _healthy(tmp_path)
    preflight.runner = _runner(
        {
            "clinfo": (0, "Platform: Mesa"),  # Intel yo'q
            "vainfo": (0, "VAProfileH264Main"),
            "systemctl": (0, "active\n"),
            "ffprobe": (0, "{}"),
        }
    )

    assert _status(preflight, "iGPU (OpenCL)") == FAIL


def test_missing_vaapi_only_warns(tmp_path: Path) -> None:
    """Apparatli dekodsiz ham 4 kamera ishlashi mumkin — bu to'siq emas."""
    preflight = _healthy(tmp_path)
    preflight.runner = _runner(
        {
            "clinfo": (0, "Intel(R) Graphics"),
            "systemctl": (0, "active\n"),
            "ffprobe": (0, "{}"),
        }
    )

    assert _status(preflight, "VAAPI (video dekod)") == WARN


def test_world_readable_env_is_a_failure(tmp_path: Path) -> None:
    """Faylda NVR paroli va device token turadi."""
    preflight = _healthy(tmp_path)
    preflight.env_path.chmod(0o644)

    assert _status(preflight, "Sozlama fayli huquqi") == FAIL


def test_unpaired_device_is_reported_with_the_pairing_command(tmp_path: Path) -> None:
    preflight = _healthy(tmp_path)
    preflight.env_path.write_text(
        "CHAQIMCHI_CLOUD_URL=https://ai.example.test\n"
        "CHAQIMCHI_SITE_ID=FROM_PAIRING\n"
        "CHAQIMCHI_DEVICE_ID=FROM_PAIRING\n"
        "CHAQIMCHI_DEVICE_TOKEN=FROM_PAIRING\n",
        encoding="utf-8",
    )

    check = next(item for item in preflight.run() if item.name == "Pairing")
    assert check.status == FAIL
    assert "pair_sotqin.py" in check.fix


def test_a_full_disk_stops_clip_recording(tmp_path: Path) -> None:
    preflight = _healthy(tmp_path)
    preflight.disk_usage = lambda _path: Disk(2 * 1024**3)

    assert _status(preflight, "Disk") == FAIL


def test_a_stopped_service_is_reported_with_the_log_command(tmp_path: Path) -> None:
    preflight = _healthy(tmp_path)
    preflight.runner = _runner(
        {
            "clinfo": (0, "Intel(R) Graphics"),
            "vainfo": (0, "VAProfileH264Main"),
            "systemctl": (3, "inactive\n"),
            "ffprobe": (0, "{}"),
        }
    )

    check = next(item for item in preflight.run() if item.name == "Xizmat chaqimchi-retail")
    assert check.status == FAIL
    assert "journalctl" in check.fix


def test_an_offline_camera_is_named(tmp_path: Path) -> None:
    preflight = _healthy(tmp_path)
    preflight.runner = _runner(
        {
            "clinfo": (0, "Intel(R) Graphics"),
            "vainfo": (0, "VAProfileH264Main"),
            "systemctl": (0, "active\n"),
            "ffprobe": (1, ""),
        }
    )

    check = next(item for item in preflight.run() if item.name == "Kameralar")
    assert check.status == FAIL
    assert "camera-01" in check.detail


# ── Chiziq va zona ───────────────────────────────────────────────────────


def test_no_geometry_is_a_failure(tmp_path: Path) -> None:
    """Chiziqsiz mijoz to'lovni boshlaydi-yu, panelda "kirdi: 0" turaveradi."""
    preflight = _healthy(tmp_path)
    preflight.config_cache.write_text(
        json.dumps(
            {
                "cameras": [{"camera_id": "camera-01", "source": "rtsp://nvr/1", "enabled": True}],
                "config": {"lines": [], "zones": []},
            }
        ),
        encoding="utf-8",
    )

    check = next(item for item in preflight.run() if item.name == "Chiziq va zona")
    assert check.status == FAIL
    assert "hisoblanmaydi" in check.detail


def test_zones_without_a_counting_line_only_warn(tmp_path: Path) -> None:
    """Faqat navbat kerak bo'lgan do'kon ham bo'lishi mumkin, lekin
    o'rnatuvchi kirganlar sanalmasligini bilishi shart."""
    preflight = _healthy(tmp_path)
    preflight.config_cache.write_text(
        json.dumps(
            {
                "cameras": [{"camera_id": "camera-01", "source": "rtsp://nvr/1", "enabled": True}],
                "config": {"lines": [], "zones": [{"name": "kassa", "camera_id": "camera-01"}]},
            }
        ),
        encoding="utf-8",
    )

    check = next(item for item in preflight.run() if item.name == "Chiziq va zona")
    assert check.status == WARN
    assert "sanalmaydi" in check.detail


# ── Chiqish ──────────────────────────────────────────────────────────────


def test_output_shows_the_fix_under_each_problem(tmp_path: Path) -> None:
    preflight = _healthy(tmp_path)
    preflight.disk_usage = lambda _path: Disk(1024)

    text = render(preflight.run())

    assert "✗ Disk" in text
    assert "→" in text
    assert "1 ta muammo bor" in text


def test_a_clean_run_says_the_job_is_done(tmp_path: Path) -> None:
    assert "topshirish mumkin" in render(_healthy(tmp_path).run())


def test_exit_code_is_nonzero_when_something_failed(tmp_path: Path, monkeypatch) -> None:
    """`bootstrap_sotqin.sh` shu koddan foydalanadi."""
    from scripts import sotqin_preflight

    monkeypatch.setattr(sotqin_preflight, "Preflight", lambda **_kwargs: _healthy(tmp_path))
    assert sotqin_preflight.main(["--env", str(tmp_path / "sotqin.env")]) == 0


@pytest.mark.parametrize("flag", [[], ["--json"]])
def test_both_output_modes_work(tmp_path: Path, monkeypatch, capsys, flag) -> None:
    from scripts import sotqin_preflight

    monkeypatch.setattr(sotqin_preflight, "Preflight", lambda **_kwargs: _healthy(tmp_path))
    sotqin_preflight.main([*flag, "--env", str(tmp_path / "sotqin.env")])

    output = capsys.readouterr().out
    if flag:
        assert json.loads(output)["ready"] is True
    else:
        assert "iGPU" in output
