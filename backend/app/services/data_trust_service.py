from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import inspect, text

from ..data_access import database_engine, jsonable


CATALOG_VERSION = "p1_20260612"

CORE_DATASETS: dict[str, dict[str, Any]] = {
    "raw_market": {
        "dataset_id": "market_price_raw",
        "display_name": "市场电价原始宽表",
        "business_domain": "market_price",
        "description": "PJM/DOM 市场电价原始及清洗后明细，优先承载日前、实时和节点价格口径。",
        "time_field": "datetime",
        "default_order_field": "datetime",
        "grain": "hourly",
        "refresh_frequency": "daily_or_intraday",
        "source_system": "PJM Data Miner 2",
        "source_url": "https://dataminer2.pjm.com/",
        "aliases": ["市场电价", "节点电价", "LMP", "日前价格", "实时价格"],
        "fields": [
            {"field_name": "datetime", "business_name": "时间", "meaning": "价格对应小时", "role": "time"},
            {"field_name": "node", "business_name": "节点", "meaning": "PJM 节点或区域标识", "role": "dimension"},
            {"field_name": "price_type", "business_name": "价格类型", "meaning": "日前/实时等价格口径", "role": "dimension"},
            {"field_name": "da_price", "business_name": "日前电价", "meaning": "Day-Ahead LMP", "unit": "USD/MWh", "role": "metric"},
            {"field_name": "rt_price", "business_name": "实时电价", "meaning": "Real-Time LMP", "unit": "USD/MWh", "role": "metric"},
            {"field_name": "lmp", "business_name": "节点边际电价", "meaning": "Locational Marginal Price", "unit": "USD/MWh", "role": "metric"},
        ],
    },
    "raw_da_price": {
        "dataset_id": "day_ahead_price_raw",
        "display_name": "日前价格原始数据",
        "business_domain": "market_price",
        "description": "PJM Day-Ahead LMP 小时价格数据。",
        "time_field": "datetime",
        "default_order_field": "datetime",
        "grain": "hourly",
        "refresh_frequency": "daily",
        "source_system": "PJM Data Miner 2 / Day-Ahead LMP",
        "source_url": "https://dataminer2.pjm.com/feed/da_hrl_lmps",
        "aliases": ["日前价格", "DA LMP", "日前电价"],
        "fields": [
            {"field_name": "datetime", "business_name": "时间", "meaning": "日前价格对应小时", "role": "time"},
            {"field_name": "da_price", "business_name": "日前电价", "meaning": "日前市场节点边际电价", "unit": "USD/MWh", "role": "metric"},
            {"field_name": "node", "business_name": "节点", "meaning": "PJM 节点或区域标识", "role": "dimension"},
        ],
    },
    "raw_rt_price": {
        "dataset_id": "real_time_price_raw",
        "display_name": "实时价格原始数据",
        "business_domain": "market_price",
        "description": "PJM Real-Time LMP 小时价格数据。",
        "time_field": "datetime",
        "default_order_field": "datetime",
        "grain": "hourly",
        "refresh_frequency": "intraday_or_daily",
        "source_system": "PJM Data Miner 2 / Real-Time LMP",
        "source_url": "https://dataminer2.pjm.com/feed/rt_hrl_lmps",
        "aliases": ["实时价格", "RT LMP", "实时电价"],
        "fields": [
            {"field_name": "datetime", "business_name": "时间", "meaning": "实时价格对应小时", "role": "time"},
            {"field_name": "rt_price", "business_name": "实时电价", "meaning": "实时市场节点边际电价", "unit": "USD/MWh", "role": "metric"},
            {"field_name": "node", "business_name": "节点", "meaning": "PJM 节点或区域标识", "role": "dimension"},
        ],
    },
    "raw_actual_load": {
        "dataset_id": "actual_load_raw",
        "display_name": "实际负荷原始数据",
        "business_domain": "load",
        "description": "PJM 实际负荷小时数据。",
        "time_field": "datetime",
        "default_order_field": "datetime",
        "grain": "hourly",
        "refresh_frequency": "daily",
        "source_system": "PJM Data Miner 2 / Actual Load",
        "source_url": "https://dataminer2.pjm.com/feed/hrl_load_metered",
        "aliases": ["实际负荷", "负荷回填"],
        "fields": [
            {"field_name": "datetime", "business_name": "时间", "meaning": "负荷对应小时", "role": "time"},
            {"field_name": "actual_load", "business_name": "实际负荷", "meaning": "实际用电负荷", "unit": "MW", "role": "metric"},
        ],
    },
    "raw_load": {
        "dataset_id": "load_raw",
        "display_name": "负荷宽表",
        "business_domain": "load",
        "description": "负荷预测和实际负荷的清洗后宽表。",
        "time_field": "datetime",
        "default_order_field": "datetime",
        "grain": "hourly",
        "refresh_frequency": "daily",
        "source_system": "PJM Data Miner 2",
        "source_url": "https://dataminer2.pjm.com/",
        "aliases": ["负荷", "预测负荷", "实际负荷"],
        "fields": [
            {"field_name": "datetime", "business_name": "时间", "meaning": "负荷对应小时", "role": "time"},
            {"field_name": "forecast_load", "business_name": "预测负荷", "meaning": "预测用电负荷", "unit": "MW", "role": "metric"},
            {"field_name": "actual_load", "business_name": "实际负荷", "meaning": "实际用电负荷", "unit": "MW", "role": "metric"},
        ],
    },
    "raw_forecast_load_selected": {
        "dataset_id": "forecast_load_raw",
        "display_name": "预测负荷原始数据",
        "business_domain": "load",
        "description": "PJM 7 日负荷预测小时数据。",
        "time_field": "datetime",
        "default_order_field": "datetime",
        "grain": "hourly",
        "refresh_frequency": "daily",
        "source_system": "PJM Data Miner 2 / Load Forecast",
        "source_url": "https://dataminer2.pjm.com/feed/load_frcstd_7_day",
        "aliases": ["预测负荷", "负荷预测"],
        "fields": [
            {"field_name": "datetime", "business_name": "时间", "meaning": "预测负荷对应小时", "role": "time"},
            {"field_name": "forecast_load", "business_name": "预测负荷", "meaning": "预测用电负荷", "unit": "MW", "role": "metric"},
        ],
    },
    "raw_weather": {
        "dataset_id": "weather_raw",
        "display_name": "天气原始数据",
        "business_domain": "weather",
        "description": "NOAA/NWS 天气数据，用于解释负荷和价格扰动。",
        "time_field": "datetime",
        "default_order_field": "datetime",
        "grain": "hourly_or_daily",
        "refresh_frequency": "daily",
        "source_system": "NOAA / National Weather Service",
        "source_url": "https://www.weather.gov/documentation/services-web-api",
        "aliases": ["天气", "气温", "温度"],
        "fields": [
            {"field_name": "datetime", "business_name": "时间", "meaning": "天气观测或预报时间", "role": "time"},
            {"field_name": "temperature", "business_name": "温度", "meaning": "气温", "unit": "C", "role": "metric"},
            {"field_name": "humidity", "business_name": "湿度", "meaning": "相对湿度", "unit": "%", "role": "metric"},
            {"field_name": "wind_speed", "business_name": "风速", "meaning": "风速", "role": "metric"},
            {"field_name": "precipitation", "business_name": "降水", "meaning": "降水量或降水概率", "role": "metric"},
        ],
    },
    "model_master_table": {
        "dataset_id": "model_master_table",
        "display_name": "建模主表",
        "business_domain": "feature_engineering",
        "description": "价格、负荷、天气等特征工程后的训练/预测主表。",
        "time_field": "datetime",
        "default_order_field": "datetime",
        "grain": "hourly",
        "refresh_frequency": "daily",
        "source_system": "项目特征工程管道",
        "source_url": "https://dataminer2.pjm.com/",
        "aliases": ["建模主表", "特征主表", "训练主表"],
        "fields": [
            {"field_name": "datetime", "business_name": "时间", "meaning": "特征对应小时", "role": "time"},
            {"field_name": "da_price", "business_name": "日前电价", "meaning": "模型目标或历史价格特征", "unit": "USD/MWh", "role": "metric"},
            {"field_name": "rt_price", "business_name": "实时电价", "meaning": "实时价格特征", "unit": "USD/MWh", "role": "metric"},
            {"field_name": "forecast_load", "business_name": "预测负荷", "meaning": "预测负荷特征", "unit": "MW", "role": "metric"},
            {"field_name": "actual_load", "business_name": "实际负荷", "meaning": "实际负荷特征", "unit": "MW", "role": "metric"},
            {"field_name": "temperature", "business_name": "温度", "meaning": "天气温度特征", "unit": "C", "role": "metric"},
        ],
    },
    "forecast_results": {
        "dataset_id": "forecast_results",
        "display_name": "预测结果入库表",
        "business_domain": "forecast",
        "description": "未来 24 小时预测价格、风险等级和辅助字段。",
        "time_field": "forecast_datetime",
        "default_order_field": "forecast_datetime",
        "grain": "hourly",
        "refresh_frequency": "per_forecast_run",
        "source_system": "项目预测管道",
        "aliases": ["预测结果", "未来24小时预测", "forecast"],
        "fields": [
            {"field_name": "run_id", "business_name": "运行ID", "meaning": "预测任务运行标识", "role": "dimension"},
            {"field_name": "forecast_datetime", "business_name": "预测小时", "meaning": "预测结果对应小时", "role": "time"},
            {"field_name": "predicted_price", "business_name": "预测电价", "meaning": "模型预测价格", "unit": "USD/MWh", "role": "metric"},
            {"field_name": "corrected_predicted_price", "business_name": "修正预测电价", "meaning": "业务修正后的预测价格", "unit": "USD/MWh", "role": "metric"},
            {"field_name": "risk_level", "business_name": "风险等级", "meaning": "尖峰或交易风险等级", "role": "dimension"},
            {"field_name": "spike_risk_prob", "business_name": "尖峰风险概率", "meaning": "尖峰价格风险概率", "role": "metric"},
            {"field_name": "forecast_load", "business_name": "预测负荷", "meaning": "预测负荷", "unit": "MW", "role": "metric"},
        ],
    },
    "prediction_tracking": {
        "dataset_id": "prediction_tracking",
        "display_name": "预测误差跟踪表",
        "business_domain": "model_monitoring",
        "description": "预测值与真实回填值的误差跟踪，用于模型可信度判断。",
        "time_field": "datetime",
        "default_order_field": "created_at",
        "grain": "forecast_observation",
        "refresh_frequency": "after_actual_backfill",
        "source_system": "项目模型监控管道",
        "aliases": ["模型误差", "真实值回填", "prediction tracking"],
        "fields": [
            {"field_name": "datetime", "business_name": "预测小时", "meaning": "被评估的预测小时", "role": "time"},
            {"field_name": "model_version", "business_name": "模型版本", "meaning": "生成预测的模型版本", "role": "dimension"},
            {"field_name": "predicted_price", "business_name": "预测电价", "meaning": "模型预测价格", "unit": "USD/MWh", "role": "metric"},
            {"field_name": "actual_price", "business_name": "真实电价", "meaning": "真实回填价格", "unit": "USD/MWh", "role": "metric"},
            {"field_name": "abs_error", "business_name": "绝对误差", "meaning": "预测值与真实值绝对差", "unit": "USD/MWh", "role": "metric"},
            {"field_name": "created_at", "business_name": "记录创建时间", "meaning": "误差记录入库时间", "role": "time"},
        ],
    },
    "model_registry": {
        "dataset_id": "model_registry",
        "display_name": "模型注册表",
        "business_domain": "model_monitoring",
        "description": "模型版本、状态、指标和激活信息。",
        "time_field": "created_at",
        "default_order_field": "created_at",
        "grain": "model_version",
        "refresh_frequency": "per_model_run",
        "source_system": "项目模型管理管道",
        "aliases": ["模型状态", "模型版本", "model registry"],
        "fields": [
            {"field_name": "model_version", "business_name": "模型版本", "meaning": "模型版本标识", "role": "dimension"},
            {"field_name": "status", "business_name": "状态", "meaning": "模型状态", "role": "dimension"},
            {"field_name": "is_active", "business_name": "是否激活", "meaning": "当前是否为生产激活模型", "role": "dimension"},
            {"field_name": "test_mae", "business_name": "测试 MAE", "meaning": "测试集平均绝对误差", "role": "metric"},
            {"field_name": "test_rmse", "business_name": "测试 RMSE", "meaning": "测试集均方根误差", "role": "metric"},
            {"field_name": "created_at", "business_name": "创建时间", "meaning": "模型记录创建时间", "role": "time"},
            {"field_name": "activated_at", "business_name": "激活时间", "meaning": "模型激活时间", "role": "time"},
        ],
    },
    "feature_importance": {
        "dataset_id": "feature_importance",
        "display_name": "特征重要性表",
        "business_domain": "model_monitoring",
        "description": "模型特征重要性或解释性指标。",
        "time_field": "created_at",
        "default_order_field": "created_at",
        "grain": "feature",
        "refresh_frequency": "per_model_run",
        "source_system": "项目模型解释管道",
        "aliases": ["特征重要性", "模型解释"],
        "fields": [
            {"field_name": "model_version", "business_name": "模型版本", "meaning": "模型版本标识", "role": "dimension"},
            {"field_name": "feature_name", "business_name": "特征名", "meaning": "模型输入特征", "role": "dimension"},
            {"field_name": "importance", "business_name": "重要性", "meaning": "特征重要性分数", "role": "metric"},
            {"field_name": "created_at", "business_name": "创建时间", "meaning": "记录创建时间", "role": "time"},
        ],
    },
    "task_runs": {
        "dataset_id": "task_runs",
        "display_name": "任务运行记录",
        "business_domain": "operations",
        "description": "后台任务中心的任务运行记录，用于追踪数据刷新、预测和知识库任务。",
        "time_field": "created_at",
        "default_order_field": "created_at",
        "grain": "task_run",
        "refresh_frequency": "per_task_run",
        "source_system": "任务中心",
        "aliases": ["任务记录", "任务中心", "task runs"],
        "fields": [
            {"field_name": "task_id", "business_name": "任务ID", "meaning": "任务标识", "role": "dimension"},
            {"field_name": "kind", "business_name": "任务类型", "meaning": "任务类型", "role": "dimension"},
            {"field_name": "status", "business_name": "状态", "meaning": "任务执行状态", "role": "dimension"},
            {"field_name": "created_at", "business_name": "创建时间", "meaning": "任务创建时间", "role": "time"},
            {"field_name": "started_at", "business_name": "开始时间", "meaning": "任务开始时间", "role": "time"},
            {"field_name": "finished_at", "business_name": "结束时间", "meaning": "任务结束时间", "role": "time"},
        ],
    },
}

