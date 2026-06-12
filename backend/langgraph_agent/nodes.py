from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from typing import Any

import requests

from backend.app.ai.intent_classifier import classify
from backend.model_gateway.config import load_model_gateway_config

from .prompts import ANSWER_SYSTEM_PROMPT
from .schemas import INTENT_TOOL_PLAN, PROFESSIONAL_INTENTS
from .state import AgentState
from .tools import run_agent_tools


_LLM_DISABLED_UNTIL = 0.0


POWER_KEYWORDS = {
    "电价",
    "日前",
    "实时",
    "预测",
    "负荷",
    "新能源",
    "风电",
    "光伏",
    "出力",
    "交易",
    "售电",
    "采购",
    "敞口",
    "储能",
    "尖峰",
    "高峰",
    "风险",
    "模型",
    "日报",
    "报告",
}

COMPLEX_KEYWORDS = {
    "分析",
    "原因",
    "为什么",
    "风险提示",
    "交易建议",
    "策略",
    "综合",
    "生成",
    "日报",
    "周报",
    "解释",
    "对比",
    "上涨",
    "下跌",
    "影响",
    "复核",
}


def _contains_any(text: str, keys: set[str] | list[str]) -> bool:
    return any(key.lower() in text.lower() for key in keys)


def _is_general_weather_question(question: str) -> bool:
    text = re.sub(r"\s+", "", question or "")
    weather = _contains_any(text, {"天气", "气温", "温度", "下雨", "降雨", "风速", "湿度"})
    return weather and not _contains_any(text, POWER_KEYWORDS - {"风险"})


def _extract_city(question: str) -> str | None:
    match = re.search(r"([\u4e00-\u9fa5]{2,8})(?:天气|气温|温度|下雨|降雨)", question or "")
    if match:
        city = match.group(1)
        for prefix in ["明天", "今天", "昨日", "昨天", "后天"]:
            city = city.replace(prefix, "")
        return city or None
    return None


def _money(value: Any) -> str:
    try:
        return f"{float(value):.2f} USD/MWh"
    except Exception:
        return "-"


