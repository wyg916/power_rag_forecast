from __future__ import annotations

import hashlib
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .contracts import AdmissionStatus, SourceLedgerEntry


DIRECT_FORMATS = {"pdf", "docx", "xlsx", "html", "txt", "md"}
CONVERSION_FORMATS = {"doc", "xls", "wps", "et", "ofd"}
IMAGE_FORMATS = {"jpg", "jpeg", "png"}
KNOWN_FORMATS = DIRECT_FORMATS | CONVERSION_FORMATS | IMAGE_FORMATS
OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class FormatProbe:
    declared_format: str
    detected_format: str
    error: str = ""


def normalized_relative_path(path: Path, root: Path) -> str:
    relative = path.relative_to(root).as_posix()
    return unicodedata.normalize("NFC", relative)


def stable_source_id(relative_path: str) -> str:
    identity = unicodedata.normalize("NFC", relative_path).replace("\\", "/").casefold()
    return "src_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _declared_format(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return suffix if suffix in KNOWN_FORMATS else "unknown"


def _zip_format(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            names = {name.replace("\\", "/").casefold() for name in archive.namelist()}
    except (OSError, zipfile.BadZipFile):
        return "corrupt_zip"
    if any(name.startswith("word/") for name in names):
        return "docx"
    if any(name.startswith("xl/") for name in names):
        return "xlsx"
    if "ofd.xml" in names or any(name.endswith("/ofd.xml") for name in names):
        return "ofd"
    return "zip"


def probe_format(path: Path) -> FormatProbe:
    declared = _declared_format(path)
    try:
        with path.open("rb") as handle:
            head = handle.read(8192)
    except OSError as exc:
        return FormatProbe(declared, "unreadable", exc.__class__.__name__)
    if not head:
        return FormatProbe(declared, "empty", "empty_file")
    if head.startswith(b"%PDF-"):
        detected = "pdf"
    elif head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        detected = _zip_format(path)
    elif head.startswith(OLE_SIGNATURE):
        detected = declared if declared in {"doc", "xls", "wps", "et"} else "ole"
    elif head.startswith(b"\xff\xd8\xff"):
        detected = "jpg"
    elif head.startswith(PNG_SIGNATURE):
        detected = "png"
    else:
        lowered = head.lower()
        if b"<html" in lowered or b"<!doctype html" in lowered:
            detected = "html"
        elif declared in {"txt", "md"}:
            try:
                head.decode("utf-8")
                detected = declared
            except UnicodeDecodeError:
                detected = "unknown"
        else:
            detected = "unknown"
    error = "invalid_container" if detected == "corrupt_zip" else ""
    return FormatProbe(declared, detected, error)


def _admission(probe: FormatProbe) -> tuple[AdmissionStatus, str]:
    if probe.detected_format in {"empty", "unreadable", "corrupt_zip"}:
        return AdmissionStatus.CORRUPT, probe.error or probe.detected_format
    if probe.declared_format != "unknown" and probe.detected_format != probe.declared_format:
        return AdmissionStatus.QUARANTINED, "declared_format_mismatch"
    if probe.detected_format in DIRECT_FORMATS:
        return AdmissionStatus.READY, ""
    if probe.detected_format in CONVERSION_FORMATS:
        return AdmissionStatus.QUARANTINED, "controlled_conversion_required"
    if probe.detected_format in IMAGE_FORMATS:
        return AdmissionStatus.QUARANTINED, "ocr_required"
    return AdmissionStatus.QUARANTINED, "unsupported_or_unknown_format"


def inspect_source(path: Path, root: Path) -> SourceLedgerEntry:
    relative_path = normalized_relative_path(path, root)
    source_id = stable_source_id(relative_path)
    try:
        size_bytes = path.stat().st_size
        content_hash = sha256_file(path)
    except OSError as exc:
        return SourceLedgerEntry(
            source_id=source_id,
            relative_path=relative_path,
            file_name=path.name,
            size_bytes=0,
            sha256="",
            declared_format=_declared_format(path),
            detected_format="unreadable",
            admission_status=AdmissionStatus.CORRUPT,
            isolation_reason=exc.__class__.__name__,
        )
    probe = probe_format(path)
    status, reason = _admission(probe)
    return SourceLedgerEntry(
        source_id=source_id,
        relative_path=relative_path,
        file_name=path.name,
        size_bytes=size_bytes,
        sha256=content_hash,
        declared_format=probe.declared_format,
        detected_format=probe.detected_format,
        admission_status=status,
        isolation_reason=reason,
    )