ALLOWED_READ_TABLES = frozenset(CORE_DATASETS)
SAFE_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
TABLE_REF_RE = re.compile(
    r"\b(?:from|join)\s+((?:\"[^\"]+\"|`[^`]+`|[a-zA-Z_][a-zA-Z0-9_]*)(?:\s*\.\s*(?:\"[^\"]+\"|`[^`]+`|[a-zA-Z_][a-zA-Z0-9_]*))?)",
    re.IGNORECASE,
)
FORBIDDEN_SQL_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|merge|grant|revoke|copy|call|execute|vacuum|analyze|attach|detach|replace|upsert|set|show|use)\b",
    re.IGNORECASE,
)
FORBIDDEN_SCHEMA_RE = re.compile(r"\b(information_schema|pg_catalog)\b", re.IGNORECASE)
FORBIDDEN_TABLE_RE = re.compile(r"\b(users|audit_logs)\b", re.IGNORECASE)
DANGEROUS_FUNCTION_RE = re.compile(
    r"\b(pg_sleep|dblink|lo_import|lo_export|pg_read_file|pg_ls_dir|pg_stat_file|pg_terminate_backend|pg_cancel_backend|set_config)\s*\(",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"(20\d{2})[-/年](\d{1,2})(?:[-/月](\d{1,2}))?")


