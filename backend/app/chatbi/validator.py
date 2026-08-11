from __future__ import annotations

from dataclasses import asdict, dataclass

from backend.app.data_registry import DatasetRegistryError, get_dataset

from .catalog import DIMENSION_CATALOG, JOIN_CATALOG, METRIC_CATALOG
from .contracts import AnalysisPlan


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    field: str
    message: str


@dataclass(frozen=True)
class PlanValidation:
    status: str
    executable: bool
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def valid(self) -> bool:
        return self.status == "valid" and not self.issues

    def public_dict(self) -> dict:
        return {"status": self.status, "valid": self.valid, "executable": self.executable, "issues": [asdict(item) for item in self.issues]}


def validate_analysis_plan(plan: AnalysisPlan, *, permissions: tuple[str, ...] | list[str] | set[str]) -> PlanValidation:
    if plan.clarification_required:
        return PlanValidation("clarification_required", False)

    issues: list[ValidationIssue] = []
    permission_set = set(permissions)
    wildcard = "*" in permission_set

    def issue(code: str, field: str, message: str) -> None:
        issues.append(ValidationIssue(code, field, message))

    datasets = {}
    for dataset_id in plan.datasets:
        try:
            dataset = get_dataset(dataset_id)
        except DatasetRegistryError:
            issue("unregistered_dataset", "datasets", "数据集未注册。")
            continue
        datasets[dataset_id] = dataset
        if not dataset.ai_allowed:
            issue("dataset_not_ai_accessible", "datasets", "数据集不允许 AI 访问。")
        if not wildcard and dataset.required_permission not in permission_set:
            issue("dataset_forbidden", "datasets", "缺少数据集访问权限。")
    if not datasets:
        issue("dataset_required", "datasets", "可执行计划必须指定已注册数据集。")
    if not plan.metrics:
        issue("metric_required", "metrics", "可执行计划必须指定已注册指标。")

    metrics = {}
    for metric_id in plan.metrics:
        metric = METRIC_CATALOG.get(metric_id)
        if not metric or metric.status != "active":
            issue("unregistered_metric", "metrics", "指标未注册或未启用。")
            continue
        metrics[metric_id] = metric
        if not set(metric.allowed_datasets).intersection(datasets):
            issue("metric_dataset_mismatch", "metrics", "指标不允许用于所选数据集。")
        if not wildcard and metric.permission not in permission_set:
            issue("metric_forbidden", "metrics", "缺少指标访问权限。")
        if plan.time_grain and plan.time_grain not in metric.time_grain:
            issue("metric_time_grain_forbidden", "time_grain", "指标不支持所选时间粒度。")

    referenced_dimensions = set(plan.dimensions) | set(plan.group_by) | {item.dimension for item in plan.filters}
    if plan.drill_level:
        referenced_dimensions.add(plan.drill_level)
    dimensions = {}
    for dimension_id in referenced_dimensions:
        dimension = DIMENSION_CATALOG.get(dimension_id)
        if not dimension or dimension.status != "active":
            issue("unregistered_dimension", "dimensions", "维度未注册或未启用。")
            continue
        dimensions[dimension_id] = dimension
        if dimension.dataset not in datasets:
            issue("dimension_dataset_mismatch", "dimensions", "维度不属于所选数据集。")
        if not wildcard and dimension.permission not in permission_set:
            issue("dimension_forbidden", "dimensions", "缺少维度访问权限。")
    if not set(plan.group_by).issubset(plan.dimensions):
        issue("group_by_not_selected", "group_by", "分组维度必须出现在 dimensions。")
    if plan.drill_level and plan.drill_level not in plan.dimensions:
        issue("drill_level_not_selected", "drill_level", "下钻层级必须出现在 dimensions。")

    joins = {}
    for join_id in plan.joins:
        join = JOIN_CATALOG.get(join_id)
        if not join or join.status != "active":
            issue("unregistered_join", "joins", "关联关系未注册或未启用。")
            continue
        joins[join_id] = join
        if not {join.left_dataset, join.right_dataset}.issubset(datasets):
            issue("join_dataset_mismatch", "joins", "关联关系与所选数据集不一致。")
        if not set(plan.metrics).issubset(join.allowed_metrics):
            issue("join_metric_forbidden", "joins", "关联关系不允许所选指标。")
        if not referenced_dimensions.issubset(join.allowed_dimensions):
            issue("join_dimension_forbidden", "joins", "关联关系不允许所选维度。")
        if not wildcard and join.permission not in permission_set:
            issue("join_forbidden", "joins", "缺少关联权限。")
    if len(datasets) > 1:
        connected = {next(iter(datasets))} if datasets else set()
        for join in joins.values():
            if join.left_dataset in connected or join.right_dataset in connected:
                connected.update((join.left_dataset, join.right_dataset))
        if connected != set(datasets):
            issue("join_required", "joins", "多数据集计划必须使用完整白名单关联。")

    allowed_order_fields = set(metrics) | set(dimensions)
    for order in plan.order_by:
        if order.field not in allowed_order_fields:
            issue("order_field_forbidden", "order_by", "排序字段必须是已选指标或维度。")
    if plan.comparison and not plan.time_range:
        issue("comparison_time_range_required", "comparison", "同比、环比或上期比较必须指定时间范围。")
    if plan.chart_intent == "pie" and (len(plan.metrics) != 1 or len(plan.group_by) != 1):
        issue("pie_semantics_invalid", "chart_intent", "饼图只允许单指标和单分组维度。")

    return PlanValidation("invalid" if issues else "valid", not issues, tuple(issues))
