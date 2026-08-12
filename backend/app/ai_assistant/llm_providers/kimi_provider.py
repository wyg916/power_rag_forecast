from __future__ import annotations

import os
from typing import Any, Iterator

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
            model="kimi-k2.6",
            timeout_seconds=int(os.environ.get("KIMI_TIMEOUT", os.environ.get("LLM_TIMEOUT", "120"))),
        )

    @staticmethod
    def _k2_options(options: dict[str, Any]) -> dict[str, Any]:
        # Kimi K2.6 only accepts temperature=0.6 when thinking is disabled.
        # The assistant runtime uses this stable non-thinking mode so callers can
        # keep their provider-neutral temperature contract.
        normalized = dict(options)
        normalized["temperature"] = 0.6
        normalized["thinking"] = {"type": "disabled"}
        return normalized

    def complete(self, messages: list[dict[str, str]], **options: Any):
        return super().complete(messages, **self._k2_options(options))

    def chat_stream(self, messages: list[dict[str, str]], **options: Any) -> Iterator[str]:
        return super().chat_stream(messages, **self._k2_options(options))
