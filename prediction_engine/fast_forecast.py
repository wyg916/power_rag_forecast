from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from automation_common import get_pipeline_paths, get_run_context
from model_ops.active_model_loader import ActiveModelBundle, load_active_model_artifacts
from model_ops.bias_corrector import apply_bias_correction
from prediction_engine.formal_forecast import add_residual_prediction_intervals
from prediction_engine.legacy_engine import load_engine_module


FORECAST_RESULT_FILE = "18_未来24小时预测结果_正式版.xlsx"
FORECAST_FEATURE_FILE = "18_未来24小时预测输入特征_正式版.xlsx"
BUSINESS_SUMMARY_FILE = "19_业务统计摘要.xlsx"
TEST_PREDICTION_FILE = "12_测试集预测结果.xlsx"


@dataclass
class FastForecastResult:
    future_result_path: Path
    feature_snapshot_path: Path
    business_summary_path: Path
    model_version: str
    feature_version: str | None
    rows: int


def _log(log, message: str) -> None:
    if log:
        log(message)


def _prepare_history(paths, bundle: ActiveModelBundle, log=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    engine = load_engine_module()
    master_path = paths.data_dir / "master_table.xlsx"
    if not master_path.exists():
        raise FileNotFoundError(f"未找到建模主表：{master_path}")
    history = pd.read_excel(master_path, engine="openpyxl")
    if "datetime" not in history.columns:
        raise ValueError("建模主表缺少 datetime 字段，无法执行快速预测。")
    history["datetime"] = pd.to_datetime(history["datetime"], errors="coerce")
    history = history.dropna(subset=["datetime"]).sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)
    history = engine.run_full_feature_engineering(history)
    missing_cols = [col for col in bundle.feature_cols if col not in history.columns]
    if missing_cols:
        _log(log, "WARNING: 快速预测特征缺失，将按安全默认值填补：" + "、".join(missing_cols[:20]))
        for col in missing_cols:
            history[col] = 0.0
    target = getattr(engine, "TARGET_COL", "da_price")
    model_df = history[["datetime", target] + bundle.feature_cols].copy()
    model_df[bundle.feature_cols] = model_df[bundle.feature_cols].apply(pd.to_numeric, errors="coerce")
    model_df = model_df.dropna(subset=["datetime", target]).reset_index(drop=True)
    return history, model_df


def _add_standard_columns(future_result: pd.DataFrame, bundle: ActiveModelBundle) -> pd.DataFrame:
    output = future_result.copy()
    price_col = "预测的未来24小时日前电价"
    if price_col not in output.columns:
        for candidate in ["predicted_price", "forecast_price", "da_price_pred"]:
            if candidate in output.columns:
                output[price_col] = pd.to_numeric(output[candidate], errors="coerce")
                break
    if "raw_base_pred" in output.columns and "base_prediction" not in output.columns:
        output["base_prediction"] = pd.to_numeric(output["raw_base_pred"], errors="coerce")
    if "base_prediction" in output.columns and "raw_base_pred" not in output.columns:
        output["raw_base_pred"] = pd.to_numeric(output["base_prediction"], errors="coerce")
    if "peak_pred" in output.columns and "peak_prediction" not in output.columns:
        output["peak_prediction"] = pd.to_numeric(output["peak_pred"], errors="coerce")
    if "peak_prediction" in output.columns and "peak_pred" not in output.columns:
        output["peak_pred"] = pd.to_numeric(output["peak_prediction"], errors="coerce")
    if "spike_prob" in output.columns and "spike_risk_prob" not in output.columns:
        output["spike_risk_prob"] = pd.to_numeric(output["spike_prob"], errors="coerce")
    if "spike_risk_prob" in output.columns and "spike_prob" not in output.columns:
        output["spike_prob"] = pd.to_numeric(output["spike_risk_prob"], errors="coerce")
    if "dynamic_alpha" not in output.columns and "blend_weight" in output.columns:
        output["dynamic_alpha"] = pd.to_numeric(output["blend_weight"], errors="coerce")
    if "blend_weight" not in output.columns and "dynamic_alpha" in output.columns:
        output["blend_weight"] = pd.to_numeric(output["dynamic_alpha"], errors="coerce")
    if "blended_pred" not in output.columns and "predicted_price" in output.columns:
        output["blended_pred"] = pd.to_numeric(output["predicted_price"], errors="coerce")
    if "predicted_price" not in output.columns and "blended_pred" in output.columns:
        output["predicted_price"] = pd.to_numeric(output["blended_pred"], errors="coerce")
    if "spike_risk_prob" not in output.columns and "尖峰风险概率" in output.columns:
        output["spike_risk_prob"] = pd.to_numeric(output["尖峰风险概率"], errors="coerce")
    if "尖峰风险概率" in output.columns and "spike_risk_prob" not in output.columns:
        output["spike_risk_prob"] = pd.to_numeric(output["尖峰风险概率"], errors="coerce")
    if "尖峰风险概率" not in output.columns and "spike_risk_prob" in output.columns:
        output["尖峰风险概率"] = output["spike_risk_prob"]
    if "尖峰风险概率" not in output.columns and "尖峰风险概率" not in output.columns:
        for col in output.columns:
            if "风险" in str(col) and ("概率" in str(col) or "prob" in str(col).lower()):
                output["spike_risk_prob"] = pd.to_numeric(output[col], errors="coerce")
                break
    output["model_version"] = bundle.model_version
    output["feature_version"] = bundle.feature_version or ""
    output["is_peak_hour"] = pd.to_datetime(output["datetime"], errors="coerce").dt.hour.isin([6, 7, 8, 9, 10, 11, 18, 19, 20, 21]).astype(int)
    if "risk_level" not in output.columns:
        prob = pd.to_numeric(output.get("spike_risk_prob", pd.Series([0] * len(output))), errors="coerce").fillna(0)
        output["risk_level"] = prob.map(lambda x: "high" if x >= 0.5 else ("medium" if x >= 0.2 else "low"))
    return output


