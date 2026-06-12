from __future__ import annotations

import os
from dataclasses import dataclass

from config_loader import load_dotenv


@dataclass(frozen=True)
class ModelGatewayConfig:
    base_url: str
    model: str
    api_key: str
    timeout_seconds: int


def load_model_gateway_config() -> ModelGatewayConfig:
    load_dotenv()
    return ModelGatewayConfig(
        base_url=os.environ.get("LOCAL_LLM_BASE_URL", os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")).rstrip("/"),
        model=os.environ.get("LOCAL_LLM_MODEL", os.environ.get("LLM_MODEL", "qwen3:4b")),
        api_key=os.environ.get("LOCAL_LLM_API_KEY", os.environ.get("LLM_API_KEY", "")),
        timeout_seconds=int(os.environ.get("LOCAL_LLM_TIMEOUT", os.environ.get("LLM_TIMEOUT", "120"))),
    )
