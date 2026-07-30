from __future__ import annotations

import pytest

from backend.app.services.strategy_governance_service import (
    ALLOWED_TRANSITIONS,
    StrategyGovernanceError,
    validate_reviewer,
    validate_transition,
)


@pytest.mark.parametrize(
    ("previous", "action", "expected"),
    [
        ("draft", "submit", "pending_review"),
        ("pending_review", "approve", "approved"),
        ("pending_review", "reject", "rejected"),
        ("pending_review", "return", "draft"),
        ("approved", "publish", "published"),
        ("approved", "supersede", "superseded"),
        ("published", "supersede", "superseded"),
        ("published", "expire", "expired"),
    ],
)
def test_d1_allowed_state_transitions(previous: str, action: str, expected: str) -> None:
    assert validate_transition(previous, action).new_status == expected


@pytest.mark.parametrize(
    ("previous", "action"),
    [
        ("draft", "publish"),
        ("draft", "approve"),
        ("pending_review", "publish"),
        ("rejected", "publish"),
        ("expired", "publish"),
        ("published", "approve"),
    ],
)
def test_d1_illegal_state_transitions_fail_closed(previous: str, action: str) -> None:
    with pytest.raises(StrategyGovernanceError, match="illegal_strategy_transition"):
        validate_transition(previous, action)


def test_d1_terminal_states_have_no_outgoing_transition() -> None:
    for status in ("rejected", "superseded", "expired", "cancelled"):
        assert ALLOWED_TRANSITIONS[status] == set()


def test_d1_creator_cannot_approve_own_strategy() -> None:
    with pytest.raises(StrategyGovernanceError, match="creator_cannot_approve"):
        validate_reviewer(creator="analyst_a", reviewer="analyst_a", reviewer_role="reviewer", action="approve")


def test_d1_reviewer_and_admin_separation() -> None:
    validate_reviewer(creator="analyst_a", reviewer="reviewer_b", reviewer_role="reviewer", action="approve")
    validate_reviewer(creator="analyst_a", reviewer="admin_c", reviewer_role="admin", action="publish")
    with pytest.raises(StrategyGovernanceError, match="admin_role_required"):
        validate_reviewer(creator="analyst_a", reviewer="reviewer_b", reviewer_role="reviewer", action="publish")

def _facts(*, stale: bool = False, source_type: str = "real", count: int = 24, evidence_count: int = 2):
    records = []
    for hour in range(count):
        records.append({
            "forecast_time": f"2026-07-22T{hour % 24:02d}:00:00+08:00",
            "predicted_price": -10.0 if hour == 0 else (450.0 if hour == 18 else 120.0),
            "corrected_predicted_price": None,
            "spike_risk_prob": 0.9 if hour == 18 else 0.1,
        })
    return {
        "run_id": "run_test", "report_id": "report_test", "report_run_id": "run_test",
        "source_type": source_type, "is_stale": stale,
        "stale_reason": "forecast_window_expired" if stale else None,
        "forecast_record_count": count, "forecast_records": records,
        "report_status": "ready", "report_evidence_count": evidence_count,
    }


def test_d2_rule_inventory_covers_ten_required_rules() -> None:
    from backend.app.services.strategy_governance_service import rule_inventory
    inventory = rule_inventory()
    assert [item["rule_id"] for item in inventory] == [f"P5D-R{index:03d}" for index in range(1, 11)]
    assert all(item["condition"] and item["required_fields"] and item["prohibited_actions"] for item in inventory)


def test_d2_rule_output_is_reproducible_for_same_facts() -> None:
    from backend.app.services.strategy_governance_service import evaluate_strategy_rules
    facts = _facts()
    first = evaluate_strategy_rules(facts)
    second = evaluate_strategy_rules({**facts, "forecast_records": list(reversed(facts["forecast_records"]))})
    for field in ("matched_rule_ids", "strategy_types", "risk_level", "priority", "content_hash"):
        assert first[field] == second[field]


