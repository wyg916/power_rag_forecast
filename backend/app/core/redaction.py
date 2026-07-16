from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit


SECRET_FIELD_HINTS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "passwd",
    "pwd",
    "token",
    "secret",
    "database_url",
    "db_password",
    "deepseek_api_key",
    "openai_api_key",
}


def mask_api_key(value: str | None) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 8:
        return "******"
    return f"{text[:3]}******{text[-4:]}"


def mask_authorization(value: str | None) -> str:
    text = str(value or "")
    if not text:
        return ""
    parts = text.split(None, 1)
    if len(parts) == 2:
        return f"{parts[0]} ******"
    return "******"


def mask_db_url(value: str | None) -> str:
    text = str(value or "")
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except Exception:
        return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:******@", text)
    netloc = parts.netloc
    if "@" in netloc:
        credentials, host = netloc.rsplit("@", 1)
        user = credentials.split(":", 1)[0]
        netloc = f"{user}:******@{host}" if user else f"******@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(hint in lowered for hint in SECRET_FIELD_HINTS)


def _mask_string_by_key(key: str, value: str) -> str:
    lowered = key.lower()
    if "authorization" in lowered:
        return mask_authorization(value)
    if "database_url" in lowered or value.startswith(("postgres://", "postgresql://", "postgresql+")):
        return mask_db_url(value)
    return "******"


def mask_secret_fields(value: Any, *, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        return {
            str(key): mask_secret_fields(item, parent_key=str(key)) if not _is_secret_key(str(key)) else _mask_string_by_key(str(key), str(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [mask_secret_fields(item, parent_key=parent_key) for item in value]
    if isinstance(value, tuple):
        return [mask_secret_fields(item, parent_key=parent_key) for item in value]
    if isinstance(value, str):
        if _is_secret_key(parent_key):
            return _mask_string_by_key(parent_key, value)
        text = re.sub(r"(sk-[A-Za-z0-9_-]{12,})", lambda match: mask_api_key(match.group(1)), value)
        text = re.sub(r"(Bearer)\s+([A-Za-z0-9._~+/=-]{8,})", r"\1 ******", text, flags=re.IGNORECASE)
        text = re.sub(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\b", "[JWT REDACTED]", text)
        text = re.sub(
            r"\b(password|passwd|pwd|access[_-]?token|refresh[_-]?token|jwt[_-]?secret(?:[_-]?key)?|api[_-]?key|database[_-]?url)\b(\s*[:=]\s*)([^\s,;]+)",
            r"\1\2******",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"(postgresql(?:\+\w+)?://[^:\s/@]+:)([^@\s]+)(@)", r"\1******\3", text, flags=re.IGNORECASE)
        return text
    return value
