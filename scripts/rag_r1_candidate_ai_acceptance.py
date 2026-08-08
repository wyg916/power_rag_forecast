from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.qdrant_vector_store import QdrantReadOnlyStore
from backend.app.services.rag_runtime_contract import RetrievalContext, runtime_contract_status
from backend.app.ai.identity_context import IdentityContext
from scripts import rag_r1_candidate_acceptance as candidate
from tests.evaluation import run_ai_assistant_eval as runner


class CandidateAiAcceptanceError(RuntimeError):
    pass


AI_GOLDEN_SCHEMA_VERSION = "rag-r1-ai-golden-item/v1"
AI_SCORE_SCHEMA_VERSION = "rag-r1-ai-score/v1"
AI_GOLDEN_COUNT, AI_CRITICAL_COUNT = 100, 30
FAILURE_CLASSES = ("eval_fixture", "retrieval", "rerank", "citation", "claim", "tool_routing", "refusal")
_TOP_FIELDS = set("""
schema_version id question_id category question critical expected_domain expected_route
expected_source_type required_facts required_tool required_run_id_behavior required_citations
forbidden_claims security_expectation pass_criteria expected_document expected_version
expected_chunks citation_expectation claim_expectations tool_routing_expectation
refusal_expectation acl_expectation scoring_rule label_provenance human_verified annotator
reviewer approval_status should_use_rag should_use_tools expected_titles_any
expected_keywords_any expected_answer_points forbidden_patterns default_should_hide
""".split())
_NESTED_FIELDS = {
    "expected_document": "mode document_ids legacy_document_id_candidates title_aliases match_rule mapping_status",
    "expected_version": "release_id version_ids resolution_rule mapping_status",
    "expected_chunks": "chunk_ids resolution_rule mapping_status",
    "citation_expectation": "required minimum_count document_match version_match chunk_match quote_match content_hash_match locator_match",
    "claim_expectations": "required_claims forbidden_claims coverage_required critical_all_or_nothing",
    "tool_routing_expectation": "route required_tools allowed_tools unexpected_business_tool_is_failure run_id_behavior",
    "refusal_expectation": "required reason_code required_when_approved_evidence_missing must_not_fabricate",
    "acl_expectation": "authorized_context unauthorized_probe primary_scenario probe_required",
    "scoring_rule": "schema_version pass_mode required_checks global_gate_profile critical_all_or_nothing",
    "label_provenance": "source_files source_question_ids source_revision transformation model_generated_label",
}
_STRING_FIELDS = set("""
id question_id category question expected_domain expected_route expected_source_type required_run_id_behavior
security_expectation pass_criteria annotator reviewer approval_status
""".split())
_BOOL_FIELDS = {
    "critical", "required_citations", "human_verified",
    "should_use_rag", "should_use_tools",
}
_LIST_FIELDS = {
    "required_facts": False, "forbidden_claims": True,
    "expected_titles_any": True, "expected_keywords_any": True,
    "expected_answer_points": True, "forbidden_patterns": True,
    "default_should_hide": True,
}

def _fail(code: str, item_id: str = "") -> None:
    raise CandidateAiAcceptanceError(code + (f":{item_id}" if item_id else ""))

def _json_object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail("duplicate_json_key", key)
        value[key] = item
    return value

def _read_json_fail_closed(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_json_object_without_duplicate_keys,
        )
    except CandidateAiAcceptanceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateAiAcceptanceError(f"json_load_invalid:{path.name}") from exc

def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and "\ufffd" not in value and "??" not in value

def _strings(value: Any, empty: bool = True) -> bool:
    return isinstance(value, list) and (empty or bool(value)) and all(_text(x) for x in value)

def _require(ok: bool, code: str, item_id: str) -> None:
    if not ok:
        _fail(code, item_id)

def _validate_governed_item(item: Any, index: int) -> dict[str, Any]:
    _require(isinstance(item, Mapping), "ai_golden_item_not_object", str(index))
    item_id = str(item.get("question_id") or item.get("id") or index)
    _require(set(item) == _TOP_FIELDS, "ai_golden_item_contract_incomplete", item_id)
    _require(item["schema_version"] == AI_GOLDEN_SCHEMA_VERSION, "ai_golden_schema_version_invalid", item_id)
    _require(all(_text(item.get(x)) for x in _STRING_FIELDS), "ai_golden_string_field_invalid", item_id)
    _require(isinstance(item["required_tool"], str), "ai_golden_required_tool_invalid", item_id)
    _require(all(isinstance(item.get(x), bool) for x in _BOOL_FIELDS), "ai_golden_boolean_field_invalid", item_id)
    _require(
        all(_strings(item.get(x), empty) for x, empty in _LIST_FIELDS.items()),
        "ai_golden_list_field_invalid", item_id,
    )
    for name, fields in _NESTED_FIELDS.items():
        _require(
            isinstance(item.get(name), Mapping) and set(fields.split()) == set(item[name]),
            f"ai_golden_{name}_invalid", item_id,
        )
    _require(
        item["expected_route"] in {"rag", "tool", "tool+rag", "refuse", "unavailable"}
        and item["expected_source_type"] in {"derived", "real", "unavailable"}
        and item["required_run_id_behavior"] in {"none", "latest_success", "explicit"}
        and item["security_expectation"] in {"no_sensitive_data", "refuse"}
        and item["approval_status"] in {"pending", "approved", "rejected"},
        "ai_golden_enum_invalid", item_id,
    )
    _require(
        not (item["approval_status"] == "pending" and item["human_verified"])
        and not (
            item["approval_status"] == "approved"
            and (
                not item["human_verified"]
                or "UNASSIGNED" in {item["annotator"], item["reviewer"]}
                or item["annotator"] == item["reviewer"]
            )
        ),
        "ai_golden_approval_evidence_invalid", item_id,
    )

    document, version, chunks = item["expected_document"], item["expected_version"], item["expected_chunks"]
    statuses = {"pending_human_mapping", "approved", "not_applicable"}
    _require(
        document["mode"] in {"required", "not_applicable"}
        and all(value["mapping_status"] in statuses for value in (document, version, chunks)) and all(x.startswith("doc_") for x in document["document_ids"]) and all(x.startswith("kb_") for x in document["legacy_document_id_candidates"])
        and version["release_id"] == candidate.RELEASE_ID
        and all(_strings(value) for value in (
            document["document_ids"], document["legacy_document_id_candidates"], document["title_aliases"],
            version["version_ids"], chunks["chunk_ids"],
        ))
        and all(_text(value) for value in (
            document["match_rule"], version["resolution_rule"], chunks["resolution_rule"],
        ))
        and not (
            document["mode"] == "not_applicable"
            and (document["document_ids"] or document["legacy_document_id_candidates"] or document["title_aliases"])
        ),
        "ai_golden_evidence_mapping_invalid", item_id,
    )
    citation, claims = item["citation_expectation"], item["claim_expectations"]
    claim_rows = claims["required_claims"]
    _require(
        isinstance(citation["required"], bool)
        and type(citation["minimum_count"]) is int
        and citation["minimum_count"] == (1 if item["required_citations"] else 0)
        and citation["required"] is item["required_citations"]
        and all(_text(citation[x]) for x in (
            "document_match", "version_match", "chunk_match",
            "quote_match", "content_hash_match", "locator_match",
        ))
        and isinstance(claim_rows, list) and bool(claim_rows)
        and all(
            isinstance(row, Mapping)
            and {"claim_id", "text", "citation_required"} <= set(row)
            and _text(row["claim_id"]) and _text(row["text"])
            and isinstance(row["citation_required"], bool)
            for row in claim_rows
        )
        and len({row["claim_id"] for row in claim_rows}) == len(claim_rows)
        and _strings(claims["forbidden_claims"])
        and type(claims["coverage_required"]) in {int, float}
        and 0 <= claims["coverage_required"] <= 1
        and claims["critical_all_or_nothing"] is item["critical"],
        "ai_golden_claim_citation_invalid", item_id,
    )

    tool, refusal = item["tool_routing_expectation"], item["refusal_expectation"]
    acl, score, provenance = item["acl_expectation"], item["scoring_rule"], item["label_provenance"]
    contexts = (acl["authorized_context"], acl["unauthorized_probe"])
    score_checks = {
        "route", "domain", "source_type", "claim_grounding", "tool_routing",
        "refusal", "acl", "citation_integrity", "no_hallucinated_digits",
    }
    _require(
        tool["route"] == item["expected_route"]
        and tool["run_id_behavior"] == item["required_run_id_behavior"]
        and _strings(tool["required_tools"]) and _strings(tool["allowed_tools"])
        and set(tool["required_tools"]) <= set(tool["allowed_tools"])
        and (not item["required_tool"] or item["required_tool"] in tool["required_tools"])
        and tool["unexpected_business_tool_is_failure"] is True
        and refusal["required"] is (item["expected_route"] in {"refuse", "unavailable"})
        and refusal["reason_code"] in {"none", "security_policy", "evidence_unavailable"}
        and all(type(refusal[x]) is bool for x in (
            "required", "required_when_approved_evidence_missing", "must_not_fabricate",
        ))
        and all(
            isinstance(ctx, Mapping)
            and {"tenant_id", "roles", "release_id"} <= set(ctx)
            and _text(ctx["tenant_id"]) and _strings(ctx["roles"], False)
            and ctx["release_id"] == candidate.RELEASE_ID
            for ctx in contexts
        )
        and acl["authorized_context"]["tenant_id"] != acl["unauthorized_probe"]["tenant_id"]
        and acl["unauthorized_probe"].get("expected_behavior") == "deny_without_cross_tenant_evidence"
        and acl["primary_scenario"] in {"authorized", "unauthorized"}
        and acl["probe_required"] is True
        and score["schema_version"] == AI_SCORE_SCHEMA_VERSION
        and score["pass_mode"] == "all_required_checks"
        and _strings(score["required_checks"], False)
        and score_checks <= set(score["required_checks"])
        and score["global_gate_profile"] == "rag-r1-ai-100"
        and score["critical_all_or_nothing"] is item["critical"]
        and _strings(provenance["source_files"], False)
        and _strings(provenance["source_question_ids"], False)
        and _text(provenance["source_revision"])
        and _text(provenance["transformation"])
        and provenance["model_generated_label"] is False,
        "ai_golden_governance_invalid", item_id,
    )
    _require(
        item["should_use_rag"] is (item["expected_route"] in {"rag", "tool+rag"})
        and item["should_use_tools"] is (item["expected_route"] in {"tool", "tool+rag"}),
        "ai_golden_legacy_route_mismatch", item_id,
    )
    return dict(item)

def validate_governed_ai_questions(value: Any) -> list[dict[str, Any]]:
    _require(isinstance(value, list) and len(value) == AI_GOLDEN_COUNT, "ai_golden_question_count_invalid", "")
    items = [_validate_governed_item(item, index) for index, item in enumerate(value)]
    for field in ("id", "question_id", "question"):
        values = [str(item[field]).strip() for item in items]
        _require(len(values) == len(set(values)), f"ai_golden_duplicate_{field}", "")
    _require(sum(item["critical"] for item in items) == AI_CRITICAL_COUNT, "ai_golden_critical_count_invalid", "")
    expected = getattr(runner, "PHASE5_B_CATEGORIES", {})
    _require(not expected or Counter(item["category"] for item in items) == Counter(expected), "ai_golden_category_distribution_invalid", "")
    return items

