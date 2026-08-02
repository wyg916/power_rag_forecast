from dataclasses import replace

from knowledge_pipeline.enterprise.chunking import build_candidate
from knowledge_pipeline.enterprise.citation import citation_errors, text_hash
from knowledge_pipeline.enterprise.parsed_contracts import BoundingBox, ParsedBlock, ParsedDocument, ParseStatus


def test_cross_page_citations_keep_page_bbox_offsets_quote_and_hash() -> None:
    blocks = (
        ParsedBlock("p1", 1, "text", "第一页证据", page=1, bbox=BoundingBox(1, 2, 30, 40)),
        ParsedBlock("p2", 2, "text", "第二页证据", page=2, bbox=BoundingBox(5, 6, 35, 45)),
    )
    document = ParsedDocument("src_pdf", "fixture.pdf", "pdf", "b" * 64, "pdf", "1", ParseStatus.READY, blocks)
    candidate = build_candidate(document, token_counter=len, max_tokens=20)
    assert [chunk.citation.page for chunk in candidate.chunks] == [1, 2]
    for chunk in candidate.chunks:
        parent = next(parent for parent in candidate.parents if parent.parent_id == chunk.parent_id)
        locator = chunk.citation
        assert parent.content[locator.char_start:locator.char_end] == locator.quote
        assert locator.content_hash == text_hash(locator.quote)
        assert locator.bbox == parent.bbox
        assert citation_errors(locator, parent) == ()


def test_citation_validator_rejects_bounds_quote_hash_and_location_mismatch() -> None:
    block = ParsedBlock("p1", 1, "text", "完整证据", page=1, bbox=BoundingBox(1, 2, 3, 4))
    document = ParsedDocument("src", "fixture.pdf", "pdf", "c" * 64, "pdf", "1", ParseStatus.READY, (block,))
    candidate = build_candidate(document, token_counter=len, max_tokens=20)
    parent, citation = candidate.parents[0], candidate.chunks[0].citation
    broken = replace(citation, char_end=999, quote="伪造", content_hash="bad", page=0, section_path=("",))
    errors = set(citation_errors(broken, parent))
    assert {
        "citation_locator_out_of_bounds", "citation_hash_mismatch",
        "citation_location_invalid", "citation_location_mismatch",
    } <= errors
