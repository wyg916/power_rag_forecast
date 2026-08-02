from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from .contracts import AdmissionStatus, SourceLedgerEntry
from .file_inspector import inspect_source, normalized_relative_path


def _source_files(root: Path) -> list[Path]:
    if not root.exists() or not root.is_dir():
        raise ValueError(f"corpus_directory_unavailable:{root}")
    files = [path for path in root.rglob("*") if path.is_file()]
    return sorted(
        files,
        key=lambda path: (
            normalized_relative_path(path, root).casefold(),
            normalized_relative_path(path, root),
        ),
    )


def build_source_ledger(root: Path, *, expected_count: int | None = None) -> list[SourceLedgerEntry]:
    files = _source_files(root)
    if expected_count is not None and len(files) != expected_count:
        raise ValueError(f"corpus_count_mismatch:expected={expected_count}:actual={len(files)}")
    inspected = [inspect_source(path, root) for path in files]
    groups: dict[str, list[SourceLedgerEntry]] = {}
    for entry in inspected:
        if entry.sha256 and entry.admission_status is not AdmissionStatus.CORRUPT:
            groups.setdefault(entry.sha256, []).append(entry)
    priority = {
        AdmissionStatus.READY: 0,
        AdmissionStatus.QUARANTINED: 1,
        AdmissionStatus.CORRUPT: 2,
    }
    canonical_by_hash = {
        content_hash: min(
            group,
            key=lambda entry: (
                priority.get(entry.admission_status, 3),
                entry.relative_path.casefold(),
                entry.relative_path,
            ),
        )
        for content_hash, group in groups.items()
    }
    entries: list[SourceLedgerEntry] = []
    for entry in inspected:
        canonical = canonical_by_hash.get(entry.sha256)
        if canonical is not None and canonical.source_id != entry.source_id:
            entry = replace(
                entry,
                admission_status=AdmissionStatus.DUPLICATE,
                isolation_reason="duplicate_content",
                duplicate_of_source_id=canonical.source_id,
                duplicate_of_path=canonical.relative_path,
            )
        entries.append(entry)
    return entries


def serialize_ledger(entries: Iterable[SourceLedgerEntry]) -> bytes:
    rows = [
        json.dumps(entry.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for entry in entries
    ]
    return (("\n".join(rows) + "\n") if rows else "").encode("utf-8")


def write_source_ledger(entries: list[SourceLedgerEntry], output_path: Path) -> dict[str, object]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = serialize_ledger(entries)
    try:
        with output_path.open("xb") as handle:
            handle.write(payload)
        write_status = "created"
    except FileExistsError:
        if output_path.read_bytes() != payload:
            raise ValueError(f"immutable_ledger_conflict:{output_path}")
        write_status = "unchanged"
    counts = Counter(entry.admission_status.value for entry in entries)
    return {
        "output_path": str(output_path),
        "entry_count": len(entries),
        "status_counts": dict(sorted(counts.items())),
        "write_status": write_status,
    }
