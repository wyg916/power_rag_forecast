from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from backend.app.core.config import get_settings


class JWTError(ValueError):
    pass


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _sign(message: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), message.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def _configured_secret() -> str:
    secret = get_settings().jwt_secret_key.strip()
    if not secret:
        raise JWTError("JWT_SECRET_KEY is not configured")
    return secret


def create_access_token(
    *,
    subject: str,
    user_id: str,
    role: str,
    permissions: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    if settings.jwt_algorithm.upper() != "HS256":
        raise JWTError("Only HS256 JWT signing is supported")
    now = int(time.time())
    expire = now + max(60, int(settings.jwt_access_token_expire_minutes) * 60)
    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "sub": subject,
        "user_id": user_id,
        "role": role,
        "permissions": permissions or [],
        "iat": now,
        "exp": expire,
    }
    payload.update(extra or {})
    signing_input = ".".join(
        [
            _b64encode(json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")),
            _b64encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")),
        ]
    )
    return f"{signing_input}.{_sign(signing_input, _configured_secret())}"


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        header_b64, payload_b64, signature = str(token or "").split(".", 2)
        signing_input = f"{header_b64}.{payload_b64}"
        expected = _sign(signing_input, _configured_secret())
        if not hmac.compare_digest(signature, expected):
            raise JWTError("Invalid JWT signature")
        header = json.loads(_b64decode(header_b64).decode("utf-8"))
        payload = json.loads(_b64decode(payload_b64).decode("utf-8"))
    except JWTError:
        raise
    except Exception as exc:
        raise JWTError("Invalid JWT token") from exc
    if str(header.get("alg") or "").upper() != settings.jwt_algorithm.upper():
        raise JWTError("Unsupported JWT algorithm")
    if int(payload.get("exp") or 0) < int(time.time()):
        raise JWTError("JWT token expired")
    return payload

