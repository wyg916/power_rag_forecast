from __future__ import annotations

import re

from ..schemas import IntentDecision
from .input_normalizer import compact_question, looks_like_user_text_explain, normalize_question

TABLE_NAME_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9_]{2,}\b")


def _has_any(question: str, terms: list[str]) -> bool:
    return any(compact_question(term) in question for term in terms if compact_question(term))


def _extract_table_names(question: str) -> list[str]:
    candidates: list[str] = []
    for value in TABLE_NAME_RE.findall(question):
        lower = value.lower()
        if lower.startswith(("raw_", "result_", "forecast_", "prediction_", "model_", "kb_", "ai_")) or lower in {
            "tasks",
            "reports",
            "users",
            "audit_logs",
            "feature_importance",
        }:
            candidates.append(lower)
    return list(dict.fromkeys(candidates))[:8]


def _extract_limit(question: str) -> int | None:
    match = re.search(r"(?:前|最新|最近)?\s*(\d{1,3})\s*(?:条|行|个|笔)", question)
    if not match:
        return None
    return max(1, min(int(match.group(1)), 50))


def _hour(question: str) -> int | None:
    match = re.search(r"(?<!\d)([01]?\d|2[0-3])\s*(?:点|时|:00|：00)", question)
    return int(match.group(1)) if match else None


def _station_id(question: str) -> str:
    match = re.search(r"\d{8,}", question)
    return match.group(0) if match else ""


def _business_month(question: str) -> str:
    match = re.search(r"(20\d{2})\D{0,3}([01]?\d)", question)
    return f"{match.group(1)}{int(match.group(2)):02d}" if match else ""


def _grid_date(question: str) -> str:
    match = re.search(r"(20\d{2})\D{0,2}([01]?\d)\D{0,2}([0-3]?\d)", question)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    match = re.search(r"(20\d{2})\D{0,2}([01]?\d)\s*(?:月|/|-)", question)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-15"
    match = re.search(r"(20\d{2})\s*年?", question)
    return f"{match.group(1)}-06-30" if match else ""


