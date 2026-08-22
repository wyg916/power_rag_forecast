from __future__ import annotations

import os
import re
import time
from dataclasses import replace
from typing import Any

from config_loader import load_dotenv

from .llm_providers import (
    DeepSeekProvider,
    KimiProvider,
    MiMoProvider,
    OllamaProvider,
    ProviderRequestError,
)
from .capability_registry import (
    LogicalModelAlias,
    ModelCapability,
    PremiumConsentRequired,
    alias_for_task,
    capability_registry,
    fallback_capability,
    resolve_capability,
)


def _env(name: str, default: str = "") -> str:
    load_dotenv()
    return os.environ.get(name, default).strip()


def sanitize_error(error: Exception | str) -> str:
    text = str(error)
    key_prefix = "sk" + "-"
    text = re.sub(rf"{key_prefix}[A-Za-z0-9_\-]{{12,}}", key_prefix + "***", text)
    text = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]+", "Bearer ***", text, flags=re.I)
    return text[:500]


class LLMRouteError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int, retryable: bool, provider: str = "") -> None:
        self.code, self.status_code, self.retryable, self.provider = code, status_code, retryable, provider
        super().__init__(message)


def provider_error_semantics(error: ProviderRequestError) -> tuple[str, int]:
    reason = error.reason.lower()
    if error.status_code == 429:
        return "PROVIDER_RATE_LIMITED", 429
    if reason in {"cancel", "cancelled", "request_cancelled"}:
        return "REQUEST_CANCELLED", 499
    if reason == "timeout":
        return "PROVIDER_TIMEOUT", 504
    if error.status_code in {401, 403}:
        return "PROVIDER_PERMISSION_DENIED", 503
    if error.status_code and error.status_code >= 500 or reason == "network_unavailable":
        return "PROVIDER_UNAVAILABLE", 503
    if "capability" in reason or "unsupported" in reason:
        return "PROVIDER_CAPABILITY_UNSUPPORTED", 422
    return "PROVIDER_INVALID_RESPONSE", 502