def _clean_identifier(name: str) -> str:
    value = str(name or "").strip()
    if "." in value:
        value = value.split(".")[-1]
    return value.strip('"`').lower()


def _quote_identifier(name: str, dialect: str) -> str:
    if dialect == "postgresql":
        return '"' + name.replace('"', '""') + '"'
    return "`" + name.replace("`", "``") + "`"


def _catalog_entry(table_name: str, runtime: dict[str, Any] | None = None) -> dict[str, Any]:
    table = _clean_identifier(table_name)
    base = dict(CORE_DATASETS.get(table) or {})
    base["table_name"] = table
    base["allowed_for_read_only_sql"] = table in ALLOWED_READ_TABLES
    base["catalog_version"] = CATALOG_VERSION
    if runtime:
        base["runtime"] = runtime
    return jsonable(base)


def get_data_catalog(search: str | None = None, include_runtime: bool = False) -> dict[str, Any]:
    keyword = str(search or "").strip().lower()
    engine = database_engine() if include_runtime else None
    inspector = None
    existing_tables: set[str] = set()
    if engine is not None:
        try:
            inspector = inspect(engine)
            existing_tables = set(inspector.get_table_names()) | set(inspector.get_view_names())
        except Exception:
            inspector = None
            existing_tables = set()

    datasets: list[dict[str, Any]] = []
    for table_name, meta in CORE_DATASETS.items():
        haystack = " ".join(
            [
                table_name,
                str(meta.get("dataset_id") or ""),
                str(meta.get("display_name") or ""),
                str(meta.get("description") or ""),
                " ".join(str(item) for item in meta.get("aliases") or []),
            ]
        ).lower()
        if keyword and keyword not in haystack:
            continue
        runtime: dict[str, Any] | None = None
        if include_runtime:
            runtime = {"exists": table_name in existing_tables}
            if inspector and table_name in existing_tables:
                try:
                    runtime["columns_count"] = len(inspector.get_columns(table_name))
                except Exception:
                    runtime["columns_count"] = None
        datasets.append(_catalog_entry(table_name, runtime=runtime))
    return {"available": True, "catalog_version": CATALOG_VERSION, "datasets": datasets, "total": len(datasets)}


