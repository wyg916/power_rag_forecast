from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal


ObjectType = Literal["table", "view"]
FieldType = Literal["string", "integer", "number", "boolean", "datetime"]
Sensitivity = Literal["public_business", "internal_business"]

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_DATASET_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_FORBIDDEN_OBJECTS = frozenset(
    {
        "alembic_version",
        "audit_logs",
        "permissions",
        "roles",
        "schema_migrations",
        "system_api_configs",
        "system_api_test_logs",
        "system_runtime_config",
        "task_logs",
        "task_runs",
        "user_roles",
        "users",
    }
)
_FORBIDDEN_FIELD_TOKENS = (
    "api_key",
    "connection",
    "credential",
    "password",
    "payload_json",
    "raw_json",
    "secret",
    "token",
)


class DatasetRegistryError(RuntimeError):
    """Raised when the static dataset registry violates the Day 4 contract."""


@dataclass(frozen=True)
class DatasetField:
    field_id: str
    column_name: str
    display_name: str
    data_type: FieldType
    description: str
    sortable: bool = False
    filterable: bool = False
    searchable: bool = False

    def public_dict(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id,
            "display_name": self.display_name,
            "data_type": self.data_type,
            "description": self.description,
            "sortable": self.sortable,
            "filterable": self.filterable,
            "searchable": self.searchable,
        }


@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    display_name: str
    description: str
    business_domain: str
    object_name: str
    object_type: ObjectType
    fields: tuple[DatasetField, ...]
    default_sort: str
    default_sort_direction: Literal["asc", "desc"] = "desc"
    max_page_size: int = 100
    export_allowed: bool = False
    export_max_rows: int = 5000
    required_permission: str = "data:read"
    source_type: str = "historical"
    sensitivity: Sensitivity = "public_business"
    ai_allowed: bool = False
    consumers: tuple[str, ...] = ("数据中心",)
    aliases: tuple[str, ...] = ()

    @property
    def field_map(self) -> dict[str, DatasetField]:
        return {field.field_id: field for field in self.fields}

    @property
    def column_map(self) -> dict[str, DatasetField]:
        return {field.column_name: field for field in self.fields}

    def public_dict(self, *, exists: bool | None = None) -> dict[str, Any]:
        result = {
            "dataset_id": self.dataset_id,
            "display_name": self.display_name,
            "description": self.description,
            "business_domain": self.business_domain,
            "object_type": self.object_type,
            "fields": [field.public_dict() for field in self.fields],
            "default_sort": self.default_sort,
            "default_sort_direction": self.default_sort_direction,
            "allowed_sort_fields": [field.field_id for field in self.fields if field.sortable],
            "allowed_filter_fields": [field.field_id for field in self.fields if field.filterable],
            "max_page_size": self.max_page_size,
            "export_allowed": self.export_allowed,
            "export_max_rows": self.export_max_rows,
            "required_permission": self.required_permission,
            "source_type": self.source_type,
            "sensitivity": self.sensitivity,
            "ai_allowed": self.ai_allowed,
            "consumers": list(self.consumers),
        }
        if exists is not None:
            result["runtime"] = {"exists": exists}
        return result


def _field(
    field_id: str,
    column_name: str,
    display_name: str,
    data_type: FieldType,
    description: str,
    *,
    sortable: bool = False,
    filterable: bool = False,
    searchable: bool = False,
) -> DatasetField:
    return DatasetField(
        field_id=field_id,
        column_name=column_name,
        display_name=display_name,
        data_type=data_type,
        description=description,
        sortable=sortable,
        filterable=filterable,
        searchable=searchable,
    )


