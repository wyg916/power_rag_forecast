from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "rag-r1-ai-proxy-consensus/v2"
VERIFICATION_MODE = (
    "equivalent_ai_proxy_consensus_deterministic_independent_passes"
)
TECHNICAL_GATE_KEYS = tuple("""
question_count_100 result_identity_exact pass_count_gte_97 critical_30_of_30 citation_integrity_100pct grounding_gte_98pct hallucinated_digits_zero hallucination_rate_zero refusal_accuracy_100pct unavailable_precision_100pct tool_success_100pct tool_fact_mismatch_zero unauthorized_acl_block_100pct declared_passes_consistent summary_consistent candidate_runtime_read_only
""".split())
SUMMARY_FIELDS = tuple("""
total passed failed critical_total critical_passed citation_integrity grounding_rate refusal_accuracy unavailable_precision tool_success_rate tool_fact_mismatch_count acl_accuracy hallucinated_digit_count hallucination_rate declared_pass_mismatch_count result_record_count duplicate_result_question_ids missing_result_question_ids unexpected_result_question_ids
""".split())
TAXONOMY = tuple("""
retrieval_miss rerank_error wrong_chunk context_truncation context_ordering metric_time_mismatch citation_mismatch answer_reasoning refusal_error hallucination tool_routing domain_routing source_metadata_mismatch acl_security evaluation_consistency
""".split())


class AiProxyConsensusError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AiProxyConsensusError(f"mapping_required:{label}")
    return value


def _require_rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(
        not isinstance(item, Mapping) for item in value
    ):
        raise AiProxyConsensusError(f"rows_required:{label}")
    return list(value)


def _reviewer_b_recount(report: Mapping[str, Any]) -> dict[str, Any]:
    gate = _require_mapping(report.get("formal_gate"), "formal_gate")
    rows = _require_rows(gate.get("per_item"), "formal_gate.per_item")
    results = _require_rows(report.get("results"), "results")
    by_id = {
        str(item.get("question_id") or ""): item
        for item in results
        if item.get("question_id")
    }
    row_ids = [str(item.get("question_id") or "") for item in rows]
    result_ids = [str(item.get("question_id") or "") for item in results]
    expected_ids = set(row_ids)
    critical = [item for item in rows if item.get("critical") is True]
    routed = {
        route: [
            row
            for row in rows
            if str(by_id.get(str(row.get("question_id")), {}).get("expected_route"))
            == route
        ]
        for route in ("refuse", "unavailable")
    }
    tool_rows = [
        row
        for row in rows
        if (
            by_id.get(str(row.get("question_id")), {})
            .get("tool_routing_expectation", {})
            .get("required_tools")
        )
    ]
    check_ids: dict[str, list[str]] = {}
    for row in rows:
        checks = _require_mapping(row.get("checks"), "per_item.checks")
        for name, passed in checks.items():
            if passed is not True:
                check_ids.setdefault(str(name), []).append(
                    str(row.get("question_id") or "")
                )
    digit_count = sum(len(row.get("digit_issues") or []) for row in rows)
    digit_rows = sum(bool(row.get("digit_issues")) for row in rows)
    passed = sum(row.get("passed") is True for row in rows)
    duplicate_result_ids = sorted(
        question_id
        for question_id, count in Counter(result_ids).items()
        if question_id and count > 1
    )
    summary = {
        "total": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "critical_total": len(critical),
        "critical_passed": sum(row.get("passed") is True for row in critical),
        "citation_integrity": _rate(
            sum(
                row.get("checks", {}).get("citation_integrity") is True
                for row in rows
            ),
            len(rows),
        ),
        "grounding_rate": _rate(
            sum(
                row.get("checks", {}).get("claim_grounding") is True
                for row in rows
            ),
            len(rows),
        ),
        "refusal_accuracy": _rate(
            sum(
                row.get("checks", {}).get("refusal") is True
                for row in routed["refuse"]
            ),
            len(routed["refuse"]),
        ),
        "unavailable_precision": _rate(
            sum(
                row.get("checks", {}).get("refusal") is True
                for row in routed["unavailable"]
            ),
            len(routed["unavailable"]),
        ),
        "tool_success_rate": _rate(
            sum(
                row.get("checks", {}).get("tool_routing") is True
                for row in tool_rows
            ),
            len(tool_rows),
        ),
        "tool_fact_mismatch_count": sum(
            len(row.get("tool_fact_errors") or []) for row in rows
        ),
        "acl_accuracy": _rate(
            sum(row.get("checks", {}).get("acl") is True for row in rows),
            len(rows),
        ),
        "hallucinated_digit_count": digit_count,
        "hallucination_rate": _rate(digit_rows, len(rows)),
        "declared_pass_mismatch_count": sum(
            row.get("declared_pass_consistent") is not True for row in rows
        ),
        "result_record_count": len(results),
        "duplicate_result_question_ids": duplicate_result_ids,
        "missing_result_question_ids": sorted(expected_ids - set(result_ids)),
        "unexpected_result_question_ids": sorted(set(result_ids) - expected_ids),
    }
    return {
        "summary": summary,
        "failed_check_counts": {
            name: len(question_ids)
            for name, question_ids in sorted(check_ids.items())
        },
        "failed_check_question_ids": dict(sorted(check_ids.items())),
        "failed_question_ids": sorted(
            str(row.get("question_id") or "")
            for row in rows
            if row.get("passed") is not True
        ),
    }


