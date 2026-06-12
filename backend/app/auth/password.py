from __future__ import annotations

import hashlib
import hmac
import os
import secrets

try:  # pragma: no cover - optional dependency path
    from passlib.context import CryptContext
except Exception:  # pragma: no cover - passlib is optional in this repo
    CryptContext = None  # type: ignore[assignment]


_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto") if CryptContext else None
_PBKDF2_PREFIX = "pbkdf2_sha256"
_PBKDF2_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    """Hash a password without ever returning or logging the plaintext."""

    value = str(password or "")
    if _pwd_context is not None:
        return _pwd_context.hash(value)
    salt = secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERATIONS)
    return f"{_PBKDF2_PREFIX}${_PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    value = str(password or "")
    stored = str(password_hash)
    if _pwd_context is not None and not stored.startswith(f"{_PBKDF2_PREFIX}$"):
        try:
            return bool(_pwd_context.verify(value, stored))
        except Exception:
            return False
    try:
        prefix, iterations, salt, digest = stored.split("$", 3)
        if prefix != _PBKDF2_PREFIX:
            return False
        computed = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt.encode("utf-8"), int(iterations)).hex()
        return hmac.compare_digest(computed, digest)
    except Exception:
        return False
