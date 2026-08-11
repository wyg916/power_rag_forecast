from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from backend.app.data_registry import get_dataset


CATALOG_VERSION = "chatbi-v1.0.0"
VALID_FROM = date(2026, 8, 11)
GRAINS = ("hour", "day", "week", "month")


@dataclass(frozen=True)
class MetricSpec:
    metric_id: str
    metric_name: str
    business_name: str
    description: str
    formula: str
    value_field: str
    unit: str
    aggregation: str
    time_grain: tuple[str, ...]
    allowed_dimensions: tuple[str, ...]
    allowed_datasets: tuple[str, ...]
    allowed_joins: tuple[str, ...]
    valid_from: date = VALID_FROM
    valid_to: date | None = None
    version: int = 1
    status: str = "active"
    permission: str = "data:read"


@dataclass(frozen=True)
class DimensionSpec:
    dimension_id: str
    name: str
    business_name: str
    dataset: str
    field: str
    data_type: str
    allowed_values: tuple[str, ...] | None = None
    hierarchy: tuple[str, ...] = ()
    sensitivity: str = "public_business"
    permission: str = "data:read"
    valid_from: date = VALID_FROM
    valid_to: date | None = None
    version: int = 1
    status: str = "active"


@dataclass(frozen=True)
class JoinSpec:
    join_id: str
    left_dataset: str
    right_dataset: str
    join_keys: tuple[tuple[str, str], ...]
    join_type: str
    allowed_metrics: tuple[str, ...]
    allowed_dimensions: tuple[str, ...]
    permission: str = "data:read"
    version: int = 1
    status: str = "active"


def _dimension(identifier: str, label: str, dataset: str, field: str, *, hierarchy: tuple[str, ...] = (), sensitivity: str = "public_business") -> DimensionSpec:
    data_type = get_dataset(dataset).field_map[field].data_type
    return DimensionSpec(identifier, identifier, label, dataset, field, data_type, hierarchy=hierarchy, sensitivity=sensitivity)


_DIMENSIONS = (
    _dimension("market_observed_at", "市场业务时间", "market_price_history", "observed_at"),
    _dimension("market_code", "市场", "market_price_history", "market_code"),
    _dimension("market_node", "节点", "market_price_history", "node_label", hierarchy=("market_code", "market_node")),
    _dimension("price_category", "价格类型", "market_price_history", "price_category"),
    _dimension("load_observed_at", "负荷业务时间", "load_history", "observed_at"),
    _dimension("load_market_code", "负荷市场", "load_history", "market_code"),
    _dimension("weather_observed_at", "气象业务时间", "weather_observations", "observed_at"),
    _dimension("weather_city", "城市", "weather_observations", "city_label"),
    _dimension("weather_location", "观测点", "weather_observations", "location_label", hierarchy=("weather_city", "weather_location")),
    _dimension("forecast_run_id", "预测批次", "forecast_output", "run_id", sensitivity="internal_business"),
    _dimension("forecast_at", "预测时间", "forecast_output", "forecast_at"),
    _dimension("forecast_risk_level", "风险等级", "forecast_output", "risk_level"),
    _dimension("forecast_model_version", "模型版本", "forecast_output", "model_version", sensitivity="internal_business"),
    _dimension("forecast_feature_version", "特征版本", "forecast_output", "feature_version", sensitivity="internal_business"),
    _dimension("forecast_generated_at", "生成时间", "forecast_output", "generated_at"),
    _dimension("accuracy_run_id", "评估批次", "prediction_accuracy", "run_id", sensitivity="internal_business"),
    _dimension("accuracy_forecast_at", "评估时间", "prediction_accuracy", "forecast_at"),
    _dimension("accuracy_model_version", "评估模型版本", "prediction_accuracy", "model_version", sensitivity="internal_business"),
    _dimension("accuracy_feature_version", "评估特征版本", "prediction_accuracy", "feature_version", sensitivity="internal_business"),
    _dimension("feature_model_version", "特征模型版本", "feature_importance", "model_version", sensitivity="internal_business"),
    _dimension("feature_name", "特征", "feature_importance", "feature_name", sensitivity="internal_business"),
)
DIMENSION_CATALOG = {item.dimension_id: item for item in _DIMENSIONS}

MARKET_DIMS = ("market_observed_at", "market_code", "market_node", "price_category")
LOAD_DIMS = ("load_observed_at", "load_market_code")
WEATHER_DIMS = ("weather_observed_at", "weather_city", "weather_location")
FORECAST_DIMS = ("forecast_run_id", "forecast_at", "forecast_risk_level", "forecast_model_version", "forecast_feature_version", "forecast_generated_at")
ACCURACY_DIMS = ("accuracy_run_id", "accuracy_forecast_at", "accuracy_model_version", "accuracy_feature_version")


