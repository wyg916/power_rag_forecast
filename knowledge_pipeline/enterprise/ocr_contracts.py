from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .parsed_contracts import BoundingBox


OCR_SOURCE_FORMATS = {"pdf", "jpg", "jpeg"}
ELEMENT_KINDS = {"text", "table", "formula", "chart", "image"}


@dataclass(frozen=True)
class OCRProviderProfile:
    provider: str
    provider_version: str


@dataclass(frozen=True)
class OCRApprovalPolicy:
    approved_profiles: tuple[OCRProviderProfile, ...]

    def allows(self, profile: OCRProviderProfile) -> bool:
        return profile in self.approved_profiles


@dataclass(frozen=True)
class OCRRequest:
    source_path: Path
    source_format: str
    source_sha256: str
    tenant_id: str
    version_id: str
    expected_profile: OCRProviderProfile
    page_sizes: tuple[tuple[int, float, float], ...]
    source_page_digits: tuple[tuple[int, tuple[str, ...]], ...]


@dataclass(frozen=True)
class VisionElement:
    element_id: str
    source_sha256: str
    tenant_id: str
    version_id: str
    page: int
    page_width: float
    page_height: float
    bbox: BoundingBox
    asset_type: str
    status: str
    text: str = ""
    cells: tuple[tuple[str, ...], ...] = ()
    confidence: float = 0.0
    content_hash: str = ""


@dataclass(frozen=True)
class OCRResult:
    source_sha256: str
    tenant_id: str
    version_id: str
    status: str
    provider: str
    provider_version: str
    elements: tuple[VisionElement, ...]


class OCRProvider(Protocol):
    def analyze(self, request: OCRRequest) -> OCRResult: ...


def element_payload(text: str, cells: tuple[tuple[str, ...], ...]) -> str:
    if cells:
        width = max(len(row) for row in cells)
        rows = [tuple(list(row) + [""] * (width - len(row))) for row in cells]
        escaped = [[cell.replace("|", "\\|").replace("\n", " ").strip() for cell in row] for row in rows]
        lines = ["| " + " | ".join(escaped[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
        lines.extend("| " + " | ".join(row) + " |" for row in escaped[1:])
        return "\n".join(lines)
    return text.strip()


def element_hash(text: str, cells: tuple[tuple[str, ...], ...] = ()) -> str:
    return hashlib.sha256(element_payload(text, cells).encode("utf-8")).hexdigest()
