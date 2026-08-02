from __future__ import annotations

import hashlib
from numbers import Integral
from typing import Callable

from .chunk_contracts import ChunkAsset, ChunkBuildResult, ChildChunk, ParentChunk
from .citation import make_citation, text_hash
from .parsed_contracts import ParsedBlock, ParsedDocument, ParsedTable, ParseStatus


TokenCounter = Callable[[str], int]


class ChunkBuildError(RuntimeError):
    pass


def _stable_id(prefix: str, *parts: object) -> str:
    value = "\0".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(value).hexdigest()[:24]}"


def derive_version_id(document: ParsedDocument) -> str:
    if not document.source_id or not document.content_hash:
        raise ChunkBuildError("document_identity_incomplete")
    return _stable_id("ver", document.source_id, document.content_hash, document.schema_version, document.parser_version)


def derive_document_id(document: ParsedDocument) -> str:
    if not document.source_id:
        raise ChunkBuildError("document_identity_incomplete")
    return _stable_id("doc", document.source_id)


def _count(counter: TokenCounter | None, text: str) -> int:
    if counter is None:
        raise ChunkBuildError("token_counter_required")
    try:
        value = counter(text)
    except Exception as exc:
        raise ChunkBuildError("token_counter_failed") from exc
    if isinstance(value, bool) or not isinstance(value, Integral) or int(value) <= 0:
        raise ChunkBuildError("token_counter_invalid")
    return int(value)


