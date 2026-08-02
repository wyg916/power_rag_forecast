from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from jsonschema import Draft202012Validator, FormatChecker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from knowledge_pipeline.enterprise.candidate_orchestrator import (
    DocumentMetadata,
    EmbeddingProfile,
    ParsedSourceInput,
    build_candidate_corpus,
)
from knowledge_pipeline.enterprise.chunking import build_candidate
from knowledge_pipeline.enterprise.contracts import AdmissionStatus, SourceLedgerEntry
from knowledge_pipeline.enterprise.frozen_export import export_frozen_records
from knowledge_pipeline.enterprise.ledger import build_source_ledger, serialize_ledger
from knowledge_pipeline.enterprise.orchestrator import parse_document
from knowledge_pipeline.enterprise.parsed_contracts import ParsedDocument, ParseStatus


EXPECTED_SOURCE_ROOT = Path("E:/智能运营分析项目/知识库").resolve()
EXPECTED_RUNTIME_ROOT = Path("E:/智能运营分析项目/.runtime/rag").resolve()
EXPECTED_MODEL_ROOT = Path("E:/智能运营分析项目/bge-large-zh-v1.5").resolve()
EXPECTED_LEDGER_SHA256 = "ee61af9a0aa4509b2e7947e37c99004e2029fbfd69a55fe663e8acacafebf7d6"
EXPECTED_MODEL_MANIFEST_SHA256 = "a6854a4b265bc6c7159d02927ece3548e63e7b57cf49deee2a77b94bbb0ec3fa"
RELEASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
CONTROL_CODEPOINTS = frozenset(range(0, 32)) | frozenset(range(127, 160))


class CandidateCorpusRunError(RuntimeError):
    pass


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_ledger(path: Path) -> tuple[list[SourceLedgerEntry], bytes]:
    try:
        payload = path.read_bytes()
        rows = [json.loads(line) for line in payload.decode("utf-8").splitlines() if line]
        entries = []
        for row in rows:
            row["admission_status"] = AdmissionStatus(row["admission_status"])
            entries.append(SourceLedgerEntry(**row))
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise CandidateCorpusRunError("source_ledger_invalid") from exc
    if len(entries) != 83 or serialize_ledger(entries) != payload:
        raise CandidateCorpusRunError("source_ledger_not_canonical")
    if _sha256_bytes(payload) != EXPECTED_LEDGER_SHA256:
        raise CandidateCorpusRunError("source_ledger_hash_mismatch")
    return entries, payload


def verify_source_snapshot(source_root: Path, expected_payload: bytes) -> None:
    try:
        current = serialize_ledger(build_source_ledger(source_root, expected_count=83))
    except (OSError, ValueError) as exc:
        raise CandidateCorpusRunError("source_snapshot_unavailable") from exc
    if current != expected_payload:
        raise CandidateCorpusRunError("source_snapshot_drift")


def model_manifest_sha256(model_root: Path) -> str:
    files = sorted(path for path in model_root.rglob("*") if path.is_file())
    if not files:
        raise CandidateCorpusRunError("embedding_model_files_missing")
    manifest: list[dict[str, Any]] = []
    for path in files:
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(model_root).as_posix()
        except ValueError as exc:
            raise CandidateCorpusRunError("embedding_model_file_escaped_root") from exc
        size = resolved.stat().st_size
        if size < 1:
            raise CandidateCorpusRunError("embedding_model_zero_byte_file")
        manifest.append({"path": relative, "bytes": size, "sha256": _sha256_file(resolved)})
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(canonical)


def _document_text(document: ParsedDocument) -> str:
    values = [block.text for block in document.blocks if block.text]
    values.extend(cell for table in document.tables for row in table.rows for cell in row if cell)
    return "\n".join(values)


def text_quality_issue(document: ParsedDocument) -> str:
    text = _document_text(document)
    if not text.strip():
        return "empty_extracted_text"
    if "\ufffd" in text:
        return "replacement_character_detected"
    forbidden_controls = sum(ord(char) in CONTROL_CODEPOINTS and char not in "\n\r\t" for char in text)
    if forbidden_controls:
        return "forbidden_control_character_detected"
    private_use = sum(0xE000 <= ord(char) <= 0xF8FF for char in text)
    if private_use:
        return "private_use_character_detected"
    meaningful = sum(char.isalnum() or "\u3400" <= char <= "\u9fff" for char in text)
    if len(text) >= 100 and meaningful / len(text) < 0.25:
        return "low_meaningful_character_ratio"
    return ""