def load_governed_ai_questions(path: Path) -> list[dict[str, Any]]:
    return validate_governed_ai_questions(_read_json_fail_closed(path))

def question_bank_sha256(items: Sequence[Mapping[str, Any]]) -> str:
    payload = json.dumps(list(items), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def golden_review_summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(item.get("approval_status") or "invalid") for item in items)
    approved = {
        item["question_id"] for item in items
        if item["approval_status"] == "approved" and item["human_verified"]
        and "UNASSIGNED" not in {item["annotator"], item["reviewer"]}
        and item["annotator"] != item["reviewer"]
    }
    pending_map = [
        item["question_id"] for item in items
        if item["expected_document"]["mode"] == "required"
        and (
            any(item[name]["mapping_status"] != "approved" for name in (
                "expected_document", "expected_version", "expected_chunks",
            ))
            or any(not item[name][field] for name, field in (
                ("expected_document", "document_ids"), ("expected_version", "version_ids"),
                ("expected_chunks", "chunk_ids"),
            ))
        )
    ]
    return {
        "total": len(items), "approval_status_counts": dict(sorted(statuses.items())),
        "human_verified": sum(item["human_verified"] for item in items),
        "approved": len(approved), "pending_human_approval": len(items) - len(approved),
        "critical_total": sum(item["critical"] for item in items),
        "critical_approved": sum(item["critical"] and item["question_id"] in approved for item in items),
        "mapping_pending": len(pending_map), "mapping_pending_question_ids": pending_map,
        "approval_complete": len(approved) == len(items) and not pending_map,
    }


_CITATION_REQUIRED_FIELDS = frozenset(
    {
        "document_id",
        "chunk_id",
        "version_id",
        "page",
        "section_path",
        "char_start",
        "char_end",
        "bbox",
        "asset_id",
        "quote",
        "content_hash",
    }
)
_CITATION_ALLOWED_FIELDS = _CITATION_REQUIRED_FIELDS | {
    "citation_id",
    "release_id",
    "title",
    "score",
}

def _citation_shape_errors(citation: Any) -> list[str]:
    if not isinstance(citation, Mapping):
        return ["citation_type_invalid"]
    if _CITATION_REQUIRED_FIELDS - set(citation) or set(citation) - _CITATION_ALLOWED_FIELDS:
        return ["citation_fields_invalid"]
    if any(
        not _text(citation.get(field))
        for field in ("document_id", "chunk_id", "version_id", "quote", "content_hash")
    ):
        return ["citation_field_type_invalid"]
    if any(
        field in citation and citation[field] is not None and not _text(citation[field])
        for field in ("citation_id", "release_id", "title")
    ) or (
        "score" in citation and citation["score"] is not None
        and (type(citation["score"]) not in {int, float} or not math.isfinite(citation["score"]))
    ):
        return ["citation_optional_field_type_invalid"]
    page = citation.get("page")
    if page is not None and (type(page) is not int or page < 1):
        return ["citation_page_invalid"]
    section_path = citation.get("section_path")
    if not isinstance(section_path, list) or any(
        not _text(value) for value in section_path
    ):
        return ["citation_section_path_invalid"]
    start = citation.get("char_start")
    end = citation.get("char_end")
    if type(start) is not int or type(end) is not int or start < 0 or end <= start:
        return ["citation_offsets_invalid"]
    bbox = citation.get("bbox")
    if bbox is not None:
        if (
            not isinstance(bbox, (list, tuple))
            or len(bbox) != 4
            or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in bbox)
            or not all(math.isfinite(float(value)) for value in bbox)
            or float(bbox[0]) > float(bbox[2])
            or float(bbox[1]) > float(bbox[3])
            or page is None
        ):
            return ["citation_bbox_invalid"]
    asset_id = citation.get("asset_id")
    if asset_id is not None and not _text(asset_id):
        return ["citation_asset_id_invalid"]
    return []

def immutable_citation_validator(
    chunks: Mapping[str, Mapping[str, Any]],
):
    def validate(
        citations: list[dict[str, Any]],
    ) -> tuple[bool, list[str]]:
        if not isinstance(citations, list):
            return False, ["citations_type_invalid"]
        errors: list[str] = []
        locator_fields = (
            "page",
            "section_path",
            "char_start",
            "char_end",
            "bbox",
            "asset_id",
        )
        identities: set[tuple[Any, ...]] = set()
        for citation in citations:
            shape_errors = _citation_shape_errors(citation)
            if shape_errors:
                errors.extend(shape_errors)
                continue
            identity = (
                citation["document_id"],
                citation["version_id"],
                citation["chunk_id"],
                citation["char_start"],
                citation["char_end"],
            )
            if identity in identities:
                errors.append("duplicate_citation")
                continue
            identities.add(identity)
            chunk = chunks.get(str(citation.get("chunk_id") or ""))
            if chunk is None or chunk.get("document_id") != citation.get("document_id"):
                errors.append("fabricated_citation")
                continue
            immutable = chunk.get("citation")
            if not isinstance(immutable, Mapping):
                errors.append("immutable_citation_missing")
                continue
            if chunk.get("version_id") != citation.get("version_id"):
                errors.append("version_mismatch")
            if str(immutable.get("quote") or "") != str(citation.get("quote") or ""):
                errors.append("quote_mismatch")
            if str(immutable.get("content_hash") or "") != str(
                citation.get("content_hash") or ""
            ):
                errors.append("content_hash_mismatch")
            if any(immutable.get(field) != citation.get(field) for field in locator_fields):
                errors.append("locator_mismatch")
        unique = list(dict.fromkeys(errors))
        return not unique, unique

    return validate

