from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import MetaData, Table, text

from database_utils import (
    apply_database_migrations,
    create_database_engine,
    get_database_config,
    normalize_dataframe_for_sql,
)

from ..config import PROJECT_ROOT, project_config
from ..data_access import artifact_inventory, database_engine, jsonable, load_latest_forecast, model_status, price_column


TARIFF_DATA_DIR = PROJECT_ROOT / "electricity_tariff_output" / "02_processed_data"


def _log(log, message: str) -> None:
    if log:
        log(message)


def _dumps(value: Any) -> str:
    return json.dumps(jsonable(value), ensure_ascii=False, default=str)


def _to_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        text_value = str(value).strip().replace(",", "")
        if not text_value:
            return None
        return float(text_value)
    except Exception:
        return None


def _to_datetime(value: Any) -> Any:
    dt = pd.to_datetime(value, errors="coerce")
    return dt.to_pydatetime() if pd.notna(dt) else None


def _to_date(value: Any) -> Any:
    dt = pd.to_datetime(value, errors="coerce")
    return dt.date() if pd.notna(dt) else None


def _read_csv(name: str) -> pd.DataFrame:
    path = TARIFF_DATA_DIR / name
    if not path.exists() or path.stat().st_size <= 0:
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


def _engine_or_none(log=None):
    engine = database_engine()
    if engine is not None:
        return engine
    cfg = project_config()
    if not get_database_config(cfg).enabled:
        _log(log, "数据库未启用，跳过事实表与电价规则入库。")
        return None
    apply_database_migrations(cfg, log=log)
    return create_database_engine(cfg)


def _quote_identifier(name: str, dialect: str) -> str:
    if dialect == "postgresql":
        return '"' + str(name).replace('"', '""') + '"'
    return "`" + str(name).replace("`", "``") + "`"


def _normalize_json_columns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    json_columns = {
        "summary_json",
        "raw_json",
        "metrics_json",
        "command_json",
        "payload_json",
        "tools_json",
        "evidence_json",
        "guard_result_json",
        "trace_json",
        "metadata_json",
        "content_json",
    }
    normalized: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for column in list(item):
            if column in json_columns and isinstance(item[column], str):
                try:
                    item[column] = json.loads(item[column])
                except Exception:
                    item[column] = item[column] or None
        normalized.append(item)
    return normalized