def _runtime_columns(table_name: str) -> dict[str, str]:
    engine = database_engine()
    if engine is None:
        return {}
    try:
        inspector = inspect(engine)
        if table_name not in set(inspector.get_table_names()) | set(inspector.get_view_names()):
            return {}
        return {str(col.get("name")): str(col.get("type") or "") for col in inspector.get_columns(table_name)}
    except Exception:
        return {}


def get_field_mappings(table: str | None = None, search: str | None = None) -> dict[str, Any]:
    requested_table = _clean_identifier(table or "")
    keyword = str(search or "").strip().lower()
    rows: list[dict[str, Any]] = []
    tables = [requested_table] if requested_table else list(CORE_DATASETS)
    for table_name in tables:
        meta = CORE_DATASETS.get(table_name)
        if not meta:
            continue
        runtime_types = _runtime_columns(table_name)
        for field in meta.get("fields") or []:
            item = dict(field)
            item["table_name"] = table_name
            item["display_name"] = meta.get("display_name")
            item["business_domain"] = meta.get("business_domain")
            item["runtime_type"] = runtime_types.get(str(item.get("field_name") or ""), "")
            haystack = " ".join(str(value) for value in item.values()).lower()
            if keyword and keyword not in haystack:
                continue
            rows.append(jsonable(item))
    return {
        "available": bool(rows),
        "catalog_version": CATALOG_VERSION,
        "table_name": requested_table or "",
        "fields": rows,
        "total": len(rows),
        "message": "" if rows else "未找到匹配字段映射。",
    }


def _pick_datetime_field(table_name: str, runtime_columns: list[str] | None = None) -> str:
    meta = CORE_DATASETS.get(table_name) or {}
    preferred = str(meta.get("time_field") or "")
    if preferred:
        return preferred
    columns = runtime_columns or []
    for candidate in ["datetime", "forecast_datetime", "created_at", "updated_at", "date"]:
        if candidate in columns:
            return candidate
    for name in columns:
        lower = name.lower()
        if "time" in lower or "date" in lower:
            return name
    return ""


def _freshness_for_table(engine: Any, inspector: Any, table_name: str) -> dict[str, Any]:
    table = _clean_identifier(table_name)
    if table not in CORE_DATASETS:
        return {"table_name": table, "available": False, "status": "unknown_table", "not_found_reason": "该表不在 P1 数据目录中。"}
    try:
        names = set(inspector.get_table_names()) | set(inspector.get_view_names())
    except Exception as exc:
        return {"table_name": table, "available": False, "status": "schema_error", "not_found_reason": f"读取数据库元数据失败：{exc}"}
    if table not in names:
        return {"table_name": table, "available": False, "status": "missing_table", "not_found_reason": "数据库中未找到该表或视图。"}
    try:
        columns = [str(col.get("name")) for col in inspector.get_columns(table) if col.get("name")]
    except Exception as exc:
        return {"table_name": table, "available": False, "status": "column_error", "not_found_reason": f"读取字段失败：{exc}"}
    dialect = engine.dialect.name
    dt_col = _pick_datetime_field(table, columns)
    q_table = _quote_identifier(table, dialect)
    if dt_col and dt_col in columns:
        q_dt = _quote_identifier(dt_col, dialect)
        sql = f"""
            SELECT
                COUNT(*) AS row_count,
                MIN({q_dt}) AS min_datetime,
                MAX({q_dt}) AS max_datetime,
                SUM(CASE WHEN {q_dt} IS NULL THEN 1 ELSE 0 END) AS missing_time_count
            FROM {q_table}
        """
    else:
        sql = f"SELECT COUNT(*) AS row_count FROM {q_table}"
    try:
        with engine.connect() as conn:
            row = conn.execute(text(sql)).mappings().first() or {}
    except Exception as exc:
        return {"table_name": table, "available": False, "status": "query_error", "not_found_reason": f"读取表失败：{exc}"}
    item = {
        "table_name": table,
        "display_name": CORE_DATASETS[table].get("display_name"),
        "available": True,
        "status": "ok",
        "datetime_field": dt_col,
        "min_datetime": row.get("min_datetime"),
        "max_datetime": row.get("max_datetime"),
        "row_count": int(row.get("row_count") or 0),
        "missing_time_count": int(row.get("missing_time_count") or 0),
        "fields_mapped": [field.get("field_name") for field in CORE_DATASETS[table].get("fields") or []],
        "query_summary": "按数据目录登记的时间字段执行 min/max/count 新鲜度检查。",
    }
    if not item["row_count"]:
        item["status"] = "empty"
        item["not_found_reason"] = "表存在但没有记录。"
    return jsonable(item)


