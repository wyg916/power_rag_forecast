from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


PARSED_SCHEMA_VERSION = "rag-parsed-document/v1"


class ParseStatus(str, Enum):
    READY = "ready"
    OCR_REQUIRED = "ocr_required"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class BoundingBox:
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class ParsedBlock:
    block_id: str
    order: int
    kind: str
    text: str
    section_path: tuple[str, ...] = ()
    page: int | None = None
    bbox: BoundingBox | None = None
    table_id: str = ""


@dataclass(frozen=True)
class ParsedTable:
    table_id: str
    order: int
    rows: tuple[tuple[str, ...], ...]
    sheet_name: str = ""
    page: int | None = None
    bbox: BoundingBox | None = None


@dataclass(frozen=True)
class ParsedAsset:
    asset_id: str
    order: int
    kind: str
    status: str
    page: int | None = None
    bbox: BoundingBox | None = None
    source_ref: str = ""
    alt_text: str = ""
    content_hash: str = ""


@dataclass(frozen=True)
class ParsedDocument:
    source_id: str
    source_path: str
    detected_format: str
    content_hash: str
    parser_name: str
    parser_version: str
    status: ParseStatus
    blocks: tuple[ParsedBlock, ...] = ()
    tables: tuple[ParsedTable, ...] = ()
    assets: tuple[ParsedAsset, ...] = ()
    page_count: int = 0
    isolation_reason: str = ""
    schema_version: str = PARSED_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload
