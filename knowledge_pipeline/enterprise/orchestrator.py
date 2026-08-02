from __future__ import annotations

from importlib import import_module
from pathlib import Path

from .file_inspector import sha256_file
from .parsed_contracts import ParsedDocument, ParseStatus
from .parsers.base import ParseContext, ParseFailure, ParserLimits, finish


PARSERS = {
    "docx": ("knowledge_pipeline.enterprise.parsers.docx_parser", "parse_docx"),
    "xlsx": ("knowledge_pipeline.enterprise.parsers.xlsx_parser", "parse_xlsx"),
    "html": ("knowledge_pipeline.enterprise.parsers.html_parser", "parse_html"),
    "pdf": ("knowledge_pipeline.enterprise.parsers.pdf_parser", "parse_pdf"),
}


def _quarantined(context: ParseContext, reason: str, parser_name: str = "none") -> ParsedDocument:
    return finish(context, parser_name, status=ParseStatus.QUARANTINED, reason=reason)


def parse_document(
    path: Path,
    *,
    source_id: str,
    detected_format: str,
    limits: ParserLimits | None = None,
) -> ParsedDocument:
    if not source_id.strip():
        raise ValueError("source_id_required")
    limits = limits or ParserLimits()
    path = path.resolve()
    empty_context = ParseContext(path, source_id, detected_format, "", limits)
    if not path.exists() or not path.is_file():
        return _quarantined(empty_context, "source_unavailable")
    try:
        if path.stat().st_size > limits.max_file_bytes:
            return _quarantined(empty_context, "resource_limit:file_bytes")
        content_hash = sha256_file(path)
    except OSError:
        return _quarantined(empty_context, "source_unreadable")
    context = ParseContext(path, source_id, detected_format, content_hash, limits)
    target = PARSERS.get(detected_format)
    if target is None:
        return _quarantined(context, f"unsupported_parser_format:{detected_format}")
    try:
        parser = getattr(import_module(target[0]), target[1])
        return parser(context)
    except ParseFailure as exc:
        return _quarantined(context, str(exc), detected_format)
    except Exception as exc:
        return _quarantined(context, f"parse_error:{exc.__class__.__name__}", detected_format)
