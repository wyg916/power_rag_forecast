from __future__ import annotations

from scripts.day3a_ai_quality_audit import build_artifacts


def _golden(qid: str = "Q1") -> dict:
    return {
        "question_id": qid,
        "critical": True,
        "expected_domain": "system_knowledge",
        "expected_answer_points": ["historical"],
        "required_facts": ["historical"],
        "claim_expectations": {
            "required_claims": [{"claim_id": f"{qid}-C1", "text": "historical"}],
        },
        "acl_expectation": {"authorized_context": {"tenant_id": "default"}},
    }


def test_audit_classifies_same_answer_legacy_pass_strict_fail():
    raw = {
        "summary": {"passed": 1},
        "results": [{
            "question_id": "Q1",
            "passed": True,
            "answer": "historical data",
            "citations": [],
            "failed_checks": [],
            "required_facts_covered": ["historical"],
        }],
    }
    formal = {"formal_gate": {"per_item": [{
        "question_id": "Q1",
        "passed": False,
        "claim_coverage": 1.0,
        "checks": {"claim_grounding": True, "no_hallucinated_digits": False},
        "digit_issues": ["3"],
    }]}}

    value = build_artifacts(raw, formal, [_golden()])

    assert value["delta"]["items"][0]["classification"] == "B"
    assert value["failures"]["items"][0]["failure_category"] == ["HALLUCINATION"]
    assert value["claims"]["items"][0]["entailment"] == "UNSUPPORTED"


def test_audit_records_historical_status_change():
    raw = {"summary": {"passed": 0}, "results": [{"question_id": "Q1", "passed": False}]}
    formal = {"formal_gate": {"per_item": [{
        "question_id": "Q1", "passed": False, "checks": {"claim_grounding": False},
    }]}}
    historical = {"summary": {"passed": 1}, "results": [{"question_id": "Q1", "passed": True}]}

    value = build_artifacts(raw, formal, [_golden()], historical)

    assert value["delta"]["summary"]["historical_to_current_status_changes"] == [
        {"question_id": "Q1", "historical": "PASS", "current": "FAIL"}
    ]
