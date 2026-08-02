from __future__ import annotations

import re

from ..parsed_contracts import ParsedBlock, ParsedTable
from .base import ParseContext, ParseFailure, element_id, finish


def parse_docx(context: ParseContext):
    try:
        from docx import Document
        from docx.oxml.table import CT_Tbl
        from docx.oxml.text.paragraph import CT_P
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:
        raise ParseFailure("dependency_unavailable:python-docx") from exc
    try:
        document = Document(context.path)
    except Exception as exc:
        raise ParseFailure("corrupt_docx") from exc
    blocks, tables, section = [], [], []
    total_chars = total_rows = order = 0
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if not text:
                continue
            style = (paragraph.style.name if paragraph.style else "").lower()
            heading = "heading" in style or "标题" in style
            if heading:
                match = re.search(r"(\d+)", style)
                level = max(1, min(int(match.group(1)) if match else 1, 6))
                section = section[: level - 1] + [text]
            total_chars += len(text)
            order += 1
            blocks.append(ParsedBlock(element_id(context.source_id, "block", order), order, "heading" if heading else "paragraph", text, tuple(section)))
        elif isinstance(child, CT_Tbl):
            table = Table(child, document)
            rows = tuple(tuple(cell.text.strip() for cell in row.cells) for row in table.rows)
            total_rows += len(rows)
            total_chars += sum(len(cell) for row in rows for cell in row)
            if any(any(cell for cell in row) for row in rows):
                order += 1
                table_id = element_id(context.source_id, "table", order)
                tables.append(ParsedTable(table_id, order, rows))
                blocks.append(ParsedBlock(element_id(context.source_id, "block", order), order, "table", "", tuple(section), table_id=table_id))
        if len(blocks) > context.limits.max_blocks or total_rows > context.limits.max_table_rows:
            raise ParseFailure("resource_limit:document_structure")
        if total_chars > context.limits.max_text_chars or any(len(cell) > context.limits.max_cell_chars for table in tables[-1:] for row in table.rows for cell in row):
            raise ParseFailure("resource_limit:text")
    return finish(context, "docx", blocks=tuple(blocks), tables=tuple(tables))
