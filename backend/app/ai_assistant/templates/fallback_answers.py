from __future__ import annotations

from typing import Any


def _money(value: Any) -> str:
    try:
        return f"{float(value):.2f} USD/MWh"
    except Exception:
        return "-"


def answer_storage_discharge(result: dict[str, Any]) -> str:
    if not result.get("available"):
        return "结论：当前系统未查询到可用预测数据，无法给出储能放电窗口。"
    discharge = result.get("recommended_discharge_hours") or []
    charge = result.get("charge_reference_hours") or []
    discharge_lines = [f"{idx}. {item.get('time')}，预测价 {_money(item.get('predicted_price'))}，风险 {item.get('risk_level')}，原因：{item.get('reason')}" for idx, item in enumerate(discharge, 1)]
    charge_lines = [f"{idx}. {item.get('time')}，预测价 {_money(item.get('predicted_price'))}，原因：{item.get('reason')}" for idx, item in enumerate(charge, 1)]
    return (
        "结论：以下时段更适合作为储能放电候选窗口，不是只看单个最高价小时。\n\n"
        "推荐放电时段：\n" + ("\n".join(discharge_lines) if discharge_lines else "暂无明显高价放电候选。")
        + "\n\n低价充电参考：\n" + ("\n".join(charge_lines) if charge_lines else "暂无明显低价充电参考。")
        + f"\n\n数据依据：未来24小时均价约 {_money(result.get('avg_price'))}，峰谷价差约 {_money(result.get('spread'))}，P75阈值约 {_money(result.get('p75'))}。"
        + f"\n\n业务建议：{result.get('strategy_note')}"
    )


def answer_storage_charge(result: dict[str, Any]) -> str:
    if not result.get("available"):
        return "结论：当前系统未查询到可用预测数据，无法给出储能充电窗口。"
    charge = result.get("recommended_charge_hours") or []
    discharge = result.get("discharge_reference_hours") or []
    charge_lines = [f"{idx}. {item.get('time')}，预测价 {_money(item.get('predicted_price'))}，原因：{item.get('reason')}" for idx, item in enumerate(charge, 1)]
    discharge_lines = [f"{idx}. {item.get('time')}，预测价 {_money(item.get('predicted_price'))}，风险 {item.get('risk_level')}" for idx, item in enumerate(discharge, 1)]
    return (
        "结论：以下时段更适合作为储能充电候选窗口。\n\n"
        "推荐充电时段：\n" + ("\n".join(charge_lines) if charge_lines else "暂无明显低价充电候选。")
        + "\n\n高价放电参考：\n" + ("\n".join(discharge_lines) if discharge_lines else "暂无明显高价放电参考。")
        + f"\n\n数据依据：未来24小时均价约 {_money(result.get('avg_price'))}，峰谷价差约 {_money(result.get('spread'))}。"
        + f"\n\n业务建议：{result.get('strategy_note')}"
    )


def answer_low_price_reason(result: dict[str, Any]) -> str:
    reasons = result.get("possible_reasons") or []
    return (
        f"结论：{result.get('time')} 被识别为低价窗口，预测电价约 {_money(result.get('predicted_price'))}，低于未来24小时均价 {_money(result.get('avg_price'))}。\n\n"
        "关键依据：\n" + "\n".join(f"{idx}. {reason}" for idx, reason in enumerate(reasons, 1))
        + f"\n\n业务建议：{result.get('advice')}"
    )


def answer_high_price_reason(result: dict[str, Any]) -> str:
    if not result.get("available"):
        reason = str(
            result.get("message")
            or result.get("unavailable_reason")
            or "当前未查询到可用预测数据。"
        ).rstrip("。")
        return (
            "结论：当前缺少可核验的高价时段预测事实，暂不能判断高价风险原因。\n\n"
            f"数据状态：{reason}。\n\n"
            "建议：先确认预测批次、负荷、天气和新能源出力数据均可用，再结合知识依据复核风险驱动；"
            "系统不会用空值拼接业务结论。"
        )
    reasons = result.get("possible_reasons") or []
    return (
        f"结论：{result.get('time')} 预测电价约 {_money(result.get('predicted_price'))}，在未来24小时中排名第 {result.get('rank')}，属于高价/风险复核窗口。\n\n"
        "关键依据：\n" + "\n".join(f"{idx}. {reason}" for idx, reason in enumerate(reasons, 1))
        + f"\n\n风险与建议：{result.get('advice')}"
    )


def answer_user_text(result: dict[str, Any]) -> str:
    points = result.get("key_points") or []
    return (
        f"结论：{result.get('summary')}\n\n"
        "关键信息：\n" + ("\n".join(f"{idx}. {point}" for idx, point in enumerate(points, 1)) if points else "未提取到完整指标。")
        + f"\n\n通俗解释：{result.get('plain_language_explanation')}\n\n"
        f"数据依据：用户粘贴文本；运行 ID：{result.get('detected_run_id') or '-'}；预测窗口：{result.get('prediction_window') or '-'}。"
    )


def answer_weather_summary(result: dict[str, Any]) -> str:
    if not result.get("available"):
        return f"结论：当前系统未查询到可用天气数据。\n\n原因：{result.get('message') or '-'}"
    return (
        f"结论：当前天气数据参考城市为 {result.get('city') or '-'}，气温约 {result.get('min_temperature')} 至 {result.get('max_temperature')} 摄氏度，平均约 {result.get('avg_temperature')} 摄氏度。\n\n"
        f"数据说明：{result.get('message') or '来自系统天气数据接口。'}"
    )