def test_d2_stale_conflict_suppresses_current_actionable_strategy() -> None:
    from backend.app.services.strategy_governance_service import evaluate_strategy_rules
    result = evaluate_strategy_rules(_facts(stale=True))
    assert {"P5D-R001", "P5D-R003", "P5D-R004", "P5D-R005", "P5D-R007", "P5D-R010"}.issubset(result["matched_rule_ids"])
    assert result["strategy_types"] == ["manual_review_required", "no_action"]
    assert result["priority"] == 20
    assert result["mode"] == "audit_only"


def test_d2_unavailable_and_23_rows_fail_closed() -> None:
    from backend.app.services.strategy_governance_service import evaluate_strategy_rules
    result = evaluate_strategy_rules(_facts(count=23))
    assert result["available"] is False
    assert "P5D-R008" in result["matched_rule_ids"]
    assert result["strategy_types"] == ["data_refresh_required", "no_action"]
    assert result["source_type"] == "unavailable"


def test_d2_report_evidence_missing_requires_manual_review() -> None:
    from backend.app.services.strategy_governance_service import evaluate_strategy_rules
    result = evaluate_strategy_rules(_facts(evidence_count=0))
    assert "P5D-R009" in result["matched_rule_ids"]
    assert result["strategy_types"] == ["manual_review_required", "no_action"]


def test_d2_low_price_high_volatility_conflict_requires_manual_review() -> None:
    from backend.app.services.strategy_governance_service import evaluate_strategy_rules
    facts = _facts()
    for index, record in enumerate(facts["forecast_records"]):
        record["predicted_price"] = -20.0 if index % 2 == 0 else 450.0
    result = evaluate_strategy_rules(facts)
    assert {"P5D-R004", "P5D-R005", "P5D-R006"}.issubset(result["matched_rule_ids"])
    assert "manual_review_required" in result["strategy_types"]


def test_d2_missing_price_is_not_silently_zero_filled() -> None:
    from backend.app.services.strategy_governance_service import evaluate_strategy_rules
    facts = _facts()
    facts["forecast_records"][3]["predicted_price"] = None
    with pytest.raises(StrategyGovernanceError, match="missing_numeric_fact"):
        evaluate_strategy_rules(facts)


def test_d2_run_report_mismatch_becomes_unavailable() -> None:
    from backend.app.services.strategy_governance_service import evaluate_strategy_rules
    result = evaluate_strategy_rules({**_facts(), "report_run_id": "another_run"})
    assert result["source_type"] == "unavailable"
    assert result["strategy_types"] == ["data_refresh_required", "no_action"]

def _d3_payload():
    from backend.app.services.strategy_governance_service import build_strategy_explanation, evaluate_strategy_rules
    facts = _facts(stale=True)
    facts.update({"applicable_start_at": "2026-06-18T12:00:00+08:00", "applicable_end_at": "2026-06-19T11:00:00+08:00", "confidence": 0.82})
    rules = evaluate_strategy_rules(facts)
    citation = {"document_id": "doc-1", "chunk_id": "chunk-1", "title": "策略约束", "quote": "策略建议必须经过人工审核，不能自动执行。"}
    payload = build_strategy_explanation(rules, facts, citations=[citation])
    return facts, rules, citation, payload


def test_d3_guarded_explanation_contains_required_contract() -> None:
    from backend.app.services.strategy_governance_service import validate_strategy_explanation
    _, rules, citation, payload = _d3_payload()
    validation = validate_strategy_explanation(payload, rules, citation_catalog=[citation])
    assert validation["valid"] is True
    assert payload["status"] == "draft"
    assert payload["run_id"] == rules["run_id"]
    assert payload["report_id"] == rules["report_id"]
    assert payload["supporting_facts"] and payload["prohibited_actions"]


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [("run_id", "fabricated", "run_id_mismatch"), ("report_id", "fabricated", "report_id_mismatch"), ("risk_level", "high", "risk_level_mismatch")],
)
def test_d3_identity_and_risk_tampering_fail(field: str, value: str, error: str) -> None:
    from backend.app.services.strategy_governance_service import validate_strategy_explanation
    _, rules, citation, payload = _d3_payload()
    validation = validate_strategy_explanation({**payload, field: value}, rules, citation_catalog=[citation])
    assert validation["valid"] is False
    assert error in validation["errors"]