def get_data_freshness_report(tables: list[str] | None = None) -> dict[str, Any]:
    selected = [_clean_identifier(table) for table in (tables or []) if str(table or "").strip()]
    selected = list(dict.fromkeys(selected))[:20] or list(CORE_DATASETS)
    engine = database_engine()
    if engine is None:
        items = [
            {
                "table_name": table,
                "display_name": (CORE_DATASETS.get(table) or {}).get("display_name"),
                "available": False,
                "status": "database_unavailable",
                "datetime_field": (CORE_DATASETS.get(table) or {}).get("time_field") or "",
                "not_found_reason": "数据库未启用或连接不可用。",
            }
            for table in selected
        ]
        return {"available": False, "catalog_version": CATALOG_VERSION, "items": items, "message": "数据库未启用或连接不可用。"}
    try:
        inspector = inspect(engine)
    except Exception as exc:
        items = [{"table_name": table, "available": False, "status": "schema_error", "not_found_reason": f"读取数据库元数据失败：{exc}"} for table in selected]
        return {"available": False, "catalog_version": CATALOG_VERSION, "items": items}
    items = [_freshness_for_table(engine, inspector, table) for table in selected]
    return {
        "available": any(item.get("available") for item in items),
        "catalog_version": CATALOG_VERSION,
        "checked_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "items": items,
        "summary": {
            "ok": sum(1 for item in items if item.get("status") == "ok"),
            "missing_or_unavailable": sum(1 for item in items if item.get("status") != "ok"),
            "tables_checked": len(items),
        },
    }


def _strip_trailing_semicolon(sql: str) -> str:
    value = str(sql or "").strip()
    if value.endswith(";"):
        value = value[:-1].strip()
    return value


def _extract_table_refs(sql: str) -> list[str]:
    refs: list[str] = []
    for match in TABLE_REF_RE.finditer(sql):
        raw = match.group(1)
        if raw.strip().startswith("("):
            continue
        refs.append(_clean_identifier(raw))
    return list(dict.fromkeys(refs))


def validate_read_only_sql(sql: str) -> tuple[bool, str, list[str], str]:
    normalized = _strip_trailing_semicolon(sql)
    lowered = normalized.lower().strip()
    if not normalized:
        return False, normalized, [], "SQL 不能为空。"
    if "--" in normalized or "/*" in normalized or "*/" in normalized:
        return False, normalized, [], "只读 SQL 服务不接受注释，避免注释隐藏多语句或危险操作。"
    if ";" in normalized:
        return False, normalized, [], "只读 SQL 服务只允许单条 SELECT 语句。"
    if not lowered.startswith("select"):
        return False, normalized, [], "只读 SQL 服务只允许 SELECT 查询。"
    forbidden = FORBIDDEN_SQL_RE.search(normalized)
    if forbidden:
        return False, normalized, [], f"SQL 包含禁止关键字：{forbidden.group(1)}。"
    forbidden_schema = FORBIDDEN_SCHEMA_RE.search(normalized)
    if forbidden_schema:
        return False, normalized, [], f"SQL 访问了不允许的系统 schema：{forbidden_schema.group(1)}。"
    forbidden_table = FORBIDDEN_TABLE_RE.search(normalized)
    if forbidden_table:
        return False, normalized, [], f"SQL 访问了不允许的敏感表：{forbidden_table.group(1)}。"
    dangerous_function = DANGEROUS_FUNCTION_RE.search(normalized)
    if dangerous_function:
        return False, normalized, [], f"SQL 包含不允许的危险函数：{dangerous_function.group(1)}。"
    refs = _extract_table_refs(normalized)
    if " from " in f" {lowered} " and not refs:
        return False, normalized, [], "暂不支持无法识别来源表的复杂 SQL。"
    disallowed = [table for table in refs if table not in ALLOWED_READ_TABLES]
    if disallowed:
        return False, normalized, refs, f"SQL 访问了未纳入 P1 数据目录或不允许查数的表：{', '.join(disallowed)}。"
    return True, normalized, refs, ""


def _safe_params(params: dict[str, Any] | None) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in (params or {}).items():
        if not SAFE_IDENTIFIER_RE.fullmatch(str(key)):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[str(key)] = value
    return safe


def _time_range_from_rows(rows: list[dict[str, Any]], fields: list[str]) -> dict[str, Any]:
    time_fields = [
        field
        for field in fields
        if field.lower()
        in {
            "datetime",
            "forecast_datetime",
            "date",
            "created_at",
            "updated_at",
            "started_at",
            "finished_at",
            "min_datetime",
            "max_datetime",
        }
    ]
    values: list[str] = []
    primary_field = time_fields[0] if time_fields else ""
    for row in rows:
        value = row.get(primary_field) if primary_field else None
        if value is not None:
            values.append(str(value))
    if not values:
        return {"start": None, "end": None, "field": primary_field}
    return {"start": min(values), "end": max(values), "field": primary_field}


