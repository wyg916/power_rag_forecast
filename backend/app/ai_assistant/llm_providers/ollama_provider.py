from __future__ import annotations

import os
from typing import Any

import requests

from ..core.llm_client import get_local_llm_status


class OllamaProvider:
    name = "ollama"

    def __init__(self) -> None:
        self.last_model: str | None = None

    def health(self) -> dict[str, Any]:
        status = get_local_llm_status()
        return {
            "available": bool(status.get("available")),
            "provider": self.name,
            "base_url": status.get("root_url") or status.get("base_url"),
            "model": status.get("selected_model"),
            "models": status.get("models") or [],
        }

    def _candidate_models(self, status: dict[str, Any], requested_model: str | None) -> list[str]:
        candidates: list[str] = []
        for value in [
            requested_model,
            os.environ.get("OLLAMA_MODEL"),
            os.environ.get("LOCAL_LLM_MODEL"),
            status.get("selected_model"),
        ]:
            if value and str(value).strip() not in candidates:
                candidates.append(str(value).strip())
        fallback_values = ",".join(
            [
                os.environ.get("OLLAMA_FALLBACK_MODELS", ""),
                os.environ.get("LOCAL_LLM_FALLBACK_MODELS", ""),
            ]
        )
        for value in fallback_values.replace(";", ",").split(","):
            model_name = value.strip()
            if model_name and model_name not in candidates:
                candidates.append(model_name)
        return candidates

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.25,
        max_tokens: int = 900,
        stream: bool = False,
        **_: Any,
    ) -> str:
        status = get_local_llm_status()
        root_url = str(status["root_url"]).rstrip("/")
        timeout = int(os.environ.get("LOCAL_LLM_TIMEOUT", os.environ.get("LLM_TIMEOUT", "120")))
        errors: list[str] = []
        for candidate_model in self._candidate_models(status, model):
            try:
                response = requests.post(
                    f"{root_url}/api/chat",
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": candidate_model,
                        "messages": messages,
                        "stream": stream,
                        "think": False,
                        "options": {
                            "temperature": temperature,
                            "num_predict": max_tokens,
                        },
                    },
                    timeout=timeout,
                )
                response.raise_for_status()
                content = str((response.json().get("message") or {}).get("content") or "").strip()
                if not content:
                    raise RuntimeError("Ollama returned empty content")
                self.last_model = candidate_model
                return content
            except Exception as exc:
                errors.append(f"{candidate_model}: {exc}")
        raise RuntimeError("Ollama chat failed; " + "; ".join(errors))
