from dataclasses import replace

import pytest

from knowledge_pipeline.enterprise.chunk_contracts import ChunkAsset
from knowledge_pipeline.enterprise.chunking import ChunkBuildError, build_candidate
from knowledge_pipeline.enterprise.quality import validate_candidate
from knowledge_pipeline.enterprise.parsed_contracts import ParsedAsset, ParsedBlock, ParsedDocument, ParseStatus


def _candidate():
    block = ParsedBlock("b1", 1, "paragraph", "可验证的完整证据")
    document = ParsedDocument("src", "fixture.docx", "docx", "d" * 64, "docx", "1", ParseStatus.READY, (block,))
    return build_candidate(document, token_counter=len, max_tokens=6)


def test_quality_gate_accepts_complete_candidate_and_rejects_bad_cases() -> None:
    candidate = _candidate()
    assert validate_candidate(candidate).ok
    first = candidate.chunks[0]
    bad_locator = replace(first.citation, char_start=-1, quote="错引", content_hash="bad")
    bad_chunk = replace(first, citation=bad_locator, content="", content_hash="bad", parent_id="missing")
    duplicate = replace(candidate, chunks=(bad_chunk, bad_chunk))
    bad_parent = replace(candidate.parents[0], content_hash="bad")
    broken = replace(duplicate, parents=(bad_parent,))
    codes = {issue.code for issue in validate_candidate(broken).issues}
    locator_broken = replace(candidate, chunks=(replace(first, citation=bad_locator),))
    locator_codes = {issue.code for issue in validate_candidate(locator_broken).issues}
    assert {"duplicate_chunk_id", "parent_missing", "parent_hash_mismatch", "empty_chunk_content"} <= codes
    assert {"citation_locator_out_of_bounds", "citation_hash_mismatch"} <= locator_codes


def test_quality_gate_rejects_unfinished_ocr_assets() -> None:
    candidate = _candidate()
    unfinished = ChunkAsset("ocr_page_2", candidate.version_id, "image", "", "ocr_required", 2, 2, None)
    broken = replace(candidate, document_status="ocr_required", assets=(unfinished,))
    codes = {issue.code for issue in validate_candidate(broken).issues}
    assert {"document_ocr_incomplete", "asset_not_ready"} <= codes

    parsed = ParsedDocument(
        "src_ocr", "scan.pdf", "pdf", "e" * 64, "pdf", "1", ParseStatus.OCR_REQUIRED,
        (), (), (ParsedAsset("ocr_page_2", 2, "page", "ocr_required", page=2),), page_count=2,
    )
    with pytest.raises(ChunkBuildError, match="candidate_quality_failed"):
        build_candidate(parsed, token_counter=len, max_tokens=20)


def test_quality_gate_rejects_empty_ready_document() -> None:
    empty = ParsedDocument("src_empty", "empty.docx", "docx", "f" * 64, "docx", "1", ParseStatus.READY)
    with pytest.raises(ChunkBuildError, match="empty_candidate_parents"):
        build_candidate(empty, token_counter=len, max_tokens=20)


def test_quality_gate_rejects_ready_asset_without_frozen_hash_or_locator() -> None:
    candidate = _candidate()
    incomplete = ChunkAsset("image_1", candidate.version_id, "image", "", "ready", 2, None, None)
    codes = {issue.code for issue in validate_candidate(replace(candidate, assets=(incomplete,))).issues}
    assert {"asset_hash_missing_or_invalid", "asset_locator_incomplete"} <= codes