def _failure_taxonomy(report: Mapping[str, Any]) -> dict[str, Any]:
    rows = _require_rows(
        _require_mapping(report.get("formal_gate"), "formal_gate").get(
            "per_item"
        ),
        "formal_gate.per_item",
    )
    items: list[dict[str, Any]] = []
    category_ids: dict[str, list[str]] = {name: [] for name in TAXONOMY}
    for row in rows:
        if row.get("passed") is True:
            continue
        question_id = str(row.get("question_id") or "")
        checks = _require_mapping(row.get("checks"), "per_item.checks")
        errors = [str(value).lower() for value in row.get("tool_fact_errors") or []]
        labels: list[str] = []
        if checks.get("run_id") is not True or any(
            marker in error
            for error in errors
            for marker in ("run_id", "metric", "time", "lineage")
        ):
            labels.append("metric_time_mismatch")
        if checks.get("citation_integrity") is not True:
            labels.append("citation_mismatch")
        if checks.get("claim_grounding") is not True:
            labels.append("answer_reasoning")
        if checks.get("refusal") is not True:
            labels.append("refusal_error")
        if checks.get("no_hallucinated_digits") is not True:
            labels.append("hallucination")
        if checks.get("tool_routing") is not True:
            labels.append("tool_routing")
        if checks.get("domain") is not True:
            labels.append("domain_routing")
        if checks.get("source_type") is not True:
            labels.append("source_metadata_mismatch")
        if checks.get("acl") is not True:
            labels.append("acl_security")
        if any(
            checks.get(name) is not True
            for name in (
                "result_present",
                "result_schema",
                "result_contract",
                "evaluator_checks",
            )
        ) or row.get("declared_pass_consistent") is not True:
            labels.append("evaluation_consistency")
        labels = [name for name in TAXONOMY if name in labels]
        if not labels:
            labels = ["evaluation_consistency"]
        for label in labels:
            category_ids[label].append(question_id)
        items.append(
            {
                "question_id": question_id,
                "critical": row.get("critical") is True,
                "primary": labels[0],
                "labels": labels,
                "failed_checks": sorted(
                    str(name)
                    for name, value in checks.items()
                    if value is not True
                ),
                "tool_fact_errors": row.get("tool_fact_errors") or [],
                "digit_issues": row.get("digit_issues") or [],
            }
        )
    categories = {
        name: {
            "observed_count": len(category_ids[name]),
            "question_ids": category_ids[name],
            "attribution": (
                "not_proven_by_current_evidence"
                if name
                in {
                    "retrieval_miss",
                    "rerank_error",
                    "wrong_chunk",
                    "context_truncation",
                    "context_ordering",
                }
                and not category_ids[name]
                else "observed_from_strict_checks"
            ),
        }
        for name in TAXONOMY
    }
    return {
        "failed_total": len(items),
        "classified_total": sum(bool(item["labels"]) for item in items),
        "categories": categories,
        "items": items,
    }


