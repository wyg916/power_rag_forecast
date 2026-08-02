from __future__ import annotations

from datetime import date, datetime, time

from ..parsed_contracts import ParsedBlock, ParsedTable
from .base import ParseContext, ParseFailure, element_id, finish


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return str(value)


def parse_xlsx(context: ParseContext):
    try:
        import openpyxl
    except ImportError as exc:
        raise ParseFailure("dependency_unavailable:openpyxl") from exc
    try:
        workbook = openpyxl.load_workbook(context.path, read_only=True, data_only=True)
    except Exception as exc:
        raise ParseFailure("corrupt_xlsx") from exc
    blocks, tables = [], []
    total_rows = total_chars = order = 0
    try:
        for sheet in workbook.worksheets:
            rows, has_content = [], False
            for values in sheet.iter_rows(values_only=True):
                row = tuple(_cell(value) for value in values)
                total_rows += 1
                total_chars += sum(len(cell) for cell in row)
                if total_rows > context.limits.max_table_rows:
                    raise ParseFailure("resource_limit:table_rows")
                if any(len(cell) > context.limits.max_cell_chars for cell in row) or total_chars > context.limits.max_text_chars:
                    raise ParseFailure("resource_limit:text")
                rows.append(row)
                has_content = has_content or any(row)
            if has_content:
                order += 1
                table_id = element_id(context.source_id, "table", order)
                tables.append(ParsedTable(table_id, order, tuple(rows), sheet_name=sheet.title))
                blocks.append(ParsedBlock(element_id(context.source_id, "block", order), order, "table", "", (sheet.title,), table_id=table_id))
    finally:
        workbook.close()
    return finish(context, "xlsx", blocks=tuple(blocks), tables=tuple(tables))
