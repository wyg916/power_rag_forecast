from __future__ import annotations

import json
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from config_loader import load_dotenv
from backend.app.config import PROJECT_ROOT


DEFAULT_SYNONYMS: dict[str, list[str]] = {
    "用电量": ["负荷", "电力需求", "load"],
    "价格冲高": ["高价风险", "尖峰价格", "暴涨", "spike"],
    "价格偏高": ["高价", "高价风险", "峰值电价", "尖峰"],
    "明天": ["日前", "下一自然日", "day-ahead"],
    "误差变大": ["RMSE上升", "MAE上升", "模型退化", "预测偏差"],
    "绿电证书": ["绿证", "绿色电力证书", "GEC"],
    "代理买电": ["电网代理购电", "代理购电"],
    "实时市场": ["real-time", "实时电价", "RT"],
    "日前市场": ["day-ahead", "日前电价", "DA"],
    "节点电价": ["LMP", "locational marginal price", "边际价格"],
    "峰谷价差": ["分时电价", "高峰", "低谷", "TOU"],
    "市场清算": ["市场出清", "出清价格", "结算"],
    "售电公司": ["零售商", "电力零售", "交易主体"],
    "新能源": ["光伏", "风电", "储能", "可再生能源"],
    "数据不足": ["缺少数据", "没有数据", "数据缺失", "证据不足", "无法判断", "样本不足", "data_insufficient_explanation"],
    "天气新鲜度": ["天气更新时间", "气象数据", "温度数据", "天气过期", "天气预测窗口", "weather_data_freshness_policy"],
    "尖峰概率": ["尖峰风险", "价格尖峰", "价格冲高", "晚高峰风险", "spike", "peak_spike_probability_explanation"],
    "储能约束": ["SOC", "容量约束", "功率约束", "循环次数", "储能套利", "storage_strategy_constraints"],
    "模型切换": ["模型回退", "DeepSeek", "Ollama", "本地模型", "auto", "fallback", "llm_router_fallback_policy"],
    "策略建议": ["交易建议", "辅助决策", "风险提示", "交易指令", "evidence_based_answer_policy"],
}


def _env(name: str, default: str = "") -> str:
    load_dotenv()
    return os.environ.get(name, default).strip()


def _enabled() -> bool:
    return (_env("RAG_QUERY_REWRITE_ENABLED", "1") or "1").lower() not in {"0", "false", "no", "off"}


def _config_path() -> Path:
    value = _env("RAG_DOMAIN_SYNONYMS_PATH", "")
    return Path(value) if value else PROJECT_ROOT / "knowledge_pipeline" / "domain_synonyms.json"


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").lower())


@lru_cache(maxsize=8)
def _load_synonyms(path_value: str, mtime: float) -> dict[str, list[str]]:
    _ = mtime
    path = Path(path_value)
    if not path.exists():
        return DEFAULT_SYNONYMS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_SYNONYMS
    output: dict[str, list[str]] = {}
    if not isinstance(data, dict):
        return DEFAULT_SYNONYMS
    for key, values in data.items():
        if not str(key).strip():
            continue
        if isinstance(values, list):
            clean_values = [str(item).strip() for item in values if str(item).strip()]
        else:
            clean_values = [str(values).strip()] if str(values).strip() else []
        output[str(key).strip()] = clean_values
    return output or DEFAULT_SYNONYMS


def _synonyms() -> dict[str, list[str]]:
    path = _config_path()
    try:
        mtime = path.stat().st_mtime
    except Exception:
        mtime = 0.0
    return _load_synonyms(str(path), mtime)


def _cache_ttl_seconds() -> int:
    try:
        ttl = int(_env("RAG_QUERY_REWRITE_CACHE_TTL_SECONDS", _env("RAG_CACHE_TTL_SECONDS", "600")) or "600")
    except Exception:
        ttl = 600
    return max(0, min(ttl, 3600))


def _cache_bucket() -> str:
    ttl = _cache_ttl_seconds()
    if ttl <= 0:
        return str(time.time_ns())
    return str(int(time.time() // ttl))


def rewrite_rag_query(query: str) -> dict[str, Any]:
    """Expand only the retrieval query. The original user question is preserved."""
    original = (query or "").strip()
    if not original or not _enabled():
        return {
            "query": original,
            "expanded_query": original,
            "expanded_terms": [],
            "matched_rules": [],
            "enabled": False,
        }
    return dict(_rewrite_rag_query_cached(original, _cache_bucket()))


@lru_cache(maxsize=512)
def _rewrite_rag_query_cached(original: str, bucket: str) -> dict[str, Any]:
    _ = bucket

    compact_query = _compact(original)
    expanded_terms: list[str] = []
    matched_rules: list[str] = []
    for key, values in _synonyms().items():
        terms = [key, *values]
        if any(_compact(term) and _compact(term) in compact_query for term in terms):
            matched_rules.append(key)
            expanded_terms.extend(terms)

    max_terms = 32
    try:
        max_terms = max(4, min(int(_env("RAG_QUERY_EXPANSION_MAX_TERMS", "32") or "32"), 80))
    except Exception:
        pass
    unique_terms = list(dict.fromkeys(term for term in expanded_terms if term and term not in original))[:max_terms]
    expanded_query = original if not unique_terms else f"{original}\n检索扩展词：" + " ".join(unique_terms)
    return {
        "query": original,
        "expanded_query": expanded_query,
        "expanded_terms": unique_terms,
        "matched_rules": matched_rules,
        "enabled": True,
    }
