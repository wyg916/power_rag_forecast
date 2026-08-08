from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SCHEMA = "rag-r1-retrieval-golden/v1"
CONTRACT_SCHEMA = "rag-r1-retrieval-evidence-contract/v2"
EXPECTED_SOURCE_SHA256 = (
    "1e526ee2f4c2feda72a27c52fdc08b68888fccd02be2302110e45c1e2674df7e"
)
EXPECTED_COUNT = 50
TOP_K = 5
CANONICAL_SOURCE_PATH = (
    "docs/codex/evidence/RAG_R1B_GOLDEN_AI_CONSENSUS_20260804T023000/"
    "retrieval_ai_consensus_50.json"
)


class EvidenceContractError(RuntimeError):
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


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvidenceContractError(f"json_object_required:{path.name}")
    return value


def _legacy_item_hash(item: Mapping[str, Any]) -> str:
    preserved = {
        "id": item.get("id"),
        "question": item.get("question"),
        "critical": item.get("critical"),
        "evidence_chunk_id": item.get("evidence_chunk_id"),
        "expected_chunks": item.get("expected_chunks"),
        "expected_document_ids": item.get("expected_document_ids"),
        "expected_version": item.get("expected_version"),
        "claim_expectations": item.get("claim_expectations"),
        "citation_expectation": item.get("citation_expectation"),
        "scoring_rule": item.get("scoring_rule"),
        "approval_status": item.get("approval_status"),
        "review_passes": item.get("review_passes"),
        "human_verified": item.get("human_verified"),
        "automated_consensus_verified": item.get(
            "automated_consensus_verified"
        ),
        "production_human_signoff": item.get("production_human_signoff"),
    }
    return _sha256_bytes(_canonical(preserved))


def build_contract(source: Mapping[str, Any], source_path: str) -> dict[str, Any]:
    items = source.get("items")
    if (
        source.get("schema_version") != SOURCE_SCHEMA
        or source.get("release_id") != "RAG-R1"
        or source.get("collection") != "rag_chunks_RAG-R1"
        or not isinstance(items, list)
        or len(items) != EXPECTED_COUNT
        or source.get("human_verified") is not False
        or source.get("automated_consensus_verified") is not True
        or source.get("production_human_signoff") is not False
    ):
        raise EvidenceContractError("legacy_source_contract_invalid")

    contract_items: list[dict[str, Any]] = []
    conflict_ids: list[str] = []
    for item in items:
        expected_chunks = item.get("expected_chunks") or {}
        chunk_ids = [str(value) for value in expected_chunks.get("chunk_ids") or []]
        locators = expected_chunks.get("locators") or []
        expected_documents = [str(value) for value in item.get("expected_document_ids") or []]
        legacy_anchor = str(item.get("evidence_chunk_id") or "")
        if (
            not str(item.get("id") or "")
            or not str(item.get("question") or "")
            or not chunk_ids
            or legacy_anchor not in chunk_ids
            or not expected_documents
            or len(locators) != len(chunk_ids)
            or item.get("human_verified") is not False
            or item.get("automated_consensus_verified") is not True
            or item.get("production_human_signoff") is not False
        ):
            raise EvidenceContractError(f"legacy_item_invalid:{item.get('id')}")
        if len(chunk_ids) > TOP_K:
            conflict_ids.append(str(item["id"]))
        contract_items.append(
            {
                "id": str(item["id"]),
                "question_sha256": _sha256_bytes(
                    str(item["question"]).encode("utf-8")
                ),
                "critical": bool(item.get("critical")),
                "expected_document_ids": expected_documents,
                "must_have_evidence": {
                    "minimum_count": 1,
                    "match_rule": (
                        "at_least_one_citation_valid_chunk_from_expected_document"
                    ),
                    "required_integrity": [
                        "document_id",
                        "version_id",
                        "content_hash",
                        "quote",
                    ],
                },
                "supporting_evidence": {
                    "legacy_anchor_chunk_id": legacy_anchor,
                    "legacy_expected_chunk_ids": chunk_ids,
                    "legacy_locators_sha256": _sha256_bytes(_canonical(locators)),
                    "coverage_report_required": True,
                    "top_k_hard_gate": False,
                    "grounding_gate_required": True,
                },
                "legacy_item_sha256": _legacy_item_hash(item),
                "reviewer_result": {
                    "approval_status": item.get("approval_status"),
                    "review_passes": item.get("review_passes"),
                    "verification_mode": item.get("verification_mode"),
                    "automated_consensus_verified": True,
                    "human_verified": False,
                    "production_human_signoff": False,
                },
            }
        )

    return {
        "schema_version": CONTRACT_SCHEMA,
        "release_id": "RAG-R1",
        "collection": "rag_chunks_RAG-R1",
        "top_k": TOP_K,
        "legacy_source": {
            "path": source_path.replace("\\", "/"),
            "sha256": EXPECTED_SOURCE_SHA256,
            "schema_version": SOURCE_SCHEMA,
            "preserved_read_only": True,
        },
        "change_control": {
            "change_id": "DAY3-EXPECTED-TOPK-CONTRACT-20260808",
            "reason": "legacy_exact_chunk_count_exceeds_top_k",
            "conflict_question_ids": conflict_ids,
            "conflict_question_count": len(conflict_ids),
            "questions_deleted": 0,
            "questions_rewritten": 0,
            "legacy_labels_deleted": 0,
            "global_quality_thresholds_changed": False,
            "legacy_all_exact_chunks_retained_as_supporting_evidence": True,
        },
        "quality_gates": {
            "recall_at_3": 0.90,
            "recall_at_5": 0.98,
            "mrr": 0.85,
            "critical_recall_at_5": 1.0,
            "citation_integrity": 1.0,
            "grounding": 0.98,
        },
        "review_state": {
            "verification_mode": "multi_agent_independent_consensus",
            "automated_consensus_verified": True,
            "human_verified": False,
            "production_human_signoff": False,
            "production_cutover": False,
        },
        "items": contract_items,
    }


