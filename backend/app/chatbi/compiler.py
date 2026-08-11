from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import re
from typing import Any

from sqlalchemy import String, and_, bindparam, case, cast, column, func, literal, select, table
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import ClauseElement

from backend.app.data_registry import DatasetField, get_dataset

from .catalog import DIMENSION_CATALOG, JOIN_CATALOG, METRIC_CATALOG
from .contracts import AnalysisPlan
from .validator import PlanValidation, validate_analysis_plan


QUERY_TIMEOUT_MS = 5000
_TEST_SCHEMA_RE = re.compile(r"^beta10d_(?:day3_close|day5)_[a-z0-9_]+$")


class QueryCompileError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ComparisonRange:
    label: str
    start: datetime
    end: datetime

    def public_dict(self) -> dict[str, str]:
        return {"label": self.label, "start": self.start.isoformat(), "end": self.end.isoformat()}


@dataclass(frozen=True)
class CompiledQuery:
    analysis_plan_id: str
    plan_hash: str
    query_hash: str
    statement: ClauseElement
    parameters: dict[str, Any]
    fields: tuple[str, ...]
    comparison_ranges: tuple[ComparisonRange, ...]
    timeout_ms: int = QUERY_TIMEOUT_MS

    def sql_template(self) -> str:
        return str(self.statement.compile(dialect=postgresql.dialect()))


def _schema() -> str:
    mode = os.environ.get("BETA10D_TEST_DATABASE_MODE", "").strip()
    schema = os.environ.get("BETA10D_TEST_SCHEMA", "").strip()
    if mode == "isolated-schema":
        if not _TEST_SCHEMA_RE.fullmatch(schema):
            raise QueryCompileError("invalid_test_schema", "隔离测试 Schema 未通过白名单验证。")
        return schema
    return "public"


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _shift_year(value: datetime) -> datetime:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value.replace(year=value.year - 1, day=28)


def _shift_month(value: datetime) -> datetime:
    year = value.year if value.month > 1 else value.year - 1
    month = value.month - 1 if value.month > 1 else 12
    day = value.day
    while day > 28:
        try:
            return value.replace(year=year, month=month, day=day)
        except ValueError:
            day -= 1
    return value.replace(year=year, month=month, day=day)


def _comparison_ranges(plan: AnalysisPlan) -> tuple[ComparisonRange, ...]:
    if not plan.time_range:
        return ()
    current_start, current_end = _parse_datetime(plan.time_range.start), _parse_datetime(plan.time_range.end)
    current = ComparisonRange("current", current_start, current_end)
    if not plan.comparison:
        return (current,)
    if plan.comparison == "previous_period":
        previous_end = current_start - timedelta(microseconds=1)
        previous_start = previous_end - (current_end - current_start)
    elif plan.comparison == "yoy":
        previous_start, previous_end = _shift_year(current_start), _shift_year(current_end)
    else:
        previous_start, previous_end = _shift_month(current_start), _shift_month(current_end)
    return (current, ComparisonRange(plan.comparison, previous_start, previous_end))


