from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit


QDRANT_IMAGE_VERSION = "1.18.2"
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
DISABLED_VALUES = {"", "0", "false", "no", "off", "disabled"}
ENABLED_VALUES = {"1", "true", "yes", "on"}
PLACEHOLDER_MARKERS = ("change_me", "replace", "unset", "example", "your_")


@dataclass(frozen=True)
class QdrantSecurityProfile:
    endpoint: str
    process_role: str
    access_mode: str
    tls_enabled: bool
    strict_mode: bool
    ca_path_configured: bool
    api_key_configured: bool
    image_version: str
    image_digest_configured: bool
    issues: tuple[str, ...]

    @property
    def available(self) -> bool:
        return not self.issues


def _strict_bool(
    values: Mapping[str, str], key: str, default: bool = False
) -> tuple[bool, bool]:
    raw = str(values.get(key, "")).strip().lower()
    if not raw:
        return default, True
    if raw in ENABLED_VALUES:
        return True, True
    if raw in DISABLED_VALUES:
        return False, True
    return default, False


def _secret_configured(value: str) -> bool:
    normalized = value.strip()
    lowered = normalized.lower()
    return len(normalized) >= 32 and not any(
        marker in lowered for marker in PLACEHOLDER_MARKERS
    )


def qdrant_control_plane_issues(
    env: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Validate secrets needed by the explicit pre-start control-plane gate."""

    values = env if env is not None else os.environ
    admin_key = str(values.get("QDRANT_ADMIN_API_KEY", ""))
    read_only_key = str(values.get("QDRANT_READ_ONLY_API_KEY", ""))
    image_digest = str(values.get("QDRANT_IMAGE_DIGEST", "")).strip().lower()
    issues: list[str] = []
    if not _secret_configured(admin_key):
        issues.append("qdrant_admin_key_unavailable")
    if not _secret_configured(read_only_key):
        issues.append("qdrant_read_only_key_unavailable")
    if admin_key and read_only_key and admin_key == read_only_key:
        issues.append("qdrant_keys_must_be_distinct")
    if not DIGEST_PATTERN.fullmatch(image_digest):
        issues.append("qdrant_image_digest_invalid")
    return tuple(issues)


def qdrant_security_status(
    env: Mapping[str, str] | None = None,
) -> QdrantSecurityProfile:
    values = env if env is not None else os.environ
    endpoint = str(values.get("RAG_QDRANT_URL", "")).strip()
    process_role = str(values.get("RAG_PROCESS_ROLE", "api")).strip().lower()
    access_mode = str(values.get("RAG_QDRANT_ACCESS_MODE", "")).strip().lower()
    api_key = str(values.get("RAG_QDRANT_API_KEY", ""))
    ca_path_value = str(values.get("RAG_QDRANT_TLS_CA_PATH", "")).strip()
    ca_path = Path(ca_path_value) if ca_path_value else None
    image_version = str(values.get("RAG_QDRANT_IMAGE_VERSION", "")).strip()
    image_digest = str(values.get("RAG_QDRANT_IMAGE_DIGEST", "")).strip().lower()
    tls_enabled, tls_valid = _strict_bool(values, "RAG_QDRANT_TLS_ENABLED")
    strict_mode, strict_valid = _strict_bool(values, "RAG_QDRANT_STRICT_MODE")
    expected_access = "admin" if process_role == "publisher" else "read_only"

    issues: list[str] = []
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        issues.append("qdrant_https_endpoint_required")
    if process_role not in {"api", "worker", "publisher"}:
        issues.append("qdrant_process_role_invalid")
    if access_mode != expected_access:
        issues.append("qdrant_access_mode_invalid")
    if not tls_valid or not tls_enabled:
        issues.append("qdrant_tls_required")
    if not strict_valid or not strict_mode:
        issues.append("qdrant_strict_mode_required")
    ca_configured = bool(
        ca_path_value and ca_path and ca_path.is_file() and os.access(ca_path, os.R_OK)
    )
    if not ca_configured:
        issues.append("qdrant_tls_ca_unavailable")
    key_configured = _secret_configured(api_key)
    if not key_configured:
        issues.append("qdrant_api_key_unavailable")
    if image_version != QDRANT_IMAGE_VERSION:
        issues.append("qdrant_image_version_invalid")
    digest_configured = bool(DIGEST_PATTERN.fullmatch(image_digest))
    if not digest_configured:
        issues.append("qdrant_image_digest_invalid")

    return QdrantSecurityProfile(
        endpoint=endpoint,
        process_role=process_role,
        access_mode=access_mode,
        tls_enabled=tls_enabled,
        strict_mode=strict_mode,
        ca_path_configured=ca_configured,
        api_key_configured=key_configured,
        image_version=image_version,
        image_digest_configured=digest_configured,
        issues=tuple(dict.fromkeys(issues)),
    )