def _insert_rows(engine, conn, table_name: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    if engine.dialect.name == "postgresql":
        table = Table(table_name, MetaData(), autoload_with=engine)
        target_columns = set(table.c.keys())
        payload = [
            {key: value for key, value in row.items() if key in target_columns}
            for row in _normalize_json_columns(rows)
        ]
        if payload:
            conn.execute(table.insert(), payload)
        return len(payload)
    normalize_dataframe_for_sql(pd.DataFrame(rows)).to_sql(
        table_name, conn, if_exists="append", index=False, chunksize=1000, method="multi"
    )
    return len(rows)


def _replace_table(engine, table_name: str, rows: list[dict[str, Any]], log=None) -> int:
    dialect = engine.dialect.name
    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {_quote_identifier(table_name, dialect)}"))
        inserted = _insert_rows(engine, conn, table_name, rows)
    _log(log, f"已刷新事实表：{table_name}，记录数：{inserted}")
    return int(inserted)


def sync_forecast_facts(engine=None, log=None) -> dict[str, Any]:
    engine = engine or _engine_or_none(log)
    if engine is None:
        return {"available": False, "message": "数据库未启用"}

    payload = load_latest_forecast()
    records = payload.get("records") or []
    df = pd.DataFrame(records)
    pcol = price_column(df) if not df.empty else None
    forecast_times = pd.to_datetime(df["datetime"], errors="coerce") if "datetime" in df.columns else pd.Series(dtype="datetime64[ns]")
    run_id = str(payload.get("run_id") or "latest")
    run_row = {
        "run_id": run_id,
        "source_path": payload.get("source"),
        "forecast_start": forecast_times.min().to_pydatetime() if not forecast_times.empty and pd.notna(forecast_times.min()) else None,
        "forecast_end": forecast_times.max().to_pydatetime() if not forecast_times.empty and pd.notna(forecast_times.max()) else None,
        "generated_at": _to_datetime(payload.get("generated_at")),
        "row_count": len(df),
        "status": "ready" if payload.get("available") else "missing",
        "summary_json": _dumps(payload.get("summary") or {}),
    }
    result_rows: list[dict[str, Any]] = []
    if not df.empty:
        for idx, row in df.iterrows():
            raw = row.to_dict()
            result_rows.append(
                {
                    "run_id": run_id,
                    "forecast_datetime": _to_datetime(raw.get("datetime")),
                    "predicted_price": _to_float(raw.get(pcol)) if pcol else None,
                    "corrected_predicted_price": _to_float(raw.get("corrected_predicted_price")),
                    "risk_level": raw.get("risk_level"),
                    "spike_risk_prob": _to_float(raw.get("spike_risk_prob") or raw.get("尖峰风险概率")),
                    "forecast_load": _to_float(raw.get("forecast_load") or raw.get("预测负荷")),
                    "source_row": int(idx) + 1,
                    "raw_json": _dumps(raw),
                }
            )

    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text('DELETE FROM "forecast_runs" WHERE "run_id" = :run_id'), {"run_id": run_id})
            _insert_rows(engine, conn, "forecast_runs", [run_row])
            _insert_rows(engine, conn, "forecast_results", result_rows)
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO forecast_runs (
                        run_id, source_path, forecast_start, forecast_end, generated_at,
                        row_count, status, summary_json
                    )
                    VALUES (
                        :run_id, :source_path, :forecast_start, :forecast_end, :generated_at,
                        :row_count, :status, :summary_json
                    )
                    ON DUPLICATE KEY UPDATE
                        source_path = VALUES(source_path),
                        forecast_start = VALUES(forecast_start),
                        forecast_end = VALUES(forecast_end),
                        generated_at = VALUES(generated_at),
                        row_count = VALUES(row_count),
                        status = VALUES(status),
                        summary_json = VALUES(summary_json)
                    """
                ),
                run_row,
            )
            conn.execute(text("DELETE FROM `forecast_results` WHERE `run_id` = :run_id"), {"run_id": run_id})
            _insert_rows(engine, conn, "forecast_results", result_rows)
    _log(log, f"已同步预测事实：{run_id}，明细 {len(result_rows)} 行")
    return {"available": True, "run_id": run_id, "forecast_results": len(result_rows)}


def sync_model_facts(engine=None, log=None) -> dict[str, Any]:
    engine = engine or _engine_or_none(log)
    if engine is None:
        return {"available": False, "message": "数据库未启用"}

    status = model_status()
    versions = status.get("versions") or []
    if not versions:
        versions = artifact_inventory()
    version_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    for index, item in enumerate(versions):
        version = str(item.get("model_version") or item.get("version") or f"model_{index + 1}")
        is_active = int(bool(item.get("is_active"))) if "is_active" in item else (1 if index == 0 else 0)
        version_rows.append(
            {
                "model_version": version,
                "model_name": item.get("base_model_name") or item.get("model_name") or "price_forecast_model",
                "model_type": item.get("model_type") or "forecast",
                "artifact_path": item.get("artifact_path"),
                "status": item.get("status") or ("active" if is_active else "candidate"),
                "is_active": is_active,
                "metrics_json": _dumps(item),
                "created_at": _to_datetime(item.get("created_at") or item.get("activated_at")),
            }
        )
        metric_rows.append(
            {
                "model_version": version,
                "metric_date": _to_date(item.get("created_at") or datetime.now()),
                "mae": _to_float(item.get("test_mae") or item.get("mae")),
                "rmse": _to_float(item.get("test_rmse") or item.get("rmse")),
                "r2": _to_float(item.get("test_r2") or item.get("r2")),
                "mape": _to_float(item.get("mape")),
                "peak_error": _to_float(item.get("peak_rmse") or item.get("spike_rmse") or item.get("peak_error")),
                "sample_count": int(item.get("sample_count") or 0) if str(item.get("sample_count") or "").isdigit() else None,
                "metrics_json": _dumps(item),
            }
        )

    with engine.begin() as conn:
        dialect = engine.dialect.name
        conn.execute(text(f"DELETE FROM {_quote_identifier('model_versions', dialect)}"))
        conn.execute(text(f"DELETE FROM {_quote_identifier('model_metrics', dialect)}"))
        _insert_rows(engine, conn, "model_versions", version_rows)
        _insert_rows(engine, conn, "model_metrics", metric_rows)
    _log(log, f"已同步模型事实：版本 {len(version_rows)} 条，指标 {len(metric_rows)} 条")
    return {"available": True, "model_versions": len(version_rows), "model_metrics": len(metric_rows)}


def _pv_tariff_rows() -> list[dict[str, Any]]:
    df = _read_csv("pv_tariff_rules.csv")
    rows = []
    for idx, row in df.iterrows():
        raw = row.to_dict()
        rows.append(
            {
                "province": raw.get("province"),
                "city": raw.get("city"),
                "start_date": _to_date(raw.get("start_date")),
                "end_date": _to_date(raw.get("end_date")),
                "on_grid_price": _to_float(raw.get("on_grid_price")),
                "subsidy_start_date": _to_date(raw.get("subsidy_start_date")),
                "subsidy_years": _to_float(raw.get("subsidy_years")),
                "subsidy_price": _to_float(raw.get("subsidy_price")),
                "total_price": _to_float(raw.get("total_price")),
                "remark": raw.get("remark"),
                "source_sheet": raw.get("source_sheet"),
                "source_row": int(raw.get("source_row") or idx + 1),
                "raw_json": _dumps(raw),
            }
        )
    return rows


def _policy_rows() -> list[dict[str, Any]]:
    df = _read_csv("pv_policy_files.csv")
    rows = []
    for idx, row in df.iterrows():
        raw = row.to_dict()
        rows.append(
            {
                "doc_id": str(raw.get("id") or ""),
                "title": raw.get("doc_title"),
                "doc_number": raw.get("doc_number"),
                "publish_date": _to_date(raw.get("publish_date")),
                "province": raw.get("province"),
                "city": raw.get("city"),
                "summary": raw.get("summary") or raw.get("related_clauses"),
                "source_file": raw.get("doc_image"),
                "source_sheet": raw.get("source_sheet"),
                "source_row": int(raw.get("source_row") or idx + 1),
                "raw_json": _dumps(raw),
            }
        )
    return rows


def _station_check_rows() -> list[dict[str, Any]]:
    df = _read_csv("pv_station_tariff_check.csv")
    rows = []
    for idx, row in df.iterrows():
        raw = row.to_dict()
        rows.append(
            {
                "station_id": str(raw.get("station_id") or ""),
                "station_name": raw.get("station_name") or raw.get("户主姓名"),
                "province": raw.get("province"),
                "city": raw.get("city"),
                "district": raw.get("区"),
                "grid_date": _to_date(raw.get("grid_connect_date")),
                "system_price": _to_float(raw.get("system_power_price")),
                "grid_price": _to_float(raw.get("power_bureau_price")),
                "national_subsidy": _to_float(raw.get("供电局国补")),
                "provincial_subsidy": _to_float(raw.get("供电局省补")),
                "difference_flag": raw.get("是否已纠正（系统或国电局达成一致）"),
                "remark": raw.get("explanation") or raw.get("difference"),
                "source_sheet": raw.get("source_sheet"),
                "source_row": int(raw.get("source_row") or idx + 1),
                "raw_json": _dumps(raw),
            }
        )
    return rows


def _market_power_rows() -> list[dict[str, Any]]:
    df = _read_csv("market_power_price_rules.csv")
    rows = []
    for idx, row in df.iterrows():
        raw = row.to_dict()
        rows.append(
            {
                "business_month": str(raw.get("business_month") or ""),
                "province": raw.get("province"),
                "city": raw.get("city"),
                "power_price": _to_float(raw.get("market_electricity_price") or raw.get("desulfurized_coal_price")),
                "auxiliary_cost": _to_float(raw.get("辅助分摊费用")),
                "total_price": _to_float(raw.get("comprehensive_price")),
                "remark": raw.get("备注") or raw.get("grid_period"),
                "source_sheet": raw.get("source_sheet"),
                "source_row": int(raw.get("source_row") or idx + 1),
                "raw_json": _dumps(raw),
            }
        )
    return rows


def _southern_grid_rows() -> list[dict[str, Any]]:
    df = _read_csv("southern_grid_tax_rules.csv")
    rows = []
    evidence_cols = ["电费结算单", "发票", "泰极打款截图", "完税证明", "完税凭证2", "代理商垫付凭证", "政府文件", "tax_rate_faq", "供电局截图"]
    for idx, row in df.iterrows():
        raw = row.to_dict()
        rows.append(
            {
                "province": raw.get("province"),
                "city": raw.get("city"),
                "district": raw.get("district"),
                "station_id": str(raw.get("举例电站编码") or ""),
                "station_name": raw.get("户主姓名"),
                "deduction_rate": _to_float(raw.get("（暂不准）税率") or raw.get("vat_rate")),
                "payment_formula": raw.get("回款金额公式"),
                "tax_remark": raw.get("is_substitute_withholding") or raw.get("withholding_entity"),
                "evidence_json": _dumps({col: raw.get(col) for col in evidence_cols if raw.get(col)}),
                "source_sheet": raw.get("source_sheet"),
                "source_row": int(raw.get("source_row") or idx + 1),
                "raw_json": _dumps(raw),
            }
        )
    return rows


def _period_rule_rows() -> list[dict[str, Any]]:
    df = _read_csv("pv_tariff_period_rules.csv")
    rows = []
    for idx, row in df.iterrows():
        raw = row.to_dict()
        rows.append(
            {
                "province_source": raw.get("province_省份-2"),
                "region_name": raw.get("region_地区"),
                "province": raw.get("province_省份"),
                "city": raw.get("地级市"),
                "combination": raw.get("combination_组合"),
                "grid_type": raw.get("grid_type_电网类型"),
                "period_1_on_grid_price": _to_float(raw.get("on_grid_price_电价")),
                "period_1_subsidy_price": _to_float(raw.get("subsidy_price_补贴价")),
                "period_1_total_price": _to_float(raw.get("total_price_总价")),
                "period_2_on_grid_price": _to_float(raw.get("on_grid_price_电价.1")),
                "period_2_subsidy_price": _to_float(raw.get("subsidy_price_补贴价.1")),
                "period_2_total_price": _to_float(raw.get("total_price_总价.1")),
                "period_3_on_grid_price": _to_float(raw.get("on_grid_price_电价.2")),
                "period_3_subsidy_price": _to_float(raw.get("subsidy_price_补贴价.2")),
                "period_3_total_price": _to_float(raw.get("total_price_总价.2")),
                "policy_doc_no": raw.get("policy_doc_no_发改文件号"),
                "doc_image": raw.get("文件截图"),
                "source_sheet": raw.get("source_sheet"),
                "source_row": int(raw.get("source_row") or idx + 1),
                "raw_json": _dumps(raw),
            }
        )
    return rows


def sync_tariff_assets(engine=None, log=None) -> dict[str, Any]:
    engine = engine or _engine_or_none(log)
    if engine is None:
        return {"available": False, "message": "数据库未启用"}
    tables = {
        "pv_tariff_rules": _pv_tariff_rows(),
        "pv_policy_files": _policy_rows(),
        "pv_station_tariff_check": _station_check_rows(),
        "market_power_price_rules": _market_power_rows(),
        "southern_grid_tax_rules": _southern_grid_rows(),
        "pv_tariff_period_rules": _period_rule_rows(),
    }
    counts = {table: _replace_table(engine, table, rows, log=log) for table, rows in tables.items()}
    return {"available": True, "tables": counts}


def sync_core_facts_and_tariff_assets(log=None) -> dict[str, Any]:
    engine = _engine_or_none(log)
    if engine is None:
        return {"available": False, "message": "数据库未启用"}
    started = datetime.now()
    result = {
        "available": True,
        "forecast": sync_forecast_facts(engine, log=log),
        "model": sync_model_facts(engine, log=log),
        "tariff": sync_tariff_assets(engine, log=log),
    }
    _save_sync_task_log(engine, started, "success", result)
    return result


def _save_sync_task_log(engine, started: datetime, status: str, result: dict[str, Any]) -> None:
    ended = datetime.now()
    task_id = "sync_core_" + ended.strftime("%Y%m%d%H%M%S")
    if engine.dialect.name == "postgresql":
        from ..repositories.task_repository import save_task_record

        save_task_record(
            {
                "task_id": task_id,
                "run_id": ended.strftime("%Y%m%d_%H%M%S"),
                "task_name": "sync_core_data",
                "kind": "sync_core_data",
                "status": status,
                "command": ["python", "-X", "utf8", "13_sync_core_data_to_db.py"],
                "log_path": "",
                "started_at": started,
                "ended_at": ended,
                "duration_seconds": round((ended - started).total_seconds(), 3),
                "returncode": 0 if status == "success" else 1,
                "error_message": "" if status == "success" else _dumps(result),
            },
            status=status,
            log_text=_dumps(result),
        )
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO task_logs (
                    task_id, run_id, task_name, task_kind, status,
                    command_json, log_path, started_at, ended_at,
                    duration_seconds, returncode, error_message
                )
                VALUES (
                    :task_id, :run_id, :task_name, :task_kind, :status,
                    :command_json, :log_path, :started_at, :ended_at,
                    :duration_seconds, :returncode, :error_message
                )
                ON DUPLICATE KEY UPDATE
                    status = VALUES(status),
                    ended_at = VALUES(ended_at),
                    duration_seconds = VALUES(duration_seconds),
                    returncode = VALUES(returncode),
                    error_message = VALUES(error_message)
                """
            ),
            {
                "task_id": task_id,
                "run_id": ended.strftime("%Y%m%d_%H%M%S"),
                "task_name": "核心事实表与电价规则入库",
                "task_kind": "sync_core_data_to_db",
                "status": status,
                "command_json": _dumps(["python", "-X", "utf8", "13_sync_core_data_to_db.py"]),
                "log_path": "",
                "started_at": started,
                "ended_at": ended,
                "duration_seconds": round((ended - started).total_seconds(), 3),
                "returncode": 0 if status == "success" else 1,
                "error_message": "" if status == "success" else _dumps(result),
            },
        )


