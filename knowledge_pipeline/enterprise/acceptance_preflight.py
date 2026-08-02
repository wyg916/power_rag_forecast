from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_RELEASE_ID = "RAG-R1"
EXPECTED_OCR_PAGES = 30
EXPECTED_RETRIEVAL_QUESTIONS = 50
EXPECTED_AI_QUESTIONS = 100
EXPECTED_AI_CRITICAL = 30


class AcceptancePreflightError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AcceptancePreflightError("json_unavailable_or_invalid") from exc
    if not isinstance(value, dict):
        raise AcceptancePreflightError("json_object_required")
    return value


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _unique(values: Sequence[Any]) -> bool:
    try:
        return len(values) == len(set(values))
    except TypeError:
        return False


def _asset_result(path: Path, issues: list[str], **details: Any) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "exists": path.is_file(),
        "input_ready": not issues,
        "issues": issues,
        **details,
    }


def validate_ocr_gold(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return _asset_result(path, ["ocr_gold_missing"], page_count=0)
    try:
        value = _load_object(path)
    except AcceptancePreflightError as exc:
        return _asset_result(path, [f"ocr_gold_{exc}"], page_count=0)
    pages = value.get("pages")
    issues: list[str] = []
    if value.get("schema_version") != "rag-r1-ocr-gold/v1":
        issues.append("ocr_gold_schema_invalid")
    if value.get("release_id") != EXPECTED_RELEASE_ID:
        issues.append("ocr_gold_release_mismatch")
    if not isinstance(pages, list) or len(pages) != EXPECTED_OCR_PAGES:
        issues.append("ocr_gold_requires_exactly_30_pages")
        pages = pages if isinstance(pages, list) else []
    identities: list[tuple[str, int]] = []
    table_cell_count = 0
    for item in pages:
        if not isinstance(item, Mapping):
            issues.append("ocr_gold_page_invalid")
            continue
        document_id = item.get("document_id")
        page = item.get("page")
        annotation = item.get("annotation")
        elements = item.get("elements")
        reference_cells = item.get("reference_table_cells", [])
        if not _non_empty(item.get("sample_id")) or not _non_empty(document_id):
            issues.append("ocr_gold_identity_missing")
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            issues.append("ocr_gold_page_number_invalid")
        elif _non_empty(document_id):
            identities.append((str(document_id), page))
        if not _non_empty(item.get("reference_text")):
            issues.append("ocr_gold_reference_text_missing")
        if not isinstance(elements, list) or not elements:
            issues.append("ocr_gold_locator_elements_missing")
        else:
            for element in elements:
                bbox = element.get("bbox") if isinstance(element, Mapping) else None
                if (
                    not isinstance(element, Mapping)
                    or not _non_empty(element.get("element_id"))
                    or not _non_empty(element.get("kind"))
                    or not isinstance(bbox, list)
                    or len(bbox) != 4
                    or not all(isinstance(number, (int, float)) for number in bbox)
                ):
                    issues.append("ocr_gold_locator_invalid")
                    break
        if not isinstance(reference_cells, list):
            issues.append("ocr_gold_table_cells_invalid")
        else:
            table_cell_count += len(reference_cells)
        if (
            not isinstance(annotation, Mapping)
            or annotation.get("annotator_type") != "human"
            or not _non_empty(annotation.get("reviewer_id"))
            or not _non_empty(annotation.get("approved_at"))
        ):
            issues.append("ocr_gold_human_annotation_unverified")
    if not _unique(identities) or len(identities) != len(pages):
        issues.append("ocr_gold_page_identity_duplicate_or_missing")
    if table_cell_count < 1:
        issues.append("ocr_gold_table_reference_missing")
    return _asset_result(
        path,
        sorted(set(issues)),
        page_count=len(pages),
        table_cell_count=table_cell_count,
    )


def _citation_identity_valid(value: Any, chunk_ids: set[str]) -> bool:
    return bool(
        isinstance(value, Mapping)
        and value.get("release_id") == EXPECTED_RELEASE_ID
        and _non_empty(value.get("document_id"))
        and _non_empty(value.get("version_id"))
        and _non_empty(value.get("chunk_id"))
        and value.get("chunk_id") in chunk_ids
    )


def validate_retrieval_gold(path: Path, chunk_ids: set[str]) -> dict[str, Any]:
    if not path.is_file():
        return _asset_result(path, ["retrieval_gold_missing"], question_count=0)
    try:
        value = _load_object(path)
    except AcceptancePreflightError as exc:
        return _asset_result(path, [f"retrieval_gold_{exc}"], question_count=0)
    questions = value.get("questions")
    issues: list[str] = []
    if value.get("schema_version") != "rag-r1-retrieval-gold/v1":
        issues.append("retrieval_gold_schema_invalid")
    if value.get("release_id") != EXPECTED_RELEASE_ID:
        issues.append("retrieval_gold_release_mismatch")
    if not isinstance(questions, list) or len(questions) != EXPECTED_RETRIEVAL_QUESTIONS:
        issues.append("retrieval_gold_requires_exactly_50_questions")
        questions = questions if isinstance(questions, list) else []
    question_ids: list[str] = []
    critical_count = 0
    for item in questions:
        if not isinstance(item, Mapping):
            issues.append("retrieval_gold_question_invalid")
            continue
        question_id = item.get("question_id")
        gold = item.get("gold_citations")
        if not _non_empty(question_id) or not _non_empty(item.get("question")):
            issues.append("retrieval_gold_question_identity_missing")
        else:
            question_ids.append(str(question_id))
        if item.get("critical") is True:
            critical_count += 1
        elif item.get("critical") is not False:
            issues.append("retrieval_gold_critical_flag_invalid")
        if not isinstance(gold, list) or not gold:
            issues.append("retrieval_gold_citation_missing")
        elif not all(_citation_identity_valid(citation, chunk_ids) for citation in gold):
            issues.append("retrieval_gold_citation_identity_invalid")
    if not _unique(question_ids) or len(question_ids) != len(questions):
        issues.append("retrieval_gold_question_id_duplicate_or_missing")
    if critical_count < 1:
        issues.append("retrieval_gold_critical_set_missing")
    return _asset_result(
        path,
        sorted(set(issues)),
        question_count=len(questions),
        critical_count=critical_count,
    )


def validate_ai_gold(path: Path, chunk_ids: set[str]) -> dict[str, Any]:
    if not path.is_file():
        return _asset_result(path, ["ai_gold_missing"], question_count=0, critical_count=0)
    try:
        value = _load_object(path)
    except AcceptancePreflightError as exc:
        return _asset_result(path, [f"ai_gold_{exc}"], question_count=0, critical_count=0)
    questions = value.get("questions")
    issues: list[str] = []
    if value.get("schema_version") != "rag-r1-ai-gold/v1":
        issues.append("ai_gold_schema_invalid")
    if value.get("release_id") != EXPECTED_RELEASE_ID:
        issues.append("ai_gold_release_mismatch")
    if not isinstance(questions, list) or len(questions) != EXPECTED_AI_QUESTIONS:
        issues.append("ai_gold_requires_exactly_100_questions")
        questions = questions if isinstance(questions, list) else []
    question_ids: list[str] = []
    critical_count = 0
    behaviors = {"answer_with_citations", "refuse_no_evidence", "refuse_security"}
    for item in questions:
        if not isinstance(item, Mapping):
            issues.append("ai_gold_question_invalid")
            continue
        question_id = item.get("question_id")
        behavior = item.get("expected_behavior")
        if not _non_empty(question_id) or not _non_empty(item.get("question")):
            issues.append("ai_gold_question_identity_missing")
        else:
            question_ids.append(str(question_id))
        if item.get("critical") is True:
            critical_count += 1
        elif item.get("critical") is not False:
            issues.append("ai_gold_critical_flag_invalid")
        if behavior not in behaviors:
            issues.append("ai_gold_behavior_invalid")
        if not isinstance(item.get("allowed_numeric_claims"), list):
            issues.append("ai_gold_numeric_claim_contract_missing")
        if behavior == "answer_with_citations":
            facts = item.get("required_facts")
            citations = item.get("gold_citations")
            if not isinstance(facts, list) or not facts or not all(_non_empty(fact) for fact in facts):
                issues.append("ai_gold_required_facts_missing")
            if not isinstance(citations, list) or not citations:
                issues.append("ai_gold_citation_missing")
            elif not all(_citation_identity_valid(citation, chunk_ids) for citation in citations):
                issues.append("ai_gold_citation_identity_invalid")
        elif item.get("gold_citations") not in (None, []):
            issues.append("ai_gold_refusal_must_not_require_citation")
    if not _unique(question_ids) or len(question_ids) != len(questions):
        issues.append("ai_gold_question_id_duplicate_or_missing")
    if critical_count != EXPECTED_AI_CRITICAL:
        issues.append("ai_gold_requires_exactly_30_critical")
    return _asset_result(
        path,
        sorted(set(issues)),
        question_count=len(questions),
        critical_count=critical_count,
    )


def _candidate_checks(candidate_path: Path, collection_path: Path) -> tuple[dict[str, Any], set[str]]:
    candidate = _load_object(candidate_path)
    collection = _load_object(collection_path)
    manifest = candidate.get("candidate_manifest")
    counts = candidate.get("counts")
    if not isinstance(manifest, Mapping) or not isinstance(counts, Mapping):
        raise AcceptancePreflightError("candidate_contract_invalid")
    documents = manifest.get("documents")
    chunks = manifest.get("chunks")
    isolations = candidate.get("isolations")
    duplicates = candidate.get("duplicates")
    if not all(isinstance(value, list) for value in (documents, chunks, isolations, duplicates)):
        raise AcceptancePreflightError("candidate_items_invalid")
    actual_hash = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    chunk_ids = {
        str(item.get("chunk_id"))
        for item in chunks
        if isinstance(item, Mapping) and _non_empty(item.get("chunk_id"))
    }
    terminal_total = len(documents) + len(isolations) + len(duplicates)
    ledger_issues: list[str] = []
    if int(counts.get("ledger") or 0) != 83 or terminal_total != 83:
        ledger_issues.append("ledger_not_83_terminal_items")
    if any(item.get("status") != "ready" for item in documents if isinstance(item, Mapping)):
        ledger_issues.append("candidate_document_not_ready")
    if len(chunk_ids) != len(chunks):
        ledger_issues.append("candidate_chunk_identity_invalid")
    corpus_issues: list[str] = []
    if candidate.get("candidate_release_id") != EXPECTED_RELEASE_ID:
        corpus_issues.append("candidate_release_mismatch")
    if len(documents) != int(counts.get("documents") or -1):
        corpus_issues.append("candidate_document_count_mismatch")
    if len(chunks) != int(counts.get("chunks") or -1):
        corpus_issues.append("candidate_chunk_count_mismatch")
    if collection.get("candidate_file_sha256") != actual_hash:
        corpus_issues.append("collection_candidate_hash_mismatch")
    if collection.get("release_id") != EXPECTED_RELEASE_ID:
        corpus_issues.append("collection_release_mismatch")
    if int(collection.get("point_count") or -1) != len(chunks):
        corpus_issues.append("collection_point_count_mismatch")
    if collection.get("status") != "PASS" or collection.get("strict_mode_enabled") is not True:
        corpus_issues.append("collection_contract_not_pass")
    return (
        {
            "ledger_terminal": {
                "passed": not ledger_issues,
                "issues": ledger_issues,
                "terminal_total": terminal_total,
                "published_candidate_items": len(documents),
                "isolated_items": len(isolations),
                "duplicate_items": len(duplicates),
                "damaged_items": 0,
            },
            "corpus_quality": {
                "passed": not corpus_issues,
                "issues": corpus_issues,
                "document_count": len(documents),
                "chunk_count": len(chunks),
                "asset_count": int(counts.get("assets") or 0),
                "candidate_sha256": actual_hash,
            },
        },
        chunk_ids,
    )


def run_preflight(
    *,
    candidate_path: Path,
    collection_path: Path,
    ocr_gold_path: Path,
    retrieval_gold_path: Path,
    ai_gold_path: Path,
) -> dict[str, Any]:
    candidate_gates, chunk_ids = _candidate_checks(candidate_path, collection_path)
    assets = {
        "ocr_vlm": validate_ocr_gold(ocr_gold_path),
        "retrieval": validate_retrieval_gold(retrieval_gold_path, chunk_ids),
        "ai": validate_ai_gold(ai_gold_path, chunk_ids),
    }
    input_gates = {
        "ocr_vlm_quality": assets["ocr_vlm"]["input_ready"],
        "retrieval_quality": assets["retrieval"]["input_ready"],
        "ai_grounding": assets["ai"]["input_ready"],
    }
    ready = all(gate["passed"] for gate in candidate_gates.values()) and all(input_gates.values())
    return {
        "schema_version": "rag-r1-acceptance-preflight/v1",
        "release_id": EXPECTED_RELEASE_ID,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "READY" if ready else "BLOCKED",
        "publish_allowed": False,
        "scope": "input_preflight_only_metrics_not_executed",
        "candidate_gates": candidate_gates,
        "evaluation_inputs": assets,
        "metric_gate_inputs_ready": input_gates,
        "remaining_gates": {
            "security": "not_run",
            "consistency": "not_run",
            "reliability": "not_run",
            "regression": "not_run",
        },
        "legacy_assets_rejected": {
            "tests/evaluation/ai_assistant_eval_questions.json": "legacy_title_based_contract_without_rag_r1_citation_identity",
            "tests/evaluation/phase5_base_30_questions.json": "legacy_30_question_set_with_pre_rag_r1_document_ids",
            "tests/evaluation/rag_expected_hits.json": "legacy_title_hints_not_50_question_gold_set",
            "tests/evaluation/run_phase5_rag_acceptance.py": "dynamic_32_case_self_query_and_legacy_thresholds",
        },
    }

