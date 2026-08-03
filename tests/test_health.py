from chaqimchi_ai.health import engine_status


class _FakeEngine:
    model_name = "buffalo_l"
    det_size = (640, 640)
    recognition_ready = True

    @property
    def providers(self):
        return ["CPUExecutionProvider"]


def test_engine_status_shape() -> None:
    st = engine_status(_FakeEngine())
    assert st["model_name"] == "buffalo_l"
    assert st["recognition_loaded"] is True
    assert "CPUExecutionProvider" in st["providers"]
