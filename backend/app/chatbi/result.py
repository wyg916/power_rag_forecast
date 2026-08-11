from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Literal

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app.db.session import get_engine
from backend.app.ai.identity_context import IdentityContext

from .catalog import DIMENSION_CATALOG, METRIC_CATALOG
from .compiler import QUERY_TIMEOUT_MS, CompiledQuery
from .contracts import AnalysisPlan


ResultState = Literal["success", "empty", "insufficient_data"]


class ResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ResultColumn(ResultModel):
    field: str
    business_name: str
    data_type: str
    unit: str = ""


class ResultDataset(ResultModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    schema_: list[ResultColumn] = Field(serialization_alias="schema")
    units: dict[str, str]
    query_hash: str
    result_hash: str
    analysis_plan_id: str
    executed_at: str
    state: ResultState
    row_count: int
    identity_scope_hash: str


class ChartSpec(ResultModel):
    chart_type: Literal["line", "bar", "table", "pie"]
    title: str
    x: str | None
    y: list[str]
    series: str | None
    unit: str
    legend: bool
    sort: list[dict[str, str]]
    data_hash: str
    analysis_plan_id: str
    identity_scope_hash: str


class NarrativeClaim(ResultModel):
    text: str
    field: str | None = None
    value: Any = None
    row_index: int | None = None
    result_hash: str


class GroundedNarrative(ResultModel):
    text: str
    state: ResultState
    claims: list[NarrativeClaim]
    result_hash: str
    analysis_plan_id: str
    identity_scope_hash: str
    causal_explanation: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)


class QueryExecutionError(RuntimeError):
    pass


def _column(field: str) -> ResultColumn:
    if field in DIMENSION_CATALOG:
        item = DIMENSION_CATALOG[field]
        return ResultColumn(field=field, business_name=item.business_name, data_type=item.data_type)
    metric_id = field.split("__", 1)[0]
    metric = METRIC_CATALOG[metric_id]
    suffix = field.removeprefix(metric_id)
    if suffix in {"__delta_pct", "__contribution_pct"}:
        unit, data_type = "%", "number"
    else:
        unit, data_type = metric.unit, "number"
    labels = {
        "": metric.business_name,
        "__comparison": f"对比期{metric.business_name}",
        "__delta": f"{metric.business_name}变化量",
        "__delta_pct": f"{metric.business_name}变化率",
        "__contribution_pct": f"{metric.business_name}贡献率",
    }
    return ResultColumn(field=field, business_name=labels[suffix], data_type=data_type, unit=unit)


def _state(plan: AnalysisPlan, rows: list[dict[str, Any]]) -> ResultState:
    if not rows:
        return "empty"
    if plan.comparison:
        current_fields = list(plan.metrics)
        comparison_fields = [f"{item}__comparison" for item in plan.metrics]
        current_missing = all(row.get(field) is None for row in rows for field in current_fields)
        comparison_missing = all(row.get(field) is None for row in rows for field in comparison_fields)
        if current_missing or comparison_missing:
            return "insufficient_data"
    return "success"


