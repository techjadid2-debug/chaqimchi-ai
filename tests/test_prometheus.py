from chaqimchi_ai.prometheus_export import format_prometheus


def test_prometheus_contains_metrics() -> None:
    text = format_prometheus(
        {
            "inferences_total": 10,
            "matches_total": 2,
            "errors_total": 0,
            "uptime_sec": 100.5,
            "ws_clients": 1,
            "inference_ms": {"avg": 12.3, "p95": 20.0},
            "cameras": {"cam1": {"inferences": 5}},
        }
    )
    assert "chaqimchi_inferences_total 10" in text
    assert "chaqimchi_camera_inferences_total" in text