def _write_forecast_chart(future_result: pd.DataFrame, paths) -> None:
    fig_dir = paths.result_dir / "图表"
    fig_dir.mkdir(parents=True, exist_ok=True)
    df = future_result.copy()
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    price = pd.to_numeric(df["predicted_price"], errors="coerce")
    fig = plt.figure(figsize=(12, 6))
    plt.plot(df["datetime"], price, marker="o", linewidth=1.4, label="校正后预测电价")
    if "raw_predicted_price" in df.columns:
        plt.plot(df["datetime"], pd.to_numeric(df["raw_predicted_price"], errors="coerce"), linestyle="--", linewidth=1.0, label="Active模型原始预测")
    plt.title("未来24小时日前电价快速预测结果（Active模型）")
    plt.xlabel("时间")
    plt.ylabel("预测电价（USD/MWh）")
    plt.xticks(rotation=45)
    plt.legend()
    plt.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(fig_dir / "21_未来24小时日前电价预测图_正式版.png", dpi=180)
    plt.close(fig)


def _metric_value(metrics: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in metrics and metrics[key] not in {None, ""}:
            return metrics[key]
    rows = pd.DataFrame(metrics.get("metrics") or [])
    if not rows.empty:
        if "模型" in rows.columns:
            preferred = rows[rows["模型"].astype(str).str.contains("融合|增强", regex=True, na=False)]
            row = preferred.iloc[0] if not preferred.empty else rows.sort_values("RMSE").iloc[0]
        else:
            row = rows.iloc[0]
        for key in keys:
            if key in row:
                return row[key]
    return ""


def _write_business_summary(history: pd.DataFrame, future_result: pd.DataFrame, bundle: ActiveModelBundle, paths) -> Path:
    target = "da_price" if "da_price" in history.columns else None
    price = pd.to_numeric(future_result["predicted_price"], errors="coerce")
    rows = [
        {"指标": "样本总量", "值": len(history)},
        {"指标": "起始时间", "值": str(history["datetime"].min())},
        {"指标": "结束时间", "值": str(history["datetime"].max())},
        {"指标": "平均日前电价", "值": round(float(pd.to_numeric(history[target], errors="coerce").mean()), 4) if target else ""},
        {"指标": "测试集主模型", "值": "Active模型快速推理"},
        {"指标": "测试集MAE", "值": _metric_value(bundle.metrics, ["MAE", "mae"])},
        {"指标": "测试集RMSE", "值": _metric_value(bundle.metrics, ["RMSE", "rmse"])},
        {"指标": "测试集MAPE(%)", "值": _metric_value(bundle.metrics, ["MAPE(%)", "mape"])},
        {"指标": "测试集R2", "值": _metric_value(bundle.metrics, ["R2", "r2"])},
        {"指标": "高峰专项基础模型", "值": bundle.metrics.get("base_model_name", "")},
        {"指标": "高峰专项模型", "值": bundle.metrics.get("peak_model_name", "")},
        {"指标": "尖峰风险分类器", "值": bundle.metrics.get("classifier_name", "")},
        {"指标": "最佳融合alpha", "值": bundle.artifacts.get("best_alpha", "")},
        {"指标": "最佳peak_floor", "值": bundle.artifacts.get("best_floor", "")},
        {"指标": "未来24小时预测口径", "值": "正式前瞻版-Active模型快速推理"},
        {"指标": "未来24小时预测开始", "值": str(future_result["datetime"].min())},
        {"指标": "未来24小时预测结束", "值": str(future_result["datetime"].max())},
        {"指标": "未来24小时均价", "值": round(float(price.mean()), 4)},
        {"指标": "未来24小时最高价", "值": round(float(price.max()), 4)},
        {"指标": "未来24小时最低价", "值": round(float(price.min()), 4)},
        {"指标": "模型版本", "值": bundle.model_version},
        {"指标": "特征版本", "值": bundle.feature_version or ""},
    ]
    out = paths.result_table_dir / BUSINESS_SUMMARY_FILE
    pd.DataFrame(rows).to_excel(out, index=False)
    return out


def forecast_with_saved_model(config: dict[str, Any], run_context: dict[str, Any] | None = None, log=None) -> FastForecastResult:
    paths = get_pipeline_paths(config)
    paths.result_table_dir.mkdir(parents=True, exist_ok=True)
    paths.result_dir.mkdir(parents=True, exist_ok=True)
    bundle = load_active_model_artifacts(config)
    _log(log, f"加载 Active 模型快速推理：{bundle.model_version}")
    history, model_df = _prepare_history(paths, bundle, log=log)
    future_result, future_feature_snapshot = load_engine_module().generate_formal_forward_forecast(
        history,
        bundle.feature_cols,
        bundle.artifacts,
        model_df,
    )
    future_result = _add_standard_columns(future_result, bundle)
    test_prediction_path = paths.result_table_dir / TEST_PREDICTION_FILE
    if test_prediction_path.exists():
        try:
            future_result = add_residual_prediction_intervals(future_result, pd.read_excel(test_prediction_path, engine="openpyxl"))
        except Exception as exc:
            _log(log, f"WARNING: 快速预测区间生成失败，保留点预测：{exc}")
    future_result = apply_bias_correction(future_result, bundle.model_version, config=config)
    if "predicted_price" in future_result.columns:
        future_result["预测的未来24小时日前电价"] = pd.to_numeric(future_result["predicted_price"], errors="coerce")
    future_result["model_version"] = bundle.model_version
    future_result["feature_version"] = bundle.feature_version or ""
    future_result["forecast_run_mode"] = (run_context or get_run_context()).get("run_mode", "fast_forecast")

    future_result_path = paths.result_table_dir / FORECAST_RESULT_FILE
    feature_snapshot_path = paths.result_table_dir / FORECAST_FEATURE_FILE
    future_result.to_excel(future_result_path, index=False)
    future_feature_snapshot.to_excel(feature_snapshot_path, index=False)
    business_summary_path = _write_business_summary(history, future_result, bundle, paths)
    _write_forecast_chart(future_result, paths)
    readme = paths.result_dir / "README_结果说明_高峰尖刺增强版.txt"
    readme.write_text(
        f"本次结果由 Active 模型快速推理生成。\n模型版本：{bundle.model_version}\n特征版本：{bundle.feature_version or ''}\n"
        f"预测结果：{future_result_path}\n生成时间：{pd.Timestamp.now()}\n",
        encoding="utf-8",
    )
    _log(log, f"SUCCESS: Active 模型快速预测完成，输出 {len(future_result)} 条：{future_result_path}")
    return FastForecastResult(
        future_result_path=future_result_path,
        feature_snapshot_path=feature_snapshot_path,
        business_summary_path=business_summary_path,
        model_version=bundle.model_version,
        feature_version=bundle.feature_version,
        rows=len(future_result),
    )