def _num(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "-"


def _first(state: AgentState, tool: str) -> dict[str, Any]:
    for item in state.tool_results:
        if item.get("tool") == tool:
            return item
    return {}


def _extend_unique(target: list[str], values: list[Any]) -> None:
    seen = set(target)
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            target.append(text)


def _evidence(state: AgentState, name: str, value: Any, source: str, **extra: Any) -> None:
    item = {"name": name, "value": value, "source": source}
    item.update(extra)
    state.evidence.append(item)


def intent_agent(state: AgentState) -> AgentState:
    result = classify(state.question)
    state.intent = result.intent
    state.confidence = result.confidence
    state.entities.update(result.entities)
    if state.market and not state.entities.get("market"):
        state.entities["market"] = state.market
    if state.date and not state.entities.get("date"):
        state.entities["date"] = state.date
    city = _extract_city(state.question)
    if city and not state.entities.get("city"):
        state.entities["city"] = city
    text = state.question or ""
    state.professional = state.intent in PROFESSIONAL_INTENTS or _contains_any(text, POWER_KEYWORDS)
    if _is_general_weather_question(text):
        state.professional = False
        state.intent = "weather_analysis"
    state.complexity = "complex" if state.professional and _contains_any(text, COMPLEX_KEYWORDS) else "simple"
    if state.intent == "general_analysis" and not state.professional:
        state.required_tools = []
    else:
        state.required_tools = list(INTENT_TOOL_PLAN.get(state.intent, INTENT_TOOL_PLAN["general_analysis"]))
    if state.professional and state.complexity == "complex" and state.intent in {"factor_analysis", "forecast_overview", "strategy_advice", "report_summary", "general_analysis"}:
        for name in ["get_prediction_overview", "get_load_forecast", "get_weather_forecast", "get_model_explain", "search_knowledge"]:
            if name not in state.required_tools:
                state.required_tools.append(name)
    state.trace("intent_agent", "ok", f"识别意图 {state.intent}，复杂度 {state.complexity}", required_tools=state.required_tools)
    return state


def data_agent(state: AgentState) -> AgentState:
    run_agent_tools(state)
    state.trace("data_agent", "ok", f"已调用 {len(state.tool_calls)} 个工具", data_used=state.data_used)
    return state


def prediction_agent(state: AgentState) -> AgentState:
    overview_tool = _first(state, "get_prediction_overview")
    overview = overview_tool.get("overview") if isinstance(overview_tool.get("overview"), dict) else {}
    extremes = _first(state, "get_forecast_extremes")
    load = _first(state, "get_load_forecast")
    weather = _first(state, "get_weather_forecast")
    renewable = _first(state, "get_renewable_forecast")
    model = _first(state, "get_model_explain")
    history = _first(state, "get_market_history")

    if overview:
        scope_messages = []
        if overview.get("message"):
            scope_messages.append(str(overview.get("message")))
        scope_messages.extend(str(item) for item in overview.get("messages") or [])
        if scope_messages:
            state.observations.append({"agent": "prediction_agent", "type": "data_scope", "text": " ".join(scope_messages)})
        state.risk_level = str(overview.get("risk_level") or state.risk_level or "")
        _extend_unique(state.focus_periods, overview.get("focus_periods") or [])
        factors = overview.get("main_factors") or []
        if factors:
            state.observations.append({"agent": "prediction_agent", "type": "factor", "text": "；".join(map(str, factors[:5]))})
        _evidence(state, "预测均价", _money(overview.get("avg_price_pred")), "prediction")
        _evidence(state, "预测最高价", _money(overview.get("peak_price_pred")), "prediction", hour=overview.get("peak_hour"))
        _evidence(state, "预测最低价", _money(overview.get("valley_price_pred")), "prediction", hour=overview.get("valley_hour"))

    if extremes and not extremes.get("empty"):
        text = (
            f"未来 24 小时均价约 {_money(extremes.get('avg_price'))}，"
            f"最高价在 {extremes.get('max_price_hour')}，约 {_money(extremes.get('max_price'))}；"
            f"最低价在 {extremes.get('min_price_hour')}，约 {_money(extremes.get('min_price'))}。"
        )
        state.observations.append({"agent": "prediction_agent", "type": "price_window", "text": text})
        _evidence(state, "峰谷价差", _money(extremes.get("peak_valley_spread")), "prediction")

    if load and not load.get("empty"):
        if load.get("message"):
            state.observations.append({"agent": "prediction_agent", "type": "load_scope", "text": str(load.get("message"))})
        state.observations.append(
            {
                "agent": "prediction_agent",
                "type": "load",
                "text": f"负荷预测均值约 {_num(load.get('avg_load'), 0)}，高点约 {_num(load.get('max_load'), 0)}，低点约 {_num(load.get('min_load'), 0)}。",
            }
        )
        _evidence(state, "预测负荷均值", _num(load.get("avg_load"), 0), "load")

    if weather and not weather.get("empty"):
        if weather.get("message"):
            state.observations.append({"agent": "prediction_agent", "type": "weather_scope", "text": str(weather.get("message"))})
        state.observations.append(
            {
                "agent": "prediction_agent",
                "type": "weather",
                "text": f"天气参考：{weather.get('city') or '-'}，气温约 {_num(weather.get('min_temperature'))} 至 {_num(weather.get('max_temperature'))} 摄氏度，均值约 {_num(weather.get('avg_temperature'))}。",
            }
        )
        _evidence(state, "天气温度范围", f"{_num(weather.get('min_temperature'))}-{_num(weather.get('max_temperature'))} 摄氏度", "weather")

    if renewable:
        if renewable.get("available"):
            state.observations.append({"agent": "prediction_agent", "type": "renewable", "text": "系统已接入新能源出力数据，可纳入价格影响判断。"})
        elif renewable.get("message"):
            state.observations.append({"agent": "prediction_agent", "type": "renewable_scope", "text": str(renewable.get("message"))})

    if model and not model.get("empty"):
        if model.get("message"):
            state.observations.append({"agent": "prediction_agent", "type": "model_scope", "text": str(model.get("message"))})
        if model.get("model_confidence") is not None:
            _evidence(state, "模型置信参考", _num(model.get("model_confidence")), "model")
        factors = model.get("main_factors") or [item.get("feature") for item in (model.get("feature_importance") or [])[:3]]
        factors = [str(item) for item in factors if item]
        if factors:
            state.observations.append({"agent": "prediction_agent", "type": "model", "text": "模型主要参考特征：" + "、".join(factors[:5])})

    if history and not history.get("empty"):
        rows = history.get("records") or []
        state.observations.append({"agent": "prediction_agent", "type": "history", "text": f"历史价格接口返回 {len(rows)} 条记录，可作为趋势参照。"})

    state.trace("prediction_agent", "ok", f"形成 {len(state.observations)} 条分析观察")
    return state


def risk_agent(state: AgentState) -> AgentState:
    risk = _first(state, "get_risk_level")
    high = _first(state, "get_high_risk_hours")
    trading = _first(state, "get_trading_advice")
    hour_detail = _first(state, "get_hour_detail")
    hour_evidence = _first(state, "build_hour_risk_evidence")

    if risk and not risk.get("empty"):
        state.risk_level = str(risk.get("risk_level") or risk.get("level") or state.risk_level or "")
        _extend_unique(state.focus_periods, risk.get("focus_periods") or [])
        _evidence(state, "风险等级", state.risk_level or "-", "risk")

    if high and not high.get("empty"):
        items = high.get("items") or []
        windows = [str(item.get("hour")) for item in items[:5] if item.get("hour")]
        _extend_unique(state.focus_periods, windows)
        if items:
            text = "高风险关注窗口：" + "；".join(
                f"{item.get('hour')}（{item.get('risk_level')}，{_money(item.get('predicted_price'))}）" for item in items[:5]
            )
            state.observations.append({"agent": "risk_agent", "type": "risk_window", "text": text})
            _evidence(state, "高风险时段", "、".join(windows), "prediction")

    if trading and not trading.get("empty"):
        summary = str(trading.get("summary") or "")
        if summary:
            state.observations.append({"agent": "risk_agent", "type": "trading", "text": summary})
        for window in trading.get("risk_windows") or []:
            if window.get("hour"):
                _extend_unique(state.focus_periods, [window.get("hour")])

    if hour_detail and not hour_detail.get("empty"):
        state.risk_level = str(hour_detail.get("risk_level") or state.risk_level or "")
        reasons = hour_detail.get("reasons") or []
        state.observations.append(
            {
                "agent": "risk_agent",
                "type": "hour_detail",
                "text": f"{hour_detail.get('hour')} 预测价 {_money(hour_detail.get('predicted_price'))}，风险等级 {hour_detail.get('risk_level') or '-'}；原因：" + "；".join(map(str, reasons[:4])),
            }
        )
        _evidence(state, "小时风险详情", hour_detail.get("hour"), "prediction", risk_level=hour_detail.get("risk_level"))

    if hour_evidence and not hour_evidence.get("empty"):
        recommendation = hour_evidence.get("recommendation")
        if recommendation:
            state.observations.append({"agent": "risk_agent", "type": "hour_recommendation", "text": str(recommendation)})

    state.trace("risk_agent", "ok", f"风险等级 {state.risk_level or '未单独标记'}")
    return state


def report_agent(state: AgentState) -> AgentState:
    report = _first(state, "get_report_summary")
    data_status = _first(state, "get_data_status")
    model_error = _first(state, "get_model_error_summary")
    if report and not report.get("empty"):
        summary = report.get("summary") or {}
        core = summary.get("executive_summary") or summary.get("management_summary") or summary.get("market_overview")
        if core:
            state.observations.append({"agent": "report_agent", "type": "report", "text": str(core)[:1200]})
        _evidence(state, "最新报告", report.get("report_id") or "-", "report", available=report.get("available"))
    if data_status and not data_status.get("empty"):
        sources = data_status.get("sources") or []
        normal = len([item for item in sources if item.get("status") == "正常"])
        state.observations.append({"agent": "report_agent", "type": "data_status", "text": f"数据源共 {len(sources)} 个，正常 {normal} 个。"})
        _evidence(state, "数据源状态", f"{normal}/{len(sources)} 正常", "data_status")
    if model_error and not model_error.get("empty"):
        rows = model_error.get("error_rows") or []
        if rows:
            row = rows[0]
            state.observations.append(
                {
                    "agent": "report_agent",
                    "type": "model_error",
                    "text": f"最新误差样本模型 {row.get('model_version')}，样本数 {row.get('sample_count')}，MAE 约 {_num(row.get('mae'))}。",
                }
            )
            _evidence(state, "模型误差 MAE", _num(row.get("mae")), "model")
    state.trace("report_agent", "ok", "报告、数据和模型状态已汇总")
    return state


def _brief_payload(state: AgentState) -> dict[str, Any]:
    return {
        "question": state.question,
        "intent": state.intent,
        "entities": state.entities,
        "complexity": state.complexity,
        "risk_level": state.risk_level,
        "focus_periods": state.focus_periods[:8],
        "observations": state.observations[-14:],
        "evidence": state.evidence[-12:],
        "data_used": state.data_used,
        "tool_calls": [{"tool_name": item.get("tool_name"), "success": item.get("success")} for item in state.tool_calls],
    }


def _call_local_llm(state: AgentState) -> str:
    global _LLM_DISABLED_UNTIL
    if time.time() < _LLM_DISABLED_UNTIL:
        raise RuntimeError("本地模型暂不可用，已跳过重复探测")
    cfg = load_model_gateway_config()
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    messages = [
        {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(_brief_payload(state), ensure_ascii=False)},
    ]
    response = requests.post(
        f"{cfg.base_url}/chat/completions",
        headers=headers,
        json={"model": cfg.model, "messages": messages, "temperature": 0.2},
        timeout=max(1, min(cfg.timeout_seconds, 2)),
    )
    response.raise_for_status()
    payload = response.json()
    answer = payload.get("choices", [{}])[0].get("message", {}).get("content")
    return str(answer or "").strip()


def _direct_general_answer(state: AgentState) -> str:
    text = re.sub(r"\s+", "", state.question or "")
    today = datetime.now().date()
    if "明天" in text and ("几号" in text or "日期" in text or "哪天" in text):
        return f"明天是 {(today + timedelta(days=1)).isoformat()}。"
    if "今天" in text and ("星期" in text or "周几" in text):
        weekdays = "一二三四五六日"
        return f"今天是 {today.isoformat()}，星期{weekdays[today.weekday()]}。"
    if _contains_any(text, {"你好", "您好", "hello", "hi"}):
        return "你好，我可以帮你分析电价预测、风险时段、交易建议、模型误差和日报摘要，也可以回答简单通用问题。"
    return "这个问题不需要调用电力预测数据。你可以直接告诉我需要解释、总结或改写的内容；如果要分析电价、负荷、天气对电价的影响，我会结合系统数据回答。"


def _fallback_weather_answer(state: AgentState) -> str:
    weather = _first(state, "get_weather_forecast")
    if not weather or weather.get("empty"):
        return "当前系统未查询到可用天气数据。"
    parts = []
    if weather.get("message"):
        parts.append(str(weather.get("message")))
    city = weather.get("city") or state.entities.get("city") or "当前城市"
    parts.append(
        f"{city} 天气参考：气温约 {_num(weather.get('min_temperature'))} 至 {_num(weather.get('max_temperature'))} 摄氏度，平均约 {_num(weather.get('avg_temperature'))} 摄氏度。"
    )
    records = weather.get("records") or []
    if records:
        sample = records[0]
        if sample.get("precipitation") is not None:
            parts.append(f"首条可用记录降水量为 {_num(sample.get('precipitation'))}，风速约 {_num(sample.get('wind_speed'))}。")
    return "\n\n".join(parts)


def _fallback_forecast_answer(state: AgentState) -> str:
    overview_tool = _first(state, "get_prediction_overview")
    overview = overview_tool.get("overview") if isinstance(overview_tool.get("overview"), dict) else {}
    extremes = _first(state, "get_forecast_extremes")
    lines: list[str] = []
    if overview.get("message"):
        lines.append(str(overview.get("message")))
    for message in overview.get("messages") or []:
        lines.append(str(message))
    if overview:
        lines.append(
            f"结论：当前可用预测窗口为 {overview.get('forecast_start') or '-'} 至 {overview.get('forecast_end') or '-'}；均价约 {_money(overview.get('avg_price_pred'))}，最高价约 {_money(overview.get('peak_price_pred'))}，最低价约 {_money(overview.get('valley_price_pred'))}，风险等级为 {overview.get('risk_level') or '-'}。"
        )
    elif extremes and not extremes.get("empty"):
        subject = state.entities.get("subject")
        if subject == "lowest":
            lines.append(f"结论：最低价在 {extremes.get('min_price_hour')}，约 {_money(extremes.get('min_price'))}。")
        else:
            lines.append(f"结论：最高电价在 {extremes.get('max_price_hour')}，约 {_money(extremes.get('max_price'))}。")
        lines.append(f"数据依据：均价约 {_money(extremes.get('avg_price'))}，峰谷价差约 {_money(extremes.get('peak_valley_spread'))}。")
    if overview.get("main_factors"):
        lines.append("主要影响因素：" + "；".join(map(str, overview.get("main_factors")[:5])))
    if state.focus_periods:
        lines.append("建议关注：" + "、".join(state.focus_periods[:6]))
    return "\n\n".join(lines) if lines else "当前系统未查询到可用预测数据，无法严谨分析电价。"


def _fallback_risk_answer(state: AgentState) -> str:
    hour_detail = _first(state, "get_hour_detail")
    hour_evidence = _first(state, "build_hour_risk_evidence")
    if hour_detail and not hour_detail.get("empty"):
        reasons = hour_detail.get("reasons") or []
        recommendation = hour_evidence.get("recommendation") if hour_evidence else ""
        return (
            f"结论：{hour_detail.get('hour')} 的预测电价约 {_money(hour_detail.get('predicted_price'))}，风险等级为 {hour_detail.get('risk_level') or '-'}。"
            + ("\n\n原因：" + "；".join(map(str, reasons[:5])) if reasons else "")
            + (f"\n\n建议：{recommendation}" if recommendation else "\n\n建议：结合负荷预测、尖峰概率和售电敞口做人工复核。")
        )
    high = _first(state, "get_high_risk_hours")
    if high and not high.get("empty"):
        items = high.get("items") or []
        if items:
            rows = [f"{item.get('hour')}：{item.get('risk_level')}，预测价 {_money(item.get('predicted_price'))}" for item in items[:6]]
            return "结论：当前需要重点关注以下风险时段。\n\n" + "\n".join(f"- {row}" for row in rows) + "\n\n建议：这些时段应优先复核负荷预测、尖峰概率、售电敞口和实时市场变化。"
    if state.risk_level:
        return f"当前风险等级为 {state.risk_level}。建议结合预测价格、负荷和尖峰概率做人工复核。"
    return "当前系统未查询到明确风险时段。"


def _fallback_factor_answer(state: AgentState) -> str:
    lines = [_fallback_forecast_answer(state)]
    useful = [obs["text"] for obs in state.observations if obs.get("type") in {"load", "weather", "renewable_scope", "model", "history", "risk_window", "trading"}]
    if useful:
        lines.append("原因分析：" + "\n".join(f"- {text}" for text in useful[:8]))
    if state.risk_level or state.focus_periods:
        risk = state.risk_level or "需关注"
        lines.append(f"风险提示：当前风险等级 {risk}；重点关注 {('、'.join(state.focus_periods[:6]) if state.focus_periods else '高价和尖峰概率抬升时段')}。")
    lines.append("交易建议：以上结论只作为辅助分析参考，建议结合实时市场、合同仓位和人工复核后再调整交易计划。")
    return "\n\n".join(line for line in lines if line)


def _fallback_report_answer(state: AgentState) -> str:
    report = _first(state, "get_report_summary")
    if report and not report.get("empty"):
        summary = report.get("summary") or {}
        core = summary.get("executive_summary") or summary.get("management_summary") or summary.get("market_overview") or "当前报告摘要字段不足。"
        return f"最新报告：{report.get('report_id') or '-'}，状态：{'可用' if report.get('available') else '未生成'}。\n\n{core}\n\n建议：发布前继续走报告中心审核，避免把预测结论当成确定交易指令。"
    return "当前系统未查询到可用日报或周报摘要。"


def _fallback_model_answer(state: AgentState) -> str:
    model_error = _first(state, "get_model_error_summary")
    model = _first(state, "get_model_explain")
    lines: list[str] = []
    if model_error and not model_error.get("empty"):
        rows = model_error.get("error_rows") or []
        if rows:
            row = rows[0]
            lines.append(f"模型误差参考：{row.get('model_version')} 样本数 {row.get('sample_count')}，MAE 约 {_num(row.get('mae'))}，RMSE 约 {_num(row.get('rmse'))}。")
    if model and not model.get("empty"):
        lines.append(f"当前模型置信参考值约 {_num(model.get('model_confidence'))}。")
        factors = model.get("main_factors") or [item.get("feature") for item in (model.get("feature_importance") or [])[:5]]
        factors = [str(item) for item in factors if item]
        if factors:
            lines.append("主要特征：" + "、".join(factors[:5]))
    return "\n\n".join(lines) if lines else "当前真实值回填或模型解释数据不足，暂不能严谨判断模型是否退化。"


def _fallback_answer(state: AgentState) -> str:
    if state.intent == "weather_analysis":
        return _fallback_weather_answer(state)
    if state.intent == "forecast_extreme":
        return _fallback_forecast_answer(state)
    if state.intent in {"risk_hours", "hour_explain"}:
        return _fallback_risk_answer(state)
    if state.intent in {"factor_analysis", "load_analysis", "renewable_analysis", "strategy_advice", "storage_advice", "compare_history"}:
        return _fallback_factor_answer(state)
    if state.intent == "forecast_overview":
        return _fallback_forecast_answer(state)
    if state.intent == "report_summary":
        return _fallback_report_answer(state)
    if state.intent == "model_status":
        return _fallback_model_answer(state)
    if state.intent == "data_status":
        data_status = _first(state, "get_data_status")
        sources = data_status.get("sources") or []
        if sources:
            rows = [f"{item.get('name')}：{item.get('status')}，最新时间 {item.get('latest_time') or '-'}" for item in sources[:6]]
            return "数据接入状态：\n\n" + "\n".join(f"- {row}" for row in rows)
        return "当前系统未查询到数据源状态。"
    if not state.professional:
        return _direct_general_answer(state)
    return _fallback_factor_answer(state)


def answer_agent(state: AgentState) -> AgentState:
    global _LLM_DISABLED_UNTIL
    if not state.evidence and state.intent == "general_analysis" and not state.professional:
        _evidence(state, "通用问答", "未调用电力业务数据", "assistant")
    try:
        answer = _call_local_llm(state)
        if answer:
            state.answer = answer
            state.model_used = True
    except Exception as exc:
        _LLM_DISABLED_UNTIL = time.time() + 60
        state.model_error = f"本地模型未连接或调用失败：{exc}"
        state.answer = _fallback_answer(state)

    if not state.suggestions:
        _extend_unique(state.suggestions, state.focus_periods[:6])
        for obs in state.observations:
            if obs.get("type") in {"risk_window", "trading", "data_scope"}:
                _extend_unique(state.suggestions, [obs.get("text")])
    state.related_actions = _related_actions(state)
    state.trace("answer_agent", "ok", "已生成最终回答", model_used=state.model_used)
    return state


def _related_actions(state: AgentState) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if state.intent in {"forecast_overview", "forecast_extreme", "factor_analysis", "risk_hours"}:
        actions.append({"label": "查看预测分析", "params": {"page": "forecast"}})
    if state.intent in {"strategy_advice", "storage_advice", "factor_analysis"}:
        actions.append({"label": "查看策略建议", "params": {"page": "strategy"}})
    if state.intent in {"report_summary"}:
        actions.append({"label": "查看 AI 报告", "params": {"page": "report"}})
    if state.intent in {"model_status"}:
        actions.append({"label": "查看模型监控", "params": {"page": "models"}})
    if state.intent in {"data_status"}:
        actions.append({"label": "查看数据接入", "params": {"page": "data"}})
    return actions[:3]
