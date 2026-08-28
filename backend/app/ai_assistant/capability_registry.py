from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class LogicalModelAlias(StrEnum):
    GENERAL_DEFAULT = "GENERAL_DEFAULT"
    VISION_DEFAULT = "VISION_DEFAULT"
    DATA_PLANNER = "DATA_PLANNER"
    COMPLEX_REASONER = "COMPLEX_REASONER"
    PREMIUM = "PREMIUM"


@dataclass(frozen=True)
class ModelCapability:
    alias: LogicalModelAlias
    provider: str
    model: str
    route_reason: str
    supports_vision: bool = False
    supports_structured: bool = False
    premium: bool = False


class PremiumConsentRequired(ValueError):
    pass


def _model(stable_name: str, _legacy_provider_name: str, stable_default: str) -> str:
    """Resolve the governed product model without legacy environment drift."""

    return os.environ.get(stable_name, "").strip() or stable_default


def capability_registry() -> dict[LogicalModelAlias, ModelCapability]:
    """Single source of truth for business-level model aliases."""

    mimo = _model("MIMO_STABLE_MODEL_ID", "MIMO_MODEL", "mimo-v2.5")
    deepseek = _model("DEEPSEEK_STABLE_MODEL_ID", "DEEPSEEK_MODEL", "deepseek-v4-flash")
    kimi = _model("KIMI_STABLE_MODEL_ID", "KIMI_MODEL", "kimi-k2.6")
    return {
        LogicalModelAlias.GENERAL_DEFAULT: ModelCapability(
            LogicalModelAlias.GENERAL_DEFAULT, "mimo", mimo, "general_low_cost"
        ),
        LogicalModelAlias.VISION_DEFAULT: ModelCapability(
            LogicalModelAlias.VISION_DEFAULT, "mimo", mimo, "vision_input", supports_vision=True
        ),
        LogicalModelAlias.DATA_PLANNER: ModelCapability(
            LogicalModelAlias.DATA_PLANNER, "deepseek", deepseek, "governed_analysis_plan", supports_structured=True
        ),
        LogicalModelAlias.COMPLEX_REASONER: ModelCapability(
            LogicalModelAlias.COMPLEX_REASONER, "deepseek", deepseek, "complex_reasoning", supports_structured=True
        ),
        LogicalModelAlias.PREMIUM: ModelCapability(
            LogicalModelAlias.PREMIUM, "kimi", kimi, "explicit_premium", premium=True
        ),
    }


def alias_for_task(task_type: str, *, requested_tier: str = "standard", premium_confirmed: bool = False) -> LogicalModelAlias:
    tier = (requested_tier or "standard").strip().lower()
    if tier == "premium":
        if not premium_confirmed:
            raise PremiumConsentRequired("premium_explicit_confirmation_required")
        return LogicalModelAlias.PREMIUM
    normalized = (task_type or "general").strip().lower()
    if normalized in {"vision", "vision_analysis", "image", "chart_vision"}:
        return LogicalModelAlias.VISION_DEFAULT
    if normalized in {"data_planner", "chatbi", "nl2sql", "analysis_plan"}:
        return LogicalModelAlias.DATA_PLANNER
    if normalized in {"complex_analysis", "model_diagnosis", "business_analysis", "action_advice", "report_generation"}:
        return LogicalModelAlias.COMPLEX_REASONER
    return LogicalModelAlias.GENERAL_DEFAULT


def resolve_capability(
    alias: LogicalModelAlias | str,
    *,
    requested_tier: str = "standard",
    premium_confirmed: bool = False,
) -> ModelCapability:
    resolved = LogicalModelAlias(alias)
    if resolved == LogicalModelAlias.PREMIUM and (
        (requested_tier or "standard").strip().lower() != "premium" or not premium_confirmed
    ):
        raise PremiumConsentRequired("premium_explicit_confirmation_required")
    return capability_registry()[resolved]


def fallback_capability(primary: ModelCapability) -> ModelCapability | None:
    """Only one transparent fallback is allowed; Premium is never a fallback."""

    if primary.alias == LogicalModelAlias.GENERAL_DEFAULT:
        return capability_registry()[LogicalModelAlias.COMPLEX_REASONER]
    return None


ROUTE_PERMISSIONS = {
    "dashboard": "dashboard:read",
    "forecast": "forecast:read",
    "data": "data:read",
    "strategy": "strategy:read",
    "report": "report:read",
    "knowledge": "knowledge:read",
    "model": "model:read",
    "task": "task:read",
    "settings": "settings:read",
    "assistant": "assistant:use",
}

ACTION_PERMISSIONS = {
    "forecast.run": "forecast:run",
    "data.export": "data:export",
    "strategy.generate": "strategy:generate",
    "report.generate": "report:generate",
    "settings.write": "settings:write",
    "assistant.use": "assistant:use",
    "assistant.export": "assistant:export",
}


def capability_manifest(permissions: list[str]) -> dict[str, Any]:
    allowed = set(permissions)
    permits = lambda value: "*" in allowed or value in allowed
    return {
        "routes": {key: permits(value) for key, value in ROUTE_PERMISSIONS.items()},
        "actions": {key: permits(value) for key, value in ACTION_PERMISSIONS.items()},
        "policy_version": "v2.12.0",
    }


PAGE_CONTEXT_KEYS = {
    "route_key", "page_title", "active_filters", "selected_entity",
    "visible_summary", "permission_snapshot_hash",
}


def validate_page_context(page_context: dict[str, Any] | None, permissions: list[str]) -> dict[str, Any] | None:
    if page_context is None:
        return None
    if not isinstance(page_context, dict) or set(page_context) - PAGE_CONTEXT_KEYS:
        raise ValueError("page_context_contract_invalid")
    route_prefix = str(page_context.get("route_key") or "").split(".", 1)[0]
    required = ROUTE_PERMISSIONS.get(route_prefix)
    allowed = set(permissions)
    if required and "*" not in allowed and required not in allowed:
        raise PermissionError("page_context_permission_denied")
    return {key: page_context[key] for key in PAGE_CONTEXT_KEYS if key in page_context}
