from __future__ import annotations

import os

from config_loader import load_dotenv

from .openai_compatible import OpenAICompatibleProvider


class KimiProvider(OpenAICompatibleProvider):
    name = "kimi"
    display_name = "Kimi K2.6"

    def __init__(self) -> None:
        load_dotenv()
        super().__init__(
            api_key=os.environ.get("KIMI_API_KEY", ""),
            base_url=os.environ.get("KIMI_BASE_URL", "https://api.moonshot.cn/v1"),
            model=os.environ.get("KIMI_MODEL", "kimi-k2.6"),
            timeout_seconds=int(os.environ.get("KIMI_TIMEOUT", os.environ.get("LLM_TIMEOUT", "120"))),
        )
