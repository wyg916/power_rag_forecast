from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pandas as pd

from automation_common import (
    find_first_column,
    format_duration,
    get_pipeline_paths,
    get_run_context,
    load_config,
    normalize_timestamp,
    now_text,
    read_excel,
    read_json,
    safe_float,
    safe_int,
    setup_run_logger,
    write_json,
)
from database_utils import save_ai_input_summary, save_pipeline_event


FIELD_ALIASES = {
    "base_model_name": ["base_model_name", "基础模型", "高峰专项基础模型"],
    "peak_model_name": ["peak_model_name", "高峰专项模型", "peak_model"],
    "classifier_name": ["classifier_name", "尖峰风险分类器", "spike_classifier"],
    "best_alpha": ["best_alpha", "最佳融合alpha", "最佳融合 alpha", "最优融合Alpha", "最优融合 Alpha", "最优融合alpha"],
    "best_peak_floor": ["best_peak_floor", "最佳peak_floor", "最佳 peak_floor", "最优peak_floor", "最优 peak_floor", "最优Peak_floor"],
}


def get_summary_value(summary: dict[str, object], canonical_name: str) -> object | None:
    for key in FIELD_ALIASES.get(canonical_name, [canonical_name]):
        value = summary.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() != "nan":
            return value
    return None


def read_business_summary(path: Path) -> dict[str, object]:
    df = read_excel(path)
    summary: dict[str, object] = {}
    for _, row in df.iterrows():
        summary[str(row["指标"])] = row["值"]
    return summary


def build_model_summary(metrics_df: pd.DataFrame) -> dict:
    preferred_name = "高峰增强融合模型"
    if preferred_name in metrics_df["模型"].values:
        row = metrics_df.loc[metrics_df["模型"] == preferred_name].iloc[0]
    else:
        row = metrics_df.sort_values("RMSE").iloc[0]

    best_row = metrics_df.sort_values("RMSE").iloc[0]
    return {
        "final_model": str(row["模型"]),
        "mae": safe_float(row["MAE"]),
        "rmse": safe_float(row["RMSE"]),
        "mape_pct": safe_float(row["MAPE(%)"]),
        "r2": safe_float(row["R2"]),
        "best_rmse_model": str(best_row["模型"]),
        "best_rmse": safe_float(best_row["RMSE"]),
    }


def build_peak_summary(peak_df: pd.DataFrame) -> dict:
    preferred_name = "高峰增强融合模型"
    if preferred_name in peak_df["模型"].values:
        row = peak_df.loc[peak_df["模型"] == preferred_name].iloc[0]
    else:
        row = peak_df.iloc[0]
    return {
        "model": str(row["模型"]),
        "overall_rmse": safe_float(row["整体RMSE"]),
        "overall_mae": safe_float(row["整体MAE"]),
        "peak_rmse": safe_float(row["高峰时段RMSE"]),
        "peak_mae": safe_float(row["高峰时段MAE"]),
        "morning_peak_rmse": safe_float(row["晨峰RMSE"]),
        "morning_peak_mae": safe_float(row["晨峰MAE"]),
        "spike_rmse": safe_float(row["尖峰样本RMSE"]),
        "spike_mae": safe_float(row["尖峰样本MAE"]),
    }


def build_forecast_summary(future_df: pd.DataFrame, forecast_mode: str) -> dict:
    price_col = next(
        (col for col in ["predicted_price", "corrected_predicted_price", "预测的未来24小时日前电价", "forecast_price", "da_price_pred"] if col in future_df.columns),
        "预测的未来24小时日前电价",
    )
    probability_col = next(
        (col for col in ["spike_risk_prob", "尖峰风险概率", "spike_prob"] if col in future_df.columns),
        "尖峰风险概率",
    )
    future_df = future_df.copy()
    future_df["datetime"] = pd.to_datetime(future_df["datetime"])
    future_df["hour_text"] = future_df["datetime"].dt.strftime("%H:%M")

    max_row = future_df.loc[future_df[price_col].idxmax()]
    min_row = future_df.loc[future_df[price_col].idxmin()]
    risk_rows = future_df.sort_values(probability_col, ascending=False).head(5)
    top_price_rows = future_df.sort_values(price_col, ascending=False).head(5)

    return {
        "forecast_mode": forecast_mode,
        "forecast_start": normalize_timestamp(future_df["datetime"].min()),
        "forecast_end": normalize_timestamp(future_df["datetime"].max()),
        "next_24h_avg_price": safe_float(future_df[price_col].mean()),
        "next_24h_max_price": safe_float(max_row[price_col]),
        "next_24h_max_hour": str(max_row["hour_text"]),
        "next_24h_min_price": safe_float(min_row[price_col]),
        "next_24h_min_hour": str(min_row["hour_text"]),
        "peak_valley_spread": safe_float(max_row[price_col] - min_row[price_col]),
        "top_predicted_hours": [
            {"hour": str(row["hour_text"]), "predicted_price": safe_float(row[price_col])}
            for _, row in top_price_rows.iterrows()
        ],
        "top_risk_hours": [
            {
                "hour": str(row["hour_text"]),
                "predicted_price": safe_float(row[price_col]),
                "spike_risk_probability": safe_float(row[probability_col]),
            }
            for _, row in risk_rows.iterrows()
        ],
        "weather_sources": sorted(
            [
                str(x)
                for x in future_df.get("future_weather_source", pd.Series(dtype=str)).dropna().unique().tolist()
                if str(x).strip()
            ]
        ),
        "forecast_load_sources": sorted(
            [
                str(x)
                for x in future_df.get("forecast_load_source", pd.Series(dtype=str)).dropna().unique().tolist()
                if str(x).strip()
            ]
        ),
    }