def test_d3_fabricated_citation_and_quote_fail() -> None:
    from backend.app.services.strategy_governance_service import validate_strategy_explanation
    _, rules, citation, payload = _d3_payload()
    bad_id = {**citation, "chunk_id": "fabricated"}
    assert "citation_not_found" in validate_strategy_explanation({**payload, "citations": [bad_id]}, rules, citation_catalog=[citation])["errors"]
    bad_quote = {**citation, "quote": "不存在的引文"}
    assert "quote_mismatch" in validate_strategy_explanation({**payload, "citations": [bad_quote]}, rules, citation_catalog=[citation])["errors"]


def test_d3_auto_execution_and_guaranteed_return_fail() -> None:
    from backend.app.services.strategy_governance_service import validate_strategy_explanation
    _, rules, citation, payload = _d3_payload()
    tampered = {**payload, "executive_summary": "系统将自动执行并保证收益。"}
    errors = validate_strategy_explanation(tampered, rules, citation_catalog=[citation])["errors"]
    assert any(item.startswith("prohibited_phrase") for item in errors)


def test_d3_stale_must_not_be_described_as_current() -> None:
    from backend.app.services.strategy_governance_service import validate_strategy_explanation
    _, rules, citation, payload = _d3_payload()
    tampered = {**payload, "executive_summary": "这是当前可执行方案。"}
    errors = validate_strategy_explanation(tampered, rules, citation_catalog=[citation])["errors"]
    assert "stale_disclaimer_missing" in errors
    assert any(item.startswith("stale_described_as_current") for item in errors)


class _ValidRouter:
    def generate_answer(self, *_args, **_kwargs):
        return "基于历史预测数据，仅用于审计与流程验证，不触发任何自动操作。", {"provider": "test", "model": "guarded"}


class _TimeoutRouter:
    def generate_answer(self, *_args, **_kwargs):
        raise TimeoutError("provider timeout")


def test_d3_provider_output_is_wrapped_and_validated() -> None:
    from backend.app.services.strategy_governance_service import evaluate_strategy_rules, generate_guarded_strategy_explanation
    facts = _facts(stale=True)
    rules = evaluate_strategy_rules(facts)
    result = generate_guarded_strategy_explanation(rules, facts, router=_ValidRouter())
    assert result["validation"]["valid"] is True
    assert result["model_provider"] == "test"


def test_d3_provider_timeout_keeps_draft_and_blocks_submission() -> None:
    from backend.app.services.strategy_governance_service import evaluate_strategy_rules, generate_guarded_strategy_explanation
    facts = _facts(stale=True)
    rules = evaluate_strategy_rules(facts)
    result = generate_guarded_strategy_explanation(rules, facts, router=_TimeoutRouter())
    assert result["status"] == "draft"
    assert result["validation"]["validation_status"] == "validation_failed"
    assert result["validation"]["can_submit_review"] is False


def _d4_user(name: str, role: str):
    from backend.app.core.security import CurrentUser, ROLE_PERMISSIONS
    return CurrentUser(name, name, role, sorted(ROLE_PERMISSIONS[role]), "phase5d_test")


