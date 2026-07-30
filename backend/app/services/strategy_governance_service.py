from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine
from typing import Any


STRATEGY_STATUSES = {
    "draft", "pending_review", "approved", "rejected", "published",
    "superseded", "expired", "cancelled",
}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"pending_review", "cancelled", "expired"},
    "pending_review": {"draft", "approved", "rejected", "cancelled", "expired"},
    "approved": {"published", "superseded", "expired", "cancelled"},
    "published": {"superseded", "expired", "cancelled"},
    "rejected": set(),
    "superseded": set(),
    "expired": set(),
    "cancelled": set(),
}

ACTION_TARGETS = {
    "submit": "pending_review",
    "approve": "approved",
    "reject": "rejected",
    "return": "draft",
    "publish": "published",
    "supersede": "superseded",
    "expire": "expired",
    "cancel": "cancelled",
}


class StrategyGovernanceError(ValueError):
    """Fail-closed strategy governance contract violation."""


@dataclass(frozen=True)
class TransitionDecision:
    action: str
    previous_status: str
    new_status: str


def validate_transition(previous_status: str, action: str) -> TransitionDecision:
    previous = str(previous_status or "").strip().lower()
    normalized_action = str(action or "").strip().lower()
    if previous not in STRATEGY_STATUSES:
        raise StrategyGovernanceError(f"unknown_strategy_status:{previous or 'empty'}")
    target = ACTION_TARGETS.get(normalized_action)
    if not target:
        raise StrategyGovernanceError(f"unknown_strategy_action:{normalized_action or 'empty'}")
    if target not in ALLOWED_TRANSITIONS[previous]:
        raise StrategyGovernanceError(f"illegal_strategy_transition:{previous}->{target}")
    return TransitionDecision(normalized_action, previous, target)


def validate_reviewer(*, creator: str, reviewer: str, reviewer_role: str, action: str) -> None:
    actor = str(reviewer or "").strip()
    role = str(reviewer_role or "").strip().lower()
    if not actor:
        raise StrategyGovernanceError("reviewer_required")
    if action in {"approve", "reject", "return"} and role not in {"reviewer", "admin"}:
        raise StrategyGovernanceError("reviewer_role_required")
    if action in {"publish", "supersede", "expire", "cancel"} and role != "admin":
        raise StrategyGovernanceError("admin_role_required")
    if action == "approve" and str(creator or "").strip() == actor:
        raise StrategyGovernanceError("creator_cannot_approve_own_strategy")

RULE_VERSION = "phase5d-rules-v1"
PROHIBITED_ACTIONS = [
    "auto_trade", "auto_bid", "device_control", "storage_dispatch",
    "load_control", "fund_transfer", "external_system_write", "guaranteed_return",
]


@dataclass(frozen=True)
class StrategyRule:
    rule_id: str
    strategy_type: str
    condition: str
    required_fields: tuple[str, ...]
    threshold: Any
    risk_level: str
    priority: int
    explanation_template: str

    def public(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_version": RULE_VERSION,
            "strategy_type": self.strategy_type,
            "condition": self.condition,
            "required_fields": list(self.required_fields),
            "threshold": self.threshold,
            "risk_level": self.risk_level,
            "priority": self.priority,
            "prohibited_actions": PROHIBITED_ACTIONS,
            "explanation_template": self.explanation_template,
            "active": True,
            "effective_at": "2026-07-22T00:00:00+08:00",
            "expires_at": None,
        }