def build_comparison_summary(future_df: pd.DataFrame, master_df: pd.DataFrame) -> dict:
    price_col = next(
        (col for col in ["predicted_price", "corrected_predicted_price", "预测的未来24小时日前电价", "forecast_price", "da_price_pred"] if col in future_df.columns),
        "预测的未来24小时日前电价",
    )
    future_df = future_df.copy()
    future_df["datetime"] = pd.to_datetime(future_df["datetime"])
    master_df = master_df.copy()
    master_df["datetime"] = pd.to_datetime(master_df["datetime"])
    history = master_df.set_index("datetime")["da_price"].to_dict()

    future_df["yesterday_actual"] = future_df["datetime"].map(lambda x: history.get(x - pd.Timedelta(days=1)))
    future_df["lastweek_actual"] = future_df["datetime"].map(lambda x: history.get(x - pd.Timedelta(days=7)))
    future_df["hour"] = future_df["datetime"].dt.hour

    current_avg = future_df[price_col].mean()
    yesterday_avg = future_df["yesterday_actual"].dropna().mean()
    lastweek_avg = future_df["lastweek_actual"].dropna().mean()

    morning_mask = future_df["hour"].between(6, 9)
    evening_mask = future_df["hour"].between(18, 21)

    def pct_change(current: float | None, base: float | None) -> float | None:
        if base in (None, 0) or pd.isna(base):
            return None
        return float((current - base) / base * 100)

    return {
        "vs_yesterday_avg_pct": pct_change(current_avg, yesterday_avg),
        "vs_lastweek_avg_pct": pct_change(current_avg, lastweek_avg),
        "morning_peak_change_pct": pct_change(
            future_df.loc[morning_mask, price_col].mean(),
            future_df.loc[morning_mask, "yesterday_actual"].dropna().mean(),
        ),
        "evening_peak_change_pct": pct_change(
            future_df.loc[evening_mask, price_col].mean(),
            future_df.loc[evening_mask, "yesterday_actual"].dropna().mean(),
        ),
    }


def build_anomaly_summary(anomaly_df: pd.DataFrame) -> dict:
    anomaly_only = anomaly_df.loc[anomaly_df["是否异常"] == 1].copy()
    main_risk_hours = anomaly_only["hour"].value_counts().head(5).index.astype(int).tolist() if not anomaly_only.empty else []
    top_anomalies = anomaly_only.sort_values("绝对误差", ascending=False).head(10)

    return {
        "anomaly_count": safe_int(anomaly_only.shape[0]),
        "anomaly_ratio_pct": safe_float(anomaly_df["是否异常"].mean() * 100),
        "main_risk_hours": [f"{hour:02d}:00" for hour in main_risk_hours],
        "top_anomalies": [
            {
                "datetime": normalize_timestamp(row["datetime"]),
                "actual": safe_float(row["真实值"]),
                "predicted": safe_float(row["预测值"]),
                "absolute_error": safe_float(row["绝对误差"]),
                "relative_error_pct": safe_float(row["相对误差(%)"]),
            }
            for _, row in top_anomalies.iterrows()
        ],
    }