@pytest.fixture
def d4_db():
    import os
    import uuid
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import create_engine, text

    url = os.getenv("PHASE5_D_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("PHASE5_D_TEST_DATABASE_URL is not configured")
    engine = create_engine(url, future=True, pool_pre_ping=True)
    run_ids: list[str] = []

    def create_facts(*, stale: bool = False) -> tuple[str, str]:
        suffix = uuid.uuid4().hex[:16]
        run_id = f"p5d_run_{suffix}"
        report_id = f"p5d_report_{suffix}"
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=3) if stale else now + timedelta(days=1)
        end = start + timedelta(hours=23)
        metadata = {"is_stale": stale, "stale_reason": "forecast_window_expired" if stale else None, "report_hash": f"report_hash_{suffix}"}
        content = {"evidence": [{"table": "forecast_runs", "run_id": run_id}, {"table": "forecast_results", "record_count": 24}]}
        with engine.begin() as conn:
            conn.execute(text("""INSERT INTO forecast_runs (
                run_id,status,row_count,record_count,domain,target_name,forecast_start_at,forecast_end_at,
                model_version,feature_version,result_hash,source_type,created_at,updated_at
                ) VALUES (:run_id,'success',24,24,'price','da_price',:start,:end,:model,:feature,:hash,'real',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"""),
                {"run_id": run_id, "start": start, "end": end, "model": f"model_{suffix}", "feature": f"features_{suffix}", "hash": f"result_hash_{suffix}"})
            for hour in range(24):
                conn.execute(text("""INSERT INTO forecast_results (
                    run_id,forecast_time,predicted_price,corrected_predicted_price,spike_risk_prob,
                    model_version,feature_version,source_type,created_at
                    ) VALUES (:run_id,:time,:price,NULL,:spike,:model,:feature,'real',CURRENT_TIMESTAMP)"""),
                    {"run_id": run_id, "time": start + timedelta(hours=hour), "price": -5.0 if hour == 1 else (440.0 if hour == 18 else 120.0), "spike": 0.92 if hour == 18 else 0.1, "model": f"model_{suffix}", "feature": f"features_{suffix}"})
            conn.execute(text("""INSERT INTO report_runs (
                report_id,run_id,title,status,report_type,metadata_json,content_json,created_at,updated_at
                ) VALUES (:report_id,:run_id,'PHASE5-D test report','ready','operation_decision',CAST(:metadata AS jsonb),CAST(:content AS jsonb),CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"""),
                {"report_id": report_id, "run_id": run_id, "metadata": __import__('json').dumps(metadata), "content": __import__('json').dumps(content)})
        run_ids.append(run_id)
        return run_id, report_id

    yield engine, create_facts

    with engine.begin() as conn:
        for run_id in run_ids:
            conn.execute(text("DELETE FROM audit_logs WHERE resource_type='strategy' AND resource_id IN (SELECT strategy_id FROM strategy_advice WHERE run_id=:run_id)"), {"run_id": run_id})
            conn.execute(text("DELETE FROM strategy_reviews WHERE strategy_id IN (SELECT strategy_id FROM strategy_advice WHERE run_id=:run_id)"), {"run_id": run_id})
            conn.execute(text("DELETE FROM strategy_advice WHERE run_id=:run_id"), {"run_id": run_id})
            conn.execute(text("DELETE FROM report_runs WHERE run_id=:run_id"), {"run_id": run_id})
            conn.execute(text("DELETE FROM forecast_results WHERE run_id=:run_id"), {"run_id": run_id})
            conn.execute(text("DELETE FROM forecast_runs WHERE run_id=:run_id"), {"run_id": run_id})
    engine.dispose()


def test_d4_role_permissions_are_separated() -> None:
    from backend.app.core.security import ROLE_PERMISSIONS
    assert {"strategy:read", "strategy:generate", "strategy:submit"}.issubset(ROLE_PERMISSIONS["analyst"])
    assert "strategy:review" not in ROLE_PERMISSIONS["analyst"]
    assert "strategy:review" in ROLE_PERMISSIONS["reviewer"]
    assert "strategy:generate" not in ROLE_PERMISSIONS["reviewer"]
    assert ROLE_PERMISSIONS["viewer"].intersection({"strategy:generate", "strategy:submit", "strategy:review"}) == set()
    assert "*" in ROLE_PERMISSIONS["admin"]