def execute_read_only_sql(sql: str, params: dict[str, Any] | None = None, limit: int = 100) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 100), 500))
    valid, normalized, table_refs, reason = validate_read_only_sql(sql)
    if not valid:
        return {
            "available": False,
            "safe": False,
            "sql": normalized,
            "tables": table_refs,
            "columns": [],
            "records": [],
            "row_count": 0,
            "not_found_reason": reason,
            "query_summary": "SQL 安全校验未通过，未执行数据库查询。",
        }
    engine = database_engine()
    if engine is None:
        return {
            "available": False,
            "safe": True,
            "sql": normalized,
            "tables": table_refs,
            "columns": [],
            "records": [],
            "row_count": 0,
            "not_found_reason": "数据库未启用或连接不可用。",
            "query_summary": "SQL 已通过只读校验，但没有可用数据库连接。",
        }
    safe_params = _safe_params(params)
    safe_params["__p1_limit"] = safe_limit
    wrapped_sql = f"SELECT * FROM ({normalized}) AS p1_readonly_query LIMIT :__p1_limit"
    try:
        with engine.connect() as conn:
            result = conn.execute(text(wrapped_sql), safe_params)
            rows = [jsonable(dict(row)) for row in result.mappings().all()]
            columns = list(result.keys())
    except Exception as exc:
        return {
            "available": False,
            "safe": True,
            "sql": normalized,
            "tables": table_refs,
            "columns": [],
            "records": [],
            "row_count": 0,
            "not_found_reason": f"查询执行失败：{exc}",
            "query_summary": "SQL 已通过只读校验，但数据库执行失败。",
        }
    time_range = _time_range_from_rows(rows, columns)
    return {
        "available": bool(rows),
        "safe": True,
        "sql": normalized,
        "tables": table_refs,
        "columns": columns,
        "records": rows,
        "row_count": len(rows),
        "limit": safe_limit,
        "time_range": time_range,
        "not_found_reason": "" if rows else "查询成功但未返回记录，可能是表为空或过滤条件无匹配。",
        "query_summary": f"执行只读 SELECT，涉及表 {', '.join(table_refs) if table_refs else '常量查询'}，返回前 {safe_limit} 行。",
    }


def _extract_dates(question: str) -> list[str]:
    dates: list[str] = []
    for year, month, day in DATE_RE.findall(question or ""):
        if day:
            dates.append(f"{year}-{int(month):02d}-{int(day):02d}")
        else:
            dates.append(f"{year}-{int(month):02d}-01")
    return dates[:2]


def _limit_from_question(question: str, fallback: int = 5) -> int:
    match = re.search(r"(?:前|最新|最近)?\s*(\d{1,3})\s*(?:条|行|个|笔)", question or "")
    if match:
        return max(1, min(int(match.group(1)), 50))
    return fallback


def _extract_tables_from_question(question: str) -> list[str]:
    lowered = (question or "").lower()
    matches = [table for table in CORE_DATASETS if table in lowered]
    if matches:
        return matches[:3]
    compact = re.sub(r"\s+", "", question or "")
    scored: list[tuple[int, str]] = []
    for table, meta in CORE_DATASETS.items():
        score = 0
        for alias in meta.get("aliases") or []:
            if str(alias).lower() in lowered or str(alias) in compact:
                score += 2
        if str(meta.get("display_name") or "") in compact:
            score += 3
        if score:
            scored.append((score, table))
    scored.sort(reverse=True)
    return [table for _, table in scored[:3]]


def _looks_like_catalog_question(question: str) -> bool:
    compact = re.sub(r"\s+", "", question or "")
    return any(token in compact for token in ["核心业务表", "有哪些表", "数据目录", "当前数据库有哪些", "数据库有哪些"])


def _looks_like_empty_table_question(question: str) -> bool:
    compact = re.sub(r"\s+", "", question or "")
    return any(token in compact for token in ["哪些表为空", "哪些表当前为空", "空表", "没有数据的表"])


def _looks_like_prediction_readiness_question(question: str) -> bool:
    compact = re.sub(r"\s+", "", question or "")
    return "数据" in compact and "支撑预测" in compact


def _catalog_query_result() -> dict[str, Any]:
    datasets = get_data_catalog(include_runtime=False).get("datasets") or []
    records = [
        {
            "table_name": item.get("table_name"),
            "display_name": item.get("display_name"),
            "business_domain": item.get("business_domain"),
            "time_field": item.get("time_field"),
            "grain": item.get("grain"),
            "exists": (item.get("runtime") or {}).get("exists"),
        }
        for item in datasets
    ]
    return jsonable(
        {
            "tool": "query_business_data",
            "available": True,
            "safe": True,
            "query_type": "data_catalog_list",
            "table_name": "p1_data_catalog",
            "display_name": "P1 数据目录",
            "fields": ["table_name", "display_name", "business_domain", "time_field", "grain", "exists"],
            "time_range": {"start": None, "end": None, "field": ""},
            "query_summary": "读取 P1 数据目录，列出允许 AI 查数的核心业务表及字段口径。",
            "records": records,
            "row_count": len(records),
            "columns": ["table_name", "display_name", "business_domain", "time_field", "grain", "exists"],
            "not_found_reason": "",
            "evidence": [
                {
                    "source": "p1_data_catalog",
                    "fields": ["table_name", "display_name", "business_domain", "time_field"],
                    "time_range": {"start": None, "end": None, "field": ""},
                    "operation": "catalog_list",
                    "query_summary": "列出 P1 数据目录核心业务表。",
                    "available": True,
                }
            ],
        }
    )


def _empty_table_query_result() -> dict[str, Any]:
    report = get_data_freshness_report()
    items = report.get("items") or []
    empty_items = [item for item in items if item.get("available") and int(item.get("row_count") or 0) == 0]
    records = [
        {
            "table_name": item.get("table_name"),
            "display_name": item.get("display_name"),
            "status": item.get("status"),
            "datetime_field": item.get("datetime_field"),
            "row_count": item.get("row_count"),
            "not_found_reason": item.get("not_found_reason") or "",
        }
        for item in empty_items
    ]
    return jsonable(
        {
            "tool": "query_business_data",
            "available": True,
            "safe": True,
            "query_type": "empty_table_scan",
            "table_name": "p1_data_catalog",
            "display_name": "P1 数据目录",
            "fields": ["table_name", "display_name", "status", "datetime_field", "row_count", "not_found_reason"],
            "time_range": {"start": None, "end": None, "field": ""},
            "query_summary": "扫描 P1 数据目录登记表的新鲜度结果，筛选记录数为 0 的空表。",
            "records": records,
            "row_count": len(records),
            "columns": ["table_name", "display_name", "status", "datetime_field", "row_count", "not_found_reason"],
            "not_found_reason": "" if records else "未发现已建表且记录数为 0 的空表；未建表或不可用表需查看 freshness 明细。",
            "freshness_summary": report.get("summary") or {},
            "evidence": [
                {
                    "source": "p1_data_freshness",
                    "fields": ["table_name", "row_count", "status"],
                    "time_range": {"start": None, "end": None, "field": ""},
                    "operation": "empty_table_scan",
                    "query_summary": "按 row_count=0 判断空表。",
                    "available": True,
                }
            ],
        }
    )