RULES = (
    StrategyRule("P5D-R001", "peak_avoidance", "maximum_price >= threshold", ("prices",), 300.0, "high", 80, "发现高价时段，仅供人工规避风险评估。"),
    StrategyRule("P5D-R002", "peak_avoidance", "maximum_spike_probability >= threshold", ("spike_probabilities",), 0.7, "high", 85, "尖峰概率达到阈值，应人工复核预测不确定性。"),
    StrategyRule("P5D-R003", "load_shift", "peak_valley_spread >= threshold", ("prices",), 200.0, "medium", 60, "峰谷价差达到阈值，可评估负荷转移但不得自动执行。"),
    StrategyRule("P5D-R004", "low_price_window", "minimum_price <= threshold", ("prices",), 40.0, "low", 40, "存在低价窗口，需结合约束人工评估。"),
    StrategyRule("P5D-R005", "negative_price_opportunity", "minimum_price < threshold", ("prices",), 0.0, "medium", 65, "出现负电价，仅提示人工调查机会与约束。"),
    StrategyRule("P5D-R006", "volatility_watch", "population_price_stddev >= threshold", ("prices",), 100.0, "high", 75, "价格波动较高，应优先风险复核。"),
    StrategyRule("P5D-R007", "manual_review_required", "is_stale is true", ("is_stale",), True, "high", 100, "数据已过期，仅限历史审计。"),
    StrategyRule("P5D-R008", "data_refresh_required", "source unavailable or forecast row count != 24", ("source_type", "forecast_record_count"), 24, "high", 100, "预测来源不可用或记录不完整，停止生成操作性建议。"),
    StrategyRule("P5D-R009", "manual_review_required", "report unavailable or lacks evidence", ("report_status", "report_evidence_count"), 2, "high", 95, "报告证据不足，必须补充证据后人工复核。"),
    StrategyRule("P5D-R010", "no_action", "historical or stale input", ("source_type", "is_stale"), "historical_or_stale", "medium", 100, "历史数据只能用于审计验证，不形成当前行动。"),
)

_RULE_BY_ID = {rule.rule_id: rule for rule in RULES}
_RISK_RANK = {"low": 1, "medium": 2, "high": 3}


def rule_inventory() -> list[dict[str, Any]]:
    return [rule.public() for rule in RULES]


