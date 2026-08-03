"""FastAPI ilovasi import va marshrutlar (lifespan ishga tushmasin)."""


def test_app_title_and_health_route_registered():
    from webapp.main import app

    assert "Chaqimchi" in app.title
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/health" in paths
    assert "/api/persons" in paths
    assert "/api/events" in paths
    assert "/ws" in paths
    assert "/api/persons/{face_id}" in paths
    assert "/api/snapshots/{filename}" in paths
    assert "/api/calibrate/threshold" in paths
    assert "/api/calibrate/apply" in paths
    assert "/api/identify" in paths
    assert "/api/analyze" in paths
    assert "/api/metrics" in paths
    assert "/ready" in paths
    assert "/metrics" in paths
    assert "/api/auth/token" in paths
