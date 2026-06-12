from __future__ import annotations

import pytest

from backend.app.auth.jwt import JWTError, create_access_token, decode_access_token
from backend.app.auth.password import hash_password, verify_password
from backend.app.core.config import reset_settings_cache


@pytest.fixture(autouse=True)
def _jwt_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "unit_test_jwt_secret")
    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_password_hash_is_not_plaintext():
    hashed = hash_password("CorrectHorseBatteryStaple")
    assert hashed != "CorrectHorseBatteryStaple"
    assert verify_password("CorrectHorseBatteryStaple", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_create_and_decode_roundtrip():
    token = create_access_token(subject="alice", user_id="u1", role="admin", permissions=["*"])
    payload = decode_access_token(token)
    assert payload["sub"] == "alice"
    assert payload["user_id"] == "u1"
    assert payload["role"] == "admin"


def test_jwt_rejects_tampered_token():
    token = create_access_token(subject="alice", user_id="u1", role="admin", permissions=["*"])
    tampered = token[:-2] + "xx"
    with pytest.raises(JWTError):
        decode_access_token(tampered)

