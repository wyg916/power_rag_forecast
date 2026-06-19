from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TaskRunRequest(BaseModel):
    kind: Literal[
        "today_analysis",
        "refresh_data",
        "sync_core_data",
        "fast_forecast",
        "report_only",
        "health_check",
        "retrain_model",
        "model_auto_optimize",
        "knowledge_import",
        "embedding_refresh",
        "report_generate",
        "data_sync",
        "forecast_run",
    ] = "today_analysis"
    payload: dict | None = None
    idempotency_key: str | None = Field(default=None, max_length=256)
    dedupe_window_seconds: int | None = Field(default=None, ge=0, le=86400)


class TaskCreateRequest(TaskRunRequest):
    created_by: str = Field(default="web_user", max_length=128)


class ForecastRunRequest(BaseModel):
    mode: Literal["fast_forecast", "refresh_fast_forecast", "retrain_model"] = "refresh_fast_forecast"


class ChatRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    question: str = Field(..., min_length=1, max_length=1000)
    session_id: str | None = None
    run_id: str = "latest"
    market: str | None = Field(default=None, max_length=64)
    date: str | None = Field(default=None, max_length=32)
    page_context: dict | None = None
    scenario: str = Field(default="power_trading", max_length=64)
    user_role: str = Field(default="trader", max_length=64)
    answer_style: str = Field(default="professional_brief", max_length=64)
    model_provider: str = Field(default="auto", max_length=64)
    debug: bool = False


class AgentAnalyzeRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    question: str = Field(..., min_length=1, max_length=1000)
    session_id: str | None = None
    run_id: str = "latest"
    market: str | None = Field(default=None, max_length=64)
    date: str | None = Field(default=None, max_length=32)
    page_context: dict | None = None
    scenario: str = Field(default="power_trading", max_length=64)
    user_role: str = Field(default="trader", max_length=64)
    answer_style: str = Field(default="professional_brief", max_length=64)
    model_provider: str = Field(default="auto", max_length=64)
    debug: bool = False


class ChatFeedbackRequest(BaseModel):
    session_id: str | None = None
    trace_id: str | None = None
    rating: str = Field(..., pattern="^(up|down)$")
    comment: str = Field(default="", max_length=1000)


class AnswerFeedbackRequest(BaseModel):
    session_id: str | None = None
    trace_id: str | None = None
    question: str = Field(default="", max_length=2000)
    answer: str = Field(default="", max_length=10000)
    feedback_type: Literal["accurate", "answer_mismatch", "wrong_data", "unclear_explanation"] = "answer_mismatch"
    feedback_comment: str = Field(default="", max_length=2000)


class ReadOnlySqlRequest(BaseModel):
    sql: str = Field(..., min_length=1, max_length=5000)
    params: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    limit: int = Field(default=100, ge=1, le=500)


class ReviewRequest(BaseModel):
    reviewer: str = Field(default="web_user", max_length=64)
    review_comment: str = Field(default="", max_length=2000)


class ReportGenerateRequest(BaseModel):
    run_id: str = "latest"


class ScheduledTaskCreateRequest(BaseModel):
    name: str = Field(default="PowerMarket_WebDaily", min_length=1, max_length=128)
    mode: Literal[
        "fast_forecast",
        "refresh_fast_forecast",
        "retrain_model",
        "model_auto_optimize",
        "full",
        "refresh_data",
        "skip_prediction",
        "prediction_report_only",
        "model_ops_daily",
        "health_check",
        "smoke_test",
        "web_smoke_test",
    ] = "refresh_fast_forecast"
    run_time: str = Field(default="06:30", pattern=r"^\d{2}:\d{2}$")
    highest: bool = False


class UserListItem(BaseModel):
    id: int | str | None = None
    user_id: str
    username: str
    email: str = ""
    display_name: str = ""
    role: str
    is_active: bool = True
    is_superuser: bool = False
    last_login_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: str = Field(default="", max_length=255)
    display_name: str = Field(default="", max_length=128)
    password: str = Field(..., min_length=8, max_length=256)
    role: Literal["admin", "analyst", "viewer", "developer", "operator"] = "viewer"
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    display_name: str | None = Field(default=None, max_length=128)
    role: Literal["admin", "analyst", "viewer", "developer", "operator"] | None = None
    is_active: bool | None = None


class UserResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=256)
