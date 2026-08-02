from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


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

REDACTION_MASK = "******"
ASSIGNMENT_REDACTION_MASK = "[REDACTED]"
_URL_CREDENTIAL_RE = re.compile(
    r"(?P<prefix>\b(?:postgres(?:ql)?(?:\+[A-Za-z0-9_]+)?|redis(?:s)?|amqp(?:s)?):"
    r"//[^\s/:@]+:)(?P<secret>[^@\s/]+)(?P<suffix>@)",
    flags=re.IGNORECASE,
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?P<prefix>(?<![A-Za-z0-9_])(?P<key_quote>['\"]?)(?:password|passwd|pwd|token|"
    r"access[_-]?token|refresh[_-]?token|api[_-]?key|secret|authorization|"
    r"jwt[_-]?secret[_-]?key)(?P=key_quote)\s*[:=]\s*)"
    r"(?P<value_quote>['\"]?)(?P<secret>[^\s,'\";}&]+)(?P=value_quote)",
    flags=re.IGNORECASE,
)
_SECRET_QUERY_RE = re.compile(
    r"(?P<prefix>[?&](?:password|passwd|pwd|token|access[_-]?token|refresh[_-]?token|"
    r"api[_-]?key|secret)=)(?P<secret>[^&\s#]+)",
    flags=re.IGNORECASE,
)
_BEARER_RE = re.compile(r"(?P<prefix>\bBearer\s+)(?P<secret>[^\s,;]+)", flags=re.IGNORECASE)


def redact_text(value: object, *, extra_secrets: Iterable[str] = ()) -> str:
    """Redact credentials from arbitrary text without relying on one failure shape."""

    text = str(value or "")
    for secret in sorted({str(item) for item in extra_secrets if item}, key=len, reverse=True):
        text = text.replace(secret, REDACTION_MASK)
    text = _URL_CREDENTIAL_RE.sub(rf"\g<prefix>{REDACTION_MASK}\g<suffix>", text)
    text = _SECRET_QUERY_RE.sub(rf"\g<prefix>{REDACTION_MASK}", text)
    text = _BEARER_RE.sub(rf"\g<prefix>{REDACTION_MASK}", text)
    text = _SECRET_ASSIGNMENT_RE.sub(
        lambda match: (
            f"{match.group('prefix')}{match.group('value_quote')}"
            f"{ASSIGNMENT_REDACTION_MASK}{match.group('value_quote')}"
        ),
        text,
    )
    return text


def safe_exception_summary(exc: BaseException, *, extra_secrets: Iterable[str] = ()) -> dict[str, Any]:
    """Return a bounded, redacted exception chain safe for logs and evidence."""

    chain: list[dict[str, str]] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen and len(chain) < 6:
        seen.add(id(current))
        chain.append(
            {
                "error_type": type(current).__name__,
                "message": redact_text(str(current), extra_secrets=extra_secrets),
            }
        )
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    return {
        "error_type": type(exc).__name__,
        "message": chain[0]["message"] if chain else "",
        "chain": chain,
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
    return redact_text(value)


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
        text = re.sub(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\b", "[JWT REDACTED]", text)
        return redact_text(text)
    return value