def _canonical_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _number(value: Any, field: str) -> float:
    if value is None or isinstance(value, bool):
        raise StrategyGovernanceError(f"missing_numeric_fact:{field}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise StrategyGovernanceError(f"invalid_numeric_fact:{field}") from exc
    if result != result or result in {float("inf"), float("-inf")}:
        raise StrategyGovernanceError(f"invalid_numeric_fact:{field}")
    return result


def _ordered_records(facts: dict[str, Any]) -> list[dict[str, Any]]:
    records = facts.get("forecast_records")
    if not isinstance(records, list):
        return []
    return sorted(
        (dict(item) for item in records if isinstance(item, dict)),
        key=lambda item: str(item.get("forecast_time") or item.get("datetime") or ""),
    )


def evaluate_strategy_rules(facts: dict[str, Any]) -> dict[str, Any]:
    """Evaluate facts deterministically; no LLM or external side effect is allowed."""
    run_id = str(facts.get("run_id") or "").strip()
    report_id = str(facts.get("report_id") or "").strip()
    if not run_id or not report_id:
        raise StrategyGovernanceError("run_id_and_report_id_required")
    if facts.get("report_run_id") and str(facts["report_run_id"]) != run_id:
        facts = {**facts, "source_type": "unavailable", "unavailable_reason": "run_report_mismatch"}

    records = _ordered_records(facts)
    row_count = int(facts.get("forecast_record_count") if facts.get("forecast_record_count") is not None else len(records))
    source_type = str(facts.get("source_type") or "unavailable").lower()
    is_stale = bool(facts.get("is_stale"))
    unavailable = source_type == "unavailable" or row_count != 24 or bool(facts.get("unavailable_reason"))
    prices: list[float] = []
    spikes: list[float] = []
    if not unavailable:
        if len(records) != 24:
            unavailable = True
        else:
            for index, item in enumerate(records):
                price = item.get("corrected_predicted_price")
                if price is None:
                    price = item.get("predicted_price")
                prices.append(_number(price, f"forecast_records[{index}].predicted_price"))
                if item.get("spike_risk_prob") is not None:
                    spikes.append(_number(item.get("spike_risk_prob"), f"forecast_records[{index}].spike_risk_prob"))

    indicators = {
        "forecast_record_count": row_count,
        "maximum_price": max(prices) if prices else None,
        "minimum_price": min(prices) if prices else None,
        "peak_valley_spread": max(prices) - min(prices) if prices else None,
        "population_price_stddev": statistics.pstdev(prices) if len(prices) > 1 else None,
        "maximum_spike_probability": max(spikes) if spikes else None,
        "negative_price_count": sum(1 for price in prices if price < 0),
    }
    report_status = str(facts.get("report_status") or "").lower()
    report_evidence_count = int(facts.get("report_evidence_count") or 0)
    insufficient_report = report_status not in {"ready", "approved", "published"} or report_evidence_count < 2

    matched: list[str] = []
    if prices and indicators["maximum_price"] >= 300.0:
        matched.append("P5D-R001")
    if spikes and indicators["maximum_spike_probability"] >= 0.7:
        matched.append("P5D-R002")
    if prices and indicators["peak_valley_spread"] >= 200.0:
        matched.append("P5D-R003")
    if prices and indicators["minimum_price"] <= 40.0:
        matched.append("P5D-R004")
    if prices and indicators["minimum_price"] < 0.0:
        matched.append("P5D-R005")
    if len(prices) > 1 and indicators["population_price_stddev"] >= 100.0:
        matched.append("P5D-R006")
    if is_stale:
        matched.append("P5D-R007")
    if unavailable:
        matched.append("P5D-R008")
    if insufficient_report:
        matched.append("P5D-R009")
    if is_stale or source_type == "historical":
        matched.append("P5D-R010")
    matched = sorted(set(matched))

    if unavailable:
        strategy_types = ["data_refresh_required", "no_action"]
        risk_level, priority, output_source = "high", 100, "unavailable"
    elif is_stale or source_type == "historical":
        strategy_types = ["manual_review_required", "no_action"]
        risk_level, priority, output_source = "medium", 20, source_type
    elif insufficient_report:
        strategy_types = ["manual_review_required", "no_action"]
        risk_level, priority, output_source = "high", 95, source_type
    else:
        strategy_types = sorted({_RULE_BY_ID[item].strategy_type for item in matched}) or ["no_action"]
        if "P5D-R006" in matched and {"P5D-R004", "P5D-R005"}.intersection(matched):
            strategy_types = sorted(set(strategy_types) | {"manual_review_required"})
        risk_level = max((_RULE_BY_ID[item].risk_level for item in matched), key=lambda item: _RISK_RANK[item], default="low")
        priority = max((_RULE_BY_ID[item].priority for item in matched), default=0)
        output_source = source_type

    canonical_input = {
        "run_id": run_id,
        "report_id": report_id,
        "rule_version": RULE_VERSION,
        "source_type": source_type,
        "is_stale": is_stale,
        "unavailable_reason": facts.get("unavailable_reason"),
        "report_status": report_status,
        "report_evidence_count": report_evidence_count,
        "records": [{
            "forecast_time": item.get("forecast_time") or item.get("datetime"),
            "predicted_price": item.get("predicted_price"),
            "corrected_predicted_price": item.get("corrected_predicted_price"),
            "spike_risk_prob": item.get("spike_risk_prob"),
        } for item in records],
    }
    content_hash = _canonical_hash({
        "input": canonical_input,
        "matched_rules": matched,
        "strategy_types": strategy_types,
        "risk_level": risk_level,
        "priority": priority,
    })
    return {
        "available": not unavailable,
        "run_id": run_id,
        "report_id": report_id,
        "rule_version": RULE_VERSION,
        "matched_rule_ids": matched,
        "rule_hits": [_RULE_BY_ID[item].public() for item in matched],
        "strategy_types": strategy_types,
        "risk_level": risk_level,
        "priority": priority,
        "source_type": output_source,
        "is_stale": is_stale,
        "stale_reason": facts.get("stale_reason") if is_stale else None,
        "mode": "audit_only" if is_stale or source_type == "historical" else "decision_support",
        "status": "draft",
        "indicators": indicators,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
        "content_hash": content_hash,
        "evaluated_at": datetime.now().astimezone().isoformat(),
    }

PROMPT_VERSION = "phase5d-strategy-explain-v1"
PROHIBITED_OUTPUT_PATTERNS = ("将自动执行", "立即下单", "立即交易", "必须买入", "必须卖出", "保证收益", "稳赚", "自动充电", "自动放电", "automatic execution")
STALE_CURRENT_PATTERNS = ("当前可执行", "实时策略", "今日执行", "现在执行")


def _strategy_id(content_hash: str) -> str:
    return f"p5d_{str(content_hash)[:24]}"


def _fact_evidence(rule_result: dict[str, Any], facts: dict[str, Any]) -> list[dict[str, Any]]:
    indicators = dict(rule_result.get("indicators") or {})
    return [
        {"evidence_type": "database_fact", "table": "forecast_runs", "run_id": rule_result["run_id"], "source_type": facts.get("source_type"), "is_stale": bool(rule_result.get("is_stale")), "stale_reason": rule_result.get("stale_reason")},
        {"evidence_type": "database_fact", "table": "forecast_results", "run_id": rule_result["run_id"], "record_count": indicators.get("forecast_record_count"), "maximum_price": indicators.get("maximum_price"), "minimum_price": indicators.get("minimum_price"), "peak_valley_spread": indicators.get("peak_valley_spread"), "maximum_spike_probability": indicators.get("maximum_spike_probability")},
        {"evidence_type": "database_fact", "table": "report_runs", "report_id": rule_result["report_id"], "run_id": facts.get("report_run_id"), "status": facts.get("report_status")},
    ]


def _is_historical_result(rule_result: dict[str, Any]) -> bool:
    return bool(rule_result.get("is_stale") or rule_result.get("source_type") == "historical" or rule_result.get("mode") == "audit_only")


def _explanation_text(rule_result: dict[str, Any]) -> tuple[str, str, list[str], list[str]]:
    indicators = rule_result.get("indicators") or {}
    matched = ", ".join(rule_result.get("matched_rule_ids") or []) or "?"
    if _is_historical_result(rule_result):
        summary = "基于历史预测数据，仅用于审计与流程验证；不得作为当前交易、调度或设备控制依据。"
    elif not rule_result.get("available"):
        summary = "当前事实不可用或不完整，策略仅保留为草案并要求补充数据。"
    else:
        summary = "规则引擎已形成决策支持草案，须经人工审核，系统不会自动执行。"
    rationale = f"确定性规则命中：{matched}。最高价={indicators.get('maximum_price')}，最低价={indicators.get('minimum_price')}，峰谷价差={indicators.get('peak_valley_spread')}。"
    risks = ["预测存在误差与市场变化风险", "缺少合同、设备及实时执行约束时不得形成具体执行指令"]
    limitations = ["仅为辅助决策草案", "所有交易、调度、负荷和设备动作均被禁止自动触发"]
    if _is_historical_result(rule_result):
        risks.insert(0, "预测窗口已过期")
        limitations.insert(0, "仅限 historical_validation / audit_only")
    return summary, rationale, risks, limitations


def build_strategy_explanation(rule_result: dict[str, Any], facts: dict[str, Any], *, citations: list[dict[str, Any]] | None = None, ai_summary: str = "", provider_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    summary, rationale, risks, limitations = _explanation_text(rule_result)
    if ai_summary.strip():
        summary = ai_summary.strip()
    evidence = _fact_evidence(rule_result, facts)
    return {
        "strategy_id": _strategy_id(str(rule_result.get("content_hash") or "")),
        "run_id": rule_result.get("run_id"), "report_id": rule_result.get("report_id"),
        "strategy_types": list(rule_result.get("strategy_types") or []), "risk_level": rule_result.get("risk_level"), "priority": rule_result.get("priority"),
        "title": "历史策略审计草案" if _is_historical_result(rule_result) else "智能运营策略草案",
        "executive_summary": summary, "rationale": rationale, "supporting_facts": evidence,
        "risks": risks, "limitations": limitations,
        "applicable_window": {"start": facts.get("applicable_start_at"), "end": facts.get("applicable_end_at"), "mode": rule_result.get("mode")},
        "review_requirements": ["分析人员提交", "审核人员批准或拒绝", "管理员方可发布"],
        "prohibited_actions": list(rule_result.get("prohibited_actions") or []),
        "citations": list(citations or []), "evidence": evidence,
        "source_type": rule_result.get("source_type"), "is_stale": bool(rule_result.get("is_stale")), "confidence": None if facts.get("confidence") is None else float(facts["confidence"]),
        "rule_version": rule_result.get("rule_version"), "prompt_version": PROMPT_VERSION,
        "model_provider": (provider_meta or {}).get("provider") or "deterministic_guarded_draft", "model_name": (provider_meta or {}).get("model") or "none",
        "content_hash": rule_result.get("content_hash"), "status": "draft",
    }

def validate_strategy_explanation(payload: dict[str, Any], rule_result: dict[str, Any], *, citation_catalog: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    errors: list[str] = []
    if payload.get("run_id") != rule_result.get("run_id"):
        errors.append("run_id_mismatch")
    if payload.get("report_id") != rule_result.get("report_id"):
        errors.append("report_id_mismatch")
    if sorted(payload.get("strategy_types") or []) != sorted(rule_result.get("strategy_types") or []):
        errors.append("strategy_type_mismatch")
    if payload.get("risk_level") != rule_result.get("risk_level"):
        errors.append("risk_level_mismatch")
    if not payload.get("supporting_facts"):
        errors.append("supporting_facts_missing")
    supporting = payload.get("supporting_facts") if isinstance(payload.get("supporting_facts"), list) else []
    fact_by_table = {
        str(item.get("table")): item for item in supporting if isinstance(item, dict) and item.get("table")
    }
    run_fact = fact_by_table.get("forecast_runs") or {}
    result_fact = fact_by_table.get("forecast_results") or {}
    report_fact = fact_by_table.get("report_runs") or {}
    if supporting and run_fact.get("run_id") != rule_result.get("run_id"):
        errors.append("supporting_fact_run_id_mismatch")
    if supporting and report_fact.get("report_id") != rule_result.get("report_id"):
        errors.append("supporting_fact_report_id_mismatch")
    indicators = rule_result.get("indicators") or {}
    expected_metrics = {
        "record_count": indicators.get("forecast_record_count"),
        "maximum_price": indicators.get("maximum_price"),
        "minimum_price": indicators.get("minimum_price"),
        "peak_valley_spread": indicators.get("peak_valley_spread"),
        "maximum_spike_probability": indicators.get("maximum_spike_probability"),
    }
    for field, expected in expected_metrics.items():
        if supporting and result_fact.get(field) != expected:
            errors.append(f"supporting_fact_mismatch:{field}")
    required_prohibitions = set(rule_result.get("prohibited_actions") or [])
    if not required_prohibitions.issubset(set(payload.get("prohibited_actions") or [])):
        errors.append("prohibited_actions_removed")
    catalog = {(str(item.get("document_id") or ""), str(item.get("chunk_id") or "")): item for item in citation_catalog or []}
    for citation in payload.get("citations") or []:
        key = (str(citation.get("document_id") or ""), str(citation.get("chunk_id") or ""))
        source = catalog.get(key)
        if not source:
            errors.append("citation_not_found")
        elif not str(citation.get("quote") or "") or str(citation.get("quote")) not in str(source.get("quote") or ""):
            errors.append("quote_mismatch")
    text_blob = " ".join(str(payload.get(field) or "") for field in ("title", "executive_summary", "rationale"))
    text_blob += " " + " ".join(str(item) for field in ("risks", "limitations") for item in payload.get(field) or [])
    for pattern in PROHIBITED_OUTPUT_PATTERNS:
        if pattern.lower() in text_blob.lower():
            errors.append(f"prohibited_phrase:{pattern}")
    if _is_historical_result(rule_result):
        summary_text = str(payload.get("executive_summary") or "")
        if "历史" not in summary_text or "审计" not in summary_text:
            errors.append("stale_disclaimer_missing")
        for pattern in STALE_CURRENT_PATTERNS:
            if pattern in text_blob:
                errors.append(f"stale_described_as_current:{pattern}")
    if payload.get("source_type") != rule_result.get("source_type"):
        errors.append("source_type_mismatch")
    if payload.get("content_hash") != rule_result.get("content_hash"):
        errors.append("content_hash_mismatch")
    unique_errors = list(dict.fromkeys(errors))
    return {"valid": not unique_errors, "validation_status": "passed" if not unique_errors else "validation_failed", "errors": unique_errors, "status": "draft", "can_submit_review": not unique_errors}


def generate_guarded_strategy_explanation(rule_result: dict[str, Any], facts: dict[str, Any], *, citations: list[dict[str, Any]] | None = None, router: Any = None, requested_provider: str = "auto") -> dict[str, Any]:
    ai_summary = ""
    provider_meta: dict[str, Any] = {}
    provider_error = ""
    if router is not None:
        try:
            prompt_payload = {
                "rule_result": {key: rule_result.get(key) for key in ("run_id", "report_id", "strategy_types", "risk_level", "priority", "indicators", "is_stale", "stale_reason", "mode")},
                "contract": "仅解释以上事实；不得新增策略、修改风险、给出自动执行或收益保证。基于历史数据时必须明确仅用于审计。",
            }
            ai_summary, provider_meta = router.generate_answer(
                [{"role": "system", "content": "你是智能运营决策解释器，只输出一段中文执行摘要。"}, {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False, default=str)}],
                task_type="strategy_advice", requested_provider=requested_provider, temperature=0.1, max_tokens=240,
            )
        except Exception as exc:
            provider_error = exc.__class__.__name__
    payload = build_strategy_explanation(rule_result, facts, citations=citations, ai_summary=ai_summary, provider_meta=provider_meta)
    validation = validate_strategy_explanation(payload, rule_result, citation_catalog=citations)
    if provider_error:
        validation = {"valid": False, "validation_status": "validation_failed", "errors": [f"provider_error:{provider_error}"], "status": "draft", "can_submit_review": False}
    return {**payload, "validation": validation}


def _json_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise StrategyGovernanceError("invalid_json_fact") from exc
        if isinstance(parsed, dict):
            return parsed
    return {}


def load_strategy_facts(run_id: str, report_id: str, *, engine: Engine) -> dict[str, Any]:
    safe_run_id = str(run_id or "").strip()
    safe_report_id = str(report_id or "").strip()
    if not safe_run_id or not safe_report_id:
        raise StrategyGovernanceError("run_id_and_report_id_required")
    with engine.connect() as conn:
        run = conn.execute(
            text("SELECT * FROM forecast_runs WHERE run_id=:run_id"),
            {"run_id": safe_run_id},
        ).mappings().first()
        report = conn.execute(
            text("SELECT * FROM report_runs WHERE report_id=:report_id"),
            {"report_id": safe_report_id},
        ).mappings().first()
        records = conn.execute(
            text(
                """SELECT COALESCE(forecast_time,forecast_datetime) AS forecast_time,
                predicted_price,corrected_predicted_price,spike_risk_prob,risk_level,
                model_version,feature_version,source_type
                FROM forecast_results WHERE run_id=:run_id
                ORDER BY COALESCE(forecast_time,forecast_datetime),id"""
            ),
            {"run_id": safe_run_id},
        ).mappings().all()
    if not run:
        raise StrategyGovernanceError("forecast_run_not_found")
    if not report:
        raise StrategyGovernanceError("report_run_not_found")
    run_data, report_data = dict(run), dict(report)
    if str(report_data.get("run_id") or "") != safe_run_id:
        raise StrategyGovernanceError("run_report_mismatch")
    if str(run_data.get("status") or "").lower() != "success":
        raise StrategyGovernanceError("forecast_run_not_success")
    if str(report_data.get("status") or "").lower() not in {"ready", "approved", "published"}:
        raise StrategyGovernanceError("report_not_ready")
    declared_count = int(run_data.get("record_count") or run_data.get("row_count") or 0)
    if declared_count != 24 or len(records) != 24:
        raise StrategyGovernanceError("forecast_record_count_invalid")

    metadata = _json_mapping(report_data.get("metadata_json"))
    content = _json_mapping(report_data.get("content_json"))
    evidence = content.get("evidence") if isinstance(content.get("evidence"), list) else []
    if len(evidence) < 2:
        raise StrategyGovernanceError("report_evidence_insufficient")
    end_at = run_data.get("forecast_end_at") or run_data.get("forecast_end")
    end_utc: datetime | None = None
    if isinstance(end_at, datetime):
        end_utc = end_at if end_at.tzinfo else end_at.replace(tzinfo=timezone.utc)
    elif end_at:
        end_utc = datetime.fromisoformat(str(end_at).replace("Z", "+00:00"))
        if end_utc.tzinfo is None:
            end_utc = end_utc.replace(tzinfo=timezone.utc)
    is_stale = bool(metadata.get("is_stale")) or bool(end_utc and end_utc.astimezone(timezone.utc) < datetime.now(timezone.utc))
    original_source_type = str(run_data.get("source_type") or "real").lower()
    return {
        "run_id": safe_run_id,
        "report_id": safe_report_id,
        "report_run_id": str(report_data.get("run_id") or ""),
        "report_status": str(report_data.get("status") or ""),
        "report_evidence_count": len(evidence),
        "forecast_record_count": len(records),
        "forecast_records": [dict(item) for item in records],
        "source_type": "historical" if is_stale else original_source_type,
        "original_source_type": original_source_type,
        "is_stale": is_stale,
        "stale_reason": metadata.get("stale_reason") or ("forecast_window_expired" if is_stale else None),
        "applicable_start_at": run_data.get("forecast_start_at") or run_data.get("forecast_start"),
        "applicable_end_at": end_at,
        "model_version": run_data.get("model_version"),
        "feature_version": run_data.get("feature_version"),
        "domain": run_data.get("domain") or "price",
        "target_name": run_data.get("target_name") or "da_price",
        "result_hash": run_data.get("result_hash"),
        "report_hash": metadata.get("report_hash"),
        "report_evidence": evidence,
    }


def generate_strategy_draft(
    run_id: str,
    report_id: str,
    *,
    created_by: str,
    engine: Engine,
    citations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create one idempotent governed draft from an explicit forecast/report pair."""
    from backend.app.repositories.strategy_repository import create_strategy

    actor = str(created_by or "").strip()
    if not actor:
        raise StrategyGovernanceError("created_by_required")
    facts = load_strategy_facts(run_id, report_id, engine=engine)
    rule_result = evaluate_strategy_rules(facts)
    explanation = generate_guarded_strategy_explanation(rule_result, facts, citations=citations)
    validation = dict(explanation.get("validation") or {})
    if not validation.get("valid"):
        raise StrategyGovernanceError("strategy_explanation_validation_failed")
    strategy_types = list(rule_result.get("strategy_types") or ["no_action"])
    evidence_json = {
        "rule_hits": rule_result.get("rule_hits") or [],
        "explanation": explanation,
        "validation": validation,
        "facts": {
            "run_id": facts["run_id"],
            "report_id": facts["report_id"],
            "model_version": facts.get("model_version"),
            "feature_version": facts.get("feature_version"),
            "result_hash": facts.get("result_hash"),
            "report_hash": facts.get("report_hash"),
            "forecast_record_count": facts.get("forecast_record_count"),
            "report_evidence_count": facts.get("report_evidence_count"),
            "original_source_type": facts.get("original_source_type"),
        },
        "citations": list(citations or []),
    }
    payload = {
        "strategy_id": explanation["strategy_id"],
        "run_id": facts["run_id"],
        "report_id": facts["report_id"],
        "model_version": facts.get("model_version"),
        "feature_version": facts.get("feature_version"),
        "domain": facts.get("domain"),
        "target_name": facts.get("target_name"),
        "strategy_type": strategy_types[0],
        "title": explanation["title"],
        "summary": explanation["executive_summary"],
        "priority": rule_result.get("priority"),
        "confidence": None,
        "risk_level": rule_result.get("risk_level"),
        "source_type": rule_result.get("source_type"),
        "is_stale": rule_result.get("is_stale"),
        "stale_reason": rule_result.get("stale_reason"),
        "applicable_start_at": facts.get("applicable_start_at"),
        "applicable_end_at": facts.get("applicable_end_at"),
        "generated_at": datetime.now(timezone.utc),
        "created_by": actor,
        "rule_version": RULE_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model_provider": explanation.get("model_provider"),
        "model_name": explanation.get("model_name"),
        "constraints_json": {"mode": rule_result.get("mode"), "human_review_required": True},
        "expected_effect_json": {"kind": "decision_support_only", "realized_return": None},
        "prohibited_actions_json": list(PROHIBITED_ACTIONS),
        "review_required": True,
        "evidence_json": evidence_json,
        "content_hash": rule_result["content_hash"],
        "mode": rule_result.get("mode"),
    }
    strategy, created = create_strategy(payload, engine=engine)
    return {"strategy": strategy, "created": created, "rule_result": rule_result}