def _prediction_readiness_result() -> dict[str, Any]:
    required = ["raw_market", "raw_load", "raw_weather", "model_master_table", "forecast_results"]
    report = get_data_freshness_report(required)
    items = report.get("items") or []
    blocking = [item for item in items if not item.get("available") or int(item.get("row_count") or 0) <= 0]
    records = [
        {
            "table_name": item.get("table_name"),
            "display_name": item.get("display_name"),
            "status": item.get("status"),
            "datetime_field": item.get("datetime_field"),
            "min_datetime": item.get("min_datetime"),
            "max_datetime": item.get("max_datetime"),
            "row_count": item.get("row_count"),
            "not_found_reason": item.get("not_found_reason") or "",
        }
        for item in items
    ]
    ready = not blocking
    return jsonable(
        {
            "tool": "query_business_data",
            "available": True,
            "safe": True,
            "query_type": "prediction_readiness",
            "readiness_status": "ready" if ready else "partial",
            "table_name": ",".join(required),
            "display_name": "预测数据支撑检查",
            "fields": ["table_name", "datetime_field", "min_datetime", "max_datetime", "row_count", "status"],
            "time_range": {"start": None, "end": None, "field": "per_table_datetime_field"},
            "query_summary": "检查市场电价、负荷、天气、建模主表和预测结果表的新鲜度与记录数，判断是否具备预测支撑数据。",
            "records": records,
            "row_count": len(records),
            "columns": ["table_name", "display_name", "status", "datetime_field", "min_datetime", "max_datetime", "row_count", "not_found_reason"],
            "not_found_reason": "" if ready else "部分预测支撑表不可用或记录数为 0，需先完成数据同步/特征工程/预测入库。",
            "freshness_summary": report.get("summary") or {},
            "evidence": [
                {
                    "source": "p1_prediction_readiness",
                    "fields": ["table_name", "datetime_field", "min_datetime", "max_datetime", "row_count"],
                    "time_range": {"start": None, "end": None, "field": "per_table_datetime_field"},
                    "operation": "prediction_readiness_check",
                    "query_summary": "检查预测依赖核心表的新鲜度和记录数。",
                    "available": True,
                }
            ],
        }
    )


def _field_names(table: str) -> list[str]:
    return [str(field.get("field_name")) for field in (CORE_DATASETS.get(table) or {}).get("fields") or [] if field.get("field_name")]


def _default_fields_for_query(table: str) -> list[str]:
    fields = _field_names(table)
    preferred = []
    time_field = str((CORE_DATASETS.get(table) or {}).get("time_field") or "")
    if time_field in fields:
        preferred.append(time_field)
    for field in fields:
        if field not in preferred:
            preferred.append(field)
    return preferred[:6] or ["*"]


def _fields_from_question(table: str, question: str, requested_fields: list[str] | None = None) -> list[str]:
    fields = _field_names(table)
    if not fields:
        return ["*"]
    requested = [str(field).strip() for field in (requested_fields or []) if str(field).strip()]
    selected = [field for field in requested if field in fields]
    lowered = (question or "").lower()
    token_map = {
        "电价": ["predicted_price", "corrected_predicted_price", "da_price", "rt_price", "lmp"],
        "价格": ["predicted_price", "corrected_predicted_price", "da_price", "rt_price", "lmp"],
        "日前": ["da_price"],
        "实时": ["rt_price"],
        "负荷": ["forecast_load", "actual_load"],
        "天气": ["temperature", "humidity", "wind_speed", "precipitation"],
        "温度": ["temperature"],
        "气温": ["temperature"],
        "风险": ["risk_level", "spike_risk_prob"],
        "概率": ["spike_risk_prob"],
        "误差": ["abs_error", "test_mae", "test_rmse"],
        "模型": ["model_version", "status", "is_active"],
    }
    for token, candidates in token_map.items():
        if token in lowered or token in (question or ""):
            selected.extend(candidate for candidate in candidates if candidate in fields)
    for field in fields:
        if field.lower() in lowered:
            selected.append(field)
    time_field = str((CORE_DATASETS.get(table) or {}).get("time_field") or "")
    if time_field and time_field in fields:
        selected.insert(0, time_field)
    selected = list(dict.fromkeys(selected))
    return selected[:8] or _default_fields_for_query(table)