_SPECS = (
    DatasetSpec(
        dataset_id="market_price_history",
        display_name="市场电价历史",
        description="PJM 市场节点日前、实时和边际电价明细。",
        business_domain="market_price",
        object_name="raw_market",
        object_type="table",
        fields=(
            _field("observed_at", "datetime", "业务时间", "datetime", "价格对应小时", sortable=True, filterable=True),
            _field("market_code", "market", "市场", "string", "市场代码", filterable=True, searchable=True),
            _field("node_label", "node_name", "节点", "string", "市场节点或区域", filterable=True, searchable=True),
            _field("price_category", "price_type", "价格类型", "string", "日前或实时等价格口径", filterable=True, searchable=True),
            _field("day_ahead_price", "da_price", "日前电价", "number", "日前市场电价", sortable=True),
            _field("real_time_price", "rt_price", "实时电价", "number", "实时市场电价", sortable=True),
            _field("marginal_price", "lmp", "节点边际电价", "number", "节点边际电价", sortable=True),
        ),
        default_sort="observed_at",
        export_allowed=True,
        ai_allowed=True,
        aliases=("raw_market", "市场电价", "节点电价", "lmp"),
    ),
    DatasetSpec(
        dataset_id="day_ahead_price",
        display_name="日前电价",
        description="PJM 日前市场小时电价。",
        business_domain="market_price",
        object_name="raw_da_price",
        object_type="view",
        fields=(
            _field("observed_at", "datetime", "业务时间", "datetime", "日前价格对应小时", sortable=True, filterable=True),
            _field("market_code", "market", "市场", "string", "市场代码", filterable=True, searchable=True),
            _field("node_label", "node_name", "节点", "string", "市场节点或区域", filterable=True, searchable=True),
            _field("day_ahead_price", "da_price", "日前电价", "number", "日前市场电价", sortable=True),
        ),
        default_sort="observed_at",
        export_allowed=True,
        ai_allowed=True,
        aliases=("raw_da_price", "日前价格", "日前电价", "da lmp"),
    ),
    DatasetSpec(
        dataset_id="real_time_price",
        display_name="实时电价",
        description="PJM 实时市场小时电价。",
        business_domain="market_price",
        object_name="raw_rt_price",
        object_type="view",
        fields=(
            _field("observed_at", "datetime", "业务时间", "datetime", "实时价格对应小时", sortable=True, filterable=True),
            _field("market_code", "market", "市场", "string", "市场代码", filterable=True, searchable=True),
            _field("node_label", "node_name", "节点", "string", "市场节点或区域", filterable=True, searchable=True),
            _field("real_time_price", "rt_price", "实时电价", "number", "实时市场电价", sortable=True),
        ),
        default_sort="observed_at",
        export_allowed=True,
        ai_allowed=True,
        aliases=("raw_rt_price", "实时价格", "实时电价", "rt lmp"),
    ),
    DatasetSpec(
        dataset_id="actual_load",
        display_name="实际负荷",
        description="PJM 实际负荷小时数据。",
        business_domain="load",
        object_name="raw_actual_load",
        object_type="view",
        fields=(
            _field("observed_at", "datetime", "业务时间", "datetime", "负荷对应小时", sortable=True, filterable=True),
            _field("market_code", "market", "市场", "string", "市场代码", filterable=True, searchable=True),
            _field("actual_load_mw", "actual_load", "实际负荷", "number", "实际用电负荷 MW", sortable=True),
        ),
        default_sort="observed_at",
        export_allowed=True,
        ai_allowed=True,
        aliases=("raw_actual_load", "实际负荷"),
    ),
    DatasetSpec(
        dataset_id="load_history",
        display_name="负荷历史",
        description="预测负荷与实际负荷的清洗后小时宽表。",
        business_domain="load",
        object_name="raw_load",
        object_type="table",
        fields=(
            _field("observed_at", "datetime", "业务时间", "datetime", "负荷对应小时", sortable=True, filterable=True),
            _field("market_code", "market", "市场", "string", "市场代码", filterable=True, searchable=True),
            _field("forecast_load_mw", "forecast_load", "预测负荷", "number", "预测用电负荷 MW", sortable=True),
            _field("actual_load_mw", "actual_load", "实际负荷", "number", "实际用电负荷 MW", sortable=True),
        ),
        default_sort="observed_at",
        export_allowed=True,
        ai_allowed=True,
        aliases=("raw_load", "负荷历史", "负荷"),
    ),
    DatasetSpec(
        dataset_id="load_forecast",
        display_name="负荷预测",
        description="PJM 七日负荷预测小时数据。",
        business_domain="load",
        object_name="raw_forecast_load_selected",
        object_type="view",
        fields=(
            _field("observed_at", "datetime", "业务时间", "datetime", "预测负荷对应小时", sortable=True, filterable=True),
            _field("market_code", "market", "市场", "string", "市场代码", filterable=True, searchable=True),
            _field("forecast_load_mw", "forecast_load", "预测负荷", "number", "预测用电负荷 MW", sortable=True),
        ),
        default_sort="observed_at",
        export_allowed=True,
        ai_allowed=True,
        aliases=("raw_forecast_load_selected", "预测负荷", "负荷预测"),
    ),
    DatasetSpec(
        dataset_id="weather_observations",
        display_name="天气观测",
        description="天气观测与预报要素，用于解释负荷和价格扰动。",
        business_domain="weather",
        object_name="raw_weather",
        object_type="table",
        fields=(
            _field("observed_at", "datetime", "业务时间", "datetime", "天气观测或预报时间", sortable=True, filterable=True),
            _field("location_label", "point_name", "观测点", "string", "天气观测点", filterable=True, searchable=True),
            _field("city_label", "city", "城市", "string", "城市名称", filterable=True, searchable=True),
            _field("temperature_c", "temperature", "温度", "number", "摄氏温度", sortable=True),
            _field("humidity_pct", "humidity", "湿度", "number", "相对湿度百分比", sortable=True),
            _field("wind_speed", "wind_speed", "风速", "number", "风速", sortable=True),
        ),
        default_sort="observed_at",
        export_allowed=True,
        ai_allowed=True,
        aliases=("raw_weather", "天气", "气温", "温度"),
    ),
    DatasetSpec(
        dataset_id="forecast_output",
        display_name="预测结果",
        description="已入库的价格预测、风险与模型版本结果。",
        business_domain="forecast",
        object_name="forecast_results",
        object_type="table",
        fields=(
            _field("run_id", "run_id", "运行 ID", "string", "预测任务运行标识", filterable=True, searchable=True),
            _field("forecast_at", "forecast_datetime", "预测时间", "datetime", "预测结果对应小时", sortable=True, filterable=True),
            _field("predicted_price", "predicted_price", "预测电价", "number", "模型预测价格", sortable=True),
            _field("corrected_price", "corrected_predicted_price", "修正预测电价", "number", "业务修正后的预测价格", sortable=True),
            _field("risk_level", "risk_level", "风险等级", "string", "预测风险等级", filterable=True, searchable=True),
            _field("spike_probability", "spike_risk_prob", "尖峰风险概率", "number", "尖峰价格风险概率", sortable=True),
            _field("forecast_load_mw", "forecast_load", "预测负荷", "number", "预测负荷 MW", sortable=True),
            _field("model_version", "model_version", "模型版本", "string", "生成预测的模型版本", filterable=True, searchable=True),
            _field("feature_version", "feature_version", "特征版本", "string", "生成预测的特征版本", filterable=True, searchable=True),
            _field("generated_at", "generated_at", "生成时间", "datetime", "预测生成时间", sortable=True, filterable=True),
            _field("source_type", "source_type", "来源类型", "string", "受控来源分类", filterable=True),
        ),
        default_sort="forecast_at",
        export_allowed=True,
        ai_allowed=True,
        sensitivity="internal_business",
        consumers=("数据中心", "预测中心", "AI 助手"),
        aliases=("forecast_results", "预测结果", "未来24小时预测", "forecast"),
    ),
    DatasetSpec(
        dataset_id="prediction_accuracy",
        display_name="预测误差跟踪",
        description="预测值与实际回填值的误差跟踪。",
        business_domain="model_monitoring",
        object_name="prediction_tracking",
        object_type="table",
        fields=(
            _field("run_id", "run_id", "运行 ID", "string", "预测任务运行标识", filterable=True, searchable=True),
            _field("forecast_at", "forecast_datetime", "预测时间", "datetime", "被评估的预测小时", sortable=True, filterable=True),
            _field("generated_at", "generated_at", "生成时间", "datetime", "预测生成时间", sortable=True),
            _field("predicted_price", "predicted_price", "预测电价", "number", "模型预测价格", sortable=True),
            _field("actual_price", "actual_price", "实际电价", "number", "实际回填价格", sortable=True),
            _field("absolute_error", "abs_error", "绝对误差", "number", "预测与实际价格绝对差", sortable=True),
            _field("percentage_error", "pct_error", "百分比误差", "number", "预测误差百分比", sortable=True),
            _field("model_version", "model_version", "模型版本", "string", "生成预测的模型版本", filterable=True, searchable=True),
            _field("feature_version", "feature_version", "特征版本", "string", "生成预测的特征版本", filterable=True, searchable=True),
        ),
        default_sort="forecast_at",
        export_allowed=False,
        ai_allowed=True,
        sensitivity="internal_business",
        consumers=("数据中心", "模型中心", "AI 助手"),
        aliases=("prediction_tracking", "模型误差", "预测误差"),
    ),
    DatasetSpec(
        dataset_id="model_inventory",
        display_name="模型版本清单",
        description="模型版本、状态和受控评估指标，不暴露制品路径或哈希。",
        business_domain="model_monitoring",
        object_name="model_registry",
        object_type="table",
        fields=(
            _field("model_version", "model_version", "模型版本", "string", "模型版本标识", sortable=True, filterable=True, searchable=True),
            _field("model_role", "model_role", "模型角色", "string", "Candidate 或 Active 等模型角色", filterable=True),
            _field("status", "status", "状态", "string", "模型治理状态", filterable=True, searchable=True),
            _field("is_active", "is_active", "是否激活", "integer", "是否为当前 Active 模型", filterable=True),
            _field("test_mae", "test_mae", "测试 MAE", "number", "测试集平均绝对误差", sortable=True),
            _field("test_rmse", "test_rmse", "测试 RMSE", "number", "测试集均方根误差", sortable=True),
            _field("domain", "domain", "业务域", "string", "模型业务域", filterable=True, searchable=True),
            _field("target_name", "target_name", "预测目标", "string", "模型预测目标", filterable=True, searchable=True),
            _field("created_at", "created_at", "创建时间", "datetime", "模型记录创建时间", sortable=True, filterable=True),
            _field("activated_at", "activated_at", "激活时间", "datetime", "模型激活时间", sortable=True),
            _field("source_type", "source_type", "来源类型", "string", "受控来源分类", filterable=True),
        ),
        default_sort="created_at",
        export_allowed=False,
        ai_allowed=False,
        sensitivity="internal_business",
        consumers=("数据中心", "模型中心"),
        aliases=("model_registry", "模型状态", "模型版本"),
    ),
    DatasetSpec(
        dataset_id="feature_importance",
        display_name="特征重要性",
        description="模型特征重要性和排序，不暴露原始输入数据。",
        business_domain="model_monitoring",
        object_name="feature_importance",
        object_type="table",
        fields=(
            _field("model_version", "model_version", "模型版本", "string", "模型版本标识", filterable=True, searchable=True),
            _field("feature_name", "feature", "特征名称", "string", "模型输入特征", filterable=True, searchable=True),
            _field("importance_score", "importance", "重要性", "number", "特征重要性分数", sortable=True),
            _field("importance_rank", "rank", "排名", "integer", "特征重要性排名", sortable=True),
            _field("created_at", "created_at", "创建时间", "datetime", "记录创建时间", sortable=True, filterable=True),
        ),
        default_sort="importance_rank",
        default_sort_direction="asc",
        export_allowed=False,
        ai_allowed=True,
        sensitivity="internal_business",
        consumers=("数据中心", "模型中心", "AI 助手"),
        aliases=("特征重要性", "feature_importance"),
    ),
)

