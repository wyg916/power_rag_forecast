from __future__ import annotations

import os
from typing import Any

import requests

from config_loader import load_dotenv


def _env(name: str, default: str = "") -> str:
    load_dotenv()
    return os.environ.get(name, default).strip()


class DeepSeekProvider:
    name = "deepseek"

    def __init__(self) -> None:
        self.api_key = _env("DEEPSEEK_API_KEY")
        self.base_url = _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
        self.default_model = _env("DEEPSEEK_MODEL", _env("DEEPSEEK_DEFAULT_MODEL", "deepseek-chat"))
        self.reasoning_model = _env("DEEPSEEK_REASONING_MODEL", "deepseek-reasoner")
        self.timeout_seconds = int(_env("DEEPSEEK_TIMEOUT", _env("LLM_TIMEOUT", "120")) or "120")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")
        return {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}

    def _chat_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _models_url(self) -> str:
        return f"{self.base_url}/models"

    def health(self) -> dict[str, Any]:
        if not self.api_key:
            return {"available": False, "provider": self.name, "reason": "missing_api_key"}
        response = requests.get(self._models_url(), headers=self._headers(), timeout=min(self.timeout_seconds, 20))
        response.raise_for_status()
        models = response.json().get("data") or []
        return {
            "available": True,
            "provider": self.name,
            "base_url": self.base_url,
            "model": self.default_model,
            "reasoning_model": self.reasoning_model,
            "models": [str(item.get("id") or item.get("model") or "") for item in models if item.get("id") or item.get("model")],
        }

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.35,
        max_tokens: int = 1400,
        stream: bool = False,
        **options: Any,
    ) -> str:
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            **options,
        }
        response = requests.post(
            self._chat_url(),
            headers=self._headers(),
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        content = str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        if not content:
            raise RuntimeError("DeepSeek returned empty content")
        return content
