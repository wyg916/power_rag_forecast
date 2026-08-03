from __future__ import annotations

import copy
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import rag_r1_candidate_ai_acceptance as module


ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "tests" / "evaluation" / "ai_assistant_eval_questions.json"

@pytest.fixture()
def golden() -> list[dict]:
    return module.load_governed_ai_questions(QUESTIONS)

def test_governed_ai_100_loads_directly(golden) -> None:
    assert (len(golden), len({x["id"] for x in golden}), len({x["question_id"] for x in golden}), sum(x["critical"] for x in golden)) == (100, 100, 100, 30)
    assert module.golden_review_summary(golden)["pending_human_approval"] == 100
    source = inspect.getsource(module.run)
    assert "_expand_phase5_b_questions" not in source
    assert all(marker in source for marker in ("finally:", "candidate_corpus_duplicate_chunk_id", "query_embedding_count_invalid"))

@pytest.mark.parametrize(
    "mutation",
    ("duplicate_id", "duplicate_question", "critical_count", "missing_field", "approval", "revision"),
)
def test_governed_contract_mutations_fail_closed(golden, mutation) -> None:
    value = copy.deepcopy(golden)
    if mutation == "duplicate_id":
        value[1]["id"] = value[0]["id"]
    elif mutation == "duplicate_question":
        value[1]["question"] = value[0]["question"]
    elif mutation == "critical_count":
        next(item for item in value if item["critical"])["critical"] = False
    elif mutation == "missing_field":
        value[0].pop("acl_expectation")
    elif mutation == "approval":
        value[0]["approval_status"] = "approved"
    else:
        value[0]["label_provenance"]["source_revision"] = ""
    with pytest.raises(module.CandidateAiAcceptanceError):
        module.validate_governed_ai_questions(value)

def test_duplicate_json_keys_fail_closed(tmp_path, golden) -> None:
    text = json.dumps(golden, ensure_ascii=False)
    needle = '"schema_version": "rag-r1-ai-golden-item/v1"'
    path = tmp_path / "duplicate.json"
    path.write_text(text.replace(needle, f"{needle}, {needle}", 1), encoding="utf-8")
    with pytest.raises(module.CandidateAiAcceptanceError, match="duplicate_json_key"):
        module.load_governed_ai_questions(path)

def _citation() -> tuple[dict, dict]:
    citation = {
        "document_id": "doc", "chunk_id": "chunk", "version_id": "version",
        "page": 1, "section_path": ["s"], "char_start": 0, "char_end": 2,
        "bbox": None, "asset_id": None, "quote": "正文", "content_hash": "hash",
    }
    chunk = {
        "document_id": "doc", "version_id": "version",
        "citation": {key: value for key, value in citation.items() if key not in {"document_id", "chunk_id"}},
    }
    return citation, chunk

def test_immutable_citations_are_strict_but_empty_is_caller_controlled() -> None:
    citation, chunk = _citation()
    validate = module.immutable_citation_validator({"chunk": chunk})
    assert (validate([]), validate([citation]), validate([citation, citation])[1]) == ((True, []), (True, []), ["duplicate_citation"])
    assert validate([{**citation, "char_start": True}])[1] == ["citation_offsets_invalid"]
    assert validate([{**citation, "page": 2}])[1] == ["locator_mismatch"]
    broken = dict(citation)
    broken.pop("quote")
    assert validate([broken])[1] == ["citation_fields_invalid"]

def test_business_tool_does_not_exempt_unproved_digits() -> None:
    result = {
        "question_id": "Q", "question": "价格是多少", "answer": "价格是123.45",
        "citations": [], "evidence": [], "business_tool_names": ["get_forecast_metrics"],
        "tool_fact_errors": [],
    }
    assert module._digit_issues(result) == ["123.45"]

def test_failure_classifier_supports_all_labels_and_primary() -> None:
    result = {
        "question_id": "Q", "passed": False, "expected_route": "refuse",
        "failed_checks": ["rag_expectation", "top_k_rank", "citations", "required_facts", "route", "security"],
        "fixture_errors": ["database_unavailable"],
    }
    classified = module.classify_failure(result)
    assert (classified["primary"], set(classified["labels"])) == ("eval_fixture", set(module.FAILURE_CLASSES))