DATASET_REGISTRY: dict[str, DatasetSpec] = {spec.dataset_id: spec for spec in _SPECS}
_OBJECT_TO_DATASET = {spec.object_name: spec.dataset_id for spec in _SPECS}


def validate_dataset_registry() -> None:
    errors: list[str] = []
    if len(DATASET_REGISTRY) != len(_SPECS):
        errors.append("dataset_id 必须唯一")
    if len(_OBJECT_TO_DATASET) != len(_SPECS):
        errors.append("数据库对象不得登记到多个数据集")
    for spec in _SPECS:
        if not _DATASET_ID_RE.fullmatch(spec.dataset_id):
            errors.append(f"非法 dataset_id: {spec.dataset_id}")
        if not _IDENTIFIER_RE.fullmatch(spec.object_name):
            errors.append(f"非法对象名: {spec.object_name}")
        if spec.object_name in _FORBIDDEN_OBJECTS:
            errors.append(f"敏感对象不得进入数据集注册表: {spec.object_name}")
        if not 1 <= spec.max_page_size <= 200:
            errors.append(f"{spec.dataset_id} max_page_size 超出 1..200")
        if not 1 <= spec.export_max_rows <= 10000:
            errors.append(f"{spec.dataset_id} export_max_rows 超出 1..10000")
        field_ids = [field.field_id for field in spec.fields]
        columns = [field.column_name for field in spec.fields]
        if len(set(field_ids)) != len(field_ids) or len(set(columns)) != len(columns):
            errors.append(f"{spec.dataset_id} 字段键或列映射重复")
        if spec.default_sort not in field_ids:
            errors.append(f"{spec.dataset_id} 默认排序字段未登记")
        if not spec.field_map[spec.default_sort].sortable:
            errors.append(f"{spec.dataset_id} 默认排序字段未标记 sortable")
        for field in spec.fields:
            if not _IDENTIFIER_RE.fullmatch(field.field_id) or not _IDENTIFIER_RE.fullmatch(field.column_name):
                errors.append(f"{spec.dataset_id} 包含非法字段标识符")
            lowered = f"{field.field_id} {field.column_name}".lower()
            if any(token in lowered for token in _FORBIDDEN_FIELD_TOKENS):
                errors.append(f"{spec.dataset_id} 暴露敏感字段: {field.field_id}")
    if errors:
        raise DatasetRegistryError("数据集注册表无效：" + "；".join(errors))


