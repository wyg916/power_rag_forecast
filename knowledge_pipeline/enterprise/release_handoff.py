from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError

from .candidate_orchestrator import (
    FROZEN_MANIFEST_VERSION,
    ORCHESTRATION_VERSION,
    CandidateCorpusArtifact,
)
from .contracts import AdmissionStatus, SCHEMA_VERSION


ENVELOPE_VERSION = "rag-candidate-release-envelope/v1"
MANIFEST_SCHEMA_PATH = Path(__file__).parents[2] / "docs/codex/contracts/rag_candidate_corpus_v1.schema.json"
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
REASON_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")
OUTER_KEYS = {
    "orchestration_version", "candidate_release_id", "tenant_id", "created_at", "source_ledger",
    "embedding_profile", "versions", "counts", "duplicates", "isolations", "candidate_manifest",
    "artifact_sha256",
}
OUTER_COUNT_KEYS = {"ledger", "documents", "chunks", "assets", "duplicates", "isolations"}
LEDGER_KEYS = {
    "source_id", "relative_path", "file_name", "size_bytes", "sha256", "declared_format", "detected_format",
    "admission_status", "isolation_reason", "duplicate_of_source_id", "duplicate_of_path", "schema_version",
}
VERSION_KEYS = {"source_id", "document_id", "version_id", "source_sha256", "content_sha256", "transformed"}
STATUS_VALUES = tuple(status.value for status in AdmissionStatus)


class CandidateReleaseHandoffError(RuntimeError):
    pass


class CandidateReleaseSinkRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class ApprovedEmbeddingArtifact:
    provider: str
    model: str
    approved_version: str
    dimension: int
    model_sha256: str
    sparse_profile: str


@dataclass(frozen=True)
class CandidateReleaseEnvelope:
    value: dict[str, Any]

    def to_json_bytes(self) -> bytes:
        return _canonical_bytes(self.value) + b"\n"


@dataclass(frozen=True)
class CandidateReleaseReceipt:
    tenant_id: str
    release_id: str
    envelope_sha256: str
    stored: bool


class CandidateReleaseSink(Protocol):
    def store(self, envelope: CandidateReleaseEnvelope) -> CandidateReleaseReceipt: ...


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, OverflowError):
        raise CandidateReleaseHandoffError("candidate_artifact_not_json") from None


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _manifest_schema_validate(manifest: Any) -> None:
    try:
        schema = json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)
    except ValidationError:
        raise CandidateReleaseHandoffError("candidate_manifest_schema_invalid") from None
    except (OSError, UnicodeError, json.JSONDecodeError, SchemaError):
        raise CandidateReleaseHandoffError("candidate_manifest_schema_unavailable") from None


def _ledger_facts(serialized_ledger: bytes) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    if not isinstance(serialized_ledger, bytes):
        raise CandidateReleaseHandoffError("source_ledger_payload_invalid")
    try:
        rows = [json.loads(line) for line in serialized_ledger.decode("utf-8").splitlines() if line]
    except (UnicodeError, json.JSONDecodeError):
        raise CandidateReleaseHandoffError("source_ledger_payload_invalid") from None
    if not rows:
        raise CandidateReleaseHandoffError("source_ledger_payload_invalid")
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != LEDGER_KEYS
            or row.get("schema_version") != SCHEMA_VERSION
            or row.get("admission_status") not in STATUS_VALUES
            or not ID_PATTERN.fullmatch(str(row.get("source_id") or ""))
            or row["source_id"] in by_id
            or not SHA256_PATTERN.fullmatch(str(row.get("sha256") or ""))
        ):
            raise CandidateReleaseHandoffError("source_ledger_contract_invalid")
        by_id[row["source_id"]] = row
    counts = Counter(row["admission_status"] for row in rows)
    return by_id, {status: counts[status] for status in STATUS_VALUES}


def _validate_embedding(profile: Any, approval: ApprovedEmbeddingArtifact) -> dict[str, Any]:
    if not isinstance(approval, ApprovedEmbeddingArtifact):
        raise CandidateReleaseHandoffError("embedding_approval_invalid")
    approved = asdict(approval)
    expected = {key: value for key, value in approved.items() if key != "approved_version"}
    if (
        approval.provider != "sentence_transformers"
        or approval.model != "BAAI/bge-large-zh-v1.5"
        or approval.dimension != 1024
        or not ID_PATTERN.fullmatch(approval.approved_version)
        or not SHA256_PATTERN.fullmatch(approval.model_sha256)
        or not approval.sparse_profile
        or len(approval.sparse_profile) > 128
    ):
        raise CandidateReleaseHandoffError("embedding_approval_invalid")
    if profile != expected:
        raise CandidateReleaseHandoffError("embedding_profile_mismatch")
    return approved


