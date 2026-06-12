from __future__ import annotations

import os
from dataclasses import dataclass

from config_loader import load_dotenv


def _bool_env(name: str, default: bool = False) -> bool:
    load_dotenv()
    value = str(os.environ.get(name, str(int(default)))).strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


@dataclass(frozen=True)
class AIPhaseOneConfig:
    dify_enabled: bool
    dify_base_url: str
    dify_api_key: str
    dify_user: str
    local_llm_base_url: str
    local_llm_model: str


def load_ai_phase_one_config() -> AIPhaseOneConfig:
    load_dotenv()
    return AIPhaseOneConfig(
        dify_enabled=_bool_env("DIFY_ENABLED", False),
        dify_base_url=os.environ.get("DIFY_BASE_URL", "http://localhost:8080").rstrip("/"),
        dify_api_key=os.environ.get("DIFY_API_KEY", ""),
        dify_user=os.environ.get("DIFY_USER", "web_user"),
        local_llm_base_url=os.environ.get("LOCAL_LLM_BASE_URL", os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")).rstrip("/"),
        local_llm_model=os.environ.get("LOCAL_LLM_MODEL", os.environ.get("LLM_MODEL", "qwen3:4b")),
    )