def build_hourly_error_summary(hourly_df: pd.DataFrame) -> dict:
    best_rows = hourly_df.sort_values("MAE").head(3)
    worst_rows = hourly_df.sort_values("MAE", ascending=False).head(5)
    return {
        "best_hours_by_mae": [
            {"hour": int(row["hour"]), "mae": safe_float(row["MAE"])}
            for _, row in best_rows.iterrows()
        ],
        "worst_hours_by_mae": [
            {
                "hour": int(row["hour"]),
                "mae": safe_float(row["MAE"]),
                "rmse": safe_float(row["RMSE"]),
                "anomaly_count": safe_int(row["异常点数量"]),
            }
            for _, row in worst_rows.iterrows()
        ],
    }


def build_backtest_summary(backtest_df: pd.DataFrame) -> dict:
    worst_fold = backtest_df.sort_values("RMSE", ascending=False).iloc[0]
    return {
        "fold_count": safe_int(len(backtest_df)),
        "avg_mae": safe_float(backtest_df["MAE"].mean()),
        "avg_rmse": safe_float(backtest_df["RMSE"].mean()),
        "avg_mape_pct": safe_float(backtest_df["MAPE(%)"].mean()),
        "avg_r2": safe_float(backtest_df["R2"].mean()),
        "worst_fold": {
            "fold": safe_int(worst_fold["Fold"]),
            "rmse": safe_float(worst_fold["RMSE"]),
            "mape_pct": safe_float(worst_fold["MAPE(%)"]),
            "test_start": normalize_timestamp(worst_fold["测试开始"]),
            "test_end": normalize_timestamp(worst_fold["测试结束"]),
        },
    }


def build_feature_summary(feature_df: pd.DataFrame) -> dict:
    columns = [str(col) for col in feature_df.columns]
    feature_col = find_first_column(columns, ["特征", "feature"])
    importance_col = find_first_column(columns, ["重要", "importance", "gain"])
    if not feature_col or not importance_col:
        return {"top_features": []}

    top_features = feature_df.sort_values(importance_col, ascending=False).head(10)
    return {
        "top_features": [
            {
                "feature": str(row[feature_col]),
                "importance": safe_float(row[importance_col]),
            }
            for _, row in top_features.iterrows()
        ]
    }


def build_peak_model_summary(business_summary: dict[str, object]) -> dict:
    base_model = str(get_summary_value(business_summary, "base_model_name") or "")
    peak_model = str(get_summary_value(business_summary, "peak_model_name") or "")
    classifier = str(get_summary_value(business_summary, "classifier_name") or "")
    best_alpha = safe_float(get_summary_value(business_summary, "best_alpha"))
    best_peak_floor = safe_float(get_summary_value(business_summary, "best_peak_floor"))
    return {
        "base_model_name": base_model,
        "peak_model_name": peak_model,
        "classifier_name": classifier,
        "best_alpha": best_alpha,
        "best_peak_floor": best_peak_floor,
        # Backward-compatible keys consumed by older report templates.
        "base_model": base_model,
        "peak_model": peak_model,
        "spike_classifier": classifier,
        "alpha": best_alpha,
        "peak_floor": best_peak_floor,
    }


def load_forecast_result(result_table_dir: Path) -> tuple[pd.DataFrame, str, str]:
    candidates = [
        ("18_未来24小时预测结果_正式版.xlsx", "正式前瞻版"),
        ("18_未来24小时预测结果_演示版.xlsx", "演示版"),
    ]
    for filename, mode in candidates:
        path = result_table_dir / filename
        if path.exists():
            future_df = read_excel(path)
            if "forecast_mode" in future_df.columns and not future_df["forecast_mode"].dropna().empty:
                mode = str(future_df["forecast_mode"].dropna().iloc[0])
            return future_df, mode, filename
    raise FileNotFoundError("未找到未来24小时预测结果文件。")


def build_report_facts(summary: dict[str, Any]) -> dict[str, Any]:
    forecast = summary["forecast_summary"]
    model = summary["model_summary"]
    anomaly = summary["anomaly_summary"]
    comparison = summary["comparison_summary"]
    backtest = summary["backtest_summary"]
    business = summary["business_summary"]

    return {
        "data_window_start": business.get("起始时间"),
        "data_window_end": business.get("结束时间"),
        "current_master_rows": business.get("样本总量"),
        "forecast_start": forecast.get("forecast_start"),
        "forecast_end": forecast.get("forecast_end"),
        "avg_price": forecast.get("next_24h_avg_price"),
        "max_price": forecast.get("next_24h_max_price"),
        "max_hour": forecast.get("next_24h_max_hour"),
        "min_price": forecast.get("next_24h_min_price"),
        "min_hour": forecast.get("next_24h_min_hour"),
        "peak_valley_spread": forecast.get("peak_valley_spread"),
        "risk_hours": forecast.get("top_risk_hours"),
        "final_model": model.get("final_model"),
        "rmse": model.get("rmse"),
        "mae": model.get("mae"),
        "r2": model.get("r2"),
        "backtest_avg_rmse": backtest.get("avg_rmse"),
        "anomaly_count": anomaly.get("anomaly_count"),
        "anomaly_ratio_pct": anomaly.get("anomaly_ratio_pct"),
        "main_risk_hours": anomaly.get("main_risk_hours"),
        "vs_yesterday_avg_pct": comparison.get("vs_yesterday_avg_pct"),
        "vs_lastweek_avg_pct": comparison.get("vs_lastweek_avg_pct"),
    }


