from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
FilterOperator = Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "contains"]
TimeGrain = Literal["hour", "day", "week", "month"]
Comparison = Literal["previous_period", "yoy", "mom"]
ChartIntent = Literal["line", "bar", "table", "pie"]
AnalysisMode = Literal["aggregate", "ranking", "contribution"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class AnalysisFilter(ContractModel):
    dimension: str
    operator: FilterOperator = "eq"
    value: str | int | float | bool | list[str | int | float | bool]

    @field_validator("dimension")
    @classmethod
    def valid_dimension(cls, value: str) -> str:
        if not IDENTIFIER_RE.fullmatch(value):
            raise ValueError("invalid dimension identifier")
        return value


class AnalysisTimeRange(ContractModel):
    start: str
    end: str

    @model_validator(mode="after")
    def valid_range(self) -> "AnalysisTimeRange":
        try:
            start = datetime.fromisoformat(self.start.replace("Z", "+00:00"))
            end = datetime.fromisoformat(self.end.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("time range must use ISO-8601") from exc
        if (start.tzinfo is None) != (end.tzinfo is None):
            raise ValueError("time range timezone must be consistent")
        if start > end:
            raise ValueError("time range start must not exceed end")
        return self


class AnalysisOrder(ContractModel):
    field: str
    direction: Literal["asc", "desc"] = "desc"

    @field_validator("field")
    @classmethod
    def valid_field(cls, value: str) -> str:
        if not IDENTIFIER_RE.fullmatch(value):
            raise ValueError("invalid order field identifier")
        return value


class AnalysisPlan(ContractModel):
    analysis_plan_id: str = Field(default_factory=lambda: f"plan_{uuid4().hex}")
    datasets: list[str] = Field(default_factory=list, max_length=4)
    metrics: list[str] = Field(default_factory=list, max_length=8)
    dimensions: list[str] = Field(default_factory=list, max_length=8)
    filters: list[AnalysisFilter] = Field(default_factory=list, max_length=16)
    time_range: AnalysisTimeRange | None = None
    time_grain: TimeGrain | None = None
    comparison: Comparison | None = None
    group_by: list[str] = Field(default_factory=list, max_length=8)
    order_by: list[AnalysisOrder] = Field(default_factory=list, max_length=4)
    limit: int = Field(default=100, ge=1, le=500)
    joins: list[str] = Field(default_factory=list, max_length=3)
    drill_level: str | None = None
    chart_intent: ChartIntent = "table"
    analysis_mode: AnalysisMode = "aggregate"
    clarification_required: bool = False
    clarification_question: str | None = Field(default=None, max_length=300)

    @field_validator("datasets", "metrics", "dimensions", "group_by", "joins")
    @classmethod
    def unique_identifiers(cls, values: list[str]) -> list[str]:
        if any(not IDENTIFIER_RE.fullmatch(value) for value in values):
            raise ValueError("invalid catalog identifier")
        if len(values) != len(set(values)):
            raise ValueError("duplicate catalog identifier")
        return values

    @field_validator("analysis_plan_id", "drill_level")
    @classmethod
    def valid_optional_identifier(cls, value: str | None) -> str | None:
        if value is not None and not IDENTIFIER_RE.fullmatch(value):
            raise ValueError("invalid plan identifier")
        return value

    @model_validator(mode="after")
    def clarification_contract(self) -> "AnalysisPlan":
        if self.clarification_required and not self.clarification_question:
            raise ValueError("clarification question is required")
        return self

    def stable_hash(self) -> str:
        payload: dict[str, Any] = self.model_dump(mode="json", exclude={"analysis_plan_id"})
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
