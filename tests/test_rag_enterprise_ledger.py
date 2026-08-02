from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from knowledge_pipeline.enterprise.cli import run
from knowledge_pipeline.enterprise.contracts import AdmissionStatus
from knowledge_pipeline.enterprise.file_inspector import stable_source_id
from knowledge_pipeline.enterprise.ledger import (
    build_source_ledger,
    serialize_ledger,
    write_source_ledger,
)


def _zip(path: Path, members: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, value in members.items():
            archive.writestr(name, value)


def test_ledger_is_deterministic_and_links_content_duplicates(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "B.md").write_text("同一份资料", encoding="utf-8")
    (corpus / "a.md").write_text("同一份资料", encoding="utf-8")
    (corpus / "c.txt").write_text("独立资料", encoding="utf-8")

    first = build_source_ledger(corpus, expected_count=3)
    second = build_source_ledger(corpus, expected_count=3)

    assert serialize_ledger(first) == serialize_ledger(second)
    assert [item.relative_path for item in first] == ["a.md", "B.md", "c.txt"]
    assert first[1].admission_status is AdmissionStatus.DUPLICATE
    assert first[1].duplicate_of_source_id == first[0].source_id
    assert first[1].duplicate_of_path == "a.md"
    assert first[0].source_id == stable_source_id("a.md")


def test_duplicate_canonical_prefers_ready_source_over_path_order(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.bin").write_text("同一份资料", encoding="utf-8")
    (corpus / "z.md").write_text("同一份资料", encoding="utf-8")
    by_name = {entry.file_name: entry for entry in build_source_ledger(corpus)}
    assert by_name["z.md"].admission_status is AdmissionStatus.READY
    assert by_name["a.bin"].admission_status is AdmissionStatus.DUPLICATE
    assert by_name["a.bin"].duplicate_of_source_id == by_name["z.md"].source_id


def test_format_admission_is_fail_closed(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "rule.pdf").write_bytes(b"%PDF-1.7\nbody")
    _zip(corpus / "ordered.docx", {"word/document.xml": "<document/>"})
    _zip(corpus / "table.xlsx", {"xl/workbook.xml": "<workbook/>"})
    _zip(corpus / "manual.ofd", {"OFD.xml": "<ofd/>"})
    (corpus / "scan.jpg").write_bytes(b"\xff\xd8\xff\xe0image")
    (corpus / "wrong.pdf").write_text("not a pdf", encoding="utf-8")
    (corpus / "empty.docx").write_bytes(b"")

    by_name = {entry.file_name: entry for entry in build_source_ledger(corpus)}

    assert by_name["rule.pdf"].admission_status is AdmissionStatus.READY
    assert by_name["ordered.docx"].detected_format == "docx"
    assert by_name["table.xlsx"].admission_status is AdmissionStatus.READY
    assert by_name["manual.ofd"].isolation_reason == "controlled_conversion_required"
    assert by_name["scan.jpg"].isolation_reason == "ocr_required"
    assert by_name["wrong.pdf"].isolation_reason == "declared_format_mismatch"
    assert by_name["empty.docx"].admission_status is AdmissionStatus.CORRUPT


def test_unknown_suffix_can_be_detected_by_magic(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "download.bin").write_bytes(b"\x89PNG\r\n\x1a\nimage")
    entry = build_source_ledger(corpus)[0]
    assert entry.declared_format == "unknown"
    assert entry.detected_format == "png"
    assert entry.isolation_reason == "ocr_required"


def test_missing_or_incomplete_corpus_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="corpus_directory_unavailable"):
        build_source_ledger(tmp_path / "missing", expected_count=83)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "one.md").write_text("one", encoding="utf-8")
    with pytest.raises(ValueError, match="corpus_count_mismatch"):
        build_source_ledger(corpus, expected_count=83)
    with pytest.raises(ValueError, match="invalid_run_id"):
        run(
            SimpleNamespace(
                input=corpus,
                staging_root=tmp_path / "staging",
                run_id="..",
                expected_count=1,
            )
        )
    with pytest.raises(ValueError, match="staging_root_must_not_be_inside_corpus"):
        run(
            SimpleNamespace(
                input=corpus,
                staging_root=corpus / ".runtime",
                run_id="valid_run",
                expected_count=1,
            )
        )


def test_corrupt_files_are_not_used_as_duplicate_canonical_sources(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "one.docx").write_bytes(b"")
    (corpus / "two.docx").write_bytes(b"")
    entries = build_source_ledger(corpus, expected_count=2)
    assert [entry.admission_status for entry in entries] == [
        AdmissionStatus.CORRUPT,
        AdmissionStatus.CORRUPT,
    ]


def test_written_jsonl_is_complete_and_byte_stable(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "政策.md").write_text("政策正文", encoding="utf-8")
    entries = build_source_ledger(corpus, expected_count=1)
    first_path = tmp_path / "one" / "source_ledger.jsonl"
    second_path = tmp_path / "two" / "source_ledger.jsonl"

    first_result = write_source_ledger(entries, first_path)
    original = first_path.read_bytes()
    fixed_time_ns = 1_700_000_000_000_000_000
    os.utime(first_path, ns=(fixed_time_ns, fixed_time_ns))
    unchanged_result = write_source_ledger(entries, first_path)
    second_result = write_source_ledger(entries, second_path)
    row = json.loads(first_path.read_text(encoding="utf-8"))

    assert first_result["entry_count"] == 1
    assert first_result["status_counts"] == {"ready": 1}
    assert first_result["write_status"] == "created"
    assert unchanged_result["write_status"] == "unchanged"
    assert first_path.stat().st_mtime_ns == fixed_time_ns
    assert first_path.read_bytes() == second_path.read_bytes()
    assert row["schema_version"] == "rag-source-ledger/v1"
    assert row["admission_status"] != "published"
    (corpus / "政策.md").write_text("不同正文", encoding="utf-8")
    conflicting = build_source_ledger(corpus, expected_count=1)
    with pytest.raises(ValueError, match="immutable_ledger_conflict"):
        write_source_ledger(conflicting, first_path)
    assert first_path.read_bytes() == original