def _digit_issues(result: Mapping[str, Any]) -> list[str]:
    answer = str(result.get("answer") or "")
    digits = set(re.findall(r"(?<![A-Za-z0-9_])-?\d+(?:\.\d+)?%?", answer))
    if not digits:
        return []
    verified_tool_facts = (
        result.get("verified_tool_facts") or []
        if not (result.get("tool_fact_errors") or [])
        else []
    )
    evidence = "\n".join(
        [
            str(result.get("question") or ""),
            *[str(item.get("quote") or "") for item in result.get("citations") or [] if isinstance(item, Mapping)],
            json.dumps(result.get("evidence") or [], ensure_ascii=False),
            json.dumps(verified_tool_facts, ensure_ascii=False),
        ]
    )
    supported = set(re.findall(r"(?<![A-Za-z0-9_])-?\d+(?:\.\d+)?%?", evidence))

    def add_verified_presentations(value: Any) -> None:
        if isinstance(value, Mapping):
            for nested in value.values():
                add_verified_presentations(nested)
        elif isinstance(value, list):
            for nested in value:
                add_verified_presentations(nested)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            numeric = float(value)
            supported.update({f"{numeric:.1f}", f"{numeric:.2f}"})
            if numeric.is_integer():
                supported.add(str(int(numeric)))

    add_verified_presentations(verified_tool_facts)
    return sorted(digits - supported)

def classify_failure(result: Mapping[str, Any]) -> dict[str, Any]:
    signals = {
        str(value).lower() for value in result.get("failed_checks") or []
    }
    for field in (
        "citation_errors", "tool_fact_errors", "retrieval_errors",
        "rerank_errors", "fixture_errors",
    ):
        signals.update(str(value).lower() for value in result.get(field) or [])
    if _digit_issues(result):
        signals.add("hallucinated_digits")
    if result.get("error") or result.get("exception"):
        signals.add("evaluator_exception")
    joined = " ".join(sorted(signals))
    rules = {
        "eval_fixture": ("fixture", "database", "embedding", "cache", "evaluator", "exception"),
        "retrieval": ("retrieval", "rag_expectation", "evidence_missing", "no_evidence"),
        "rerank": ("rerank", "top_k", "rank_"),
        "citation": ("citation", "quote_mismatch", "content_hash", "locator_mismatch"),
        "claim": (
            "required_facts", "forbidden_claims", "grounding",
            "hallucinated_digits", "source_type", "domain",
        ),
        "tool_routing": (
            "route", "required_tool", "tool_success",
            "tool_db_consistency", "tool_fact",
        ),
    }
    labels = {label for label, tokens in rules.items() if any(token in joined for token in tokens)}
    if result.get("expected_route") in {"rag", "tool+rag"} and result.get("actual_route") == "unavailable":
        labels.add("retrieval")
    if (
        result.get("expected_route") in {"refuse", "unavailable"}
        and any(token in joined for token in ("route", "security", "refusal", "answer_non_empty"))
    ):
        labels.add("refusal")
    if result.get("passed") is False and not labels:
        labels.add("eval_fixture")
    ordered = [label for label in FAILURE_CLASSES if label in labels]
    return {
        "question_id": str(result.get("question_id") or result.get("id") or ""),
        "primary": ordered[0] if ordered else None,
        "labels": ordered,
        "signals": sorted(signals),
    }

