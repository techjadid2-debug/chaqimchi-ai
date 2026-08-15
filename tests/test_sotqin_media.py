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
                {
                    "streams": [
                        {
                            "codec_name": "h264",
                            "width": 1280,
                            "height": 720,
                            "avg_frame_rate": "10/1",
                        }
                    ]
                }
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


# ── O'rnatuvchi uchun bitta kadr ─────────────────────────────────────────

JPEG = b"\xff\xd8\xff\xe0" + b"soxta-jpeg" * 20


def _media_with(stdout: bytes, *, returncode: int = 0) -> SotqinMediaRuntime:
    def runner(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=b""
        )

    media = SotqinMediaRuntime(runner=runner)
    media.apply_config({"cameras": [_camera()]})
    return media


def test_preview_returns_the_jpeg_bytes() -> None:
    media = _media_with(JPEG)

    assert media.grab_preview(_camera()) == JPEG


def test_preview_command_asks_for_exactly_one_frame_over_tcp() -> None:
    seen: list = []

    def runner(command, *_args, **_kwargs):
        seen.append(command)
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=JPEG, stderr=b"")

    media = SotqinMediaRuntime(runner=runner)
    command = " ".join(map(str, (media.grab_preview(_camera()), seen[0])[1]))

    # Bitta kadr — aks holda ffmpeg oqimni cheksiz o'qib turardi.
    assert "-frames:v 1" in command
    # UDP paket yo'qotishi buzuq kadr beradi.
    assert "-rtsp_transport tcp" in command
    # Brauzerda chizish uchun 640 px yetarli va rasm kichik qoladi.
    assert "scale=640:-2" in command


def test_preview_fails_closed_when_ffmpeg_errors_or_times_out() -> None:
    assert _media_with(JPEG, returncode=1).grab_preview(_camera()) is None

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("ffmpeg", 12)

    media = SotqinMediaRuntime(runner=timeout)
    assert media.grab_preview(_camera()) is None


def test_preview_rejects_output_that_is_not_a_jpeg() -> None:
    """ffmpeg xato matnini stdout'ga yozib qo'ysa u rasm sifatida ketmasin."""
    assert _media_with(b"Invalid data found when processing input").grab_preview(_camera()) is None


def test_preview_rejects_an_oversized_frame() -> None:
    from chaqimchi_ai.sotqin_media import PREVIEW_MAX_BYTES

    huge = b"\xff\xd8" + b"x" * PREVIEW_MAX_BYTES
    assert _media_with(huge).grab_preview(_camera()) is None


def test_camera_lookup_is_by_id() -> None:
    media = _media_with(JPEG)

    assert media.camera("camera-01")["label"] == "Kirish"
    assert media.camera("camera-09") is None