def main() -> None:
    start = time.perf_counter()
    config = load_config()
    paths = get_pipeline_paths(config)
    run_context = get_run_context()
    log, _ = setup_run_logger(paths.log_dir, "02_build_ai_summary")

    metrics_df = read_excel(paths.result_table_dir / "10_模型评估结果.xlsx")
    peak_df = read_excel(paths.result_table_dir / "11_高峰尖刺专项评估.xlsx")
    anomaly_df = read_excel(paths.result_table_dir / "14_异常波动明细.xlsx")
    hourly_df = read_excel(paths.result_table_dir / "15_按小时误差统计.xlsx")
    backtest_df = read_excel(paths.result_table_dir / "16_滚动回测结果.xlsx")
    future_df, forecast_mode, forecast_filename = load_forecast_result(paths.result_table_dir)
    business_summary = read_business_summary(paths.result_table_dir / "19_业务统计摘要.xlsx")
    feature_df = read_excel(paths.result_table_dir / "13_特征重要性.xlsx")
    master_df = read_excel(paths.data_dir / "master_table.xlsx")

    inventory_path = paths.current_dir / "local_model_inventory.json"
    inventory = read_json(inventory_path) if inventory_path.exists() else {}

    summary = {
        "run_id": run_context["run_id"],
        "run_mode": run_context["run_mode"],
        "run_started_at": run_context["run_started_at"],
        "generated_at": now_text(),
        "run_date": now_text("%Y-%m-%d"),
        "engine_version": paths.engine_script.name,
        "result_folder": str(paths.result_dir.name),
        "data_source_mode": "mysql_snapshot_to_excel",
        "forecast_mode": forecast_mode,
        "forecast_result_file": forecast_filename,
        "model_summary": build_model_summary(metrics_df),
        "peak_model_summary": build_peak_model_summary(business_summary),
        "peak_special_summary": build_peak_summary(peak_df),
        "forecast_summary": build_forecast_summary(future_df, forecast_mode),
        "comparison_summary": build_comparison_summary(future_df, master_df),
        "anomaly_summary": build_anomaly_summary(anomaly_df),
        "hourly_error_summary": build_hourly_error_summary(hourly_df),
        "backtest_summary": build_backtest_summary(backtest_df),
        "feature_summary": build_feature_summary(feature_df),
        "business_summary": business_summary,
        "hardware_recommendation": inventory.get("recommendation", {}),
    }
    summary["report_facts"] = build_report_facts(summary)
    summary["summary_signature"] = hashlib.sha256(
        json.dumps(summary, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

    json_path = paths.current_dir / "ai_input_summary.json"
    md_path = paths.current_dir / "ai_input_summary.md"
    write_json(json_path, summary)

    md_lines = [
        "# AI 输入摘要",
        "",
        f"- 运行 ID：{summary['run_id']}",
        f"- 生成时间：{summary['generated_at']}",
        f"- 结果目录：{summary['result_folder']}",
        f"- 预测引擎：{summary['engine_version']}",
        f"- 摘要签名：{summary['summary_signature']}",
        f"- 默认本地主模型建议：{summary['hardware_recommendation'].get('recommended_default_model', '')}",
        "",
        "## 核心模型表现",
        json.dumps(summary["model_summary"], ensure_ascii=False, indent=2),
        "",
        "## 未来24小时预测摘要",
        json.dumps(summary["forecast_summary"], ensure_ascii=False, indent=2),
        "",
        "## 异常摘要",
        json.dumps(summary["anomaly_summary"], ensure_ascii=False, indent=2),
    ]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    save_ai_input_summary(config, summary, run_context=run_context, log=log)
    elapsed = format_duration(time.perf_counter() - start)
    log(f"已生成 AI 输入摘要：{json_path}，耗时：{elapsed}")
    save_pipeline_event(config, "ai_input_summary", "completed", f"AI 输入摘要已生成，耗时：{elapsed}", run_context)


if __name__ == "__main__":
    main()