def _domain(title: str) -> str:
    rules = (
        (("储能", "充电"), "energy-storage"),
        (("绿电", "绿证", "非化石", "可再生"), "green-power"),
        (("风电", "光伏", "新能源"), "renewable-development"),
        (("电价", "交易", "电力市场", "输电权"), "power-market"),
        (("电网", "监管"), "grid-regulation"),
    )
    for keywords, domain in rules:
        if any(keyword in title for keyword in keywords):
            return domain
    return "energy-policy"


def _load_token_counter(model_root: Path) -> Callable[[str], int]:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(
            str(model_root), local_files_only=True, trust_remote_code=False, use_fast=True
        )
    except Exception as exc:
        raise CandidateCorpusRunError("embedding_tokenizer_load_failed") from exc
    if not getattr(tokenizer, "is_fast", False):
        raise CandidateCorpusRunError("embedding_fast_tokenizer_required")

    def count(text: str) -> int:
        encoded = tokenizer(
            text,
            add_special_tokens=True,
            truncation=False,
            return_attention_mask=False,
            return_token_type_ids=False,
            verbose=False,
        )
        return len(encoded["input_ids"])

    return count


def _parse_ready_sources(
    entries: Iterable[SourceLedgerEntry],
    source_root: Path,
    created_at: str,
) -> tuple[dict[str, ParsedSourceInput], dict[str, DocumentMetadata], list[dict[str, Any]]]:
    parsed_sources: dict[str, ParsedSourceInput] = {}
    metadata: dict[str, DocumentMetadata] = {}
    probes: list[dict[str, Any]] = []
    for entry in entries:
        if entry.admission_status is not AdmissionStatus.READY:
            continue
        source_path = (source_root / Path(entry.relative_path)).resolve()
        try:
            source_path.relative_to(source_root)
        except ValueError as exc:
            raise CandidateCorpusRunError("source_path_escaped_root") from exc
        document = parse_document(
            source_path,
            source_id=entry.source_id,
            detected_format=entry.detected_format,
        )
        quality_issue = ""
        if document.status is ParseStatus.READY:
            quality_issue = text_quality_issue(document)
            if quality_issue:
                document = replace(
                    document,
                    status=ParseStatus.QUARANTINED,
                    isolation_reason=f"text_quality_failed:{quality_issue}",
                )
        parsed_sources[entry.source_id] = ParsedSourceInput(entry.source_id, entry.sha256, document)
        metadata[entry.source_id] = DocumentMetadata(
            entry.source_id,
            Path(entry.relative_path).name,
            _domain(entry.file_name),
            created_at,
        )
        probes.append(
            {
                "source_id": entry.source_id,
                "relative_path": entry.relative_path,
                "detected_format": entry.detected_format,
                "parser": document.parser_name,
                "parse_status": document.status.value,
                "isolation_reason": document.isolation_reason,
                "quality_issue": quality_issue,
                "blocks": len(document.blocks),
                "tables": len(document.tables),
                "assets": len(document.assets),
                "pages": document.page_count,
                "characters": len(_document_text(document)),
            }
        )
    return parsed_sources, metadata, probes


def _validate_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CandidateCorpusRunError("created_at_invalid") from exc
    if parsed.tzinfo is None:
        raise CandidateCorpusRunError("created_at_timezone_required")


def _validate_paths(source_root: Path, runtime_root: Path, model_root: Path) -> None:
    if source_root.resolve() != EXPECTED_SOURCE_ROOT:
        raise CandidateCorpusRunError("source_root_rejected")
    if runtime_root.resolve() != EXPECTED_RUNTIME_ROOT:
        raise CandidateCorpusRunError("runtime_root_rejected")
    if model_root.resolve() != EXPECTED_MODEL_ROOT:
        raise CandidateCorpusRunError("embedding_model_root_rejected")
    if not source_root.is_dir() or not model_root.is_dir():
        raise CandidateCorpusRunError("required_input_root_unavailable")


def _check_immutable(path: Path, payload: bytes) -> str:
    if not path.exists():
        return "create"
    if not path.is_file() or path.read_bytes() != payload:
        raise CandidateCorpusRunError(f"immutable_output_conflict:{path.name}")
    return "unchanged"


def write_immutable(path: Path, payload: bytes) -> str:
    disposition = _check_immutable(path, payload)
    if disposition == "unchanged":
        return disposition
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise CandidateCorpusRunError(f"immutable_output_race:{path.name}") from exc
    return "created"


