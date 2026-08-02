from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.qdrant_vector_store import QdrantReadOnlyStore
from backend.app.services.rag_runtime_contract import RetrievalContext, runtime_contract_status
from scripts import rag_r1_candidate_acceptance as candidate
from tests.evaluation import run_ai_assistant_eval as runner


class CandidateAiAcceptanceError(RuntimeError):
    pass


def immutable_citation_validator(
    chunks: Mapping[str, Mapping[str, Any]],
):
    def validate(
        citations: list[dict[str, Any]],
    ) -> tuple[bool, list[str]]:
        errors: list[str] = []
        locator_fields = (
            "page",
            "section_path",
            "char_start",
            "char_end",
            "bbox",
            "asset_id",
        )
        for citation in citations:
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
    if result.get("business_tool_names") and not result.get("tool_fact_errors"):
        return []
    evidence = "\n".join(
        [
            str(result.get("question") or ""),
            *[str(item.get("quote") or "") for item in result.get("citations") or []],
            json.dumps(result.get("evidence") or [], ensure_ascii=False),
        ]
    )
    return sorted(value for value in digits if value not in evidence)


def formal_gate(report: Mapping[str, Any]) -> dict[str, Any]:
    summary = report["summary"]
    results = report["results"]
    digit_issues = {
        str(item["question_id"]): _digit_issues(item)
        for item in results
        if _digit_issues(item)
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
        "checks": checks,
        "passed": sum(bool(value) for value in checks.values()),
        "total": len(checks),
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
) -> dict[str, Any]:
    legacy = json.loads(questions_path.read_text(encoding="utf-8"))
    questions = runner._expand_phase5_b_questions(legacy)
    values, qdrant = candidate._runtime_values(qdrant_env, model_env)
    os.environ.update(values)
    if fixture_database:
        current_url = os.environ.get("DATABASE_URL", "").strip()
        if not current_url:
            raise CandidateAiAcceptanceError("fixture_database_url_unavailable")
        os.environ["DATABASE_URL"] = make_url(current_url).set(
            database=fixture_database
        ).render_as_string(hide_password=False)
        from backend.app.core.config import get_settings
        from backend.app.db.session import reset_db_cache

        get_settings.cache_clear()
        reset_db_cache()
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
        raise CandidateAiAcceptanceError("candidate_already_published")
    context = RetrievalContext(
        tenant_id=candidate.TENANT_ID,
        user_id="rag-r1-ai-acceptance",
        roles=("viewer",),
        acl_fingerprint="rag-r1-ai-acceptance",
        release_id=candidate.RELEASE_ID,
    )
    store = QdrantReadOnlyStore(transport, contract.release, contract.embedding)
    cache_questions = [
        {"id": item["question_id"], "question": item["question"]}
        for item in questions
    ]
    embeddings, _, _ = candidate._embeddings(
        cache_questions, contract, embedding_cache
    )
    embedding_by_query = {
        item["question"]: embedding for item, embedding in zip(questions, embeddings)
    }

    from backend.app.ai_assistant import service as ai_service
    from backend.app.services import rag_service

    original_answer = ai_service.answer_chat_accurate
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    chunks = {
        str(item["chunk_id"]): item
        for item in corpus["candidate_manifest"]["chunks"]
    }

    def injected_answer(*args: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs["rag_context"] = context
        kwargs["enterprise_store"] = store
        return original_answer(*args, **kwargs)

    def cached_embedding(text: str) -> dict[str, Any]:
        value = embedding_by_query.get(text)
        if value is None:
            raise CandidateAiAcceptanceError("uncached_query_embedding_rejected")
        return value

    ai_service.answer_chat_accurate = injected_answer
    rag_service.embed_text_with_metadata = cached_embedding
    runner._validate_citations = immutable_citation_validator(chunks)
    output_dir.mkdir(parents=True, exist_ok=True)
    runner._run_phase5_b_direct(questions, output_dir, workers)
    report_path = output_dir / "ai_100_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    alias_after = transport.alias_target()
    formal = formal_gate(report)
    formal_report = {
        "schema_version": "rag-r1-candidate-ai-acceptance/v1",
        "scope": "prepublication_candidate_read_only",
        "formal_gate": formal,
        "summary": report["summary"],
        "runtime": {
            "collection": candidate.COLLECTION,
            "alias_before": alias_before,
            "alias_after": alias_after,
            "write_count": transport.write_count,
            "access_mode": contract.qdrant.access_mode,
            "admin_key_loaded_into_runtime": False,
            "secret_values_emitted": False,
        },
    }
    if alias_before != alias_after or alias_after == candidate.COLLECTION:
        formal_report["formal_gate"]["status"] = "FAIL"
        formal_report["formal_gate"]["checks"]["candidate_alias_unchanged"] = False
    else:
        formal_report["formal_gate"]["checks"]["candidate_alias_unchanged"] = True
    (output_dir / "rag_r1_candidate_ai_100_formal.json").write_text(
        json.dumps(formal_report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return formal_report


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
        )
    except Exception as exc:
        print(f"RAG-R1 candidate AI acceptance FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["formal_gate"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
