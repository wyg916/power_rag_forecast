from __future__ import annotations

import hashlib

from .chunk_contracts import CitationLocator, ParentChunk


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_citation(parent: ParentChunk, start: int, end: int) -> CitationLocator:
    if start < 0 or end <= start or end > len(parent.content):
        raise ValueError("citation_locator_out_of_bounds")
    quote = parent.content[start:end]
    return CitationLocator(
        source_id=parent.source_id,
        version_id=parent.version_id,
        parent_id=parent.parent_id,
        block_id=parent.block_id,
        page=parent.page,
        section_path=parent.section_path,
        char_start=start,
        char_end=end,
        bbox=parent.bbox,
        asset_ids=parent.asset_ids,
        quote=quote,
        content_hash=text_hash(quote),
    )


def citation_errors(citation: CitationLocator, parent: ParentChunk) -> tuple[str, ...]:
    errors: list[str] = []
    if citation.source_id != parent.source_id or citation.version_id != parent.version_id:
        errors.append("citation_identity_mismatch")
    if citation.parent_id != parent.parent_id or citation.block_id != parent.block_id:
        errors.append("citation_parent_mismatch")
    start, end = citation.char_start, citation.char_end
    if start < 0 or end <= start or end > len(parent.content):
        errors.append("citation_locator_out_of_bounds")
    elif parent.content[start:end] != citation.quote:
        errors.append("citation_quote_mismatch")
    if citation.content_hash != text_hash(citation.quote):
        errors.append("citation_hash_mismatch")
    if citation.page is not None and (isinstance(citation.page, bool) or not isinstance(citation.page, int) or citation.page < 1):
        errors.append("citation_location_invalid")
    if any(not part for part in citation.section_path):
        errors.append("citation_location_invalid")
    if (citation.page, citation.section_path, citation.bbox) != (parent.page, parent.section_path, parent.bbox):
        errors.append("citation_location_mismatch")
    if citation.asset_ids != parent.asset_ids:
        errors.append("citation_asset_mismatch")
    return tuple(errors)
