import json
import subprocess

import pytest

from chaqimchi_ai.sotqin_media import SotqinMediaRuntime, validate_cameras


def _camera(camera_id: str = "camera-01") -> dict:
    return {
        "camera_id": camera_id,
        "label": "Kirish",
        "source": "rtsp://user:secret@192.168.10.10:554/sub",
        "enabled": True,
    }


def test_media_config_rejects_nine_cameras_and_non_rtsp_source() -> None:
    with pytest.raises(ValueError, match="8 ta"):
        validate_cameras([_camera(f"camera-{number:02d}") for number in range(1, 10)])
    with pytest.raises(ValueError, match="RTSP"):
        validate_cameras([{**_camera(), "source": "https://camera/live"}])


def test_media_probe_reports_stream_without_leaking_rtsp_url() -> None:
    def runner(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {"streams": [{"codec_name": "h264", "width": 1280, "height": 720, "avg_frame_rate": "10/1"}]}
            ),
            stderr="",
        )

    media = SotqinMediaRuntime(runner=runner)
    media.apply_config({"cameras": [_camera()]})
    result = media.probe_all()
    assert result == [
        {
            "camera_id": "camera-01",
            "status": "online",
            "error": None,
            "codec": "h264",
            "width": 1280,
            "height": 720,
            "fps": 10.0,
        }
    ]
    assert "secret" not in str(result)
    assert media.health() == {"configured": 1, "online": 1}


def test_media_probe_fails_closed_on_timeout() -> None:
    def runner(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("ffprobe", 12)

    media = SotqinMediaRuntime(runner=runner)
    media.apply_config({"cameras": [_camera()]})
    assert media.probe_all()[0]["status"] == "offline"
