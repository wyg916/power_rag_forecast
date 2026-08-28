from __future__ import annotations

from typing import Any

from backend.app.auth.password import validate_password_length
from backend.app.repositories.settings_repository import list_runtime_config


SECURITY_POLICY_DEFAULTS: dict[str, Any] = {
    "password_min_length": 12,
    "login_failed_lock_count": 5,
    "login_lock_minutes": 15,
    "session_timeout_minutes": 30,
    "two_factor_enabled": False,
    "force_periodic_password_change": True,
    "admin_reset_password_enabled": True,
}

_INTEGER_LIMITS = {
    "password_min_length": (8, 64),
    "login_failed_lock_count": (1, 20),
    "login_lock_minutes": (1, 1440),
    "session_timeout_minutes": (5, 10080),
}
_BOOLEAN_KEYS = {
    "two_factor_enabled",
    "force_periodic_password_change",
    "admin_reset_password_enabled",
}


class SecurityPolicyError(ValueError):
    pass


def security_policy_values() -> dict[str, Any]:
    values = dict(SECURITY_POLICY_DEFAULTS)
    try:
        rows = list_runtime_config("security_policy")
    except Exception:
        rows = []
    for row in rows:
        key = str(row.get("config_key") or "")
        if key in values:
            values[key] = row.get("config_value")
    return normalize_security_policy(values, partial=False, allow_unready_two_factor=True)


def normalize_security_policy(
    values: dict[str, Any],
    *,
    partial: bool = True,
    allow_unready_two_factor: bool = False,
) -> dict[str, Any]:
    if not isinstance(values, dict):
        raise SecurityPolicyError("安全策略必须是对象")
    unknown = sorted(set(values) - set(SECURITY_POLICY_DEFAULTS))
    if unknown:
        raise SecurityPolicyError(f"不支持的安全策略：{','.join(unknown)}")
    normalized: dict[str, Any] = {}
    source = values if partial else {**SECURITY_POLICY_DEFAULTS, **values}
    for key, value in source.items():
        if key in _INTEGER_LIMITS:
            try:
                parsed = int(value)
            except (TypeError, ValueError) as exc:
                raise SecurityPolicyError(f"{key} 必须是整数") from exc
            minimum, maximum = _INTEGER_LIMITS[key]
            if parsed < minimum or parsed > maximum:
                raise SecurityPolicyError(f"{key} 必须在 {minimum} 到 {maximum} 之间")
            normalized[key] = parsed
        elif key in _BOOLEAN_KEYS:
            if not isinstance(value, bool):
                raise SecurityPolicyError(f"{key} 必须是布尔值")
            normalized[key] = value
    if normalized.get("two_factor_enabled") and not allow_unready_two_factor:
        raise SecurityPolicyError("双因素认证尚未完成用户登记与验证码校验链路，当前不能安全启用")
    return normalized


def validate_password_policy(password: str) -> str:
    value = validate_password_length(password)
    minimum = int(security_policy_values()["password_min_length"])
    if len(value) < minimum:
        raise SecurityPolicyError(f"密码长度不得少于 {minimum} 位")
    return value


def session_timeout_minutes() -> int:
    return int(security_policy_values()["session_timeout_minutes"])


def admin_password_reset_enabled() -> bool:
    return bool(security_policy_values()["admin_reset_password_enabled"])


def security_policy_capabilities() -> dict[str, Any]:
    return {
        "password_min_length": {"editable": True, "enforced": True},
        "login_failed_lock_count": {"editable": True, "enforced": True},
        "session_timeout_minutes": {"editable": True, "enforced": True},
        "admin_reset_password_enabled": {"editable": True, "enforced": True},
        "force_periodic_password_change": {"editable": True, "enforced": False},
        "two_factor_enabled": {
            "editable": True,
            "enforced": False,
            "blocked_reason": "user_enrollment_and_challenge_flow_unavailable",
        },
    }
