from __future__ import annotations

from typing import Any

import requests

from .config import ModelGatewayConfig, load_model_gateway_config


class OpenAICompatibleClient:
    def __init__(self, config: ModelGatewayConfig | None = None):
        self.config = config or load_model_gateway_config()

    def chat(self, messages: list[dict[str, str]], **options: Any) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        payload = {
            "model": options.pop("model", self.config.model),
            "messages": messages,
            "temperature": options.pop("temperature", 0.2),
            **options,
        }
        response = requests.post(
            f"{self.config.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