def _result_hash(columns: list[str], rows: list[dict[str, Any]], query_hash: str) -> str:
    payload = {"columns": columns, "query_hash": query_hash, "rows": rows}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def execute_result_dataset(
    plan: AnalysisPlan,
    compiled: CompiledQuery,
    *,
    identity: IdentityContext,
    engine: Engine | None = None,
) -> ResultDataset:
    if compiled.analysis_plan_id != plan.analysis_plan_id or compiled.plan_hash != plan.stable_hash():
        raise QueryExecutionError("AnalysisPlan 与 CompiledQuery 身份不一致。")
    if compiled.timeout_ms != QUERY_TIMEOUT_MS:
        raise QueryExecutionError("CompiledQuery 资源上限不符合服务端策略。")
    active_engine = engine or get_engine()
    try:
        with active_engine.connect() as connection:
            transaction = connection.begin()
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.exec_driver_sql("SET LOCAL statement_timeout = '5000ms'")
            raw_rows = connection.execute(compiled.statement, compiled.parameters).mappings().all()
            transaction.rollback()
    except Exception as exc:
        raise QueryExecutionError("ChatBI 只读查询执行失败。") from exc
    rows = jsonable_encoder([dict(row) for row in raw_rows])
    columns = list(compiled.fields)
    schema = [_column(field) for field in columns]
    units = {item.field: item.unit for item in schema if item.unit}
    identity.require_valid(require_session=True)
    scope_raw = "|".join((identity.tenant_id, identity.workspace_id, identity.user_id, identity.agent_id, identity.session_id, identity.run_id))
    scope_hash = hashlib.sha256(scope_raw.encode("utf-8")).hexdigest()
    result_hash = _result_hash(columns, rows, compiled.query_hash)
    return ResultDataset(
        columns=columns,
        rows=rows,
        schema_=schema,
        units=units,
        query_hash=compiled.query_hash,
        result_hash=result_hash,
        analysis_plan_id=plan.analysis_plan_id,
        executed_at=datetime.now(timezone.utc).isoformat(),
        state=_state(plan, rows),
        row_count=len(rows),
        identity_scope_hash=scope_hash,
    )


def build_chart_spec(plan: AnalysisPlan, result: ResultDataset) -> ChartSpec:
    if result.analysis_plan_id != plan.analysis_plan_id:
        raise ValueError("ChartSpec 与 AnalysisPlan 身份不一致。")
    x = plan.group_by[0] if plan.group_by else None
    y = [field for field in result.columns if field not in plan.group_by]
    series = plan.group_by[1] if len(plan.group_by) > 1 else None
    metric = METRIC_CATALOG[plan.metrics[0]]
    title = f"{metric.business_name}{'对比' if plan.comparison else '分析'}"
    return ChartSpec(
        chart_type=plan.chart_intent,
        title=title,
        x=x,
        y=y,
        series=series,
        unit=metric.unit,
        legend=bool(series or len(y) > 1),
        sort=[item.model_dump() for item in plan.order_by],
        data_hash=result.result_hash,
        analysis_plan_id=plan.analysis_plan_id,
        identity_scope_hash=result.identity_scope_hash,
    )


def _display(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def build_grounded_narrative(plan: AnalysisPlan, result: ResultDataset) -> GroundedNarrative:
    base = {
        "state": result.state,
        "result_hash": result.result_hash,
        "analysis_plan_id": result.analysis_plan_id,
        "identity_scope_hash": result.identity_scope_hash,
    }
    if result.state == "empty":
        return GroundedNarrative(text="所选条件下没有可用于分析的数据。", claims=[], **base)
    if result.state == "insufficient_data":
        return GroundedNarrative(text="当前区间存在数据，但对比区间数据不足，无法形成可靠比较结论。", claims=[], **base)
    metric_id = plan.metrics[0]
    numeric = [(index, row.get(metric_id)) for index, row in enumerate(result.rows) if isinstance(row.get(metric_id), (int, float))]
    claims = [
        NarrativeClaim(
            text=f"查询返回 {result.row_count} 组可复算结果。",
            field=None,
            value=result.row_count,
            row_index=None,
            result_hash=result.result_hash,
        )
    ]
    text_value = claims[0].text
    if numeric:
        index, value = max(numeric, key=lambda item: item[1])
        dimension_text = ""
        if plan.group_by:
            dimension_text = f"，对应{DIMENSION_CATALOG[plan.group_by[0]].business_name}为{result.rows[index].get(plan.group_by[0])}"
        statement = f"{METRIC_CATALOG[metric_id].business_name}最高值为{_display(value)}{METRIC_CATALOG[metric_id].unit}{dimension_text}。"
        claims.append(
            NarrativeClaim(text=statement, field=metric_id, value=value, row_index=index, result_hash=result.result_hash)
        )
        text_value += statement
    return GroundedNarrative(text=text_value, claims=claims, **base)
