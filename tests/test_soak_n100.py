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
