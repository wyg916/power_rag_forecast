from __future__ import annotations

from ..parsed_contracts import ParsedAsset, ParsedBlock, ParsedTable
from .base import ParseContext, ParseFailure, decode_text, element_id, finish


def parse_html(context: ParseContext):
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise ParseFailure("dependency_unavailable:beautifulsoup4") from exc
    text = decode_text(context.path.read_bytes())
    if len(text) > context.limits.max_text_chars:
        raise ParseFailure("resource_limit:text")
    soup = BeautifulSoup(text, "html.parser")
    blocks, tables, assets = [], [], []
    section, order, total_rows = [], 0, 0

    def add_text(kind: str, value: str) -> None:
        nonlocal order, section
        if not value:
            return
        order += 1
        if kind == "heading":
            section = [value]
        blocks.append(ParsedBlock(element_id(context.source_id, "block", order), order, kind, value, tuple(section)))

    if soup.title:
        add_text("title", soup.title.get_text(" ", strip=True))
    body = soup.body or soup
    for node in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "table", "img"]):
        if node.name != "table" and node.find_parent("table") is not None:
            continue
        if node.name == "table":
            if node.find_parent("table") is not None:
                continue
            rows = []
            for tr in node.find_all("tr"):
                if tr.find_parent("table") is not node:
                    continue
                row = tuple(cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"], recursive=False))
                if row:
                    rows.append(row)
            total_rows += len(rows)
            if total_rows > context.limits.max_table_rows or any(len(cell) > context.limits.max_cell_chars for row in rows for cell in row):
                raise ParseFailure("resource_limit:table")
            if rows:
                order += 1
                table_id = element_id(context.source_id, "table", order)
                tables.append(ParsedTable(table_id, order, tuple(rows)))
                blocks.append(ParsedBlock(element_id(context.source_id, "block", order), order, "table", "", tuple(section), table_id=table_id))
        elif node.name == "img":
            order += 1
            assets.append(ParsedAsset(element_id(context.source_id, "asset", order), order, "image", "discovered", source_ref=str(node.get("src") or ""), alt_text=str(node.get("alt") or "")))
        else:
            add_text("heading" if node.name.startswith("h") else "paragraph", node.get_text(" ", strip=True))
        if len(blocks) > context.limits.max_blocks or len(assets) > context.limits.max_assets:
            raise ParseFailure("resource_limit:document_structure")
    return finish(context, "html", blocks=tuple(blocks), tables=tuple(tables), assets=tuple(assets))