def _render_table(table: ParsedTable) -> str:
    if not table.rows or not any(any(cell for cell in row) for row in table.rows):
        raise ChunkBuildError("empty_table")
    width = max(len(row) for row in table.rows)
    rows = [tuple(list(row) + [""] * (width - len(row))) for row in table.rows]
    escaped = [[cell.replace("|", "\\|").replace("\n", " ").strip() for cell in row] for row in rows]
    lines = ["| " + " | ".join(escaped[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in escaped[1:])
    return "\n".join(lines)


def _parent_content(block: ParsedBlock, tables: dict[str, ParsedTable]):
    if block.kind != "table":
        value = block.text.strip()
        if not value:
            raise ChunkBuildError(f"empty_block:{block.block_id}")
        return value, "", block.page, block.bbox
    table = tables.get(block.table_id)
    if table is None:
        raise ChunkBuildError(f"table_missing:{block.table_id}")
    page = table.page if table.page is not None else block.page
    bbox = table.bbox if table.bbox is not None else block.bbox
    return _render_table(table), table.table_id, page, bbox


def _layout_table_ids(tables: dict[str, ParsedTable]) -> set[str]:
    return {
        table.table_id
        for table in tables.values()
        if table.page is not None and table.bbox is not None
    }


def _block_page(block: ParsedBlock, tables: dict[str, ParsedTable]) -> int | None:
    table = tables.get(block.table_id)
    return table.page if table is not None and table.page is not None else block.page


def _asset_links(
    document: ParsedDocument,
    content_blocks: tuple[ParsedBlock, ...],
    tables: dict[str, ParsedTable],
) -> dict[str, tuple[str, ...]]:
    """Bind at most one reliably nearest layout asset to a block."""
    proposals: dict[str, list[str]] = {}
    for asset in sorted(document.assets, key=lambda item: (item.order, item.asset_id)):
        if asset.page is None:
            continue
        candidates = [block for block in content_blocks if _block_page(block, tables) == asset.page]
        if not candidates:
            continue
        distances = sorted((abs(block.order - asset.order), block.order, block.block_id) for block in candidates)
        if len(distances) > 1 and distances[0][0] == distances[1][0]:
            continue
        proposals.setdefault(distances[0][2], []).append(asset.asset_id)

    layout_tables = _layout_table_ids(tables)
    links: dict[str, tuple[str, ...]] = {}
    for block in content_blocks:
        if block.table_id in layout_tables:
            links[block.block_id] = (block.table_id,)
        elif len(proposals.get(block.block_id, ())) == 1:
            links[block.block_id] = (proposals[block.block_id][0],)
        else:
            links[block.block_id] = ()
    return links


def _prefix(section_path: tuple[str, ...]) -> str:
    return f"标题路径：{' / '.join(section_path)}\n" if section_path else ""


def _max_fitting_end(content: str, start: int, prefix: str, max_tokens: int, counter: TokenCounter) -> int:
    """Find the exact fitting boundary without repeatedly tokenizing the full suffix."""
    best = start
    width = max(1, max_tokens * 4)
    probe = min(len(content), start + width)
    while True:
        if _count(counter, prefix + content[start:probe]) <= max_tokens:
            best = probe
            if probe == len(content):
                return probe
            width *= 2
            probe = min(len(content), start + width)
            continue
        low, high = best + 1, probe - 1
        while low <= high:
            middle = (low + high) // 2
            if _count(counter, prefix + content[start:middle]) <= max_tokens:
                best, low = middle, middle + 1
            else:
                high = middle - 1
        return best


def _split_ranges(content: str, prefix: str, max_tokens: int, counter: TokenCounter) -> tuple[tuple[int, int], ...]:
    if max_tokens <= 0:
        raise ChunkBuildError("max_tokens_invalid")
    ranges: list[tuple[int, int]] = []
    start = 0
    while start < len(content):
        best = _max_fitting_end(content, start, prefix, max_tokens, counter)
        if best == len(content):
            ranges.append((start, len(content)))
            break
        if best <= start:
            raise ChunkBuildError("token_budget_too_small")
        window = content[start:best]
        minimum = max(1, len(window) // 2)
        boundaries = [window.rfind(mark) + len(mark) for mark in ("\n", "。", "！", "？", "；", ";", " ")]
        cut = max((value for value in boundaries if value >= minimum), default=len(window)) + start
        if _count(counter, prefix + content[start:cut]) > max_tokens:
            cut = best
        ranges.append((start, cut))
        start = cut
    return tuple(ranges)


def build_candidate(
    document: ParsedDocument,
    *,
    token_counter: TokenCounter | None,
    max_tokens: int,
) -> ChunkBuildResult:
    if document.status is ParseStatus.QUARANTINED:
        raise ChunkBuildError(f"parsed_document_quarantined:{document.isolation_reason}")
    version_id = derive_version_id(document)
    tables = {table.table_id: table for table in document.tables}
    if len(tables) != len(document.tables):
        raise ChunkBuildError("duplicate_table_id")
    ordered_blocks = tuple(sorted(document.blocks, key=lambda item: (item.order, item.block_id)))
    asset_links = _asset_links(document, ordered_blocks, tables)
    parents: list[ParentChunk] = []
    chunks: list[ChildChunk] = []
    for block in ordered_blocks:
        content, table_id, page, bbox = _parent_content(block, tables)
        asset_ids = asset_links[block.block_id]
        parent_hash = text_hash(content)
        parent_id = _stable_id("par", version_id, block.block_id, parent_hash)
        parent = ParentChunk(parent_id, document.source_id, version_id, block.block_id, block.order, block.kind, content, parent_hash, block.section_path, page, bbox, table_id, asset_ids)
        parents.append(parent)
        prefix = _prefix(block.section_path)
        for child_index, (start, end) in enumerate(_split_ranges(content, prefix, max_tokens, token_counter), start=1):
            citation = make_citation(parent, start, end)
            child_content = prefix + citation.quote
            token_count = _count(token_counter, child_content)
            chunk_id = _stable_id("chk", parent_id, start, end, text_hash(child_content))
            chunks.append(ChildChunk(chunk_id, parent_id, document.source_id, version_id, child_index, child_content, text_hash(child_content), token_count, table_id, asset_ids, citation))
    table_assets = tuple(
        ChunkAsset(
            table.table_id,
            version_id,
            "table",
            text_hash(_render_table(table)),
            "ready",
            table.order,
            table.page,
            table.bbox,
        )
        for table in sorted(document.tables, key=lambda item: (item.order, item.table_id))
        if table.page is not None and table.bbox is not None
    )
    parsed_assets = tuple(
        ChunkAsset(
            asset.asset_id,
            version_id,
            asset.kind,
            asset.content_hash,
            asset.status,
            asset.order,
            asset.page,
            asset.bbox,
        )
        for asset in sorted(document.assets, key=lambda item: (item.order, item.asset_id))
    )
    assets = tuple(sorted(table_assets + parsed_assets, key=lambda item: (item.order, item.asset_id)))
    candidate = ChunkBuildResult(
        derive_document_id(document),
        document.source_id,
        version_id,
        document.content_hash,
        document.status.value,
        tuple(parents),
        tuple(chunks),
        assets,
    )
    from .quality import validate_candidate

    report = validate_candidate(candidate)
    if not report.ok:
        raise ChunkBuildError("candidate_quality_failed:" + ",".join(issue.code for issue in report.issues))
    return candidate
