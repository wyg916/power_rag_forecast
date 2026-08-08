from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.auth.password import validate_password_length


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
        "data_clean",
        "price_predict",
        "load_predict",
        "strategy_gen",
        "report_daily",
        "monitor_rt",
        "model_train",
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
    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

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
    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

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
    model_config = ConfigDict(extra="forbid")

    session_id: str | None = None
    trace_id: str | None = None
    rating: str = Field(..., pattern="^(up|down)$")
    comment: str = Field(default="", max_length=1000)
    idempotency_key: str = Field(default="", max_length=160)


class AnswerFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str | None = None
    trace_id: str | None = None
    question: str = Field(default="", max_length=2000)
    answer: str = Field(default="", max_length=10000)
    feedback_type: Literal["accurate", "answer_mismatch", "wrong_data", "unclear_explanation"] = "answer_mismatch"
    feedback_comment: str = Field(default="", max_length=2000)
    idempotency_key: str = Field(default="", max_length=160)


class DataStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    sources: list[dict[str, Any]] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class DataCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    available: bool
    catalog_version: str
    datasets: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0
    meta: dict[str, Any] = Field(default_factory=dict)


class DataFreshnessResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    available: bool
    catalog_version: str
    checked_at: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class DatasetListResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    available: bool
    catalog_version: str
    datasets: list[dict[str, Any]] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class DatasetColumn(BaseModel):
    field_id: str
    display_name: str
    data_type: str
    description: str = ""
    sortable: bool = False
    filterable: bool = False
    searchable: bool = False


class DatasetRowsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    available: bool
    dataset_id: str
    display_name: str
    object_type: str = ""
    columns: list[DatasetColumn] = Field(default_factory=list)
    records: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0
    limit: int
    offset: int
    pagination: dict[str, int]
    search_applied: bool = False
    filter: dict[str, Any] = Field(default_factory=dict)
    order_by: str = ""
    order_direction: str = "desc"
    message: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)


class DataQualityItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    dataset_id: str
    source_name: str | None = None
    available: bool
    status: str
    rows: int | None = None
    missing_values: int | None = None
    missing_rate: float | None = None
    duplicate_rate: float | None = None
    freshness_score: float | None = None
    freshness_age_hours: float | None = None
    consistency_score: float | None = None
    check_pass_rate: float | None = None
    latest_time: Any = None
    message: str = ""
    data_source: str
    is_stale: bool = False
    stale_reason: str | None = None


class DataQualityAlert(BaseModel):
    model_config = ConfigDict(extra="allow")

    alert_id: str
    severity: str
    alert_type: str
    object_name: str
    detected_at: str
    status: str
    source: str
    message: str


class DataQualityResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    available: bool
    generated_at: str
    is_stale: bool = False
    stale_reason: str | None = None
    summary: dict[str, int | float | None] = Field(default_factory=dict)
    items: list[DataQualityItem] = Field(default_factory=list)
    exceptions: list[DataQualityItem] = Field(default_factory=list)
    alerts: list[DataQualityAlert] = Field(default_factory=list)
    data_source: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class DataSyncRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    record_id: str
    run_id: str | None = None
    type: str
    name: str
    task_kind: str
    status: str
    processed_rows: int | None = None
    success_rows: int | None = None
    failed_rows: int | None = None
    created_at: Any = None
    started_at: Any = None
    ended_at: Any = None
    duration_seconds: float | None = None
    error_code: str = ""
    error_message: str = ""
    status_reason: str | None = None
    data_source: str


class DataSyncRecordsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    available: bool
    generated_at: str
    records: list[DataSyncRecord] = Field(default_factory=list)
    pagination: dict[str, int]
    summary: dict[str, Any] = Field(default_factory=dict)
    data_source: str
    meta: dict[str, Any] = Field(default_factory=dict)


class ReviewRequest(BaseModel):
    reviewer: str = Field(default="web_user", max_length=64)
    review_comment: str = Field(default="", max_length=2000)


class ReportGenerateRequest(BaseModel):
    run_id: str = Field(default="latest", min_length=1, max_length=128)
    report_type: Literal["daily", "weekly", "operation_decision"] = "daily"
    region: str = Field(default="模型覆盖市场", min_length=1, max_length=128)
    report_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


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
    role: Literal["admin", "analyst", "reviewer", "viewer", "developer", "operator"] = "viewer"
    is_active: bool = True

    @field_validator("password")
    @classmethod
    def _validate_password_length(cls, value: str) -> str:
        return validate_password_length(value)


class UserUpdateRequest(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    display_name: str | None = Field(default=None, max_length=128)
    role: Literal["admin", "analyst", "reviewer", "viewer", "developer", "operator"] | None = None
    is_active: bool | None = None


class UserResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=256)

    @field_validator("new_password")
    @classmethod
    def _validate_new_password_length(cls, value: str) -> str:
        return validate_password_length(value)


class StrategyGenerateRequest(BaseModel):
    run_id: str = Field(..., min_length=8, max_length=96)
    report_id: str = Field(..., min_length=8, max_length=96)


class StrategyActionRequest(BaseModel):
    request_id: str = Field(..., min_length=8, max_length=96)
    review_comment: str = Field(default="", max_length=2000)
