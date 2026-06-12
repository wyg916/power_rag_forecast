from __future__ import annotations

import re
from typing import Any


def _first(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.I)
    return match.group(1) if match else ""


def explain_user_provided_text(text: str = "", **_: Any) -> dict[str, Any]:
    source = text or ""
    run_id = _first(r"运行ID\s*([0-9A-Za-z_\-]+)", source)
    data_window = _first(r"数据窗口为([^，。]+)", source)
    prediction_window = _first(r"预测窗口为([^，。]+)", source)
    avg_price = _first(r"均价为?\s*([-+]?\d+(?:\.\d+)?)\s*USD/MWh", source)
    max_price = _first(r"最高价\s*([-+]?\d+(?:\.\d+)?)\s*USD/MWh", source)
    max_time = _first(r"最高价[-+]?\d+(?:\.\d+)?\s*USD/MWh出现在([0-9:：\- ]+)", source)
    min_price = _first(r"最低价\s*([-+]?\d+(?:\.\d+)?)\s*USD/MWh", source)
    min_time = _first(r"最低价[-+]?\d+(?:\.\d+)?\s*USD/MWh出现在([0-9:：\- ]+)", source)
    spread = _first(r"峰谷价差(?:达|为)?\s*([-+]?\d+(?:\.\d+)?)\s*USD/MWh", source)
    rmse = _first(r"RMSE为?\s*([-+]?\d+(?:\.\d+)?)", source)
    mae = _first(r"MAE为?\s*([-+]?\d+(?:\.\d+)?)", source)
    risk = _first(r"重点风险时段为([^。；;\n]+)", source)
    key_points = []
    if avg_price:
        key_points.append(f"均价约 {avg_price} USD/MWh")
    if max_price:
        key_points.append(f"最高价 {max_price} USD/MWh，出现在 {max_time or '报告所述时段'}")
    if min_price:
        key_points.append(f"最低价 {min_price} USD/MWh，出现在 {min_time or '报告所述时段'}")
    if spread:
        key_points.append(f"峰谷价差约 {spread} USD/MWh，说明波动较明显")
    if risk:
        key_points.append(f"重点风险时段：{risk}")
    if rmse or mae:
        key_points.append(f"模型指标：RMSE {rmse or '-'}，MAE {mae or '-'}")
    return {
        "tool": "explain_user_provided_text",
        "available": True,
        "detected_run_id": run_id,
        "data_window": data_window,
        "prediction_window": prediction_window,
        "avg_price": avg_price,
        "max_price": max_price,
        "max_time": max_time,
        "min_price": min_price,
        "min_time": min_time,
        "spread": spread,
        "risk_hours": risk,
        "rmse": rmse,
        "mae": mae,
        "summary": f"这段报告说明本次运行预测的是 {prediction_window or '指定预测窗口'} 的电价表现，并给出了价格水平、波动和模型指标。",
        "key_points": key_points,
        "plain_language_explanation": "通俗来说，这份报告是在说明预测窗口内电价波动情况、重点风险时段和模型可信度，交易侧应重点关注高价/高风险时段。",
        "evidence": [{"source": "user_input_text"}],
    }