def save_ai_trace_record(
    *,
    session_id: str,
    question: str,
    intent: str,
    answer: str,
    tools: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    guard_result: dict[str, Any],
    trace_payload: dict[str, Any],
) -> None:
    try:
        from ..repositories.ai_trace_repository import save_ai_trace

        if save_ai_trace(
            trace_id=str(trace_payload.get("trace_id") or ""),
            session_id=session_id,
            question=question,
            intent=intent,
            answer=answer,
            tools=tools,
            evidence=evidence,
            guard_result=guard_result,
            trace_payload=trace_payload,
        ):
            return
    except Exception:
        pass

    cfg = project_config()
    if not get_database_config(cfg).enabled:
        return
    try:
        apply_database_migrations(cfg)
        engine = create_database_engine(cfg)
        row = {
            "trace_id": trace_payload.get("trace_id"),
            "session_id": session_id,
            "question": question,
            "intent": intent,
            "answer": answer,
            "tools_json": _dumps(tools),
            "evidence_json": _dumps(evidence),
            "guard_result_json": _dumps(guard_result),
            "trace_json": _dumps(trace_payload),
        }
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO ai_traces (
                        trace_id, session_id, question, intent, answer,
                        tools_json, evidence_json, guard_result_json, trace_json
                    )
                    VALUES (
                        :trace_id, :session_id, :question, :intent, :answer,
                        :tools_json, :evidence_json, :guard_result_json, :trace_json
                    )
                    ON DUPLICATE KEY UPDATE
                        answer = VALUES(answer),
                        tools_json = VALUES(tools_json),
                        evidence_json = VALUES(evidence_json),
                        guard_result_json = VALUES(guard_result_json),
                        trace_json = VALUES(trace_json)
                    """
                ),
                row,
            )
    except Exception:
        return
