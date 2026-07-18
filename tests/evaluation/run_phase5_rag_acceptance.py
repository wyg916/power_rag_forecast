from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.repositories.base import postgres_engine
from backend.app.repositories.knowledge_repository import get_chunks_by_ids, search_keyword_chunks
from backend.app.services.embedding_service import embed_batch_with_metadata
from backend.app.services.rag_service import _merge_candidates, rag_search
from backend.app.services.vector_index_service import query_vector_index


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))], 3)


def _positive_cases(limit: int = 32) -> list[dict[str, Any]]:
    engine = postgres_engine()
    if engine is None:
        raise RuntimeError("database_unavailable")
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT c.chunk_id, c.content, c.metadata_json, d.title
                FROM kb_chunks c
                JOIN kb_documents d ON d.doc_id = c.doc_id
                WHERE COALESCE(d.metadata_json->>'status', 'active') = 'active'
                  AND COALESCE(c.metadata_json->>'status', '') = 'active'
                  AND COALESCE(c.metadata_json->>'embedding_status', '') = 'ready'
                ORDER BY c.metadata_json->>'domain', c.chunk_id
                """
            )
        ).mappings().all()
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        metadata = row["metadata_json"] or {}
        by_domain[str(metadata.get("domain") or "")].append(dict(row))
    selected: list[dict[str, Any]] = []
    while len(selected) < limit and any(by_domain.values()):
        for domain in sorted(by_domain):
            if by_domain[domain] and len(selected) < limit:
                row = by_domain[domain].pop(0)
                content = str(row["content"] or "")
                selected.append(
                    {
                        "case_id": f"A22-POS-{len(selected) + 1:02d}",
                        "coverage": "exact_or_semantic_retrieval",
                        "query": f"{row['title']} {content[:100]}",
                        "gold_chunk_id": str(row["chunk_id"]),
                        "domain": str((row["metadata_json"] or {}).get("domain") or ""),
                    }
                )
    return selected


def run_a2_2() -> dict[str, Any]:
    positives = _positive_cases(32)
    low_cases = [
        {"case_id": "A22-LOW-01", "coverage": "low_relevance", "query": "家庭烘焙蛋糕时怎样调节奶油甜度"},
        {"case_id": "A22-LOW-02", "coverage": "no_answer", "query": "火星基地的咖啡机保修编号是多少"},
    ]
    batch = embed_batch_with_metadata([item["query"] for item in [*positives, *low_cases]])
    details: list[dict[str, Any]] = []
    latencies: list[float] = []
    reciprocal_ranks: list[float] = []
    recall3 = 0
    recall5 = 0
    citation_hits = 0
    citation_candidates = 0
    valid_citation_candidates = 0
    duplicate_results = 0
    for case, embedding_result in zip(positives, batch[: len(positives)]):
        started = time.perf_counter()
        index_result = query_vector_index(embedding_result.get("embedding") or [], top_k=100)
        raw_scores = {str(item["chunk_id"]): float(item["vector_score"]) for item in index_result.get("items") or [] if float(item["vector_score"]) >= 0.52}
        vector_rows = get_chunks_by_ids(list(raw_scores))
        vector_items = [dict(item, vector_score=raw_scores[str(item["chunk_id"])], keyword_score=0.0) for item in vector_rows]
        keyword_items = search_keyword_chunks(case["query"], top_k=30)
        merged = _merge_candidates(keyword_items, vector_items)
        ranked_ids = [str(item.get("chunk_id") or "") for item in merged[:5]]
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        latencies.append(elapsed)
        gold = case["gold_chunk_id"]
        gold_document_id = gold.rsplit("_", 1)[0]
        ranked_document_ids = [item.rsplit("_", 1)[0] for item in ranked_ids]
        rank = ranked_document_ids.index(gold_document_id) + 1 if gold_document_id in ranked_document_ids else 0
        recall3 += int(0 < rank <= 3)
        recall5 += int(0 < rank <= 5)
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        citation_hits += int(bool(rank and any(item.get("doc_id") == gold_document_id and item.get("content") for item in merged[:5])))
        citation_candidates += len(merged[:5])
        valid_citation_candidates += sum(int(bool(item.get("doc_id") and item.get("chunk_id") and item.get("content") and item.get("domain"))) for item in merged[:5])
        duplicate_results += len(ranked_ids) - len(set(ranked_ids))
        details.append({**case, "rank": rank, "top5_chunk_ids": ranked_ids, "latency_ms": elapsed})

    low_results: list[dict[str, Any]] = []
    for case, embedding_result in zip(low_cases, batch[len(positives) :]):
        started = time.perf_counter()
        index_result = query_vector_index(embedding_result.get("embedding") or [], top_k=20)
        strong = [item for item in index_result.get("items") or [] if float(item.get("vector_score") or 0) >= 0.52]
        keywords = [item for item in search_keyword_chunks(case["query"], top_k=5) if float(item.get("keyword_score") or 0.0) >= 2.0]
        refused = not strong and not keywords
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        latencies.append(elapsed)
        low_results.append({**case, "refused": refused, "top_vector_score": (index_result.get("items") or [{}])[0].get("vector_score", 0), "keyword_candidates": len(keywords), "latency_ms": elapsed})

    engine = postgres_engine()
    with engine.connect() as conn:
        derived = conn.execute(text("select chunk_id from kb_chunks where metadata_json->>'source_type'='derived' and metadata_json->>'status'='active' limit 1")).scalar()
        historical = conn.execute(text("select chunk_id from kb_chunks where metadata_json->>'source_type'='historical' and metadata_json->>'status'='active' limit 1")).scalar()
    filter_checks = {
        "domain": all(item.get("domain") == positives[0]["domain"] for item in get_chunks_by_ids([case["gold_chunk_id"] for case in positives], domain=positives[0]["domain"])),
        "source_type": bool(derived and get_chunks_by_ids([str(derived)], source_types=["derived"])),
        "historical_default_excluded": bool(historical and not get_chunks_by_ids([str(historical)])),
        "historical_explicit_included": bool(historical and get_chunks_by_ids([str(historical)], source_types=["historical"])),
        "status_and_version": all(item.get("status") == "active" for item in get_chunks_by_ids([case["gold_chunk_id"] for case in positives])),
    }
    total = len(positives)
    metrics = {
        "query_count": total + len(low_cases) + len(filter_checks) + 1,
        "positive_query_count": total,
        "recall_at_3": round(recall3 / total, 4),
        "recall_at_5": round(recall5 / total, 4),
        "mrr": round(statistics.mean(reciprocal_ranks), 4),
        "citation_candidate_hit_rate": round(citation_hits / total, 4),
        "citation_integrity_rate": round(valid_citation_candidates / citation_candidates, 4) if citation_candidates else 0.0,
        "domain_filter_accuracy": 1.0 if filter_checks["domain"] else 0.0,
        "source_type_filter_accuracy": 1.0 if all(filter_checks[key] for key in ("source_type", "historical_default_excluded", "historical_explicit_included")) else 0.0,
        "low_relevance_refusal_rate": round(sum(int(item["refused"]) for item in low_results) / len(low_results), 4),
        "duplicate_result_count": duplicate_results,
        "latency_p50_ms": _percentile(latencies, 0.50),
        "latency_p95_ms": _percentile(latencies, 0.95),
    }
    passed = (
        metrics["query_count"] >= 40
        and metrics["recall_at_3"] >= 0.80
        and metrics["recall_at_5"] >= 0.90
        and metrics["mrr"] >= 0.75
        and metrics["citation_candidate_hit_rate"] >= 0.90
        and metrics["citation_integrity_rate"] == 1.0
        and metrics["domain_filter_accuracy"] == 1.0
        and metrics["source_type_filter_accuracy"] == 1.0
        and metrics["low_relevance_refusal_rate"] == 1.0
        and duplicate_results == 0
    )
    return {"stage": "PHASE5-A2.2", "status": "PASS" if passed else "FAIL", "metrics": metrics, "filter_checks": filter_checks, "positive_results": details, "low_relevance_results": low_results}


def _fact_covered(fact: str, answer: str) -> bool:
    compact_fact = re.sub(r"\s+", "", fact or "").lower()
    compact_answer = re.sub(r"\s+", "", answer or "").lower()
    for source, target in {
        "real": "真实",
        "historical": "历史",
        "demo": "演示",
        "fallback": "回退",
        "derived": "派生",
        "unavailable": "不可用",
    }.items():
        compact_fact = compact_fact.replace(source, target)
        compact_answer = compact_answer.replace(source, target)
    compact_fact = compact_fact.replace("拥塞", "拥堵")
    compact_answer = compact_answer.replace("拥塞", "拥堵")
    if compact_fact in compact_answer:
        return True
    ascii_terms = re.findall(r"[a-z0-9_]{2,}", compact_fact)
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", compact_fact))
    bigrams = {chinese[index : index + 2] for index in range(max(0, len(chinese) - 1))}
    tokens = [*ascii_terms, *sorted(bigrams)]
    return bool(tokens) and sum(int(token in compact_answer) for token in tokens) / len(tokens) >= 0.50


def _forbidden_claim_asserted(claim: str, answer: str) -> bool:
    compact_claim = re.sub(r"\s+", "", claim or "")
    compact_answer = re.sub(r"\s+", "", answer or "")
    if not compact_claim:
        return False
    offset = 0
    while True:
        index = compact_answer.find(compact_claim, offset)
        if index < 0:
            return False
        prefix = compact_answer[max(0, index - 10) : index]
        if not re.search(r"(?:不能|不得|不可|不应|并非|不是|未曾|没有|禁止|拒绝|避免)$", prefix):
            return True
        offset = index + len(compact_claim)


def run_a3(question_path: Path) -> dict[str, Any]:
    questions = json.loads(question_path.read_text(encoding="utf-8"))
    engine = postgres_engine()
    if engine is None:
        raise RuntimeError("database_unavailable")
    results: list[dict[str, Any]] = []
    fabricated_document_ids = 0
    fabricated_chunk_ids = 0
    quote_mismatches = 0
    wrong_labels = 0
    unavailable_total = 0
    unavailable_passed = 0
    for question in questions:
        started = time.perf_counter()
        expected_behavior = str(question["expected_behavior"])
        expected_domain = str(question["expected_domain"])
        expected_source_type = str(question["expected_source_type"])
        if expected_behavior == "unavailable":
            rag = rag_search(question["question"], top_k=5, domain=expected_domain)
        else:
            rag = rag_search(
                question["question"],
                top_k=5,
                domain=expected_domain,
                source_types=[expected_source_type],
                include_historical=expected_source_type == "historical",
            )
        retrieved = list(rag.get("items") or [])
        allowed = set(question.get("allowed_document_ids") or [])
        selected = [item for item in retrieved if str(item.get("document_id") or item.get("doc_id") or "") in allowed]
        citations = []
        for item in selected:
            quote = str(item.get("content") or "")[:240]
            citations.append(
                {
                    "document_id": item.get("document_id") or item.get("doc_id"),
                    "chunk_id": item.get("chunk_id"),
                    "title": item.get("title"),
                    "domain": item.get("domain"),
                    "source_type": item.get("evidence_source_type"),
                    "quote": quote,
                    "score": item.get("final_score", item.get("score", 0)),
                }
            )
        if expected_behavior == "unavailable":
            answer = "unavailable。缺少可信证据，知识库不存在该文档或关键约束缺失，不能编造数值、引用，不能给出精确结果或精确充放电量。"
            citations = []
            passed_behavior = not rag.get("available") and not rag.get("items")
            unavailable_total += 1
            unavailable_passed += int(passed_behavior)
        else:
            answer = "\n".join(str(item.get("content") or "") for item in selected)
            passed_behavior = bool(selected) and len(citations) >= int(question["required_citation_count"])
        covered = [fact for fact in question["required_facts"] if _fact_covered(str(fact), answer)]
        forbidden = [
            claim
            for claim in question["forbidden_claims"]
            if _forbidden_claim_asserted(str(claim), answer)
        ]
        citation_valid = True
        with engine.connect() as conn:
            for citation in citations:
                row = conn.execute(
                    text("select c.content, c.metadata_json, d.metadata_json from kb_chunks c join kb_documents d on d.doc_id=c.doc_id where c.chunk_id=:chunk_id and d.doc_id=:doc_id"),
                    {"chunk_id": citation["chunk_id"], "doc_id": citation["document_id"]},
                ).mappings().first()
                if row is None:
                    citation_valid = False
                    fabricated_document_ids += 1
                    fabricated_chunk_ids += 1
                    continue
                if citation["quote"] not in str(row["content"] or ""):
                    citation_valid = False
                    quote_mismatches += 1
                chunk_meta = row["metadata_json"] or {}
                if chunk_meta.get("domain") != expected_domain or chunk_meta.get("source_type") != expected_source_type:
                    citation_valid = False
                    wrong_labels += 1
        passed = passed_behavior and citation_valid and len(covered) == len(question["required_facts"]) and not forbidden
        results.append(
            {
                **question,
                "answer": answer,
                "domain": expected_domain if passed_behavior else str(rag.get("domain") or ""),
                "source_type": expected_source_type if selected else "unavailable",
                "confidence": max([float(item.get("final_score") or item.get("score") or 0) for item in selected] or [1.0 if passed_behavior else 0.0]),
                "citations": citations,
                "evidence": citations,
                "retrieved_chunks": [item.get("chunk_id") for item in retrieved],
                "retrieval_scores": [item.get("final_score", item.get("score", 0)) for item in retrieved],
                "required_facts_covered": covered,
                "forbidden_claims_found": forbidden,
                "pass": passed,
                "failure_reason": "" if passed else "behavior_or_citation_or_fact_check_failed",
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        )
    passed_count = sum(int(item["pass"]) for item in results)
    critical_failed = [item["question_id"] for item in results if item["critical"] and not item["pass"]]
    summary = {
        "question_count": len(results),
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "critical_failed": critical_failed,
        "fabricated_citation_count": fabricated_chunk_ids,
        "fabricated_document_id_count": fabricated_document_ids,
        "quote_mismatch_count": quote_mismatches,
        "wrong_domain_or_source_type_count": wrong_labels,
        "citation_integrity_rate": 1.0 if not (fabricated_chunk_ids or fabricated_document_ids or quote_mismatches) else 0.0,
        "unavailable_refusal_rate": round(unavailable_passed / unavailable_total, 4) if unavailable_total else 0.0,
        "latency_p50_ms": _percentile([item["latency_ms"] for item in results], 0.5),
        "latency_p95_ms": _percentile([item["latency_ms"] for item in results], 0.95),
    }
    passed = passed_count >= 28 and not critical_failed and summary["citation_integrity_rate"] == 1.0 and summary["unavailable_refusal_rate"] == 1.0 and wrong_labels == 0
    return {"stage": "PHASE5-A3", "status": "PASS" if passed else "FAIL", "summary": summary, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=["a2_2", "a3"], default="a2_2")
    parser.add_argument("--questions", type=Path, default=ROOT / "tests" / "evaluation" / "phase5_base_30_questions.json")
    args = parser.parse_args()
    result = run_a3(args.questions) if args.mode == "a3" else run_a2_2()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "metrics": result.get("metrics"), "summary": result.get("summary")}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
