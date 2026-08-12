from __future__ import annotations

import hashlib
from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Sequence


CITATION_FIELDS = (
    "version_id",
    "page",
    "section_path",
    "char_start",
    "char_end",
    "bbox",
    "asset_id",
    "quote",
    "content_hash",
)


@dataclass(frozen=True)
class CitationBatch:
    available: bool
    reason: str
    citations: list[dict[str, Any]]


@dataclass(frozen=True)
class ClaimGrounding:
    available: bool
    grounding_status: str
    refusal_reason: str
    claims: list[dict[str, Any]]
    citations: list[dict[str, Any]]


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _citation_id(item: Mapping[str, Any], locator: Mapping[str, Any]) -> str:
    identity = "\0".join(
        str(value)
        for value in (
            item.get("document_id") or item.get("doc_id"),
            item.get("chunk_id"),
            locator.get("version_id"),
            locator.get("char_start"),
            locator.get("char_end"),
            locator.get("content_hash"),
        )
    )
    return "cit-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def _locator(item: Mapping[str, Any]) -> Mapping[str, Any] | None:
    nested = item.get("citation")
    return nested if isinstance(nested, Mapping) else None


def validate_candidate_citation(item: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(item, Mapping):
        return None, "citation_candidate_invalid"
    locator = _locator(item)
    if locator is None:
        return None, "citation_locator_invalid"
    if any(field not in locator for field in CITATION_FIELDS):
        return None, "citation_field_missing"

    document_id = str(item.get("document_id") or item.get("doc_id") or "").strip()
    chunk_id = str(item.get("chunk_id") or "").strip()
    version_id = str(locator.get("version_id") or "").strip()
    content = item.get("content")
    if not document_id or not chunk_id or not version_id or not isinstance(content, str) or not content:
        return None, "citation_identity_invalid"
    if item.get("version_id") and str(item.get("version_id")) != version_id:
        return None, "citation_identity_mismatch"
    chunk_hash = str(item.get("content_hash") or "").lower()
    if len(chunk_hash) != 64 or any(value not in "0123456789abcdef" for value in chunk_hash):
        return None, "chunk_hash_invalid"
    if chunk_hash != _sha256(content):
        return None, "chunk_hash_mismatch"

    page = locator.get("page")
    if page is not None and (isinstance(page, bool) or not isinstance(page, int) or page < 1):
        return None, "citation_page_invalid"
    section_path = locator.get("section_path")
    if (
        not isinstance(section_path, (list, tuple))
        or any(not isinstance(value, str) or not value.strip() for value in section_path)
    ):
        return None, "citation_section_path_invalid"

    citation_base = item.get("citation_base")
    if not isinstance(citation_base, str):
        parent_content = item.get("parent_content")
        citation_base = parent_content if isinstance(parent_content, str) and parent_content else content
    start, end = locator.get("char_start"), locator.get("char_end")
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or start < 0
        or end <= start
        or end > len(citation_base)
    ):
        return None, "citation_offsets_invalid"
    quote = locator.get("quote")
    if not isinstance(quote, str) or not quote:
        return None, "citation_quote_invalid"
    if quote != citation_base[start:end]:
        return None, "citation_quote_mismatch"

    bbox = locator.get("bbox")
    if bbox is not None:
        if (
            not isinstance(bbox, (list, tuple))
            or len(bbox) != 4
            or any(isinstance(value, bool) for value in bbox)
        ):
            return None, "citation_bbox_invalid"
        try:
            coordinates = tuple(float(value) for value in bbox)
        except (TypeError, ValueError):
            return None, "citation_bbox_invalid"
        if not all(isfinite(value) for value in coordinates) or coordinates[0] > coordinates[2] or coordinates[1] > coordinates[3]:
            return None, "citation_bbox_invalid"
        bbox = coordinates
        if page is None:
            return None, "citation_bbox_page_missing"
    asset_id = locator.get("asset_id")
    if asset_id is not None and (not isinstance(asset_id, str) or not asset_id.strip()):
        return None, "citation_asset_invalid"

    content_hash = str(locator.get("content_hash") or "").lower()
    if len(content_hash) != 64 or any(value not in "0123456789abcdef" for value in content_hash):
        return None, "citation_hash_invalid"
    if content_hash != _sha256(quote):
        return None, "citation_hash_mismatch"

    citation = {
        "citation_id": _citation_id(item, locator),
        "document_id": document_id,
        "chunk_id": chunk_id,
        "version_id": version_id,
        "page": page,
        "section_path": list(section_path),
        "char_start": start,
        "char_end": end,
        "bbox": list(bbox) if bbox is not None else None,
        "asset_id": asset_id,
        "quote": quote,
        "content_hash": content_hash,
        "title": item.get("title"),
        "score": item.get("final_score", item.get("score")),
    }
    return citation, ""


