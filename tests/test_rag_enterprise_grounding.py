from __future__ import annotations

import hashlib
from copy import deepcopy

import pytest

from backend.app.services.rag_grounding_service import (
    CITATION_FIELDS,
    validate_candidate_citation,
    validate_candidate_citations,
    validate_claim_bindings,
)


def _item() -> dict:
    content = "尖峰风险需关注负荷变化。"
    parent_content = f"运行约束：{content}"
    quote = "尖峰风险"
    char_start = parent_content.index(quote)
    return {
        "document_id": "doc-1",
        "chunk_id": "chunk-1",
        "version_id": "version-1",
        "title": "尖峰风险说明",
        "content": content,
        "parent_content": parent_content,
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "citation": {
            "version_id": "version-1",
            "page": 3,
            "section_path": ["运行风险", "尖峰风险"],
            "char_start": char_start,
            "char_end": char_start + len(quote),
            "bbox": [1.0, 2.0, 10.0, 20.0],
            "asset_id": None,
            "quote": quote,
            "content_hash": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
        },
        "final_score": 0.9,
    }


def test_complete_citation_recomputes_quote_hash_and_stable_id():
    batch = validate_candidate_citations([_item()])

    assert batch.available is True
    assert set(CITATION_FIELDS) <= set(batch.citations[0])
    item = _item()
    locator = item["citation"]
    assert batch.citations[0]["quote"] == item["parent_content"][locator["char_start"]:locator["char_end"]]
    assert batch.citations[0]["citation_id"].startswith("cit-")
    assert batch == validate_candidate_citations([_item()])


def test_chunk_hash_and_quote_hash_are_independently_verified():
    item = _item()
    citation, reason = validate_candidate_citation(item)

    assert reason == ""
    assert citation and citation["section_path"] == ["运行风险", "尖峰风险"]
    assert item["content_hash"] == hashlib.sha256(item["content"].encode("utf-8")).hexdigest()
    assert citation["content_hash"] == hashlib.sha256(citation["quote"].encode("utf-8")).hexdigest()
    assert item["content_hash"] != citation["content_hash"]


@pytest.mark.parametrize("field", CITATION_FIELDS)
def test_every_required_citation_field_is_fail_closed(field):
    item = _item()
    item["citation"].pop(field)

    citation, reason = validate_candidate_citation(item)

    assert citation is None
    assert reason == "citation_field_missing"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"quote": "负荷变化"}, "citation_quote_mismatch"),
        ({"char_end": 999}, "citation_offsets_invalid"),
        ({"content_hash": "a" * 64}, "citation_hash_mismatch"),
        ({"bbox": [10, 2, 1, 20]}, "citation_bbox_invalid"),
        ({"asset_id": ""}, "citation_asset_invalid"),
    ],
)
def test_locator_tampering_is_rejected(changes, reason):
    item = _item()
    item["citation"].update(changes)
    citation, actual = validate_candidate_citation(item)
    assert citation is None
    assert actual == reason


def test_empty_section_path_is_valid_and_bbox_requires_page():
    unsectioned = _item()
    unsectioned["citation"]["section_path"] = []
    assert validate_candidate_citation(unsectioned)[1] == ""

    no_page = _item()
    no_page["citation"]["page"] = None
    assert validate_candidate_citation(no_page)[1] == "citation_bbox_page_missing"


def test_chunk_hash_is_recomputed_separately_from_citation_hash():
    item = _item()
    item["content_hash"] = "a" * 64
    assert validate_candidate_citation(item)[1] == "chunk_hash_mismatch"


def test_every_claim_must_bind_existing_valid_citation():
    citations = validate_candidate_citations([_item()]).citations
    citation_id = citations[0]["citation_id"]

    grounded = validate_claim_bindings(
        [{"claim_id": "claim-1", "text": "尖峰风险需要关注。", "citation_ids": [citation_id]}],
        citations,
    )
    missing = validate_claim_bindings(
        [{"claim_id": "claim-1", "text": "无引用主张", "citation_ids": []}], citations,
    )
    forged = validate_claim_bindings(
        [{"claim_id": "claim-1", "text": "伪造引用", "citation_ids": ["cit-forged"]}], citations,
    )

    assert grounded.available is True and grounded.grounding_status == "grounded"
    assert missing.available is False and missing.refusal_reason == "claim_citation_missing"
    assert forged.available is False and forged.refusal_reason == "claim_citation_invalid"


def test_claim_binding_rejects_unvalidated_citation_catalog():
    invalid = deepcopy(validate_candidate_citations([_item()]).citations[0])
    invalid.pop("quote")
    result = validate_claim_bindings(
        [{"claim_id": "claim-1", "text": "主张", "citation_ids": [invalid["citation_id"]]}],
        [invalid],
    )
    assert result.available is False
    assert result.refusal_reason == "grounding_evidence_missing"
