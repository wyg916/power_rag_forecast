from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.api.v1.endpoints.auth import ChangePasswordRequest
from backend.app.auth.jwt import JWTError, create_access_token, decode_access_token
from backend.app.auth.password import hash_password, verify_password
from backend.app.core.config import reset_settings_cache
from backend.app.schemas import UserCreateRequest, UserResetPasswordRequest


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
    assert hashed.startswith("$2b$12$")
    assert verify_password("CorrectHorseBatteryStaple", hashed)
    assert not verify_password("wrong", hashed)


def test_existing_bcrypt_hash_remains_compatible():
    legacy_hash = "$2b$12$abcdefghijklmnopqrstuus30Of/ZdhTRPUfhuILygySK2SHpS/A2"
    assert verify_password("LegacyPassword123!", legacy_hash)
    assert not verify_password("wrong-password", legacy_hash)


def test_bcrypt_password_length_boundary_is_explicit_and_safe():
    exact_limit = "a" * 72
    hashed = hash_password(exact_limit)
    assert verify_password(exact_limit, hashed)
    assert not verify_password("a" * 73, hashed)
    with pytest.raises(ValueError, match="72 字节"):
        hash_password("a" * 73)
    with pytest.raises(ValueError, match="72 字节"):
        hash_password("密" * 25)


def test_password_write_requests_reject_overlong_values():
    overlong = "a" * 73
    with pytest.raises(ValidationError, match="72 字节"):
        ChangePasswordRequest(old_password="Password123!", new_password=overlong)
    with pytest.raises(ValidationError, match="72 字节"):
        UserCreateRequest(username="user1", password=overlong)
    with pytest.raises(ValidationError, match="72 字节"):
        UserResetPasswordRequest(new_password=overlong)


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
