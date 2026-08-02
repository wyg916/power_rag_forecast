import json
from dataclasses import replace
from pathlib import Path

import pytest

from knowledge_pipeline.enterprise.parsed_contracts import ParsedBlock, ParsedDocument, ParseStatus
from scripts.rag_r1_candidate_corpus import (
    CandidateCorpusRunError,
    _check_immutable,
    _domain,
    load_ledger,
    text_quality_issue,
    write_immutable,
)


def _document(text: str) -> ParsedDocument:
    return ParsedDocument(
        "src_fixture",
        "fixture.pdf",
        "pdf",
        "a" * 64,
        "fixture",
        "1",
        ParseStatus.READY,
        (ParsedBlock("block_fixture", 1, "text", text),),
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("电力市场运行规则与结算办法", ""),
        ("政策正文\ufffd", "replacement_character_detected"),
        ("政策正文\x81", "forbidden_control_character_detected"),
        ("政策正文\ue000", "private_use_character_detected"),
        ("!@#$%^&*()" * 20, "low_meaningful_character_ratio"),
    ),
)
def test_text_quality_gate_fails_closed_on_garbled_output(text: str, expected: str):
    assert text_quality_issue(_document(text)) == expected


def test_text_quality_gate_includes_table_cells():
    document = replace(_document(""), blocks=())
    assert text_quality_issue(document) == "empty_extracted_text"


@pytest.mark.parametrize(
    ("title", "expected"),
    (
        ("电化学储能建设清单", "energy-storage"),
        ("绿电直连实施办法", "green-power"),
        ("风电光伏项目方案", "renewable-development"),
        ("电力市场交易规则", "power-market"),
        ("电网公平开放监管办法", "grid-regulation"),
        ("能源行业数据安全办法", "energy-policy"),
    ),
)
def test_domain_mapping_is_deterministic(title: str, expected: str):
    assert _domain(title) == expected


def test_immutable_writer_is_idempotent_and_rejects_conflict(tmp_path: Path):
    path = tmp_path / "candidate.json"
    assert _check_immutable(path, b"one") == "create"
    assert write_immutable(path, b"one") == "created"
    assert write_immutable(path, b"one") == "unchanged"
    with pytest.raises(CandidateCorpusRunError, match="immutable_output_conflict"):
        write_immutable(path, b"two")


def test_ledger_loader_rejects_noncanonical_or_wrong_count(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    path.write_text(json.dumps({"admission_status": "ready"}) + "\n", encoding="utf-8")
    with pytest.raises(CandidateCorpusRunError, match="source_ledger_invalid"):
        load_ledger(path)