def _coerce(field: DatasetField, value: Any) -> Any:
    if isinstance(value, str) and (len(value) > 256 or any(ord(char) < 32 for char in value)):
        raise QueryCompileError("invalid_filter_value", "筛选值过长或包含控制字符。")
    try:
        if field.data_type == "integer":
            return int(value)
        if field.data_type == "number":
            return Decimal(str(value))
        if field.data_type == "boolean":
            if isinstance(value, bool):
                return value
            lowered = str(value).lower()
            if lowered in {"1", "true", "yes"}:
                return True
            if lowered in {"0", "false", "no"}:
                return False
            raise ValueError
        if field.data_type == "datetime":
            return _parse_datetime(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise QueryCompileError("invalid_filter_value", "筛选值类型与注册维度不一致。") from exc
    return str(value)


def _source_graph(plan: AnalysisPlan):
    sources = {}
    for dataset_id in plan.datasets:
        spec = get_dataset(dataset_id)
        sources[dataset_id] = table(
            spec.object_name,
            *(column(field.column_name) for field in spec.fields),
            schema=_schema(),
        ).alias(dataset_id)
    joined = {plan.datasets[0]}
    from_clause = sources[plan.datasets[0]]
    pending = list(plan.joins)
    while pending:
        progressed = False
        for join_id in tuple(pending):
            spec = JOIN_CATALOG[join_id]
            endpoints = {spec.left_dataset, spec.right_dataset}
            if len(endpoints & joined) != 1:
                continue
            existing = spec.left_dataset if spec.left_dataset in joined else spec.right_dataset
            target = spec.right_dataset if existing == spec.left_dataset else spec.left_dataset
            clauses = []
            for left_key, right_key in spec.join_keys:
                clauses.append(
                    sources[spec.left_dataset].c[get_dataset(spec.left_dataset).field_map[left_key].column_name]
                    == sources[spec.right_dataset].c[get_dataset(spec.right_dataset).field_map[right_key].column_name]
                )
            from_clause = from_clause.join(sources[target], and_(*clauses), isouter=spec.join_type == "left")
            joined.add(target)
            pending.remove(join_id)
            progressed = True
        if not progressed:
            raise QueryCompileError("join_graph_invalid", "关联图无法从注册关系确定性编译。")
    if joined != set(plan.datasets):
        raise QueryCompileError("join_graph_incomplete", "所选数据集未被白名单关联完整连接。")
    return sources, from_clause


def _dimension_expression(dimension_id: str, sources: dict[str, Any], plan: AnalysisPlan, *, align: timedelta | None = None):
    spec = DIMENSION_CATALOG[dimension_id]
    expression = sources[spec.dataset].c[get_dataset(spec.dataset).field_map[spec.field].column_name]
    if plan.time_grain and spec.data_type == "datetime":
        if align:
            expression = expression + bindparam("comparison_alignment", value=align)
        expression = func.date_trunc(plan.time_grain, expression)
    return expression


def _filter_clauses(plan: AnalysisPlan, sources: dict[str, Any], *, suffix: str) -> tuple[list[Any], dict[str, Any]]:
    clauses, params = [], {}
    for index, item in enumerate(plan.filters):
        dimension = DIMENSION_CATALOG[item.dimension]
        field = get_dataset(dimension.dataset).field_map[dimension.field]
        expression = sources[dimension.dataset].c[field.column_name]
        name = f"filter_{index}_{suffix}"
        if item.operator == "in":
            values = [_coerce(field, value) for value in item.value]
            clauses.append(expression.in_(bindparam(name, expanding=True)))
            params[name] = values
            continue
        value = _coerce(field, item.value)
        if item.operator == "contains":
            value = f"%{value}%"
            clause = cast(expression, String).ilike(bindparam(name))
        else:
            bound = bindparam(name)
            clause = {
                "eq": expression == bound,
                "ne": expression != bound,
                "gt": expression > bound,
                "gte": expression >= bound,
                "lt": expression < bound,
                "lte": expression <= bound,
            }[item.operator]
        clauses.append(clause)
        params[name] = value
    return clauses, params


def _time_clause(plan: AnalysisPlan, sources: dict[str, Any], period: ComparisonRange, suffix: str):
    time_dimensions = [DIMENSION_CATALOG[item] for item in plan.dimensions if DIMENSION_CATALOG[item].data_type == "datetime"]
    if not time_dimensions:
        raise QueryCompileError("time_dimension_required", "时间范围或比较查询必须选择注册时间维度。")
    dimension = time_dimensions[0]
    expression = sources[dimension.dataset].c[get_dataset(dimension.dataset).field_map[dimension.field].column_name]
    start_name, end_name = f"range_start_{suffix}", f"range_end_{suffix}"
    return and_(expression >= bindparam(start_name), expression <= bindparam(end_name)), {
        start_name: period.start,
        end_name: period.end,
    }


def _aggregate_query(plan: AnalysisPlan, period: ComparisonRange, suffix: str, *, align: timedelta | None = None):
    sources, from_clause = _source_graph(plan)
    group_expressions = [_dimension_expression(item, sources, plan, align=align) for item in plan.group_by]
    selected = [expression.label(identifier) for expression, identifier in zip(group_expressions, plan.group_by)]
    for metric_id in plan.metrics:
        metric = METRIC_CATALOG[metric_id]
        source = sources[metric.allowed_datasets[0]]
        value = source.c[get_dataset(metric.allowed_datasets[0]).field_map[metric.value_field].column_name]
        selected.append(func.avg(value).label(metric_id))
    clauses, params = _filter_clauses(plan, sources, suffix=suffix)
    if plan.time_range:
        clause, range_params = _time_clause(plan, sources, period, suffix)
        clauses.append(clause)
        params.update(range_params)
    statement = select(*selected).select_from(from_clause)
    if clauses:
        statement = statement.where(and_(*clauses))
    if group_expressions:
        statement = statement.group_by(*group_expressions)
    return statement, params


def _normal_statement(plan: AnalysisPlan, period: ComparisonRange):
    base, params = _aggregate_query(plan, period, "current")
    grouped = base.subquery("grouped")
    fields = list(plan.group_by) + list(plan.metrics)
    selected = [grouped.c[item] for item in fields]
    if plan.analysis_mode == "contribution":
        metric_id = plan.metrics[0]
        contribution = case(
            (func.sum(grouped.c[metric_id]).over() == 0, None),
            else_=grouped.c[metric_id] * 100.0 / func.sum(grouped.c[metric_id]).over(),
        ).label(f"{metric_id}__contribution_pct")
        selected.append(contribution)
        fields.append(contribution.name)
    statement = select(*selected)
    order_map = {item: grouped.c[item] for item in list(plan.group_by) + list(plan.metrics)}
    for order in plan.order_by:
        statement = statement.order_by(order_map[order.field].asc() if order.direction == "asc" else order_map[order.field].desc())
    if not plan.order_by:
        for item in plan.group_by:
            statement = statement.order_by(grouped.c[item].asc())
    return statement.limit(plan.limit), params, tuple(fields)


def _comparison_statement(plan: AnalysisPlan, periods: tuple[ComparisonRange, ...]):
    current, previous = periods
    alignment = current.start - previous.start
    current_query, current_params = _aggregate_query(plan, current, "current")
    previous_query, previous_params = _aggregate_query(plan, previous, "comparison", align=alignment)
    current_grouped, previous_grouped = current_query.subquery("current_grouped"), previous_query.subquery("comparison_grouped")
    join_clause = and_(*(current_grouped.c[item] == previous_grouped.c[item] for item in plan.group_by)) if plan.group_by else literal(True)
    from_clause = current_grouped.join(previous_grouped, join_clause, full=True)
    selected, fields, order_map = [], [], {}
    for item in plan.group_by:
        expression = func.coalesce(current_grouped.c[item], previous_grouped.c[item]).label(item)
        selected.append(expression); fields.append(item); order_map[item] = expression
    deltas = {}
    for metric_id in plan.metrics:
        current_value = current_grouped.c[metric_id]
        previous_value = previous_grouped.c[metric_id]
        delta = (current_value - previous_value).label(f"{metric_id}__delta")
        delta_pct = case(
            (previous_value.is_(None), None),
            (previous_value == 0, None),
            else_=delta * 100.0 / func.abs(previous_value),
        ).label(f"{metric_id}__delta_pct")
        for expression in (
            current_value.label(metric_id),
            previous_value.label(f"{metric_id}__comparison"),
            delta,
            delta_pct,
        ):
            selected.append(expression); fields.append(expression.name)
        order_map[metric_id] = current_value
        deltas[metric_id] = delta
    if plan.analysis_mode == "contribution":
        metric_id = plan.metrics[0]
        delta = deltas[metric_id]
        contribution = case(
            (func.sum(delta).over() == 0, None),
            else_=delta * 100.0 / func.sum(delta).over(),
        ).label(f"{metric_id}__contribution_pct")
        selected.append(contribution); fields.append(contribution.name)
    statement = select(*selected).select_from(from_clause)
    for order in plan.order_by:
        expression = order_map[order.field]
        statement = statement.order_by(expression.asc() if order.direction == "asc" else expression.desc())
    if not plan.order_by:
        for item in plan.group_by:
            statement = statement.order_by(order_map[item].asc())
    params = {**current_params, **previous_params, "comparison_alignment": alignment}
    return statement.limit(plan.limit), params, tuple(fields)


def _hash_query(statement: ClauseElement, parameters: dict[str, Any]) -> str:
    sql = str(statement.compile(dialect=postgresql.dialect()))
    normalized = {
        key: [part.isoformat() if isinstance(part, datetime) else str(part) for part in value]
        if isinstance(value, list)
        else value.isoformat() if isinstance(value, datetime)
        else str(value)
        for key, value in parameters.items()
    }
    payload = sql + "\n" + json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compile_analysis_plan(plan: AnalysisPlan, *, permissions: tuple[str, ...] | list[str] | set[str]) -> CompiledQuery:
    validation: PlanValidation = validate_analysis_plan(plan, permissions=permissions)
    if not validation.valid or not validation.executable:
        codes = ",".join(item.code for item in validation.issues) or validation.status
        raise QueryCompileError("plan_not_validated", f"AnalysisPlan 未通过 Validator：{codes}")
    periods = _comparison_ranges(plan)
    if plan.comparison:
        statement, parameters, fields = _comparison_statement(plan, periods)
    else:
        statement, parameters, fields = _normal_statement(plan, periods[0] if periods else ComparisonRange("current", datetime.min, datetime.max))
    return CompiledQuery(
        analysis_plan_id=plan.analysis_plan_id,
        plan_hash=plan.stable_hash(),
        query_hash=_hash_query(statement, parameters),
        statement=statement,
        parameters=parameters,
        fields=fields,
        comparison_ranges=periods,
    )
