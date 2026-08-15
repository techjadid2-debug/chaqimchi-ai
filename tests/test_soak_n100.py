from scripts.soak_n100 import summarize_samples


def test_soak_summary_counts_camera_uptime_temperature_and_final_critical() -> None:
    report = summarize_samples(
        [
            {"cameras_active": 4, "temperature_c": 70, "outbox_critical_pending": 1},
            {"cameras_active": 3, "temperature_c": 79, "outbox_critical_pending": 0},
            {"cameras_active": 4, "temperature_c": 75, "outbox_critical_pending": 0},
        ],
        duration_hours=72.2,
        restart_delta=1,
    )

    assert report == {
        "duration_hours": 72.2,
        "cameras_min_active": 3,
        "unexpected_restarts": 1,
        "camera_uptime_percent": 66.667,
        "max_temperature_c": 79.0,
        "undelivered_critical_events": 0,
        "samples": 3,
    }


def test_soak_measures_the_chain_not_ffprobe(tmp_path) -> None:
    """72 soatlik testning butun ma'nosi shu raqamda.

    `cameras_active` `ffprobe` dan olinsa, kamera RTSP uchun ochiq bo'lib
    turib retail zanjiri bir soat backoff'da bo'lishi mumkin edi — soak
    esa buni sezmasdan "4 kamera ishlayapti" deb sertifikatlab qo'yardi.

    Zanjir → holat fayli → agent `/health` → soak: butun yo'lni bir joyda
    tekshiramiz.
    """
    import json
    import time

    import chaqimchi_ai.sotqin_agent as agent
    from chaqimchi_ai.retail.service import write_status
    from scripts.soak_n100 import read_health

    status = tmp_path / "retail-status.json"
    write_status(
        status,
        {
            "streams": {
                "camera-01": {"connected": True, "offline": False},
                "camera-02": {"connected": True, "offline": False},
                "camera-03": {"connected": False, "offline": True},
                "camera-04": {"connected": False, "offline": True},
            }
        },
        now=time.time(),
    )

    control = agent.SotqinAgent()
    control.retail_status_path = status
    payload = control.health_payload()

    assert payload["cameras_active"] == 2

    # `read_health` aynan shu bo'limni oladi — soak o'sha raqamni sanaydi.
    class _Response:
        def __init__(self, body: str) -> None:
            self._body = body.encode()

        def read(self) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    import urllib.request

    original = urllib.request.urlopen
    urllib.request.urlopen = lambda *_a, **_k: _Response(
        json.dumps({"device_health": payload})
    )
    try:
        assert read_health("http://127.0.0.1:8742/health")["cameras_active"] == 2
    finally:
        urllib.request.urlopen = original