def build_proxy_consensus(
    report: Mapping[str, Any], source_sha256: str
) -> dict[str, Any]:
    if len(source_sha256) != 64:
        raise AiProxyConsensusError("source_sha256_invalid")
    gate = _require_mapping(report.get("formal_gate"), "formal_gate")
    gate_checks = _require_mapping(gate.get("checks"), "formal_gate.checks")
    reviewer_a_summary = _require_mapping(
        gate.get("recomputed_summary"), "formal_gate.recomputed_summary"
    )
    reviewer_b = _reviewer_b_recount(report)
    a_summary = {
        field: reviewer_a_summary.get(field) for field in SUMMARY_FIELDS
    }
    b_summary = {
        field: reviewer_b["summary"].get(field) for field in SUMMARY_FIELDS
    }
    metric_agreement = a_summary == b_summary
    technical_checks = {
        key: gate_checks.get(key) is True for key in TECHNICAL_GATE_KEYS
    }
    technical_pass = all(technical_checks.values())
    review_summary = _require_mapping(
        report.get("review_summary"), "review_summary"
    )
    governance = {
        "approval_complete": review_summary.get("approval_complete") is True,
        "approved": int(review_summary.get("approved") or 0),
        "pending_human_approval": int(
            review_summary.get("pending_human_approval") or 0
        ),
        "mapping_pending": int(review_summary.get("mapping_pending") or 0),
        "human_verified_count": int(review_summary.get("human_verified") or 0),
    }
    identity_exact = (
        b_summary["total"] == 100
        and b_summary["result_record_count"] == 100
        and not b_summary["duplicate_result_question_ids"]
        and not b_summary["missing_result_question_ids"]
        and not b_summary["unexpected_result_question_ids"]
    )
    consensus_verified = metric_agreement and identity_exact
    development_accepted = consensus_verified and technical_pass
    production_accepted = (
        development_accepted and governance["approval_complete"]
    )
    taxonomy = _failure_taxonomy(report)
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if development_accepted else "NOT_PASS",
        "approval_scope": "DEVELOPMENT_PREPRODUCTION",
        "verification_mode": VERIFICATION_MODE,
        "source_report_sha256": source_sha256,
        "automated_consensus_verified": consensus_verified,
        "consensus_verifies_measurement_not_acceptance": True,
        "consensus_authorizes_development_preproduction_only": True,
        "consensus_does_not_authorize_production": True,
        "human_verified": False,
        "production_human_signoff": False,
        "production_cutover": False,
        "development_preproduction_approval": {
            "status": "PASS" if development_accepted else "NOT_PASS",
            "review_sequence": [
                "REVIEWER_A",
                "REVIEWER_B",
                "ARBITRATOR",
                "DETERMINISTIC_CONSISTENCY_CHECK",
            ],
            "metric_agreement": metric_agreement,
            "identity_exact": identity_exact,
            "technical_pass": technical_pass,
            "human_verified": False,
            "production_human_signoff": False,
        },
        "external_production_gate": {
            "status": "PASS" if production_accepted else "PENDING",
            "required_for": "PRODUCTION_RELEASE_AND_CUTOVER",
            "blocks_development_preproduction": False,
            "human_verified": False,
            "production_human_signoff": False,
        },
        "reviewer_a": {
            "origin": "deterministic_governed_formal_gate_reader",
            "input_scope": "formal_gate.recomputed_summary_and_checks",
            "human_verified": False,
            "summary": a_summary,
            "technical_checks": technical_checks,
            "technical_pass": technical_pass,
        },
        "reviewer_b": {
            "origin": "deterministic_independent_per_item_recount",
            "input_scope": "formal_gate.per_item_and_raw_results_only",
            "human_verified": False,
            **reviewer_b,
        },
        "arbitrator": {
            "origin": "deterministic_consensus_arbitrator",
            "human_verified": False,
            "metric_agreement": metric_agreement,
            "identity_exact": identity_exact,
            "technical_pass": technical_pass,
            "governance_approved_for_production": governance[
                "approval_complete"
            ],
            "verdict_scope": "DEVELOPMENT_PREPRODUCTION",
            "verdict": "PASS" if development_accepted else "NOT_PASS",
        },
        "governance": governance,
        "failure_taxonomy": taxonomy,
        "blocker_root_causes": [
            {
                "code": "AI_TECHNICAL_GATE_NOT_MET",
                "active": not technical_pass,
                "evidence": {
                    "passed": b_summary["passed"],
                    "required_passed": 97,
                    "critical_passed": b_summary["critical_passed"],
                    "critical_required": 30,
                    "grounding_rate": b_summary["grounding_rate"],
                    "grounding_required": 0.98,
                },
            },
            {
                "code": "BUSINESS_TOOL_SOURCE_CONTRACT_UNAVAILABLE",
                "active": (
                    taxonomy["categories"]["tool_routing"]["observed_count"]
                    > 0
                ),
                "evidence": {
                    "tool_routing_failures": taxonomy["categories"][
                        "tool_routing"
                    ]["observed_count"],
                    "tool_fact_mismatch_count": b_summary[
                        "tool_fact_mismatch_count"
                    ],
                    "scope_note": (
                        "Current output proves tool failure/unavailable behavior; "
                        "it does not prove a database mutation or authorize fixture repair."
                    ),
                },
            },
            {
                "code": "EXTERNAL_PRODUCTION_GATE_PENDING",
                "active": not production_accepted,
                "evidence": governance,
            },
            {
                "code": "DECLARED_STRICT_RESULT_DRIFT",
                "active": b_summary["declared_pass_mismatch_count"] > 0,
                "evidence": {
                    "declared_pass_mismatch_count": b_summary[
                        "declared_pass_mismatch_count"
                    ]
                },
            },
        ],
        "release_actions": {
            "snapshot": "SKIPPED_EXTERNAL_PRODUCTION_GATE_PENDING",
            "alias_switch": "SKIPPED_EXTERNAL_PRODUCTION_GATE_PENDING",
            "smoke_after_switch": "SKIPPED_EXTERNAL_PRODUCTION_GATE_PENDING",
            "rollback": "SKIPPED_EXTERNAL_PRODUCTION_GATE_PENDING",
            "rto_rpo_measurement": "NOT_APPLICABLE_NO_RELEASE_DRILL",
        },
    }
    result["consensus_sha256"] = _sha256_bytes(_canonical(result))
    return result


