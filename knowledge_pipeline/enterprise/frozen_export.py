from __future__ import annotations

from typing import Any

from .chunk_contracts import ChunkBuildResult
from .quality import validate_candidate


FROZEN_CANDIDATE_SCHEMA_VERSION = "rag-candidate-corpus/v1"


class FrozenExportError(RuntimeError):
    pass


def _bbox(value) -> list[float] | None:
    if value is None:
        return None
    return [value.x0, value.y0, value.x1, value.y1]


def export_frozen_records(build: ChunkBuildResult) -> dict[str, Any]:
    """Export only records governed by M1's frozen chunk/citation/asset defs."""
    report = validate_candidate(build)
    if not report.ok:
        raise FrozenExportError("chunk_build_quality_failed:" + ",".join(issue.code for issue in report.issues))

    chunks: list[dict[str, Any]] = []
    for chunk in build.chunks:
        locator = chunk.citation
        if len(locator.asset_ids) > 1:
            raise FrozenExportError(f"citation_asset_cardinality_invalid:{chunk.chunk_id}")
        citation = {
            "version_id": locator.version_id,
            "page": locator.page,
            "section_path": list(locator.section_path),
            "char_start": locator.char_start,
            "char_end": locator.char_end,
            "bbox": _bbox(locator.bbox),
            "asset_id": locator.asset_ids[0] if locator.asset_ids else None,
            "quote": locator.quote,
            "content_hash": locator.content_hash,
        }
        chunks.append(
            {
                "chunk_id": chunk.chunk_id,
                "document_id": build.document_id,
                "version_id": chunk.version_id,
                "parent_chunk_id": chunk.parent_id,
                "content": chunk.content,
                "content_hash": chunk.content_hash,
                "token_count": chunk.token_count,
                "citation": citation,
            }
        )

    assets = [
        {
            "asset_id": asset.asset_id,
            "version_id": asset.version_id,
            "asset_type": asset.asset_type,
            "content_hash": asset.content_hash,
            "page": asset.page,
            "bbox": _bbox(asset.bbox),
        }
        for asset in build.assets
    ]
    return {
        "target_schema_version": FROZEN_CANDIDATE_SCHEMA_VERSION,
        "document_id": build.document_id,
        "version_id": build.version_id,
        "chunks": chunks,
        "assets": assets,
    }