def _validate_counts_and_relations(value: dict[str, Any], ledger: dict[str, dict[str, Any]], status: dict[str, int]) -> dict[str, int]:
    manifest = value["candidate_manifest"]
    documents, versions = manifest["documents"], value["versions"]
    chunks, assets = manifest["chunks"], manifest["assets"]
    duplicates, isolations = value["duplicates"], value["isolations"]
    derived = {
        "ledger": len(ledger), "documents": len(documents), "versions": len(versions), "chunks": len(chunks),
        "assets": len(assets), "duplicates": len(duplicates), "isolations": len(isolations),
    }
    outer_counts = value.get("counts")
    if (
        not isinstance(outer_counts, dict)
        or set(outer_counts) != OUTER_COUNT_KEYS
        or any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in outer_counts.values())
        or outer_counts != {key: derived[key] for key in OUTER_COUNT_KEYS}
        or value["source_ledger"].get("status_counts") != status
        or manifest["ledger_summary"] != {"total": len(ledger), **status}
        or derived["documents"] != derived["versions"]
        or derived["ledger"] != derived["documents"] + derived["duplicates"] + derived["isolations"]
    ):
        raise CandidateReleaseHandoffError("candidate_counts_mismatch")

    document_by_source = {item["source_id"]: item for item in documents}
    version_by_id = {item.get("version_id"): item for item in versions if isinstance(item, dict)}
    duplicate_by_source = {item.get("source_id"): item for item in duplicates if isinstance(item, dict)}
    isolation_by_source = {item.get("source_id"): item for item in isolations if isinstance(item, dict)}
    if (
        len(document_by_source) != len(documents)
        or len(version_by_id) != len(versions)
        or len(duplicate_by_source) != len(duplicates)
        or len(isolation_by_source) != len(isolations)
        or set(document_by_source) & set(duplicate_by_source)
        or set(document_by_source) & set(isolation_by_source)
        or set(duplicate_by_source) & set(isolation_by_source)
        or set(document_by_source) | set(duplicate_by_source) | set(isolation_by_source) != set(ledger)
    ):
        raise CandidateReleaseHandoffError("candidate_source_partition_invalid")

    for source_id, document in document_by_source.items():
        version = version_by_id.get(document["version_id"])
        row = ledger[source_id]
        if (
            row["admission_status"] != AdmissionStatus.READY.value
            or row["sha256"] != document["source_sha256"]
            or not isinstance(version, dict)
            or set(version) != VERSION_KEYS
            or (version["source_id"], version["document_id"], version["source_sha256"])
            != (source_id, document["document_id"], document["source_sha256"])
        ):
            raise CandidateReleaseHandoffError("candidate_document_version_invalid")
    for source_id, duplicate in duplicate_by_source.items():
        row, canonical = ledger[source_id], ledger.get(duplicate.get("canonical_source_id"))
        if (
            set(duplicate) != {"source_id", "canonical_source_id", "source_sha256"}
            or row["admission_status"] != AdmissionStatus.DUPLICATE.value
            or canonical is None
            or canonical["admission_status"] != AdmissionStatus.READY.value
            or duplicate["canonical_source_id"] != row["duplicate_of_source_id"]
            or not (duplicate["source_sha256"] == row["sha256"] == canonical["sha256"])
        ):
            raise CandidateReleaseHandoffError("candidate_duplicate_invalid")
    for source_id, isolation in isolation_by_source.items():
        if (
            set(isolation) != {"source_id", "ledger_status", "reason"}
            or isolation["ledger_status"] != ledger[source_id]["admission_status"]
            or isolation["ledger_status"] == AdmissionStatus.DUPLICATE.value
            or not REASON_PATTERN.fullmatch(str(isolation["reason"] or ""))
        ):
            raise CandidateReleaseHandoffError("candidate_isolation_invalid")

    document_ids = {item["document_id"] for item in documents}
    version_ids = set(version_by_id)
    document_versions = {(item["document_id"], item["version_id"]) for item in documents}
    chunk_ids = {item["chunk_id"] for item in chunks}
    asset_ids = {item["asset_id"] for item in assets}
    if (
        len(document_ids) != len(documents)
        or len(chunk_ids) != len(chunks)
        or len(asset_ids) != len(assets)
        or any(
            (item["document_id"], item["version_id"]) not in document_versions
            or hashlib.sha256(item["content"].encode("utf-8")).hexdigest() != item["content_hash"]
            or item["citation"]["version_id"] != item["version_id"]
            or hashlib.sha256(item["citation"]["quote"].encode("utf-8")).hexdigest()
            != item["citation"]["content_hash"]
            or (item["citation"].get("asset_id") is not None and item["citation"]["asset_id"] not in asset_ids)
            for item in chunks
        )
        or any(item["version_id"] not in version_ids for item in assets)
    ):
        raise CandidateReleaseHandoffError("candidate_record_relations_invalid")
    return derived