def validate_proxy_consensus(
    value: Mapping[str, Any], report: Mapping[str, Any], source_sha256: str
) -> dict[str, Any]:
    expected = build_proxy_consensus(report, source_sha256)
    if value != expected:
        raise AiProxyConsensusError("proxy_consensus_mismatch")
    if value.get("human_verified") is not False or value.get(
        "production_human_signoff"
    ) is not False:
        raise AiProxyConsensusError("proxy_consensus_human_provenance_invalid")
    development = _require_mapping(
        value.get("development_preproduction_approval"),
        "development_preproduction_approval",
    )
    production = _require_mapping(
        value.get("external_production_gate"), "external_production_gate"
    )
    if (
        development.get("human_verified") is not False
        or development.get("production_human_signoff") is not False
        or production.get("human_verified") is not False
        or production.get("production_human_signoff") is not False
        or production.get("blocks_development_preproduction") is not False
    ):
        raise AiProxyConsensusError("proxy_consensus_approval_scope_invalid")
    return {
        "status": "PASS",
        "consensus_status": value["status"],
        "approval_scope": value["approval_scope"],
        "development_preproduction_status": development["status"],
        "external_production_gate_status": production["status"],
        "automated_consensus_verified": value[
            "automated_consensus_verified"
        ],
        "human_verified": False,
        "production_human_signoff": False,
        "consensus_sha256": value["consensus_sha256"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic AI100 proxy consensus audit"
    )
    parser.add_argument("--formal-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise AiProxyConsensusError("output_exists")
    raw = args.formal_report.read_bytes()
    report = json.loads(raw.decode("utf-8"))
    report = _require_mapping(report, "formal_report")
    consensus = build_proxy_consensus(report, _sha256_bytes(raw))
    validate_proxy_consensus(consensus, report, _sha256_bytes(raw))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(consensus, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "artifact_status": "PASS",
                "consensus_status": consensus["status"],
                "output": str(args.output),
                "consensus_sha256": consensus["consensus_sha256"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