def _passing_result(item: dict) -> dict:
    answer = " ".join(claim["text"] for claim in item["claim_expectations"]["required_claims"])
    tools = list(item["tool_routing_expectation"]["required_tools"])
    checks = {name: True for name in (
        "route", "domain", "source_type", "run_id", "required_facts", "required_tool",
        "tool_success", "tool_db_consistency", "citations", "forbidden_claims",
        "security", "answer_non_empty", "acl",
    )}
    return {
        **item, "actual_route": item["expected_route"], "actual_domain": item["expected_domain"],
        "actual_source_type": item["expected_source_type"],
        "actual_run_id": None if item["required_run_id_behavior"] == "none" else "fixture",
        "answer": answer, "citations": ([{**_citation()[0], "quote": answer}] if item["required_citations"] else []),
        "citation_errors": [], "evidence": [answer], "tool_names": tools,
        "business_tool_names": tools, "tool_fact_errors": [], "checks": checks,
        "acl_probe": {"passed": True, "cross_tenant_evidence_count": 0}, "passed": True,
    }

def test_formal_gate_recomputes_and_never_passes_pending(golden) -> None:
    results = [_passing_result(item) for item in golden]
    summary = module._recompute_governed(results, golden)["summary"]
    gate = module.formal_gate({"summary": summary, "results": results}, golden)
    assert (gate["status"], gate["checks"]["summary_consistent"], gate["checks"]["golden_governance_approved"]) == ("PENDING_HUMAN_APPROVAL", True, False)
    tampered = dict(summary, passed=99)
    assert module.formal_gate({"summary": tampered, "results": results}, golden)["checks"]["summary_consistent"] is False

def test_run_restores_environment_and_monkeypatches_after_failure(monkeypatch, tmp_path) -> None:
    from backend.app.ai_assistant import service as ai_service
    from backend.app.services import rag_service
    originals = (
        ai_service.answer_chat_accurate, rag_service.embed_text_with_metadata,
        module.runner._validate_citations, module.runner._evaluate_direct,
    )
    environment = dict(os.environ)
    contract = SimpleNamespace(
        qdrant=SimpleNamespace(endpoint="https://qdrant.invalid", access_mode="read_only"),
        release=object(), embedding=object(), require_available=lambda: None,
    )
    transport = SimpleNamespace(alias_target=lambda: None, write_count=0)
    monkeypatch.setattr(module.candidate, "_runtime_values", lambda *_: ({"RAG_QDRANT_TLS_CA_PATH": "ca", "RAG_TEST_TEMP": "changed"}, {"QDRANT_READ_ONLY_API_KEY": "reader"}))
    monkeypatch.setattr(module, "runtime_contract_status", lambda: contract)
    monkeypatch.setattr(module.candidate, "CandidateQdrantReadOnlyTransport", lambda **_: transport)
    monkeypatch.setattr(module.candidate, "_load_bm25", lambda _: {})
    monkeypatch.setattr(module, "QdrantReadOnlyStore", lambda *_: object())
    monkeypatch.setattr(module.candidate, "_embeddings", lambda questions, *_: ([{} for _ in questions], 0, True))
    corpus = tmp_path / "corpus.json"
    corpus.write_text('{"candidate_manifest":{"chunks":[]}}', encoding="utf-8")
    def fail_after_patch(*_):
        assert ai_service.answer_chat_accurate is not originals[0]
        assert rag_service.embed_text_with_metadata is not originals[1]
        raise RuntimeError("stop_after_patch")
    monkeypatch.setattr(module.runner, "_run_phase5_b_direct", fail_after_patch)
    with pytest.raises(RuntimeError, match="stop_after_patch"):
        module.run(
            questions_path=QUESTIONS, qdrant_env=tmp_path / "q.env",
            model_env=tmp_path / "m.env", corpus_path=corpus,
            embedding_cache=tmp_path / "emb.json", output_dir=tmp_path / "out", workers=1,
        )
    assert (ai_service.answer_chat_accurate, rag_service.embed_text_with_metadata) == originals[:2]
    assert (module.runner._validate_citations, module.runner._evaluate_direct) == originals[2:]
    assert dict(os.environ) == environment
