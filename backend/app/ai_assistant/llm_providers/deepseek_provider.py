from __future__ import annotations

import os

from config_loader import load_dotenv

from .openai_compatible import OpenAICompatibleProvider


class DeepSeekProvider(OpenAICompatibleProvider):
    name = "deepseek"
    display_name = "DeepSeek V4-Flash"

    def __init__(self) -> None:
        load_dotenv()
        model = os.environ.get("DEEPSEEK_MODEL", os.environ.get("DEEPSEEK_DEFAULT_MODEL", "deepseek-v4-flash"))
        super().__init__(
            api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            model=model,
            timeout_seconds=int(os.environ.get("DEEPSEEK_TIMEOUT", os.environ.get("LLM_TIMEOUT", "120"))),
        )
        self.reasoning_model = os.environ.get("DEEPSEEK_REASONING_MODEL", model)