def _metric(identifier: str, label: str, dataset: str, field: str, unit: str, dimensions: tuple[str, ...], joins: tuple[str, ...] = ()) -> MetricSpec:
    return MetricSpec(identifier, identifier, label, f"{label}的注册平均口径。", f"AVG({field})", field, unit, "avg", GRAINS, dimensions, (dataset,), joins)


_METRICS = (
    _metric("avg_day_ahead_price", "平均日前电价", "market_price_history", "day_ahead_price", "元/MWh", MARKET_DIMS, ("market_load_by_time_market",)),
    _metric("avg_real_time_price", "平均实时电价", "market_price_history", "real_time_price", "元/MWh", MARKET_DIMS, ("market_load_by_time_market",)),
    _metric("avg_marginal_price", "平均边际电价", "market_price_history", "marginal_price", "元/MWh", MARKET_DIMS, ("market_load_by_time_market",)),
    _metric("avg_actual_load", "平均实际负荷", "load_history", "actual_load_mw", "MW", LOAD_DIMS, ("market_load_by_time_market",)),
    _metric("avg_forecast_load", "平均预测负荷", "load_history", "forecast_load_mw", "MW", LOAD_DIMS, ("market_load_by_time_market",)),
    _metric("avg_temperature", "平均温度", "weather_observations", "temperature_c", "°C", WEATHER_DIMS),
    _metric("avg_humidity", "平均湿度", "weather_observations", "humidity_pct", "%", WEATHER_DIMS),
    _metric("avg_wind_speed", "平均风速", "weather_observations", "wind_speed", "m/s", WEATHER_DIMS),
    _metric("avg_predicted_price", "平均预测电价", "forecast_output", "predicted_price", "元/MWh", FORECAST_DIMS, ("forecast_accuracy_by_run_time",)),
    _metric("avg_corrected_price", "平均校正电价", "forecast_output", "corrected_price", "元/MWh", FORECAST_DIMS, ("forecast_accuracy_by_run_time",)),
    _metric("avg_spike_probability", "平均尖峰概率", "forecast_output", "spike_probability", "%", FORECAST_DIMS, ("forecast_accuracy_by_run_time",)),
    _metric("avg_absolute_error", "平均绝对误差", "prediction_accuracy", "absolute_error", "元/MWh", ACCURACY_DIMS, ("forecast_accuracy_by_run_time",)),
    _metric("avg_percentage_error", "平均百分比误差", "prediction_accuracy", "percentage_error", "%", ACCURACY_DIMS, ("forecast_accuracy_by_run_time",)),
)
METRIC_CATALOG = {item.metric_id: item for item in _METRICS}

_JOINS = (
    JoinSpec(
        "market_load_by_time_market", "market_price_history", "load_history",
        (("observed_at", "observed_at"), ("market_code", "market_code")), "inner",
        tuple(item.metric_id for item in _METRICS[:5]), MARKET_DIMS + LOAD_DIMS,
    ),
    JoinSpec(
        "forecast_accuracy_by_run_time", "forecast_output", "prediction_accuracy",
        (("run_id", "run_id"), ("forecast_at", "forecast_at")), "inner",
        tuple(item.metric_id for item in _METRICS[8:]), FORECAST_DIMS + ACCURACY_DIMS,
    ),
)
JOIN_CATALOG = {item.join_id: item for item in _JOINS}


def validate_semantic_catalog() -> dict[str, Any]:
    errors: list[str] = []
    for dimension in DIMENSION_CATALOG.values():
        dataset = get_dataset(dimension.dataset)
        if not dataset.ai_allowed or dimension.field not in dataset.field_map:
            errors.append(f"dimension:{dimension.dimension_id}:invalid_field")
    for metric in METRIC_CATALOG.values():
        for dataset_id in metric.allowed_datasets:
            dataset = get_dataset(dataset_id)
            field = dataset.field_map.get(metric.value_field)
            if not dataset.ai_allowed or field is None or field.data_type not in {"integer", "number"}:
                errors.append(f"metric:{metric.metric_id}:invalid_value_field")
        if any(item not in DIMENSION_CATALOG for item in metric.allowed_dimensions):
            errors.append(f"metric:{metric.metric_id}:invalid_dimension")
        if any(item not in JOIN_CATALOG for item in metric.allowed_joins):
            errors.append(f"metric:{metric.metric_id}:invalid_join")
    for join in JOIN_CATALOG.values():
        left, right = get_dataset(join.left_dataset), get_dataset(join.right_dataset)
        for left_key, right_key in join.join_keys:
            if left_key not in left.field_map or right_key not in right.field_map:
                errors.append(f"join:{join.join_id}:invalid_key")
    if errors:
        raise RuntimeError("invalid ChatBI semantic catalog: " + ",".join(errors))
    return {"version": CATALOG_VERSION, "metrics": len(METRIC_CATALOG), "dimensions": len(DIMENSION_CATALOG), "joins": len(JOIN_CATALOG)}


CATALOG_SUMMARY = validate_semantic_catalog()
