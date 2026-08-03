from chaqimchi_ai.metrics import MetricsCollector


def test_metrics_snapshot() -> None:
    m = MetricsCollector()
    m.record_inference("cam1", 12.5, faces=2)
    m.record_match("cam1")
    snap = m.snapshot()
    assert snap["inferences_total"] == 1
    assert snap["matches_total"] == 1
    assert snap["cameras"]["cam1"]["inferences"] == 1
