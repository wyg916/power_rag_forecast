from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class IntentResult:
    intent: str
    entities: dict[str, object] = field(default_factory=dict)
    confidence: float = 0.7


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def extract_hour(question: str) -> int | None:
    text = question or ""
    patterns = [
        r"(?<!\d)([01]?\d|2[0-3])\s*[点时]",
        r"(?<!\d)([01]?\d|2[0-3])[:：]00",
        r"\b([01]?\d|2[0-3])\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return None


def extract_market(question: str) -> str | None:
    candidates = [
        "广东",
        "江苏",
        "浙江",
        "山东",
        "山西",
        "河南",
        "河北",
        "安徽",
        "福建",
        "四川",
        "PJM",
        "DOM",
    ]
    text = question or ""
    for item in candidates:
        if item.lower() in text.lower():
            return item
    return None


def extract_date(question: str) -> str | None:
    text = question or ""
    today = datetime.now().date()
    if "明天" in text:
        return (today + timedelta(days=1)).isoformat()
    if "今天" in text or "今日" in text:
        return today.isoformat()
    if "昨天" in text:
        return (today - timedelta(days=1)).isoformat()
    match = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})", text)
    if match:
        year, month, day = [int(x) for x in match.groups()]
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return None
    match = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if match:
        month, day = [int(x) for x in match.groups()]
        try:
            return datetime(today.year, month, day).date().isoformat()
        except ValueError:
            return None
    return None


def classify(question: str, previous_context: dict | None = None) -> IntentResult:
    text = _normalize(question)
    hour = extract_hour(question)
    entities: dict[str, object] = {}
    if hour is not None:
        entities["hour"] = hour
    market = extract_market(question)
    date = extract_date(question)
    if market:
        entities["market"] = market
    if date:
        entities["date"] = date

    if any(key in text for key in ["储能", "充电", "放电", "soc"]):
        return IntentResult("storage_advice", entities, 0.92)
    if hour is not None and any(key in text for key in ["为什么", "原因", "解释", "风险", "高", "异常", "波动"]):
        return IntentResult("hour_explain", entities, 0.93)
    if any(key in text for key in ["风险最高", "高风险", "高价风险", "有没有风险", "风险时段", "哪些时段风险", "晚高峰", "人工复核", "异常时段"]):
        return IntentResult("risk_hours", entities, 0.9)
    if any(key in text for key in ["可靠", "置信", "准不准", "可信", "模型", "误差", "mae", "rmse", "重训", "退化"]):
        return IntentResult("model_status", entities, 0.9)
    if any(key in text for key in ["报告", "日报", "核心结论", "发布", "审核", "摘要"]):
        return IntentResult("report_summary", entities, 0.9)
    if any(key in text for key in ["数据更新", "数据源", "数据接入", "缺失", "行数", "今天数据"]):
        return IntentResult("data_status", entities, 0.88)
    if any(key in text for key in ["天气", "气温", "温度", "下雨", "降雨", "风速", "湿度"]):
        if "电价" in text and any(key in text for key in ["影响", "原因", "上涨", "下跌"]):
            return IntentResult("factor_analysis", entities, 0.88)
        return IntentResult("weather_analysis", entities, 0.9)
    if any(key in text for key in ["新能源", "风电", "光伏", "出力"]):
        return IntentResult("renewable_analysis", entities, 0.86)
    if any(key in text for key in ["负荷", "用电"]):
        return IntentResult("load_analysis", entities, 0.86)
    if any(key in text for key in ["上涨", "下跌", "涨价", "跌价", "影响因素", "受哪些因素", "主要受", "原因分析"]):
        return IntentResult("factor_analysis", entities, 0.88)
    if any(key in text for key in ["昨天", "历史", "相比", "变化", "同比", "环比"]):
        return IntentResult("compare_history", entities, 0.78)
    if any(key in text for key in ["交易策略", "策略", "怎么做", "敞口", "采购", "售电", "交易建议"]):
        return IntentResult("strategy_advice", entities, 0.88)
    if any(key in text for key in ["怎么看", "预测", "电价走势", "价格走势", "明天电价", "今日电价"]):
        return IntentResult("forecast_overview", entities, 0.88)
    if any(key in text for key in ["最高", "最低", "高价", "低价", "均价", "峰谷", "价差", "什么时候"]):
        subject = "lowest" if any(key in text for key in ["最低", "低价"]) and "最高" not in text else "highest"
        if any(key in text for key in ["最高", "最低", "峰谷", "均价"]):
            entities["subject"] = subject
        return IntentResult("forecast_extreme", entities, 0.88)
    return IntentResult("general_analysis", entities, 0.62)