def validate_candidate_citations(items: Sequence[Mapping[str, Any]]) -> CitationBatch:
    if not items:
        return CitationBatch(False, "no_evidence", [])
    citations: list[dict[str, Any]] = []
    for item in items:
        citation, reason = validate_candidate_citation(item)
        if citation is None:
            return CitationBatch(False, reason, [])
        citations.append(citation)
    return CitationBatch(True, "", citations)


def citation_from_retrieval_item(
    item: Mapping[str, Any], *, quote_limit: int = 240
) -> tuple[dict[str, Any] | None, str]:
    """Build the immutable citation contract for a PostgreSQL retrieval row.

    The balanced/keyword retrieval path returns persisted chunks rather than the
    richer enterprise-Qdrant candidate DTO.  Normalize that trusted repository
    row into the same locator contract before claim binding instead of emitting
    a weaker, display-only citation shape.
    """

    if not isinstance(item, Mapping):
        return None, "citation_candidate_invalid"
    document_id = str(item.get("document_id") or item.get("doc_id") or "").strip()
    chunk_id = str(item.get("chunk_id") or "").strip()
    content = item.get("content")
    if not document_id or not chunk_id or not isinstance(content, str) or not content:
        return None, "citation_identity_invalid"

    raw_metadata = item.get("metadata")
    metadata = raw_metadata if isinstance(raw_metadata, Mapping) else {}
    version_id = str(
        item.get("version_id")
        or metadata.get("document_version")
        or f"sha256:{_sha256(content)[:16]}"
    ).strip()
    section = str(item.get("section_title") or item.get("section") or "").strip()
    raw_section_path = item.get("section_path") or metadata.get("section_path")
    if raw_section_path is None:
        section_path: list[str] = [section] if section else []
    elif isinstance(raw_section_path, (list, tuple)):
        section_path = [str(value).strip() for value in raw_section_path]
    else:
        return None, "citation_section_path_invalid"

    limit = max(1, int(quote_limit or 240))
    quote = content[:limit]
    candidate = {
        **dict(item),
        "document_id": document_id,
        "chunk_id": chunk_id,
        "version_id": version_id,
        "content": content,
        "content_hash": _sha256(content),
        "citation_base": content,
        "citation": {
            "version_id": version_id,
            "page": item.get("page", metadata.get("page")),
            "section_path": section_path,
            "char_start": 0,
            "char_end": len(quote),
            "bbox": item.get("bbox", metadata.get("bbox")),
            "asset_id": item.get("asset_id", metadata.get("asset_id")),
            "quote": quote,
            "content_hash": _sha256(quote),
        },
    }
    return validate_candidate_citation(candidate)


def validate_claim_bindings(
    claims: Sequence[Mapping[str, Any]],
    citations: Sequence[Mapping[str, Any]],
) -> ClaimGrounding:
    if not citations or any(
        not isinstance(item, Mapping)
        or not item.get("citation_id")
        or any(field not in item for field in CITATION_FIELDS)
        or str(item.get("content_hash") or "").lower()
        != _sha256(str(item.get("quote") or ""))
        or str(item.get("citation_id")) != _citation_id(item, item)
        for item in citations
    ):
        return ClaimGrounding(False, "unavailable", "grounding_evidence_missing", [], [])
    catalog = {str(item.get("citation_id") or ""): dict(item) for item in citations}
    if not claims or len(catalog) != len(citations):
        return ClaimGrounding(False, "unavailable", "grounding_evidence_missing", [], [])
    normalized: list[dict[str, Any]] = []
    claim_ids: set[str] = set()
    for claim in claims:
        claim_id = str(claim.get("claim_id") or "").strip()
        text = str(claim.get("text") or "").strip()
        references = claim.get("citation_ids")
        if not claim_id or claim_id in claim_ids or not text:
            return ClaimGrounding(False, "unavailable", "claim_contract_invalid", [], [])
        if not isinstance(references, (list, tuple)) or not references:
            return ClaimGrounding(False, "unavailable", "claim_citation_missing", [], [])
        citation_ids = [str(value) for value in references]
        if any(not value or value not in catalog for value in citation_ids):
            return ClaimGrounding(False, "unavailable", "claim_citation_invalid", [], [])
        claim_ids.add(claim_id)
        normalized.append({"claim_id": claim_id, "text": text, "citation_ids": list(dict.fromkeys(citation_ids))})
    return ClaimGrounding(True, "grounded", "", normalized, [dict(item) for item in citations])
