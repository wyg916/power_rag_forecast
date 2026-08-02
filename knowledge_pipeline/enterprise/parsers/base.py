from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from ..parsed_contracts import ParsedAsset, ParsedBlock, ParsedDocument, ParsedTable, ParseStatus


@dataclass(frozen=True)
class ParserLimits:
    max_file_bytes: int = 64 * 1024 * 1024
    max_blocks: int = 100_000
    max_table_rows: int = 200_000
    max_cell_chars: int = 20_000
    max_text_chars: int = 20_000_000
    max_pages: int = 5_000
    max_assets: int = 100_000


@dataclass(frozen=True)
class ParseContext:
    path: Path
    source_id: str
    detected_format: str
    content_hash: str
    limits: ParserLimits


class ParseFailure(RuntimeError):
    pass


def element_id(source_id: str, kind: str, order: int) -> str:
    value = f"{source_id}\0{kind}\0{order}".encode("utf-8")
    return f"{kind}_{hashlib.sha256(value).hexdigest()[:20]}"


def decode_text(data: bytes) -> str:
    if b"\x00" in data:
        raise ParseFailure("invalid_text_encoding")
    declared = re.search(br"charset\s*=\s*['\"]?([a-zA-Z0-9_-]+)", data[:4096], re.I)
    encodings = [declared.group(1).decode("ascii").lower()] if declared else []
    encodings.extend(["utf-8-sig", "gb18030"])
    for encoding in dict.fromkeys(encodings):
        if encoding not in {"utf-8", "utf-8-sig", "gb18030", "gbk", "gb2312"}:
            continue
        try:
            text = data.decode(encoding, errors="strict")
        except (LookupError, UnicodeDecodeError):
            continue
        invalid = sum(ord(char) < 32 and char not in "\n\r\t" for char in text)
        if invalid <= max(1, len(text) // 1000):
            return text
    raise ParseFailure("invalid_text_encoding")


def finish(
    context: ParseContext,
    parser_name: str,
    *,
    status: ParseStatus = ParseStatus.READY,
    blocks: tuple[ParsedBlock, ...] = (),
    tables: tuple[ParsedTable, ...] = (),
    assets: tuple[ParsedAsset, ...] = (),
    page_count: int = 0,
    reason: str = "",
) -> ParsedDocument:
    if status is ParseStatus.READY and not blocks and not tables:
        status, reason = ParseStatus.QUARANTINED, "empty_document"
    return ParsedDocument(
        source_id=context.source_id,
        source_path=str(context.path),
        detected_format=context.detected_format,
        content_hash=context.content_hash,
        parser_name=parser_name,
        parser_version="1",
        status=status,
        blocks=blocks,
        tables=tables,
        assets=assets,
        page_count=page_count,
        isolation_reason=reason,
    )
