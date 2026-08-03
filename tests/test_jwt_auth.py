from chaqimchi_ai.jwt_auth import create_access_token, decode_access_token
from chaqimchi_ai.settings import JwtSettings


def test_jwt_roundtrip() -> None:
    cfg = JwtSettings(
        enabled=True,
        secret="test-secret-key-with-at-least-32-bytes!!",
        expire_hours=1,
    )
    token = create_access_token("user1", cfg=cfg)
    payload = decode_access_token(token, cfg=cfg)
    assert payload["sub"] == "user1"
