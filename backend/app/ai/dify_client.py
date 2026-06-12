from __future__ import annotations

from typing import Any

import requests

from .ai_config import AIPhaseOneConfig, load_ai_phase_one_config


class DifyUnavailable(RuntimeError):
    pass


class DifyClient:
    def __init__(self, config: AIPhaseOneConfig | None = None):
        self.config = config or load_ai_phase_one_config()

    def enabled(self) -> bool:
        return bool(self.config.dify_enabled and self.config.dify_api_key and self.config.dify_base_url)

    def chat(
        self,
        question: str,
        session_id: str | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.enabled():
            raise DifyUnavailable("Dify 未启用或未配置 DIFY_API_KEY。")
        payload = {
            "inputs": inputs or {},
            "query": question,
            "response_mode": "blocking",
            "user": self.config.dify_user,
        }
        if session_id and session_id.startswith("dify_"):
            payload["conversation_id"] = session_id.replace("dify_", "", 1)
        response = requests.post(
            f"{self.config.dify_base_url}/v1/chat-messages",
            headers={
                "Authorization": f"Bearer {self.config.dify_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        conversation_id = str(data.get("conversation_id") or "")
        return {
            "session_id": f"dify_{conversation_id}" if conversation_id else session_id,
            "answer": data.get("answer") or "",
            "metadata": data.get("metadata") or {},
            "raw": data,
        }
