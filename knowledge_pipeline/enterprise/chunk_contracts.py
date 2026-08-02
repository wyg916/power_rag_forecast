from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from .parsed_contracts import BoundingBox


CHUNK_BUILD_SCHEMA_VERSION = "rag-chunk-build/v1"


@dataclass(frozen=True)
class CitationLocator:
    source_id: str
    version_id: str
    parent_id: str
    block_id: str
    page: int | None
    section_path: tuple[str, ...]
    char_start: int
    char_end: int
    bbox: BoundingBox | None
    asset_ids: tuple[str, ...]
    quote: str
    content_hash: str


@dataclass(frozen=True)
class ParentChunk:
    parent_id: str
    source_id: str
    version_id: str
    block_id: str
    order: int
    kind: str
    content: str
    content_hash: str
    section_path: tuple[str, ...]
    page: int | None
    bbox: BoundingBox | None
    table_id: str = ""
    asset_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChildChunk:
    chunk_id: str
    parent_id: str
    source_id: str
    version_id: str
    child_index: int
    content: str
    content_hash: str
    token_count: int
    table_id: str
    asset_ids: tuple[str, ...]
    citation: CitationLocator


@dataclass(frozen=True)
class ChunkAsset:
    asset_id: str
    version_id: str
    asset_type: str
    content_hash: str
    status: str
    order: int
    page: int | None
    bbox: BoundingBox | None


@dataclass(frozen=True)
class ChunkBuildResult:
    document_id: str
    source_id: str
    version_id: str
    document_hash: str
    document_status: str
    parents: tuple[ParentChunk, ...]
    chunks: tuple[ChildChunk, ...]
    assets: tuple[ChunkAsset, ...]
    schema_version: str = CHUNK_BUILD_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json_bytes(self) -> bytes:
        value = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return (value + "\n").encode("utf-8")
