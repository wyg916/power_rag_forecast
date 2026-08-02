from __future__ import annotations

import json
from pathlib import Path

from knowledge_pipeline.enterprise.acceptance_preflight import (
    validate_ai_gold,
    validate_ocr_gold,
    validate_retrieval_gold,
)


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def _citation(index: int) -> dict[str, str]:
    return {
        "release_id": "RAG-R1",
        "document_id": "doc-1",
        "version_id": "ver-1",
        "chunk_id": f"chunk-{index}",
    }


def test_missing_assets_fail_closed(tmp_path: Path) -> None:
    assert validate_ocr_gold(tmp_path / "ocr.json")["issues"] == ["ocr_gold_missing"]
    assert validate_retrieval_gold(tmp_path / "retrieval.json", set())["issues"] == [
        "retrieval_gold_missing"
    ]
    assert validate_ai_gold(tmp_path / "ai.json", set())["issues"] == ["ai_gold_missing"]


def test_ocr_gold_requires_human_review_and_table_reference(tmp_path: Path) -> None:
    pages = []
    for index in range(30):
        pages.append(
            {
                "sample_id": f"ocr-{index}",
                "document_id": "doc-1",
                "page": index + 1,
                "reference_text": "人工核对文本",
                "elements": [
                    {
                        "element_id": f"element-{index}",
                        "kind": "text",
                        "bbox": [0, 0, 10, 10],
                    }
                ],
                "reference_table_cells": ["单元格"] if index == 0 else [],
                "annotation": {
                    "annotator_type": "human",
                    "reviewer_id": "reviewer-1",
                    "approved_at": "2026-08-02T00:00:00+00:00",
                },
            }
        )
    path = _write(
        tmp_path / "ocr.json",
        {"schema_version": "rag-r1-ocr-gold/v1", "release_id": "RAG-R1", "pages": pages},
    )
    result = validate_ocr_gold(path)
    assert result["input_ready"] is True
    assert result["page_count"] == 30


def test_retrieval_gold_requires_exact_release_bound_50(tmp_path: Path) -> None:
    questions = [
        {
            "question_id": f"retrieval-{index}",
            "question": f"问题 {index}",
            "critical": index < 5,
            "gold_citations": [_citation(index)],
        }
        for index in range(50)
    ]
    path = _write(
        tmp_path / "retrieval.json",
        {
            "schema_version": "rag-r1-retrieval-gold/v1",
            "release_id": "RAG-R1",
            "questions": questions,
        },
    )
    result = validate_retrieval_gold(path, {f"chunk-{index}" for index in range(50)})
    assert result["input_ready"] is True
    assert result["question_count"] == 50


def test_ai_gold_requires_100_questions_and_30_critical(tmp_path: Path) -> None:
    questions = []
    for index in range(100):
        refusal = index >= 90
        questions.append(
            {
                "question_id": f"ai-{index}",
                "question": f"问题 {index}",
                "critical": index < 30,
                "expected_behavior": "refuse_no_evidence" if refusal else "answer_with_citations",
                "required_facts": [] if refusal else ["事实"],
                "gold_citations": [] if refusal else [_citation(index)],
                "allowed_numeric_claims": [],
            }
        )
    path = _write(
        tmp_path / "ai.json",
        {"schema_version": "rag-r1-ai-gold/v1", "release_id": "RAG-R1", "questions": questions},
    )
    result = validate_ai_gold(path, {f"chunk-{index}" for index in range(90)})
    assert result["input_ready"] is True
    assert result["critical_count"] == 30