def route_intent(question: str) -> IntentDecision:
    normalized = normalize_question(question)
    q = compact_question(normalized)
    latin_q = normalized.lower()
    entities: dict[str, object] = {}
    table_names = _extract_table_names(normalized)
    if table_names:
        freshness_terms = ["新鲜度", "更新", "截止", "到哪天", "最新时间", "数据范围", "freshness", "latest time"]
        query_terms = ["查数", "查询", "查一下", "看一下", "最新几条", "最新", "多少条", "记录数", "sql", "select", "table", "database"]
        if any(term in q or term in latin_q for term in freshness_terms) or ("最新" in q and any(term in q for term in ["几号", "哪天", "时间", "截止", "范围"])):
            return IntentDecision("database_table_freshness", 0.96, {"tables": table_names}, normalized)
        if any(term in q or term in latin_q for term in query_terms):
            query_entities: dict[str, object] = {"tables": table_names}
            limit = _extract_limit(normalized)
            if limit:
                query_entities["limit"] = limit
            return IntentDecision("data_sql_query", 0.94, query_entities, normalized)
    if any(k in q for k in ["查数", "数据库", "数据表", "最新几条", "最近几条", "多少条", "记录数"]) and any(
        k in q for k in ["天气", "预测结果", "负荷", "电价", "模型误差", "任务", "特征"]
    ):
        query_entities = {}
        limit = _extract_limit(normalized)
        if limit:
            query_entities["limit"] = limit
        return IntentDecision("data_sql_query", 0.9, query_entities, normalized)
    hour = _hour(normalized)
    if hour is not None:
        entities["hour"] = hour

    brief_terms = ["一句话回答", "一句话说说", "简短回答", "简洁回答", "用一句话", "一句话"]
    greeting_terms = ["你好", "您好", "早上好", "下午好", "晚上好", "hello", "hi"]
    thanks_terms = ["谢谢", "感谢", "辛苦了"]
    identity_terms = ["你是谁", "你是什么助手", "你是什么", "介绍一下你自己"]
    capability_terms = [
        "你能做什么",
        "你可以做什么",
        "你可以帮我分析什么",
        "你可以帮我分析哪些内容",
        "你能帮我分析什么",
        "你能帮我看什么",
        "你会分析哪些内容",
        "这个助手有什么用",
        "助手有什么用",
        "能做什么",
        "可以做什么",
    ]
    time_terms = ["现在几点", "几点了", "当前时间", "现在时间"]
    weekday_terms = ["今天星期几", "今天周几", "星期几", "周几", "当前日期", "今天几号", "今天是几号", "今天日期", "现在日期"]
    plain_terms = ["通俗话", "通俗地", "简单说", "简单解释", "解释一下你是什么助手"]
    daily_flags = {
        "brief": _has_any(q, brief_terms),
        "greeting": _has_any(q, greeting_terms),
        "thanks": _has_any(q, thanks_terms),
        "identity": _has_any(q, identity_terms),
        "capability": _has_any(q, capability_terms),
        "time": _has_any(q, time_terms),
        "weekday": _has_any(q, weekday_terms),
        "plain": _has_any(q, plain_terms),
    }
    if daily_flags["brief"] and any(marker in q for marker in ["能做什么", "可以做什么", "分析什么", "分析哪些内容"]):
        daily_flags["capability"] = True
    active_daily = [key for key, value in daily_flags.items() if value and key != "brief"]
    if len(active_daily) > 1:
        return IntentDecision("multi_daily_chat", 0.98, {"daily_flags": active_daily, "brief": daily_flags["brief"]}, normalized)
    if daily_flags["capability"]:
        return IntentDecision("capability", 0.98, {"brief": daily_flags["brief"]}, normalized)
    if daily_flags["plain"]:
        return IntentDecision("plain_language_intro", 0.97, {"brief": daily_flags["brief"]}, normalized)
    if daily_flags["identity"]:
        return IntentDecision("identity", 0.98, {"brief": daily_flags["brief"]}, normalized)
    if daily_flags["time"]:
        return IntentDecision("time", 0.99, {}, normalized)
    if daily_flags["weekday"]:
        return IntentDecision("weekday", 0.99, {}, normalized)
    if daily_flags["greeting"]:
        return IntentDecision("greeting", 0.96, {}, normalized)
    if daily_flags["thanks"]:
        return IntentDecision("thanks", 0.96, {}, normalized)
    if daily_flags["brief"]:
        return IntentDecision("brief_answer_request", 0.9, {}, normalized)

    if "天气" in q and any(k in q for k in ["没更新", "未更新", "没有更新", "过期", "更新时间", "新鲜度"]):
        return IntentDecision("weather_data_latest_time", 0.98, {"domain": "weather"}, normalized)

    if looks_like_user_text_explain(normalized):
        return IntentDecision("user_provided_text_explain", 0.98, {"text": normalized}, normalized)
    if any(k in q for k in ["今天星期几", "今天周几", "现在星期几", "现在周几", "星期几", "周几"]):
        return IntentDecision("current_date_query", 0.99, {}, normalized)
    if any(k in q for k in ["这个系统是做什么", "系统是做什么", "项目是做什么", "ai助手能做什么", "先看哪个页面", "应该先看哪个页面"]):
        return IntentDecision("knowledge_search", 0.88, {"keyword": normalized}, normalized)
    if any(k in latin_q for k in ["day-ahead", "day ahead", "real-time", "real time", "pjm", "lmp", "dom"]):
        return IntentDecision("knowledge_search", 0.9, {"keyword": normalized}, normalized)
    if any(k in q for k in ["尖峰概率", "尖峰风险", "峰谷价差", "日前市场", "实时市场", "节点电价"]):
        return IntentDecision("knowledge_search", 0.9, {"keyword": normalized}, normalized)
    if any(k in q for k in ["南网", "南方电网", "税率", "代扣代缴", "完税", "回款金额"]):
        return IntentDecision("southern_grid_tax_query", 0.95, {"keyword": normalized}, normalized)
    if any(k in q for k in ["电站编码", "电站电价", "电费清单", "核对", "供电局国补", "供电局省补"]):
        return IntentDecision("station_tariff_check", 0.95, {"station_id": _station_id(normalized), "keyword": normalized}, normalized)
    if any(k in q for k in ["市电", "综合电价", "脱硫煤", "辅助分摊", "市场电价规则"]):
        return IntentDecision("market_power_price_query", 0.93, {"business_month": _business_month(normalized), "keyword": normalized}, normalized)
    if any(k in q for k in ["知识库", "rag", "检索文档", "政策文档", "文件摘要"]):
        return IntentDecision("knowledge_search", 0.9, {"keyword": normalized}, normalized)
    if any(k in q for k in ["光伏政策", "电价政策", "补贴政策", "发改文件", "政策摘要", "文号"]):
        return IntentDecision("tariff_policy_search", 0.93, {"keyword": normalized}, normalized)
    if any(k in q for k in ["光伏电价", "上网电价", "补贴电价", "并网电价", "初始化电价", "总价"]) and any(k in q for k in ["查询", "多少", "规则", "并网", "补贴", "电价"]):
        return IntentDecision("tariff_query", 0.94, {"grid_date": _grid_date(normalized), "keyword": normalized}, normalized)
    if any(k in q for k in ["今天几号", "今天是几号", "当前日期", "现在日期", "今天日期", "现在几点", "当前时间", "几点了"]):
        return IntentDecision("current_date_query", 0.99, {}, normalized)
    if "天气" in q and any(k in q for k in ["截止", "最新", "到哪天", "日期", "数据范围", "更新时间"]):
        return IntentDecision("weather_data_latest_time", 0.99, {"domain": "weather"}, normalized)
    if any(k in q for k in ["电价数据", "价格数据", "日前价格", "实时价格"]) and any(k in q for k in ["截止", "最新", "数据范围", "更新时间"]):
        domain = "rt_price" if "实时" in q else "da_price"
        return IntentDecision("price_data_latest_time", 0.98, {"domain": domain}, normalized)
    if "负荷" in q and any(k in q for k in ["截止", "最新", "数据范围", "更新时间"]):
        return IntentDecision("load_data_latest_time", 0.98, {"domain": "forecast_load" if "预测" in q else "load"}, normalized)
    if "数据" in q and any(k in q for k in ["更新", "状态", "新鲜度", "表", "数据库"]):
        return IntentDecision("database_table_freshness", 0.92, {"domain": "master_table"}, normalized)
    if any(k in q for k in ["预测窗口", "本次预测是哪天", "预测是哪天", "预测范围"]):
        return IntentDecision("prediction_window_query", 0.96, {}, normalized)
    if any(k in q for k in ["适合储能放电", "储能放电", "放电时段", "哪些时段放电"]):
        return IntentDecision("storage_discharge_advice", 0.96, {}, normalized)
    if any(k in q for k in ["适合储能充电", "储能充电", "充电时段", "哪些时段充电"]):
        return IntentDecision("storage_charge_advice", 0.96, {}, normalized)
    if any(k in q for k in ["哪些小时价格", "哪些小时电价", "价格可能偏高", "电价可能偏高", "高价时段", "价格偏高", "电价偏高"]):
        return IntentDecision("forecast_risk_hours", 0.93, entities, normalized)
    if any(k in q for k in ["晚高峰价格高", "晚高峰电价高", "高价先看什么指标", "价格高先看什么指标", "电价高先看什么指标"]):
        return IntentDecision("trading_risk_summary", 0.9, entities, normalized)
    if any(k in q for k in ["低价窗口适合", "低价窗口是否", "低价窗口应该", "低价窗口能不能", "低价窗口可以"]) and any(k in q for k in ["采购", "买入", "利用"]):
        return IntentDecision("trading_risk_summary", 0.9, entities, normalized)
    if any(k in q for k in ["预测价格接近零", "价格接近零", "电价接近零", "零电价", "接近零"]):
        return IntentDecision("low_price_reason", 0.92, entities, normalized)
    if any(k in q for k in ["最低电价", "最低价", "电价最低", "低价窗口"]) and any(k in q for k in ["为什么", "原因", "为啥"]):
        return IntentDecision("low_price_reason", 0.95, entities, normalized)
    if any(k in q for k in ["最高电价", "最高价", "电价最高", "高价"]) and any(k in q for k in ["为什么", "原因", "为啥"]):
        return IntentDecision("high_price_reason", 0.95, entities, normalized)
    if "风险" in q and any(k in q for k in ["哪些", "最高", "时段", "高价", "晚高峰", "复核"]):
        return IntentDecision("forecast_risk_hours", 0.94, entities, normalized)
    if any(k in q for k in ["晚高峰容易出现尖峰", "晚高峰为什么尖峰", "晚高峰尖峰价格", "尖峰价格为什么"]):
        return IntentDecision("risk_reason", 0.92, entities, normalized)
    if any(k in q for k in ["温度升高", "气温升高", "高温"]) and any(k in q for k in ["预测字段", "关注哪些", "电价", "风险"]):
        return IntentDecision("weather_impact_on_price", 0.9, entities, normalized)
    if any(k in q for k in ["交易风险", "风险提示", "交易建议", "交易策略", "怎么做"]):
        return IntentDecision("trading_risk_summary", 0.9, entities, normalized)
    if any(k in q for k in ["储能套利", "低充高放"]) or ("储能" in q and "价差" in q):
        return IntentDecision("storage_spread_analysis", 0.92, entities, normalized)
    if any(k in q for k in ["连续低价", "低价时段"]) and any(k in q for k in ["采购", "策略", "注意"]):
        return IntentDecision("trading_risk_summary", 0.9, entities, normalized)
    if "风险" in q and any(k in q for k in ["为什么", "原因", "为啥"]):
        return IntentDecision("risk_reason", 0.92, entities, normalized)
    if any(k in q for k in ["最高电价", "最高价", "电价最高"]):
        return IntentDecision("forecast_max_price", 0.96, entities, normalized)
    if any(k in q for k in ["最低电价", "最低价", "电价最低", "低价窗口"]):
        return IntentDecision("forecast_min_price", 0.96, entities, normalized)
    if any(k in q for k in ["平均电价", "均价"]):
        return IntentDecision("forecast_avg_price", 0.94, entities, normalized)
    if any(k in q for k in ["峰谷价差", "价差"]):
        return IntentDecision("forecast_spread", 0.94, entities, normalized)
    if any(k in q for k in ["高风险", "风险时段", "人工复核", "晚高峰风险"]):
        return IntentDecision("forecast_risk_hours", 0.92, entities, normalized)
    if "天气" in q and "电价" in q and any(k in q for k in ["影响", "原因", "上涨", "下跌"]):
        return IntentDecision("weather_impact_on_price", 0.9, entities, normalized)
    if "天气" in q:
        return IntentDecision("weather_summary", 0.9, entities, normalized)
    if any(k in q for k in ["报告", "日报", "摘要", "核心结论"]):
        return IntentDecision("report_summary", 0.88, entities, normalized)
    if any(k in q for k in ["真实值回填", "回填不足", "样本不足"]):
        return IntentDecision("model_error_status", 0.92, entities, normalized)
    if any(k in q for k in ["模型误差", "误差变大", "误差", "mae", "rmse", "模型状态", "预测结果可靠", "可靠吗", "准不准", "可信"]):
        return IntentDecision("model_error_status", 0.9, entities, normalized)
    if any(k in q for k in ["重训", "退化"]):
        return IntentDecision("model_retrain_suggestion", 0.9, entities, normalized)
    if any(k in q for k in ["电价", "交易", "售电", "风险", "上涨", "下跌", "原因", "因素影响", "预测结果", "新能源", "出力", "负荷"]):
        return IntentDecision("trading_risk_summary", 0.75, entities, normalized)
    return IntentDecision("general_query", 0.6, entities, normalized)