def build_run(args: argparse.Namespace) -> dict[str, Any]:
    source_root, runtime_root, model_root = (
        args.source_root.resolve(), args.runtime_root.resolve(), args.model_root.resolve()
    )
    _validate_paths(source_root, runtime_root, model_root)
    _validate_timestamp(args.created_at)
    if not RELEASE_ID_RE.fullmatch(args.release_id):
        raise CandidateCorpusRunError("release_id_invalid")
    entries, ledger_payload = load_ledger(args.ledger.resolve())
    verify_source_snapshot(source_root, ledger_payload)
    model_hash = model_manifest_sha256(model_root)
    if model_hash != args.embedding_manifest_sha256 or model_hash != EXPECTED_MODEL_MANIFEST_SHA256:
        raise CandidateCorpusRunError("embedding_model_manifest_mismatch")

    parsed, metadata, probes = _parse_ready_sources(entries, source_root, args.created_at)
    token_counter = _load_token_counter(model_root)
    artifact = build_candidate_corpus(
        ledger_entries=entries,
        parsed_sources=parsed,
        document_metadata=metadata,
        candidate_release_id=args.release_id,
        tenant_id="default",
        created_at=args.created_at,
        embedding_profile=EmbeddingProfile(
            "sentence_transformers",
            "BAAI/bge-large-zh-v1.5",
            1024,
            model_hash,
            "bm25-zh-v1",
        ),
        candidate_builder=lambda document: build_candidate(
            document, token_counter=token_counter, max_tokens=args.max_tokens
        ),
        frozen_exporter=export_frozen_records,
    )
    schema = json.loads(
        (PROJECT_ROOT / "docs/codex/contracts/rag_candidate_corpus_v1.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(artifact.candidate_manifest)
    counts = artifact.value["counts"]
    if counts["documents"] + counts["duplicates"] + counts["isolations"] != 83:
        raise CandidateCorpusRunError("candidate_terminal_count_mismatch")
    if counts["documents"] < 1:
        raise CandidateCorpusRunError("candidate_documents_empty")

    artifact_payload = artifact.to_json_bytes()
    parse_counts = Counter(probe["parse_status"] for probe in probes)
    reason_counts = Counter(item["reason"] for item in artifact.value["isolations"])
    report = {
        "status": "PASS",
        "release_id": args.release_id,
        "tenant_id": "default",
        "created_at": args.created_at,
        "source_ledger_sha256": _sha256_bytes(ledger_payload),
        "embedding_manifest_sha256": model_hash,
        "max_tokens": args.max_tokens,
        "counts": counts,
        "parse_status_counts": dict(sorted(parse_counts.items())),
        "isolation_reason_counts": dict(sorted(reason_counts.items())),
        "candidate_corpus_sha256": artifact.candidate_manifest["corpus_sha256"],
        "candidate_artifact_sha256": artifact.value["artifact_sha256"],
        "candidate_file_sha256": _sha256_bytes(artifact_payload),
        "network_calls": 0,
        "model_weight_deserializations": 0,
        "source_writes": 0,
        "probes": probes,
    }
    report_payload = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    release_root = (runtime_root / "releases" / args.release_id).resolve()
    try:
        release_root.relative_to(runtime_root)
    except ValueError as exc:
        raise CandidateCorpusRunError("release_output_escaped_runtime_root") from exc
    artifact_path = release_root / "candidate_corpus.json"
    report_path = release_root / "candidate_build_report.json"
    _check_immutable(artifact_path, artifact_payload)
    _check_immutable(report_path, report_payload)
    artifact_disposition = write_immutable(artifact_path, artifact_payload)
    report_disposition = write_immutable(report_path, report_payload)
    return {
        "status": "PASS",
        "release_id": args.release_id,
        "artifact_path": str(artifact_path),
        "report_path": str(report_path),
        "artifact_write": artifact_disposition,
        "report_write": report_disposition,
        "counts": counts,
        "candidate_file_sha256": report["candidate_file_sha256"],
        "candidate_corpus_sha256": report["candidate_corpus_sha256"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the immutable RAG-R1 Candidate Corpus.")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=EXPECTED_SOURCE_ROOT)
    parser.add_argument("--runtime-root", type=Path, default=EXPECTED_RUNTIME_ROOT)
    parser.add_argument("--model-root", type=Path, default=EXPECTED_MODEL_ROOT)
    parser.add_argument("--embedding-manifest-sha256", default=EXPECTED_MODEL_MANIFEST_SHA256)
    parser.add_argument("--release-id", default="RAG-R1")
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--max-tokens", type=int, default=480)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not SHA256_RE.fullmatch(args.embedding_manifest_sha256) or not 32 <= args.max_tokens <= 510:
        raise CandidateCorpusRunError("candidate_parameters_invalid")
    result = build_run(args)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