def _build_release_envelope(
    artifact: CandidateCorpusArtifact,
    *,
    serialized_ledger: bytes,
    expected_tenant_id: str,
    expected_release_id: str,
    approved_embedding: ApprovedEmbeddingArtifact,
) -> CandidateReleaseEnvelope:
    if not isinstance(artifact, CandidateCorpusArtifact) or not isinstance(artifact.value, dict):
        raise CandidateReleaseHandoffError("candidate_artifact_type_invalid")
    value = artifact.value
    if set(value) != OUTER_KEYS or value.get("orchestration_version") != ORCHESTRATION_VERSION:
        raise CandidateReleaseHandoffError("candidate_artifact_schema_invalid")
    outer = dict(value)
    stored_artifact_hash = outer.pop("artifact_sha256")
    artifact_hash = _hash(outer)
    if stored_artifact_hash != artifact_hash:
        raise CandidateReleaseHandoffError("candidate_artifact_hash_mismatch")

    manifest = value.get("candidate_manifest")
    _manifest_schema_validate(manifest)
    manifest_base = dict(manifest)
    stored_corpus_hash = manifest_base.pop("corpus_sha256")
    corpus_hash = _hash(manifest_base)
    if stored_corpus_hash != corpus_hash:
        raise CandidateReleaseHandoffError("candidate_corpus_hash_mismatch")

    if (
        not isinstance(expected_tenant_id, str)
        or not isinstance(expected_release_id, str)
        or not ID_PATTERN.fullmatch(expected_tenant_id)
        or not ID_PATTERN.fullmatch(expected_release_id)
        or value.get("tenant_id") != expected_tenant_id
        or value.get("candidate_release_id") != expected_release_id
        or manifest.get("tenant_id") != expected_tenant_id
        or manifest.get("candidate_release_id") != expected_release_id
        or manifest.get("manifest_version") != FROZEN_MANIFEST_VERSION
    ):
        raise CandidateReleaseHandoffError("candidate_identity_mismatch")

    source_ledger = value.get("source_ledger")
    if not isinstance(source_ledger, dict) or set(source_ledger) != {"schema_version", "sha256", "status_counts"}:
        raise CandidateReleaseHandoffError("source_ledger_contract_invalid")
    ledger, status = _ledger_facts(serialized_ledger)
    ledger_hash = hashlib.sha256(serialized_ledger).hexdigest()
    if source_ledger["schema_version"] != SCHEMA_VERSION or source_ledger["sha256"] != ledger_hash:
        raise CandidateReleaseHandoffError("source_ledger_hash_mismatch")

    embedding = _validate_embedding(value.get("embedding_profile"), approved_embedding)
    if manifest.get("embedding_profile") != value["embedding_profile"]:
        raise CandidateReleaseHandoffError("embedding_profile_mismatch")
    counts = _validate_counts_and_relations(value, ledger, status)
    envelope_base = {
        "envelope_version": ENVELOPE_VERSION,
        "tenant_id": expected_tenant_id,
        "candidate_release_id": expected_release_id,
        "release_status": "candidate",
        "created_at": value["created_at"],
        "schemas": {
            "source_ledger": SCHEMA_VERSION,
            "orchestration": ORCHESTRATION_VERSION,
            "frozen_corpus": FROZEN_MANIFEST_VERSION,
        },
        "hashes": {
            "ledger_sha256": ledger_hash,
            "corpus_sha256": corpus_hash,
            "manifest_sha256": _hash(manifest),
            "artifact_sha256": artifact_hash,
        },
        "embedding": embedding,
        "counts": counts,
        "candidate_artifact": json.loads(_canonical_bytes(value)),
    }
    return CandidateReleaseEnvelope(envelope_base | {"envelope_sha256": _hash(envelope_base)})


def build_candidate_release_envelope(
    artifact: CandidateCorpusArtifact,
    *,
    serialized_ledger: bytes,
    expected_tenant_id: str,
    expected_release_id: str,
    approved_embedding: ApprovedEmbeddingArtifact,
) -> CandidateReleaseEnvelope:
    try:
        return _build_release_envelope(
            artifact,
            serialized_ledger=serialized_ledger,
            expected_tenant_id=expected_tenant_id,
            expected_release_id=expected_release_id,
            approved_embedding=approved_embedding,
        )
    except CandidateReleaseHandoffError:
        raise
    except Exception:
        raise CandidateReleaseHandoffError("candidate_handoff_internal_error") from None


def handoff_candidate_release(
    artifact: CandidateCorpusArtifact,
    *,
    serialized_ledger: bytes,
    expected_tenant_id: str,
    expected_release_id: str,
    approved_embedding: ApprovedEmbeddingArtifact,
    sink: CandidateReleaseSink,
) -> CandidateReleaseEnvelope:
    envelope = build_candidate_release_envelope(
        artifact,
        serialized_ledger=serialized_ledger,
        expected_tenant_id=expected_tenant_id,
        expected_release_id=expected_release_id,
        approved_embedding=approved_embedding,
    )
    try:
        receipt = sink.store(envelope)
    except CandidateReleaseSinkRejected:
        raise CandidateReleaseHandoffError("candidate_sink_rejected") from None
    except Exception:
        raise CandidateReleaseHandoffError("candidate_sink_internal_error") from None
    if (
        not isinstance(receipt, CandidateReleaseReceipt)
        or receipt.tenant_id != expected_tenant_id
        or receipt.release_id != expected_release_id
        or receipt.envelope_sha256 != envelope.value["envelope_sha256"]
        or receipt.stored is not True
    ):
        raise CandidateReleaseHandoffError("candidate_sink_receipt_invalid")
    return envelope