def test_d4_generate_is_idempotent_and_binds_facts(d4_db) -> None:
    from sqlalchemy import text
    from backend.app.services.strategy_governance_service import generate_strategy_draft
    engine, create_facts = d4_db
    run_id, report_id = create_facts()
    first = generate_strategy_draft(run_id, report_id, created_by="analyst_a", engine=engine)
    second = generate_strategy_draft(run_id, report_id, created_by="analyst_a", engine=engine)
    assert first["created"] is True and second["created"] is False
    assert first["strategy"]["strategy_id"] == second["strategy"]["strategy_id"]
    assert first["strategy"]["status"] == "draft"
    assert first["strategy"]["model_version"] and first["strategy"]["feature_version"]
    assert first["strategy"]["validation"]["valid"] is True
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(1) FROM strategy_advice WHERE run_id=:run_id"), {"run_id": run_id}).scalar_one() == 1


def test_d4_human_review_and_publish_workflow_is_audited(d4_db) -> None:
    from sqlalchemy import text
    from backend.app.repositories.strategy_repository import transition_strategy
    from backend.app.services.strategy_governance_service import generate_strategy_draft
    engine, create_facts = d4_db
    run_id, report_id = create_facts()
    strategy = generate_strategy_draft(run_id, report_id, created_by="analyst_a", engine=engine)["strategy"]
    strategy_id = strategy["strategy_id"]
    analyst = _d4_user("analyst_a", "analyst")
    reviewer = _d4_user("reviewer_b", "reviewer")
    admin = _d4_user("admin_c", "admin")
    submitted = transition_strategy(strategy_id, "submit", request_id=f"submit_{strategy_id}", comment="submit", user=analyst, engine=engine)
    repeated = transition_strategy(strategy_id, "submit", request_id=f"submit_{strategy_id}", comment="submit", user=analyst, engine=engine)
    assert submitted["strategy"]["status"] == "pending_review" and repeated["idempotent"] is True
    assert transition_strategy(strategy_id, "approve", request_id=f"approve_{strategy_id}", comment="evidence checked", user=reviewer, engine=engine)["strategy"]["status"] == "approved"
    assert transition_strategy(strategy_id, "publish", request_id=f"publish_{strategy_id}", comment="admin release", user=admin, engine=engine)["strategy"]["status"] == "published"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(1) FROM strategy_reviews WHERE strategy_id=:id"), {"id": strategy_id}).scalar_one() == 3
        assert conn.execute(text("SELECT count(1) FROM audit_logs WHERE resource_type='strategy' AND resource_id=:id"), {"id": strategy_id}).scalar_one() == 4


def test_d4_creator_cannot_self_approve_persisted_strategy(d4_db) -> None:
    from backend.app.repositories.strategy_repository import transition_strategy
    from backend.app.services.strategy_governance_service import generate_strategy_draft
    engine, create_facts = d4_db
    run_id, report_id = create_facts()
    strategy_id = generate_strategy_draft(run_id, report_id, created_by="reviewer_same", engine=engine)["strategy"]["strategy_id"]
    transition_strategy(strategy_id, "submit", request_id=f"submit_{strategy_id}", comment="submit", user=_d4_user("analyst_a", "analyst"), engine=engine)
    with pytest.raises(StrategyGovernanceError, match="creator_cannot_approve"):
        transition_strategy(strategy_id, "approve", request_id=f"approve_{strategy_id}", comment="self", user=_d4_user("reviewer_same", "reviewer"), engine=engine)


def test_d4_historical_strategy_can_be_reviewed_but_not_published(d4_db) -> None:
    from backend.app.repositories.strategy_repository import transition_strategy
    from backend.app.services.strategy_governance_service import generate_strategy_draft
    engine, create_facts = d4_db
    run_id, report_id = create_facts(stale=True)
    strategy = generate_strategy_draft(run_id, report_id, created_by="analyst_a", engine=engine)["strategy"]
    assert strategy["source_type"] == "historical" and strategy["is_stale"] is True
    strategy_id = strategy["strategy_id"]
    transition_strategy(strategy_id, "submit", request_id=f"submit_{strategy_id}", comment="historical audit", user=_d4_user("analyst_a", "analyst"), engine=engine)
    transition_strategy(strategy_id, "approve", request_id=f"approve_{strategy_id}", comment="audit accepted", user=_d4_user("reviewer_b", "reviewer"), engine=engine)
    with pytest.raises(StrategyGovernanceError, match="stale_strategy_cannot_publish"):
        transition_strategy(strategy_id, "publish", request_id=f"publish_{strategy_id}", comment="must fail", user=_d4_user("admin_c", "admin"), engine=engine)


