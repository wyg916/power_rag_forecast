from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.app.ai_assistant.llm_router import LLMRouter, sanitize_error
from backend.app.core.security import CurrentUser, require_permission


router = APIRouter(prefix="/api/model-gateway", tags=["model-gateway"])


class GatewayChatRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    messages: list[dict[str, str]] = Field(default_factory=list)
    model: str | None = None
    model_provider: str = "auto"
    temperature: float = 0.2
    max_tokens: int = 1200


@router.get("/health")
def gateway_health(_: Annotated[CurrentUser, Depends(require_permission("model:read"))]) -> dict:
    return {"ok": True, **LLMRouter().health()}


@router.post("/chat/completions")
def gateway_chat(
    payload: GatewayChatRequest,
    _: Annotated[CurrentUser, Depends(require_permission("assistant:use"))],
) -> dict:
    if not payload.messages:
        raise HTTPException(status_code=400, detail="messages 不能为空")
    try:
        content, status = LLMRouter().generate_answer(
            payload.messages,
            task_type="general",
            requested_provider=payload.model_provider,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
        )
        return {
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "provider": status.get("provider"),
            "model": status.get("model"),
            "fallback": status.get("fallback", False),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"模型网关调用失败：{sanitize_error(exc)}") from exc
