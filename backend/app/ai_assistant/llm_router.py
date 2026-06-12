from __future__ import annotations

import os
import re
from typing import Any

from config_loader import load_dotenv

from .llm_providers import DeepSeekProvider, OllamaProvider


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
    def __init__(self) -> None:
        self.default_provider = _env("LLM_PROVIDER", _env("MODEL_PROVIDER", "ollama")).lower() or "ollama"
        self.mode = _env("LLM_ROUTER_MODE", "auto").lower() or "auto"
        self._deepseek: DeepSeekProvider | None = None
        self._ollama: OllamaProvider | None = None

    def _get_deepseek(self) -> DeepSeekProvider:
        if self._deepseek is None:
            self._deepseek = DeepSeekProvider()
        return self._deepseek

    def _get_ollama(self) -> OllamaProvider:
        if self._ollama is None:
            self._ollama = OllamaProvider()
        return self._ollama

    def _deepseek_available(self) -> bool:
        try:
            return bool(self._get_deepseek().available)
        except Exception:
            return False

    def _ollama_available(self) -> bool:
        try:
            return bool(self._get_ollama().health().get("available"))
        except Exception:
            return False

    def _select_provider(self, *, task_type: str, requested_provider: str = "auto") -> str:
        requested = (requested_provider or "auto").strip().lower()
        if requested in {"deepseek", "ollama"}:
            return requested
        if self.mode == "local":
            return "ollama"
        if task_type in {"complex_analysis", "strategy_advice", "model_diagnosis", "report"}:
            return "deepseek" if self._deepseek_available() else "ollama"
        if task_type in {"daily_chat", "simple_data_answer"}:
            return "ollama" if self._ollama_available() else "deepseek"
        if self.default_provider == "deepseek" and self._deepseek_available():
            return "deepseek"
        return "ollama"

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
        errors: list[dict[str, str]] = []
        for provider_name in [preferred, "ollama" if preferred != "ollama" else "deepseek"]:
            try:
                if provider_name == "deepseek":
                    provider = self._get_deepseek()
                    model = provider.reasoning_model if task_type in {"complex_analysis", "model_diagnosis"} else provider.default_model
                    content = provider.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)
                    return content, {"provider": "deepseek", "model": model, "fallback": provider_name != preferred}
                if provider_name == "ollama":
                    provider = self._get_ollama()
                    content = provider.chat(messages, temperature=temperature, max_tokens=max_tokens)
                    status = provider.health()
                    model = getattr(provider, "last_model", None) or status.get("model")
                    return content, {"provider": "ollama", "model": model, "fallback": provider_name != preferred}
            except Exception as exc:
                errors.append({"provider": provider_name, "error": sanitize_error(exc)})
                continue
        raise RuntimeError("; ".join(f"{item['provider']}: {item['error']}" for item in errors))

    def health(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "router_mode": self.mode,
            "default_provider": self.default_provider,
            "deepseek": {"available": False},
            "ollama": {"available": False},
        }
        try:
            result["deepseek"] = self._get_deepseek().health()
        except Exception as exc:
            result["deepseek"] = {"available": False, "provider": "deepseek", "error": sanitize_error(exc)}
        try:
            result["ollama"] = self._get_ollama().health()
        except Exception as exc:
            result["ollama"] = {"available": False, "provider": "ollama", "error": sanitize_error(exc)}
        return result