from pathlib import Path
import copy
import json


_D5_SCENARIOS = json.loads((Path(__file__).parent / "evaluation" / "phase5_d_twenty_scenarios.json").read_text(encoding="utf-8"))


def _d5_facts(scenario: dict) -> dict:
    profile = scenario["facts"]["price_profile"]
    count = int(scenario["facts"]["record_count"])
    prices = [120.0] * count
    if profile in {"high_price", "high_spike"}:
        prices[-1] = 350.0
    elif profile == "spike_only":
        pass
    elif profile in {"extreme_multi", "negative_volatile"}:
        prices = [-20.0 if index % 2 == 0 else 450.0 for index in range(count)]
    elif profile in {"low_price", "low_spike"}:
        prices[0] = 30.0
    elif profile == "negative_price":
        prices[0] = -5.0
    elif profile == "spread_only":
        prices[0], prices[-1] = 50.0, 260.0
    elif profile == "spread_high":
        prices[0], prices[-1] = 50.0, 350.0
    elif profile == "volatility":
        prices = [50.0 if index % 2 == 0 else 270.0 for index in range(count)]
    if profile == "missing_price":
        prices[3] = None
    records = [{
        "forecast_time": f"2026-07-22T{index % 24:02d}:00:00+08:00",
        "predicted_price": price,
        "corrected_predicted_price": None,
        "spike_risk_prob": scenario["facts"]["spike_max"] if index == min(18, count - 1) else 0.1,
    } for index, price in enumerate(prices)]
    return {
        "run_id": scenario["input_run_id"],
        "report_id": scenario["input_report_id"],
        "report_run_id": scenario["input_run_id"],
        "source_type": scenario["facts"]["source_type"],
        "is_stale": bool(scenario["facts"]["is_stale"]),
        "stale_reason": "forecast_window_expired" if scenario["facts"]["is_stale"] else None,
        "forecast_record_count": count,
        "forecast_records": records,
        "report_status": scenario["facts"]["report_status"],
        "report_evidence_count": int(scenario["facts"]["report_evidence_count"]),
    }


def test_d5_twenty_scenario_asset_contract_and_fixed_categories() -> None:
    assert len(_D5_SCENARIOS) == 20
    counts: dict[str, int] = {}
    required = {"scenario_id", "input_run_id", "input_report_id", "facts", "expected_rules", "expected_strategy_types", "expected_risk_level", "expected_priority", "expected_source_type", "expected_status", "required_evidence", "forbidden_actions", "expected_review_behavior", "critical", "pass_criteria"}
    for scenario in _D5_SCENARIOS:
        assert required.issubset(scenario)
        counts[scenario["category"]] = counts.get(scenario["category"], 0) + 1
        assert len(scenario["forbidden_actions"]) == 8
    assert list(counts.values()) == [4, 4, 4, 3, 3, 2]