def get_dataset(dataset_id: str) -> DatasetSpec:
    value = str(dataset_id or "").strip().lower()
    try:
        return DATASET_REGISTRY[value]
    except KeyError as exc:
        raise DatasetRegistryError("未注册数据集") from exc


def resolve_dataset_reference(value: str, *, ai_only: bool = False) -> DatasetSpec | None:
    normalized = str(value or "").strip().lower()
    dataset_id = normalized if normalized in DATASET_REGISTRY else _OBJECT_TO_DATASET.get(normalized)
    if dataset_id:
        spec = DATASET_REGISTRY[dataset_id]
        return spec if not ai_only or spec.ai_allowed else None
    compact = normalized.replace(" ", "")
    for spec in _SPECS:
        if ai_only and not spec.ai_allowed:
            continue
        if compact and any(str(alias).lower().replace(" ", "") == compact for alias in spec.aliases):
            return spec
    return None


def find_datasets(search: str | None = None, *, ai_only: bool = False) -> list[DatasetSpec]:
    keyword = str(search or "").strip().lower()
    result: list[DatasetSpec] = []
    for spec in _SPECS:
        if ai_only and not spec.ai_allowed:
            continue
        haystack = " ".join(
            [spec.dataset_id, spec.display_name, spec.description, spec.business_domain, *spec.aliases]
        ).lower()
        if not keyword or keyword in haystack:
            result.append(spec)
    return result


def legacy_catalog_by_object() -> dict[str, dict[str, Any]]:
    """Internal compatibility view; public APIs must never return its object keys."""

    return {
        spec.object_name: {
            "dataset_id": spec.dataset_id,
            "display_name": spec.display_name,
            "business_domain": spec.business_domain,
            "description": spec.description,
            "time_field": next(
                (field.column_name for field in spec.fields if field.data_type == "datetime"),
                "",
            ),
            "default_order_field": spec.field_map[spec.default_sort].column_name,
            "grain": "business_records",
            "refresh_frequency": "controlled_pipeline",
            "source_system": "PostgreSQL 受控业务数据",
            "aliases": list(spec.aliases),
            "ai_allowed": spec.ai_allowed,
            "fields": [
                {
                    "field_id": field.field_id,
                    "field_name": field.column_name,
                    "business_name": field.display_name,
                    "meaning": field.description,
                    "data_type": field.data_type,
                    "sortable": field.sortable,
                    "filterable": field.filterable,
                    "searchable": field.searchable,
                }
                for field in spec.fields
            ],
        }
        for spec in _SPECS
    }


validate_dataset_registry()