def classify_failures(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    items = [classify_failure(item) for item in results if item.get("passed") is not True]
    return {
        "failed_total": len(items),
        "label_counts": dict(sorted(Counter(label for item in items for label in item["labels"]).items())),
        "primary_counts": dict(sorted(Counter(item["primary"] for item in items if item["primary"]).items())),
        "items": items,
    }

def _rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def _fixture_manifest(run_id: str) -> dict[str, Any]:
    from backend.app.repositories.forecast_repository import (
        get_forecast_run,
        load_forecast_results,
    )

    fixture_run = get_forecast_run(run_id)
    fixture_rows = load_forecast_results(run_id)
    if (
        not fixture_run
        or str(fixture_run.get("status") or "").lower() != "success"
        or int(fixture_run.get("record_count") or 0) != 24
        or len(fixture_rows) != 24
    ):
        _fail("fixture_run_incomplete", run_id)
    return {
        "run_id": run_id,
        "record_count": len(fixture_rows),
        "model_version": fixture_run.get("model_version"),
        "feature_version": fixture_run.get("feature_version"),
        "schema_hash": fixture_run.get("schema_hash"),
        "result_hash": fixture_run.get("result_hash"),
    }

def _governed_item_check(
    golden: Mapping[str, Any], result: Mapping[str, Any] | None
) -> dict[str, Any]:
    qid = str(golden["question_id"])
    if result is None:
        return {
            "question_id": qid, "critical": bool(golden["critical"]),
            "passed": False, "declared_pass_consistent": False,
            "checks": {"result_present": False}, "digit_issues": [],
            "tool_fact_errors": [],
        }
    raw_checks = result.get("checks")
    raw = raw_checks if isinstance(raw_checks, Mapping) else {}
    answer = str(result.get("answer") or "")
    route = str(result.get("actual_route") or "")
    expected_route = str(golden["expected_route"])
    citations_value = result.get("citations")
    citations = citations_value if isinstance(citations_value, list) else []
    citation_errors = result.get("citation_errors")
    citation_errors = citation_errors if isinstance(citation_errors, list) else ["invalid"]
    citation_ok = (
        isinstance(citations_value, list)
        and not citation_errors
        and all(not _citation_shape_errors(value) for value in citations)
        and len(citations) >= golden["citation_expectation"]["minimum_count"]
        and raw.get("citations") is True
    )
    if not golden["required_citations"] and expected_route in {"refuse", "unavailable"}:
        citation_ok = citation_ok and not citations
    expected_ids = (
        set(golden["expected_document"]["document_ids"]),
        set(golden["expected_version"]["version_ids"]),
        set(golden["expected_chunks"]["chunk_ids"]),
    )
    for citation in citations:
        if not isinstance(citation, Mapping) or any(
            expected and citation.get(field) not in expected
            for expected, field in zip(expected_ids, ("document_id", "version_id", "chunk_id"))
        ):
            citation_ok = False

    claims = golden["claim_expectations"]["required_claims"]
    covered = sum(runner._fact_hit(str(claim["text"]), answer) for claim in claims)
    forbidden = any(
        runner._forbidden_asserted(str(claim), answer)
        for claim in golden["claim_expectations"]["forbidden_claims"]
    )
    grounding = _rate(covered, len(claims))
    grounding_ok = (
        grounding >= float(golden["claim_expectations"]["coverage_required"])
        and not forbidden
    )
    tool_names_value = result.get("tool_names")
    tool_names = set(str(value) for value in tool_names_value or [])
    tool = golden["tool_routing_expectation"]
    tool_errors = result.get("tool_fact_errors")
    tool_errors = tool_errors if isinstance(tool_errors, list) else ["invalid"]
    tool_ok = (
        isinstance(tool_names_value, list)
        and set(tool["required_tools"]) <= tool_names
        and (not tool["unexpected_business_tool_is_failure"] or tool_names <= set(tool["allowed_tools"]))
        and not tool_errors
        and all(raw.get(field) is True for field in (
            "required_tool", "tool_success", "tool_db_consistency"
        ))
    )
    refusal_required = golden["refusal_expectation"]["required"]
    refusal_ok = (
        route == expected_route if refusal_required
        else route not in {"refuse", "unavailable"}
    ) and (not citations if refusal_required else True)
    acl_probe = result.get("acl_probe")
    acl_ok = (
        isinstance(acl_probe, Mapping)
        and acl_probe.get("passed") is True
        and acl_probe.get("cross_tenant_evidence_count") == 0
        and raw.get("acl") is True
    )
    if golden["acl_expectation"]["primary_scenario"] == "unauthorized":
        acl_ok = acl_ok and route in {"refuse", "unavailable"} and not citations
    run_id = result.get("actual_run_id")
    run_ok = raw.get("run_id") is True and (
        not run_id if golden["required_run_id_behavior"] == "none" else bool(run_id)
    )
    digits = _digit_issues(result)
    checks = {
        "result_present": True,
        "result_schema": bool(raw) and all(isinstance(value, bool) for value in raw.values()),
        "result_contract": all(
            result.get(field) == golden[field]
            for field in ("question", "category", "critical", "expected_route", "expected_domain", "expected_source_type")
        ),
        "route": route == expected_route and raw.get("route") is True,
        "domain": raw.get("domain") is True and (
            result.get("actual_domain") == golden["expected_domain"]
            or (expected_route == "unavailable" and not result.get("actual_domain"))
        ),
        "source_type": raw.get("source_type") is True
        and result.get("actual_source_type") == golden["expected_source_type"],
        "run_id": run_ok,
        "claim_grounding": grounding_ok,
        "citation_integrity": citation_ok,
        "tool_routing": tool_ok,
        "refusal": refusal_ok,
        "acl": acl_ok,
        "no_hallucinated_digits": not digits,
        "evaluator_checks": bool(raw) and all(raw.values()),
        "answer_non_empty": bool(answer.strip()),
    }
    passed = all(checks.values())
    return {
        "question_id": qid,
        "critical": bool(golden["critical"]),
        "passed": passed,
        "declared_pass_consistent": result.get("passed") is passed,
        "checks": checks,
        "claim_coverage": grounding,
        "digit_issues": digits,
        "tool_fact_errors": tool_errors,
    }

def _recompute_governed(
    results: Sequence[Mapping[str, Any]], golden: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    ids = [
        str(item.get("question_id"))
        for item in results
        if isinstance(item, Mapping) and _text(item.get("question_id"))
    ]
    by_id: dict[str, Mapping[str, Any]] = {}
    for item in results:
        if isinstance(item, Mapping) and _text(item.get("question_id")):
            by_id.setdefault(str(item["question_id"]), item)
    expected_ids = {str(item["question_id"]) for item in golden}
    rows = [_governed_item_check(item, by_id.get(str(item["question_id"]))) for item in golden]
    critical = [row for row in rows if row["critical"]]
    routed = {
        route: [
            row for row, item in zip(rows, golden) if item["expected_route"] == route
        ]
        for route in ("refuse", "unavailable")
    }
    tools = [
        row for row, item in zip(rows, golden)
        if item["tool_routing_expectation"]["required_tools"]
    ]
    digits = {row["question_id"]: row["digit_issues"] for row in rows if row["digit_issues"]}
    passed = sum(row["passed"] for row in rows)
    summary = {
        "total": len(rows), "passed": passed, "failed": len(rows) - passed,
        "critical_total": len(critical),
        "critical_passed": sum(row["passed"] for row in critical),
        "citation_integrity": _rate(sum(row["checks"].get("citation_integrity") is True for row in rows), len(rows)),
        "grounding_rate": _rate(sum(row["checks"].get("claim_grounding") is True for row in rows), len(rows)),
        "refusal_accuracy": _rate(sum(row["checks"].get("refusal") is True for row in routed["refuse"]), len(routed["refuse"])),
        "unavailable_precision": _rate(sum(row["checks"].get("refusal") is True for row in routed["unavailable"]), len(routed["unavailable"])),
        "tool_success_rate": _rate(sum(row["checks"].get("tool_routing") is True for row in tools), len(tools)),
        "tool_fact_mismatch_count": sum(len(row["tool_fact_errors"]) for row in rows),
        "acl_accuracy": _rate(sum(row["checks"].get("acl") is True for row in rows), len(rows)),
        "hallucinated_digit_count": sum(len(value) for value in digits.values()),
        "hallucination_rate": _rate(sum(bool(row["digit_issues"]) for row in rows), len(rows)),
        "declared_pass_mismatch_count": sum(not row["declared_pass_consistent"] for row in rows),
        "result_record_count": len(results),
        "duplicate_result_question_ids": sorted(qid for qid, count in Counter(ids).items() if count > 1),
        "missing_result_question_ids": sorted(expected_ids - set(ids)),
        "unexpected_result_question_ids": sorted(set(ids) - expected_ids),
    }
    return {"summary": summary, "per_item": rows, "digit_issues": digits}

def formal_gate(
    report: Mapping[str, Any],
    golden_items: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if golden_items is not None:
        golden = validate_governed_ai_questions(list(golden_items))
        results = report.get("results")
        results = list(results) if isinstance(results, list) else []
        computed = _recompute_governed(results, golden)
        summary = computed["summary"]
        declared = report.get("summary")
        declared = declared if isinstance(declared, Mapping) else {}
        summary_fields = (
            "total", "passed", "failed", "critical_total", "critical_passed",
            "citation_integrity", "grounding_rate", "refusal_accuracy",
            "unavailable_precision", "tool_success_rate",
            "tool_fact_mismatch_count", "hallucination_rate", "acl_accuracy",
            "hallucinated_digit_count",
        )
        mismatches = {
            field: {"declared": declared.get(field), "recomputed": summary.get(field)}
            for field in summary_fields if declared.get(field) != summary.get(field)
        }
        review = golden_review_summary(golden)
        identity_ok = (
            summary["result_record_count"] == AI_GOLDEN_COUNT
            and not summary["duplicate_result_question_ids"]
            and not summary["missing_result_question_ids"]
            and not summary["unexpected_result_question_ids"]
        )
        checks = {
            "question_count_100": summary["total"] == AI_GOLDEN_COUNT,
            "result_identity_exact": identity_ok,
            "pass_count_gte_97": summary["passed"] >= 97,
            "critical_30_of_30": summary["critical_total"] == AI_CRITICAL_COUNT
            and summary["critical_passed"] == AI_CRITICAL_COUNT,
            "citation_integrity_100pct": summary["citation_integrity"] == 1.0,
            "grounding_gte_98pct": summary["grounding_rate"] >= 0.98,
            "hallucinated_digits_zero": summary["hallucinated_digit_count"] == 0,
            "hallucination_rate_zero": summary["hallucination_rate"] == 0.0,
            "refusal_accuracy_100pct": summary["refusal_accuracy"] == 1.0,
            "unavailable_precision_100pct": summary["unavailable_precision"] == 1.0,
            "tool_success_100pct": summary["tool_success_rate"] == 1.0,
            "tool_fact_mismatch_zero": summary["tool_fact_mismatch_count"] == 0,
            "unauthorized_acl_block_100pct": summary["acl_accuracy"] == 1.0,
            "declared_passes_consistent": summary["declared_pass_mismatch_count"] == 0,
            "summary_consistent": not mismatches,
            "golden_governance_approved": review["approval_complete"],
        }
        status = (
            "PENDING_HUMAN_APPROVAL" if not review["approval_complete"]
            else "PASS" if all(checks.values()) else "FAIL"
        )
        return {
            "status": status, "checks": checks,
            "passed": sum(checks.values()), "total": len(checks),
            "digit_issues": computed["digit_issues"],
            "recomputed_summary": summary, "summary_mismatches": mismatches,
            "per_item": computed["per_item"], "review_summary": review,
        }

    summary, results = report["summary"], report["results"]
    digit_issues = {
        str(item["question_id"]): _digit_issues(item)
        for item in results if _digit_issues(item)
    }
    checks = {
        "question_count_100": summary.get("total") == 100,
        "pass_count_gte_97": int(summary.get("passed") or 0) >= 97,
        "critical_30_of_30": summary.get("critical_total") == 30
        and summary.get("critical_passed") == 30,
        "citation_integrity_100pct": summary.get("citation_integrity") == 1.0,
        "grounding_gte_98pct": float(summary.get("grounding_rate") or 0.0) >= 0.98,
        "hallucinated_digits_zero": not digit_issues,
        "hallucination_rate_zero": summary.get("hallucination_rate") == 0.0,
        "refusal_accuracy_100pct": summary.get("refusal_accuracy") == 1.0,
        "unavailable_precision_100pct": summary.get("unavailable_precision") == 1.0,
        "tool_success_100pct": summary.get("tool_success_rate") == 1.0,
        "tool_fact_mismatch_zero": summary.get("tool_fact_mismatch_count") == 0,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks, "passed": sum(checks.values()), "total": len(checks),
        "digit_issues": digit_issues,
    }

def run(
    *,
    questions_path: Path,
    qdrant_env: Path,
    model_env: Path,
    corpus_path: Path,
    embedding_cache: Path,
    output_dir: Path,
    workers: int,
    fixture_database: str = "",
    fixture_run_id: str = "run_20260716T111446497802Z_8e6e75a131",
    rerank_batch_size: int = 8,
    rerank_max_length: int = 32,
    rerank_runtime: str = "torch_fp32",
) -> dict[str, Any]:
    questions = load_governed_ai_questions(questions_path)
    environment_before = dict(os.environ)
    ai_service = rag_service = None
    originals: dict[str, Any] = {}
    settings_clear = reset_db_cache = None
    try:
        values, qdrant = candidate._runtime_values(
            qdrant_env,
            model_env,
            rerank_batch_size=rerank_batch_size,
            rerank_max_length=rerank_max_length,
            rerank_runtime=rerank_runtime,
        )
        os.environ.update(values)
        if fixture_database:
            current_url = os.environ.get("DATABASE_URL", "").strip()
            if not current_url:
                _fail("fixture_database_url_unavailable")
            os.environ["DATABASE_URL"] = make_url(current_url).set(
                database=fixture_database
            ).render_as_string(hide_password=False)
            from backend.app.core.config import get_settings
            from backend.app.db.session import reset_db_cache as reset_cache

            settings_clear, reset_db_cache = get_settings.cache_clear, reset_cache
            settings_clear()
            reset_db_cache()

        fixture_manifest = _fixture_manifest(fixture_run_id)

        contract = runtime_contract_status()
        contract.require_available()
        transport = candidate.CandidateQdrantReadOnlyTransport(
            endpoint=contract.qdrant.endpoint,
            ca_path=Path(values["RAG_QDRANT_TLS_CA_PATH"]),
            read_only_key=qdrant["QDRANT_READ_ONLY_API_KEY"],
            bm25=candidate._load_bm25(corpus_path.parent / "bm25_profile.json"),
        )
        alias_before = transport.alias_target()
        if alias_before == candidate.COLLECTION:
            _fail("candidate_already_published")
        store = QdrantReadOnlyStore(transport, contract.release, contract.embedding)
        cache_questions = [
            {"id": item["question_id"], "question": item["question"]}
            for item in questions
        ]
        embeddings, _, _ = candidate._embeddings(
            cache_questions, contract, embedding_cache
        )
        if (
            not isinstance(embeddings, list)
            or len(embeddings) != len(questions)
            or any(not isinstance(value, Mapping) for value in embeddings)
        ):
            _fail("query_embedding_count_invalid")
        embedding_by_query = {
            item["question"]: value for item, value in zip(questions, embeddings)
        }

        corpus = _read_json_fail_closed(corpus_path)
        rows = (
            corpus.get("candidate_manifest", {}).get("chunks")
            if isinstance(corpus, Mapping) else None
        )
        if not isinstance(rows, list) or any(
            not isinstance(row, Mapping) or not _text(row.get("chunk_id")) for row in rows
        ):
            _fail("candidate_corpus_chunks_invalid")
        chunk_ids = [str(row["chunk_id"]) for row in rows]
        if len(chunk_ids) != len(set(chunk_ids)):
            _fail("candidate_corpus_duplicate_chunk_id")
        chunks = {str(row["chunk_id"]): row for row in rows}

        from backend.app.ai_assistant import service as imported_ai_service
        from backend.app.services import rag_service as imported_rag_service

        ai_service, rag_service = imported_ai_service, imported_rag_service
        originals = {
            "answer": ai_service.answer_chat_accurate,
            "embedding": rag_service.embed_text_with_metadata,
            "citation": runner._validate_citations,
            "evaluate": runner._evaluate_direct,
        }
        by_question = {item["question"]: item for item in questions}

        def context(item: Mapping[str, Any], scenario: str) -> RetrievalContext:
            key = "authorized_context" if scenario == "authorized" else "unauthorized_probe"
            value = item["acl_expectation"][key]
            return RetrievalContext(
                tenant_id=value["tenant_id"],
                user_id=f"rag-r1-ai-{scenario}",
                roles=tuple(value["roles"]),
                acl_fingerprint=f"rag-r1-ai-{scenario}",
                release_id=value["release_id"],
            )

        def identity(value: RetrievalContext, run_id: str = "latest") -> IdentityContext:
            return IdentityContext(
                tenant_id=value.tenant_id,
                workspace_id="rag-r1-ai-acceptance",
                user_id=value.user_id,
                role_ids=value.roles,
                agent_id="rag-r1-ai-acceptance",
                run_id=run_id,
            )

        def injected_answer(*args: Any, **kwargs: Any) -> dict[str, Any]:
            text = str(args[0] if args else kwargs.get("question") or "")
            item = by_question.get(text)
            if item is None:
                _fail("uncached_question_rejected")
            runtime_context = context(item, item["acl_expectation"]["primary_scenario"])
            kwargs["rag_context"] = runtime_context
            kwargs["identity"] = identity(runtime_context, str(kwargs.get("run_id") or "latest"))
            kwargs["enterprise_store"] = store
            return originals["answer"](*args, **kwargs)

        def cached_embedding(text: str) -> dict[str, Any]:
            value = embedding_by_query.get(text)
            if value is None:
                _fail("uncached_query_embedding_rejected")
            return dict(value)

        def evaluate_with_acl(item: dict[str, Any], fixture_run_id: str) -> dict[str, Any]:
            result = originals["evaluate"](item, fixture_run_id)
            try:
                unauthorized_context = context(item, "unauthorized")
                payload = originals["answer"](
                    item["question"],
                    session_id=f"rag_r1_acl_{item['question_id'].lower()}",
                    run_id=(
                        fixture_run_id
                        if item["required_run_id_behavior"] == "explicit" else "latest"
                    ),
                    model_provider="auto",
                    answer_style="professional_brief",
                    debug=True,
                    persist=False,
                    rag_context=unauthorized_context,
                    identity=identity(
                        unauthorized_context,
                        fixture_run_id if item["required_run_id_behavior"] == "explicit" else "latest",
                    ),
                    enterprise_store=store,
                )
                evidence_count = len(payload.get("citations") or []) + len(payload.get("evidence") or [])
                route = runner._direct_route(payload)
                probe = {
                    "passed": route in {"refuse", "unavailable"} and evidence_count == 0,
                    "actual_route": route,
                    "cross_tenant_evidence_count": evidence_count,
                }
            except Exception as exc:
                probe = {
                    "passed": False, "actual_route": "error",
                    "cross_tenant_evidence_count": -1,
                    "error_type": type(exc).__name__,
                }
            result["acl_probe"] = probe
            result["checks"]["acl"] = probe["passed"]
            result["passed"] = all(result["checks"].values())
            result["failed_checks"] = [
                name for name, passed in result["checks"].items() if not passed
            ]
            return result

        ai_service.answer_chat_accurate = injected_answer
        rag_service.embed_text_with_metadata = cached_embedding
        runner._validate_citations = immutable_citation_validator(chunks)
        runner._evaluate_direct = evaluate_with_acl
        output_dir.mkdir(parents=True, exist_ok=True)
        runner._run_phase5_b_direct(
            questions,
            output_dir,
            workers,
            fixture_run_id=fixture_run_id,
        )
        report = _read_json_fail_closed(output_dir / "ai_100_report.json")
        alias_after = transport.alias_target()
        strict_preview = _recompute_governed(report["results"], questions)["summary"]
        report["summary"].update({
            field: strict_preview[field]
            for field in ("acl_accuracy", "hallucinated_digit_count")
        })
        formal = formal_gate(report, questions)
        read_only_ok = (
            alias_before == alias_after
            and alias_after != candidate.COLLECTION
            and transport.write_count == 0
        )
        formal["checks"]["candidate_runtime_read_only"] = read_only_ok
        if not read_only_ok:
            formal["status"] = "FAIL"
        formal["passed"] = sum(formal["checks"].values())
        formal["total"] = len(formal["checks"])
        formal_report = {
            "schema_version": "rag-r1-candidate-ai-acceptance/v1",
            "scope": "prepublication_candidate_read_only",
            "question_bank": {
                "path": str(questions_path),
                "count": len(questions),
                "canonical_sha256": question_bank_sha256(questions),
                "file_sha256": hashlib.sha256(questions_path.read_bytes()).hexdigest(),
            },
            "review_summary": golden_review_summary(questions),
            "formal_gate": formal,
            "summary": report["summary"],
            "failure_classification": classify_failures(report["results"]),
            "results": report["results"],
            "runtime": {
                "collection": candidate.COLLECTION,
                "alias_before": alias_before,
                "alias_after": alias_after,
                "write_count": transport.write_count,
                "access_mode": contract.qdrant.access_mode,
                "fixture_run_id": fixture_run_id,
                "fixture_manifest": fixture_manifest,
                "retrieval_profile": {
                    "rerank_batch_size": rerank_batch_size,
                    "rerank_max_length": rerank_max_length,
                    "rerank_runtime": rerank_runtime,
                },
                "admin_key_loaded_into_runtime": False,
                "secret_values_emitted": False,
            },
        }
        (output_dir / "rag_r1_candidate_ai_100_formal.json").write_text(
            json.dumps(formal_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return formal_report
    finally:
        if originals:
            ai_service.answer_chat_accurate = originals["answer"]
            rag_service.embed_text_with_metadata = originals["embedding"]
            runner._validate_citations = originals["citation"]
            runner._evaluate_direct = originals["evaluate"]
        for key in set(os.environ) - set(environment_before):
            del os.environ[key]
        os.environ.update(environment_before)
        if settings_clear is not None:
            settings_clear()
        if reset_db_cache is not None:
            reset_db_cache()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run AI 100 against unpublished candidate")
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--qdrant-env", type=Path, required=True)
    parser.add_argument("--model-env", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--embedding-cache", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--fixture-database", default="")
    parser.add_argument("--fixture-run-id", default="run_20260716T111446497802Z_8e6e75a131")
    parser.add_argument("--rerank-batch-size", type=int, default=8)
    parser.add_argument("--rerank-max-length", type=int, default=32)
    parser.add_argument("--rerank-runtime", default="torch_fp32")
    args = parser.parse_args(argv)
    try:
        report = run(
            questions_path=args.questions.resolve(),
            qdrant_env=args.qdrant_env.resolve(),
            model_env=args.model_env.resolve(),
            corpus_path=args.corpus.resolve(),
            embedding_cache=args.embedding_cache.resolve(),
            output_dir=args.output_dir.resolve(),
            workers=args.workers,
            fixture_database=args.fixture_database.strip(),
            fixture_run_id=args.fixture_run_id.strip(),
            rerank_batch_size=args.rerank_batch_size,
            rerank_max_length=args.rerank_max_length,
            rerank_runtime=args.rerank_runtime.strip(),
        )
    except Exception as exc:
        print(f"RAG-R1 candidate AI acceptance FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["formal_gate"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