@pytest.mark.parametrize("scenario", _D5_SCENARIOS, ids=lambda item: item["scenario_id"])
def test_d5_twenty_strategy_scenarios(scenario: dict) -> None:
    from backend.app.services.strategy_governance_service import (
        build_strategy_explanation,
        evaluate_strategy_rules,
        validate_strategy_explanation,
    )
    facts = _d5_facts(scenario)
    modes = set(scenario["facts"]["test_modes"])
    if "missing_numeric_fail_closed" in modes:
        with pytest.raises(StrategyGovernanceError, match="missing_numeric_fact"):
            evaluate_strategy_rules(facts)
        return
    result = evaluate_strategy_rules(facts)
    assert result["matched_rule_ids"] == scenario["expected_rules"]
    assert result["strategy_types"] == scenario["expected_strategy_types"]
    assert result["risk_level"] == scenario["expected_risk_level"]
    assert result["priority"] == scenario["expected_priority"]
    assert result["source_type"] == scenario["expected_source_type"]
    assert result["status"] == scenario["expected_status"]
    assert set(scenario["forbidden_actions"]).issubset(result["prohibited_actions"])

    citation = {"document_id": "doc-real", "chunk_id": "chunk-real", "title": "策略治理", "quote": "策略必须经过人工审核，不得自动执行。"}
    payload = build_strategy_explanation(result, facts, citations=[citation])
    baseline = validate_strategy_explanation(payload, result, citation_catalog=[citation])
    assert baseline["valid"] is True

    if "generation_idempotency" in modes:
        assert evaluate_strategy_rules(copy.deepcopy(facts))["content_hash"] == result["content_hash"]
    if "unauthorized_approval" in modes:
        with pytest.raises(StrategyGovernanceError, match="reviewer_role_required"):
            validate_reviewer(creator="creator", reviewer="analyst", reviewer_role="analyst", action="approve")
    if "version_upgrade" in modes:
        assert validate_transition("approved", "supersede").new_status == "superseded"
    if "supersede" in modes:
        assert validate_transition("published", "supersede").new_status == "superseded"
    if "rejected_publish_blocked" in modes:
        with pytest.raises(StrategyGovernanceError, match="illegal_strategy_transition"):
            validate_transition("rejected", "publish")
    if "expired_publish_blocked" in modes:
        with pytest.raises(StrategyGovernanceError, match="illegal_strategy_transition"):
            validate_transition("expired", "publish")
    if "ai_fabricated_metric" in modes:
        tampered = copy.deepcopy(payload)
        fact = next(item for item in tampered["supporting_facts"] if item["table"] == "forecast_results")
        fact["maximum_price"] = 999999.0
        assert any(error.startswith("supporting_fact_mismatch") for error in validate_strategy_explanation(tampered, result, citation_catalog=[citation])["errors"])
    if "ai_risk_tamper" in modes:
        tampered = {**payload, "risk_level": "high" if result["risk_level"] != "high" else "low"}
        assert "risk_level_mismatch" in validate_strategy_explanation(tampered, result, citation_catalog=[citation])["errors"]
    if "ai_auto_execution" in modes:
        tampered = {**payload, "executive_summary": "系统将自动执行并保证收益。"}
        assert any(error.startswith("prohibited_phrase") for error in validate_strategy_explanation(tampered, result, citation_catalog=[citation])["errors"])
    if "citation_error" in modes:
        fake = {**citation, "chunk_id": "fabricated"}
        assert "citation_not_found" in validate_strategy_explanation({**payload, "citations": [fake]}, result, citation_catalog=[citation])["errors"]
    if "run_id_error" in modes:
        assert "run_id_mismatch" in validate_strategy_explanation({**payload, "run_id": "wrong_run"}, result, citation_catalog=[citation])["errors"]
    if "historical" in modes or "stale_publish_blocked" in modes:
        assert result["mode"] == "audit_only"
        assert "历史" in payload["executive_summary"] and "审计" in payload["executive_summary"]


