from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from scripts import rag_r1_candidate_acceptance as module


ROOT = Path(__file__).resolve().parents[1]


def test_candidate_transport_is_exact_collection_read_only() -> None:
    source = inspect.getsource(module.CandidateQdrantReadOnlyTransport)
    assert 'method not in {"GET", "POST"}' in source
    assert 'collection != COLLECTION' in source
    assert "quote(COLLECTION)" in source
    assert "QDRANT_ADMIN_API_KEY" not in source
    assert "PUT" not in source
    assert "DELETE" not in source

    transport = object.__new__(module.CandidateQdrantReadOnlyTransport)
    with pytest.raises(module.CandidateAcceptanceError, match="collection_rejected"):
        transport.query(collection="rag_chunks_current", request={"mode": "dense"})


def test_metric_math_and_formal_thresholds() -> None:
    results = []
    for index in range(50):
        rank = 1 if index < 45 else (4 if index < 49 else 0)
        results.append(
            {
                "critical": index < 15,
                "hit_at_3": bool(rank and rank <= 3),
                "hit_at_5": bool(rank and rank <= 5),
                "reciprocal_rank": 1.0 / rank if rank else 0.0,
                "citation_integrity": index != 49,
                "latency_ms": float(index + 1),
            }
        )

    metrics = module.calculate_metrics(results)
    gate = module._gate(
        metrics,
        {
            "access_mode": "read_only",
            "write_count": 0,
            "methods_used": ["GET", "POST"],
            "alias_before": None,
            "alias_after": None,
        },
    )

    assert metrics["question_count"] == 50
    assert metrics["recall_at_3"] == 0.9
    assert metrics["recall_at_5"] == 0.98
    assert metrics["critical_recall_at_5"] == 1.0
    assert metrics["citation_integrity"] == 0.98
    assert gate["status"] == "FAIL"
    assert gate["checks"]["citation_integrity_100pct"] is False


def test_golden_set_is_fixed_50_and_does_not_claim_human_verification() -> None:
    path = ROOT / "tests" / "evaluation" / "rag_r1_retrieval_golden_50.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    items = value["items"]

    assert value["schema_version"] == "rag-r1-retrieval-golden/v1"
    assert value["release_id"] == "RAG-R1"
    assert value["collection"] == "rag_chunks_RAG-R1"
    assert value["human_verified"] is False
    assert len(items) == 50
    assert len({item["id"] for item in items}) == 50
    assert sum(item["critical"] for item in items) >= 10
    assert all(item["expected_document_ids"] for item in items)
    assert all(item["evidence_chunk_id"].startswith("chk_") for item in items)