class LLMRouter:
    REMOTE_PROVIDERS = ("deepseek", "kimi", "mimo")
    KNOWN_PROVIDERS = (*REMOTE_PROVIDERS, "ollama")

    def __init__(self) -> None:
        self.default_provider = _env("LLM_PROVIDER", _env("MODEL_PROVIDER", "ollama")).lower() or "ollama"
        self.mode = _env("LLM_ROUTER_MODE", "auto").lower() or "auto"
        self._providers: dict[str, Any] = {}

    def _get_provider(self, name: str) -> Any:
        factories = {
            "deepseek": DeepSeekProvider,
            "kimi": KimiProvider,
            "mimo": MiMoProvider,
            "ollama": OllamaProvider,
        }
        if name not in factories:
            raise ValueError(f"unknown_provider:{name}")
        if name not in self._providers:
            self._providers[name] = factories[name]()
        return self._providers[name]

    def _configured(self, name: str) -> bool:
        try:
            provider = self._get_provider(name)
            if name == "ollama":
                return bool(provider.health().get("available"))
            return bool(provider.available)
        except Exception:
            return False

    def _auto_order(self, task_type: str) -> list[str]:
        primary = resolve_capability(alias_for_task(task_type), requested_tier="standard")
        fallback = fallback_capability(primary)
        return [primary.provider, *([fallback.provider] if fallback else [])]

    def _legacy_auto_order(self, task_type: str) -> list[str]:
        """Compatibility for old direct callers; Premium is deliberately excluded."""

        configured = [
            item.strip().lower()
            for item in _env("LLM_AUTO_PROVIDER_ORDER", "deepseek,mimo,ollama").replace(";", ",").split(",")
            if item.strip().lower() in {"deepseek", "mimo", "ollama"}
        ]
        if self.default_provider in configured and task_type not in {"complex_analysis", "model_diagnosis"}:
            configured.insert(0, configured.pop(configured.index(self.default_provider)))
        return list(dict.fromkeys(configured or ["deepseek", "mimo", "ollama"]))

    def _select_provider(
        self, *, task_type: str, requested_provider: str = "auto", legacy_compatibility: bool = False
    ) -> str:
        requested = (requested_provider or "auto").strip().lower()
        if requested in self.KNOWN_PROVIDERS:
            return requested
        if requested != "auto":
            raise ValueError(f"unknown_provider:{requested}")
        if self.mode == "local":
            return "ollama"
        if task_type in {"daily_chat", "simple_data_answer"} and self._configured("ollama"):
            return "ollama"
        order = self._legacy_auto_order(task_type) if legacy_compatibility else self._auto_order(task_type)
        return next((name for name in order if self._configured(name)), "ollama")

    def generate_answer(
        self,
        messages: list[dict[str, Any]],
        *,
        task_type: str,
        requested_provider: str = "auto",
        logical_alias: LogicalModelAlias | str | None = None,
        requested_tier: str = "standard",
        premium_confirmed: bool = False,
        temperature: float = 0.35,
        max_tokens: int = 1200,
    ) -> tuple[str, dict[str, Any]]:
        try:
            alias = LogicalModelAlias(logical_alias) if logical_alias else alias_for_task(
                task_type, requested_tier=requested_tier, premium_confirmed=premium_confirmed
            )
            primary = resolve_capability(
                alias, requested_tier=requested_tier, premium_confirmed=premium_confirmed
            )
        except PremiumConsentRequired as exc:
            raise LLMRouteError("PREMIUM_CONFIRMATION_REQUIRED", str(exc), status_code=422, retryable=False) from exc
        requested = (requested_provider or "auto").strip().lower()
        explicit = requested != "auto"
        legacy_compatibility = logical_alias is None and task_type in {
            "daily_chat", "simple_data_answer", "complex_analysis", "model_diagnosis"
        }
        if legacy_compatibility:
            preferred = self._select_provider(
                task_type=task_type,
                requested_provider=requested_provider,
                legacy_compatibility=True,
            )
            primary = ModelCapability(alias, preferred, "", "legacy_direct_caller")
        if explicit:
            if requested == "kimi" and (requested_tier != "premium" or not premium_confirmed):
                raise LLMRouteError(
                    "PREMIUM_CONFIRMATION_REQUIRED", "premium_explicit_confirmation_required",
                    status_code=422, retryable=False, provider="kimi",
                )
            if requested not in self.KNOWN_PROVIDERS:
                raise LLMRouteError("PROVIDER_CAPABILITY_UNSUPPORTED", "unknown_provider", status_code=422, retryable=False)
            matches = [item for item in capability_registry().values() if item.provider == requested]
            primary = replace(matches[0], alias=alias) if matches else ModelCapability(alias, requested, "", "explicit_local_provider")
        candidates = [primary]
        if not explicit:
            if legacy_compatibility:
                candidates.extend(
                    ModelCapability(alias, name, "", "legacy_one_fallback")
                    for name in self._legacy_auto_order(task_type)
                    if name != primary.provider and self._configured(name)
                )
            elif (fallback := fallback_capability(primary)) is not None:
                candidates.append(fallback)
        errors: list[dict[str, str]] = []
        fallback_reason = ""
        last_provider_error: ProviderRequestError | None = None
        for index, capability in enumerate(candidates[:2]):
            provider_name = capability.provider
            try:
                provider = self._get_provider(provider_name)
                if provider_name != "ollama" and not provider.available:
                    raise ProviderRequestError(provider_name, "missing_api_key", retryable=False)
                started = time.perf_counter()
                if provider_name == "ollama":
                    content = provider.chat(messages, temperature=temperature, max_tokens=max_tokens)
                    status = provider.health()
                    model = capability.model or getattr(provider, "last_model", None) or status.get("model")
                    completion_meta: dict[str, Any] = {}
                    input_tokens = output_tokens = 0
                    latency_ms = round((time.perf_counter() - started) * 1000, 3)
                else:
                    model = capability.model or provider.default_model
                    result = provider.complete(messages, model=model, temperature=temperature, max_tokens=max_tokens)
                    content = result.content
                    model = getattr(result, "model", None) or model
                    input_tokens = int(getattr(result, "input_tokens", 0) or 0)
                    output_tokens = int(getattr(result, "output_tokens", 0) or 0)
                    latency_ms = float(getattr(result, "latency_ms", 0) or 0)
                    completion_meta = {
                        "finish_reason": getattr(result, "finish_reason", ""),
                        "reasoning_content": getattr(result, "reasoning_content", ""),
                        "tool_calls": list(getattr(result, "tool_calls", ()) or ()),
                    }
                input_rate = float(_env(f"AI_COST_{provider_name.upper()}_INPUT_PER_MILLION", "0") or 0)
                output_rate = float(_env(f"AI_COST_{provider_name.upper()}_OUTPUT_PER_MILLION", "0") or 0)
                return content, {
                    "provider": provider_name,
                    "model": model,
                    "selected_provider": provider_name,
                    "selected_model": model,
                    "logical_alias": alias.value,
                    "requested_tier": requested_tier,
                    "route_reason": capability.route_reason,
                    "requested_provider": requested,
                    "fallback": index > 0,
                    "fallback_used": index > 0,
                    "fallback_from": candidates[0].provider if index > 0 else None,
                    "fallback_reason": fallback_reason,
                    "fallback_count": index,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "latency_ms": latency_ms,
                    "estimated_cost": round((input_tokens * input_rate + output_tokens * output_rate) / 1_000_000, 8),
                    "currency": _env("AI_COST_CURRENCY", "CNY") or "CNY",
                    **completion_meta,
                }
            except ProviderRequestError as exc:
                last_provider_error = exc
                errors.append({"provider": provider_name, "error": sanitize_error(exc.reason)})
                if explicit or not exc.retryable or index >= len(candidates) - 1:
                    break
                fallback_reason = exc.reason
                continue
            except Exception as exc:
                errors.append({"provider": provider_name, "error": sanitize_error(exc)})
                break
        if last_provider_error is not None:
            code, status_code = provider_error_semantics(last_provider_error)
            raise LLMRouteError(
                code, "; ".join(f"{item['provider']}: {item['error']}" for item in errors),
                status_code=status_code, retryable=last_provider_error.retryable,
                provider=last_provider_error.provider,
            ) from last_provider_error
        raise LLMRouteError(
            "PROVIDER_UNAVAILABLE", "; ".join(f"{item['provider']}: {item['error']}" for item in errors),
            status_code=503, retryable=False, provider=primary.provider,
        )

    def health(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "router_mode": self.mode,
            "default_provider": self.default_provider,
            "providers": {},
        }
        for name in self.KNOWN_PROVIDERS:
            try:
                status = self._get_provider(name).health()
            except Exception as exc:
                status = {"available": False, "provider": name, "reason": sanitize_error(exc)}
            result["providers"][name] = status
            result[name] = status
        return result
