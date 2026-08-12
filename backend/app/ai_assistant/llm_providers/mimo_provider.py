from __future__ import annotations

import os

from config_loader import load_dotenv

from .openai_compatible import OpenAICompatibleProvider


class MiMoProvider(OpenAICompatibleProvider):
    name = "mimo"
    display_name = "MiMo V2.5"

    def __init__(self) -> None:
        load_dotenv()
        super().__init__(
            api_key=os.environ.get("MIMO_API_KEY", ""),
            base_url=os.environ.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1"),
            model="mimo-v2.5",
            timeout_seconds=int(os.environ.get("MIMO_TIMEOUT", os.environ.get("LLM_TIMEOUT", "120"))),
        )
