from __future__ import annotations

import re
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ....ai.identity_context import IdentityContext
from ....chatbi.contracts import AnalysisPlan
from ....chatbi.service import ChatBIServiceError, execute_chatbi_turn
from ....core.security import CurrentUser, require_permission


router = APIRouter()
_SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class ChatBIAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    session_id: str = Field(min_length=1, max_length=128)
    plan: AnalysisPlan | None = None
    model_provider: Literal["auto", "deepseek", "ollama"] = "auto"

    @field_validator("question", "session_id")
    @classmethod
    def strip_values(cls, value: str) -> str:
        return value.strip()

    @field_validator("session_id")
    @classmethod
    def valid_session(cls, value: str) -> str:
        if not _SESSION_RE.fullmatch(value):
            raise ValueError("invalid session identifier")
        return value


@router.post("/api/ai/chatbi/analyze")
def analyze_chatbi(
    payload: ChatBIAnalysisRequest,
    user: Annotated[CurrentUser, Depends(require_permission("assistant:use"))],
) -> dict:
    identity = IdentityContext.from_user(
        user,
        session_id=payload.session_id,
        run_id=f"run_chatbi_{uuid4().hex}",
        agent_id="chatbi",
    )
    try:
        return execute_chatbi_turn(
            question=payload.question,
            plan=payload.plan,
            identity=identity,
            permissions=user.permissions,
            requested_provider=payload.model_provider,
        )
    except ChatBIServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