def _where_for_dates(table: str, question: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    dates = _extract_dates(question)
    time_field = str((CORE_DATASETS.get(table) or {}).get("time_field") or "")
    if not dates or not time_field:
        return "", {}, {"start": None, "end": None, "field": time_field}
    params: dict[str, Any] = {"start_date": dates[0]}
    if len(dates) >= 2:
        params["end_date"] = dates[1]
        return f" WHERE {time_field} >= :start_date AND {time_field} <= :end_date", params, {"start": dates[0], "end": dates[1], "field": time_field}
    return f" WHERE {time_field} >= :start_date", params, {"start": dates[0], "end": None, "field": time_field}


def query_business_data(
    question: str,
    tables: list[str] | None = None,
    fields: list[str] | None = None,
    limit: int | None = None,
    **_: Any,
) -> dict[str, Any]:
    selected_tables = [_clean_identifier(table) for table in (tables or []) if str(table or "").strip()]
    selected_tables = selected_tables or _extract_tables_from_question(question)
    if not selected_tables:
        if _looks_like_catalog_question(question):
            return _catalog_query_result()
        if _looks_like_empty_table_question(question):
            return _empty_table_query_result()
        if _looks_like_prediction_readiness_question(question):
            return _prediction_readiness_result()
        return {
            "tool": "query_business_data",
            "available": False,
            "table_name": "",
            "fields": [],
            "time_range": {"start": None, "end": None, "field": ""},
            "query_summary": "未能从问题中识别要查询的数据表。",
            "not_found_reason": "请明确表名或业务数据域，例如 raw_weather、forecast_results、预测结果、天气数据。",
            "evidence": [],
        }
    table = selected_tables[0]
    if table in {"users", "audit_logs"}:
        return {
            "tool": "query_business_data",
            "available": False,
            "safe": False,
            "table_name": table,
            "fields": [],
            "time_range": {"start": None, "end": None, "field": ""},
            "query_summary": f"请求查询敏感表 {table}，已在 AI 查数入口拒绝执行。",
            "not_found_reason": f"{table} 属于敏感/管理表，不允许通过 AI 查数访问。",
            "evidence": [{"source": table, "available": False, "operation": "sensitive_table_block"}],
        }
    if table not in CORE_DATASETS:
        return {
            "tool": "query_business_data",
            "available": False,
            "table_name": table,
            "fields": [],
            "time_range": {"start": None, "end": None, "field": ""},
            "query_summary": f"请求查询表 {table}。",
            "not_found_reason": "该表不在 P1 数据目录中，或不允许通过 AI 查数访问。",
            "evidence": [{"source": table, "available": False, "operation": "read_only_sql"}],
        }
    selected_fields = _fields_from_question(table, question, fields)
    safe_fields = [_quote_identifier(field, "postgresql") for field in selected_fields if field != "*"]
    select_expr = ", ".join(safe_fields) if safe_fields else "*"
    where_sql, params, requested_range = _where_for_dates(table, question)
    safe_limit = max(1, min(int(limit or _limit_from_question(question)), 50))
    q_table = _quote_identifier(table, "postgresql")
    q_order = _quote_identifier(str((CORE_DATASETS.get(table) or {}).get("default_order_field") or (CORE_DATASETS.get(table) or {}).get("time_field") or selected_fields[0]), "postgresql")
    lowered = question.lower()
    if any(token in question for token in ["多少条", "几条", "记录数", "总数", "count"]) or "count" in lowered:
        sql = f"SELECT COUNT(*) AS row_count FROM {q_table}{where_sql}"
        query_type = "count"
    elif any(token in question for token in ["平均", "均值", "均价", "最高", "最低", "avg", "max", "min"]) or any(token in lowered for token in ["avg", "max", "min"]):
        numeric_field = next((field for field in selected_fields if field not in {"datetime", "created_at", "updated_at", "model_version", "status", "risk_level", "node", "run_id"}), "")
        if not numeric_field:
            numeric_field = next((field for field in _field_names(table) if any(key in field for key in ["price", "load", "temperature", "error", "importance", "prob"])), "")
        if numeric_field:
            q_metric = _quote_identifier(numeric_field, "postgresql")
            time_field = str((CORE_DATASETS.get(table) or {}).get("time_field") or "")
            time_select = f", MIN({_quote_identifier(time_field, 'postgresql')}) AS min_datetime, MAX({_quote_identifier(time_field, 'postgresql')}) AS max_datetime" if time_field else ""
            sql = f"SELECT COUNT(*) AS row_count{time_select}, AVG({q_metric}) AS avg_value, MIN({q_metric}) AS min_value, MAX({q_metric}) AS max_value FROM {q_table}{where_sql}"
            selected_fields = [time_field, numeric_field] if time_field else [numeric_field]
            query_type = "aggregate"
        else:
            sql = f"SELECT {select_expr} FROM {q_table}{where_sql} ORDER BY {q_order} DESC"
            query_type = "latest_rows"
    else:
        sql = f"SELECT {select_expr} FROM {q_table}{where_sql} ORDER BY {q_order} DESC"
        query_type = "latest_rows"
    result = execute_read_only_sql(sql, params=params, limit=safe_limit)
    time_range = result.get("time_range") or requested_range
    if requested_range.get("start"):
        time_range = {**time_range, "requested_start": requested_range.get("start"), "requested_end": requested_range.get("end")}
    available = bool(result.get("available"))
    query_summary = {
        "count": f"统计 {table} 的记录数。",
        "aggregate": f"按 {table} 计算数值字段聚合，并返回覆盖时间范围。",
        "latest_rows": f"查询 {table} 最新 {safe_limit} 条记录。",
    }.get(query_type, f"查询 {table}。")
    evidence = [
        {
            "source": table,
            "fields": selected_fields,
            "time_range": time_range,
            "operation": "read_only_sql",
            "query_summary": query_summary,
            "available": available,
        }
    ]
    return jsonable(
        {
            "tool": "query_business_data",
            "available": available,
            "safe": result.get("safe"),
            "table_name": table,
            "display_name": (CORE_DATASETS.get(table) or {}).get("display_name"),
            "fields": selected_fields,
            "time_range": time_range,
            "query_summary": query_summary,
            "sql": result.get("sql"),
            "records": result.get("records") or [],
            "row_count": result.get("row_count") or 0,
            "columns": result.get("columns") or [],
            "not_found_reason": "" if available else (result.get("not_found_reason") or "未查到匹配数据。"),
            "evidence": evidence,
        }
    )
