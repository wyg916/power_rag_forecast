from __future__ import annotations

import os
import re
from typing import Any

from config_loader import load_dotenv

from .llm_providers import (
    DeepSeekProvider,
    KimiProvider,
    MiMoProvider,
    OllamaProvider,
    ProviderRequestError,
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
                return True
            return bool(provider.available)
        except Exception:
            return False

    def _auto_order(self, task_type: str) -> list[str]:
        configured = [item.strip().lower() for item in _env(
            "LLM_AUTO_PROVIDER_ORDER", "deepseek,kimi,mimo,ollama"
        ).replace(";", ",").split(",") if item.strip().lower() in self.KNOWN_PROVIDERS]
        if task_type in {"daily_chat", "simple_data_answer"} and "mimo" in configured:
            configured.insert(0, configured.pop(configured.index("mimo")))
        if self.default_provider in configured and task_type not in {"complex_analysis", "model_diagnosis"}:
            configured.insert(0, configured.pop(configured.index(self.default_provider)))
        return list(dict.fromkeys(configured or list(self.KNOWN_PROVIDERS)))

    def _select_provider(self, *, task_type: str, requested_provider: str = "auto") -> str:
        requested = (requested_provider or "auto").strip().lower()
        if requested in self.KNOWN_PROVIDERS:
            return requested
        if requested != "auto":
            raise ValueError(f"unknown_provider:{requested}")
        if self.mode == "local":
            return "ollama"
        if task_type in {"daily_chat", "simple_data_answer"} and self._configured("ollama"):
            return "ollama"
        return next((name for name in self._auto_order(task_type) if self._configured(name)), "ollama")

    def generate_answer(
        self,
        messages: list[dict[str, str]],
        *,
        task_type: str,
        requested_provider: str = "auto",
        temperature: float = 0.35,
        max_tokens: int = 1200,
    ) -> tuple[str, dict[str, Any]]:
        preferred = self._select_provider(task_type=task_type, requested_provider=requested_provider)
        explicit = (requested_provider or "auto").strip().lower() != "auto"
        candidates = [preferred]
        if not explicit:
            candidates.extend(name for name in self._auto_order(task_type) if name != preferred and self._configured(name))
        errors: list[dict[str, str]] = []
        fallback_reason = ""
        for index, provider_name in enumerate(candidates):
            try:
                provider = self._get_provider(provider_name)
                if provider_name == "ollama":
                    content = provider.chat(messages, temperature=temperature, max_tokens=max_tokens)
                    status = provider.health()
                    model = getattr(provider, "last_model", None) or status.get("model")
                    completion_meta: dict[str, Any] = {}
                else:
                    model = (
                        provider.reasoning_model
                        if provider_name == "deepseek" and task_type in {"complex_analysis", "model_diagnosis"}
                        else provider.default_model
                    )
                    result = provider.complete(messages, model=model, temperature=temperature, max_tokens=max_tokens)
                    content = result.content
                    completion_meta = {
                        "finish_reason": result.finish_reason,
                        "reasoning_content": result.reasoning_content,
                        "tool_calls": list(result.tool_calls),
                    }
                return content, {
                    "provider": provider_name,
                    "model": model,
                    "requested_provider": requested_provider,
                    "fallback": index > 0,
                    "fallback_reason": fallback_reason,
                    **completion_meta,
                }
            except ProviderRequestError as exc:
                errors.append({"provider": provider_name, "error": sanitize_error(exc.reason)})
                if explicit or not exc.retryable:
                    break
                fallback_reason = exc.reason
                continue
            except Exception as exc:
                errors.append({"provider": provider_name, "error": sanitize_error(exc)})
                break
        raise RuntimeError("; ".join(f"{item['provider']}: {item['error']}" for item in errors))

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