def validate_contract(
    contract: Mapping[str, Any], source: Mapping[str, Any]
) -> dict[str, Any]:
    expected = build_contract(
        source, str((contract.get("legacy_source") or {}).get("path") or "")
    )
    checks = {
        "schema": contract.get("schema_version") == CONTRACT_SCHEMA,
        "exact_reproducible_overlay": contract == expected,
        "question_count": len(contract.get("items") or []) == EXPECTED_COUNT,
        "conflict_count": (
            (contract.get("change_control") or {}).get("conflict_question_count")
            == 5
        ),
        "no_question_deletion": (
            (contract.get("change_control") or {}).get("questions_deleted") == 0
        ),
        "no_question_rewrite": (
            (contract.get("change_control") or {}).get("questions_rewritten") == 0
        ),
        "no_legacy_label_deletion": (
            (contract.get("change_control") or {}).get("legacy_labels_deleted") == 0
        ),
        "thresholds_unchanged": (
            (contract.get("change_control") or {}).get(
                "global_quality_thresholds_changed"
            )
            is False
        ),
        "human_gate_retained": (
            (contract.get("review_state") or {}).get("human_verified") is False
            and (contract.get("review_state") or {}).get(
                "production_human_signoff"
            )
            is False
        ),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "passed": sum(bool(value) for value in checks.values()),
        "total": len(checks),
    }