def test_d5_fact_loading_failures_leave_no_strategy(d4_db) -> None:
    from sqlalchemy import text
    from backend.app.services.strategy_governance_service import generate_strategy_draft, load_strategy_facts
    engine, create_facts = d4_db
    run_a, report_a = create_facts()
    run_b, report_b = create_facts()
    with pytest.raises(StrategyGovernanceError, match="forecast_run_not_found"):
        load_strategy_facts("missing_run", report_a, engine=engine)
    with pytest.raises(StrategyGovernanceError, match="report_run_not_found"):
        load_strategy_facts(run_a, "missing_report", engine=engine)
    with pytest.raises(StrategyGovernanceError, match="run_report_mismatch"):
        load_strategy_facts(run_a, report_b, engine=engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE report_runs SET status='failed' WHERE report_id=:id"), {"id": report_a})
    with pytest.raises(StrategyGovernanceError, match="report_not_ready"):
        generate_strategy_draft(run_a, report_a, created_by="analyst", engine=engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE report_runs SET status='ready',content_json=CAST('{\"evidence\":[]}' AS jsonb) WHERE report_id=:id"), {"id": report_a})
    with pytest.raises(StrategyGovernanceError, match="report_evidence_insufficient"):
        generate_strategy_draft(run_a, report_a, created_by="analyst", engine=engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(1) FROM strategy_advice WHERE run_id IN (:a,:b)"), {"a": run_a, "b": run_b}).scalar_one() == 0


def test_d5_nth_write_failure_rolls_back_review_transaction(d4_db) -> None:
    from sqlalchemy import text
    from backend.app.repositories.strategy_repository import transition_strategy
    from backend.app.services.strategy_governance_service import generate_strategy_draft
    engine, create_facts = d4_db
    run_id, report_id = create_facts()
    strategy_id = generate_strategy_draft(run_id, report_id, created_by="analyst_a", engine=engine)["strategy"]["strategy_id"]
    transition_strategy(strategy_id, "submit", request_id=f"submit_{strategy_id}", comment="submit", user=_d4_user("analyst_a", "analyst"), engine=engine)
    with pytest.raises(Exception):
        transition_strategy(strategy_id, "approve", request_id="x" * 200, comment="force request_id column failure", user=_d4_user("reviewer_b", "reviewer"), engine=engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT status FROM strategy_advice WHERE strategy_id=:id"), {"id": strategy_id}).scalar_one() == "pending_review"
        assert conn.execute(text("SELECT count(1) FROM strategy_reviews WHERE strategy_id=:id"), {"id": strategy_id}).scalar_one() == 1
        assert conn.execute(text("SELECT count(1) FROM audit_logs WHERE resource_id=:id AND action='strategy.approve'"), {"id": strategy_id}).scalar_one() == 0


def test_d5_concurrent_approval_commits_exactly_once(d4_db) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import text
    from backend.app.repositories.strategy_repository import transition_strategy
    from backend.app.services.strategy_governance_service import generate_strategy_draft
    engine, create_facts = d4_db
    run_id, report_id = create_facts()
    strategy_id = generate_strategy_draft(run_id, report_id, created_by="analyst_a", engine=engine)["strategy"]["strategy_id"]
    transition_strategy(strategy_id, "submit", request_id=f"submit_{strategy_id}", comment="submit", user=_d4_user("analyst_a", "analyst"), engine=engine)

    def approve(index: int) -> str:
        try:
            transition_strategy(strategy_id, "approve", request_id=f"approve_{index}_{strategy_id}", comment="concurrent", user=_d4_user(f"reviewer_{index}", "reviewer"), engine=engine)
            return "approved"
        except StrategyGovernanceError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(approve, (1, 2)))
    assert results.count("approved") == 1
    assert sum(item.startswith("illegal_strategy_transition") for item in results) == 1
    with engine.connect() as conn:
        assert conn.execute(text("SELECT status FROM strategy_advice WHERE strategy_id=:id"), {"id": strategy_id}).scalar_one() == "approved"
        assert conn.execute(text("SELECT count(1) FROM strategy_reviews WHERE strategy_id=:id AND action='approve'"), {"id": strategy_id}).scalar_one() == 1


def test_d5_source_type_conflict_and_illegal_jump_fail_closed() -> None:
    from backend.app.services.strategy_governance_service import build_strategy_explanation, evaluate_strategy_rules, validate_strategy_explanation
    facts = _facts()
    result = evaluate_strategy_rules(facts)
    payload = build_strategy_explanation(result, facts)
    assert "source_type_mismatch" in validate_strategy_explanation({**payload, "source_type": "historical"}, result)["errors"]
    with pytest.raises(StrategyGovernanceError, match="illegal_strategy_transition"):
        validate_transition("draft", "publish")