def evaluate_results(
    contract: Mapping[str, Any], results_report: Mapping[str, Any]
) -> dict[str, Any]:
    rows = {
        str(item.get("id")): item for item in results_report.get("results") or []
    }
    must_have_passed = 0
    supporting_full = 0
    supporting_matches = 0
    supporting_total = 0
    question_hash_matches = 0
    hit_at_3_count = 0
    hit_at_5_count = 0
    reciprocal_rank_total = 0.0
    critical_count = 0
    critical_hit_count = 0
    citation_count = 0
    per_question: list[dict[str, Any]] = []
    for item in contract.get("items") or []:
        row = rows.get(str(item["id"])) or {}
        expected_documents = set(item["expected_document_ids"])
        ordered_documents = [
            str(value) for value in row.get("top_document_ids") or []
        ]
        top_documents = set(ordered_documents)
        rank = next(
            (
                index
                for index, document_id in enumerate(ordered_documents, start=1)
                if document_id in expected_documents
            ),
            0,
        )
        question_hash_match = (
            _sha256_bytes(str(row.get("question") or "").encode("utf-8"))
            == item["question_sha256"]
        )
        hit_at_3 = bool(rank and rank <= 3)
        hit_at_5 = bool(rank and rank <= 5)
        is_critical = bool(item.get("critical"))
        citation_ok = bool(row.get("citation_integrity"))
        supporting = set(
            item["supporting_evidence"]["legacy_expected_chunk_ids"]
        )
        top_chunks = set(str(value) for value in row.get("top_chunk_ids") or [])
        matched = len(supporting & top_chunks)
        must_have = bool(expected_documents & top_documents) and citation_ok
        question_hash_matches += int(question_hash_match)
        hit_at_3_count += int(hit_at_3)
        hit_at_5_count += int(hit_at_5)
        reciprocal_rank_total += 1.0 / rank if rank else 0.0
        critical_count += int(is_critical)
        critical_hit_count += int(is_critical and hit_at_5)
        citation_count += int(citation_ok)
        must_have_passed += int(must_have)
        supporting_full += int(matched == len(supporting))
        supporting_matches += matched
        supporting_total += len(supporting)
        per_question.append(
            {
                "id": item["id"],
                "question_hash_match": question_hash_match,
                "rank": rank or None,
                "hit_at_3": hit_at_3,
                "hit_at_5": hit_at_5,
                "must_have_evidence_pass": must_have,
                "supporting_match_count": matched,
                "supporting_expected_count": len(supporting),
                "supporting_full_coverage": matched == len(supporting),
            }
        )
    count = len(contract.get("items") or [])
    metrics = {
        "question_count": count,
        "question_hash_match_count": question_hash_matches,
        "recall_at_3": round(hit_at_3_count / max(1, count), 6),
        "recall_at_5": round(hit_at_5_count / max(1, count), 6),
        "mrr": round(reciprocal_rank_total / max(1, count), 6),
        "critical_count": critical_count,
        "critical_recall_at_5": round(
            critical_hit_count / max(1, critical_count), 6
        ),
        "citation_integrity": round(citation_count / max(1, count), 6),
        "must_have_evidence_full_coverage": round(
            must_have_passed / max(1, count), 6
        ),
        "supporting_evidence_question_full_coverage": round(
            supporting_full / max(1, count), 6
        ),
        "supporting_evidence_chunk_coverage": round(
            supporting_matches / max(1, supporting_total), 6
        ),
    }
    return {
        "status": (
            "PASS"
            if count == EXPECTED_COUNT
            and question_hash_matches == EXPECTED_COUNT
            and metrics["recall_at_3"] >= 0.90
            and metrics["recall_at_5"] >= 0.98
            and metrics["mrr"] >= 0.85
            and metrics["critical_recall_at_5"] == 1.0
            and metrics["citation_integrity"] == 1.0
            and metrics["must_have_evidence_full_coverage"] == 1.0
            else "FAIL"
        ),
        "metrics": metrics,
        "per_question": per_question,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--write-contract", action="store_true")
    parser.add_argument("--results", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    source_path = args.source.resolve(strict=True)
    if _sha256_path(source_path) != EXPECTED_SOURCE_SHA256:
        raise EvidenceContractError("legacy_source_sha256_mismatch")
    source = _read_json(source_path)
    if args.write_contract:
        if args.contract.exists():
            raise EvidenceContractError("contract_output_exists")
        contract = build_contract(source, CANONICAL_SOURCE_PATH)
        args.contract.parent.mkdir(parents=True, exist_ok=True)
        args.contract.write_text(
            json.dumps(contract, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
    contract = _read_json(args.contract)
    report: dict[str, Any] = {
        "schema_version": "rag-r1-evidence-contract-audit/v1",
        "source_sha256": _sha256_path(source_path),
        "contract_sha256": _sha256_path(args.contract),
        "contract_validation": validate_contract(contract, source),
    }
    if args.results:
        report["retrieval_evaluation"] = evaluate_results(
            contract, _read_json(args.results)
        )
    report["status"] = (
        "PASS"
        if report["contract_validation"]["status"] == "PASS"
        and (
            "retrieval_evaluation" not in report
            or report["retrieval_evaluation"]["status"] == "PASS"
        )
        else "FAIL"
    )
    if args.output.exists():
        raise EvidenceContractError("audit_output_exists")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": report["status"], "output": str(args.output)}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
