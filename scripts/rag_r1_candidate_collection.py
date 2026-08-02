from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import ssl
import sys
import unicodedata
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import numpy as np
from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from knowledge_pipeline.enterprise.candidate_orchestrator import CandidateCorpusArtifact
from knowledge_pipeline.enterprise.release_handoff import (
    ApprovedEmbeddingArtifact,
    build_candidate_release_envelope,
)
from scripts.rag_r1_candidate_corpus import (
    EXPECTED_LEDGER_SHA256,
    EXPECTED_MODEL_MANIFEST_SHA256,
    model_manifest_sha256,
    write_immutable,
)


EXPECTED_RELEASE_ROOT = Path("E:/智能运营分析项目/.runtime/rag/releases/RAG-R1").resolve()
EXPECTED_MODEL_ROOT = Path("E:/智能运营分析项目/bge-large-zh-v1.5").resolve()
EXPECTED_QDRANT_ROOT = Path("E:/智能运营分析项目_运行资产/rag-r1/qdrant").resolve()
EXPECTED_CANDIDATE_FILE_SHA256 = "ed5f62ad50a36207ca7d0e729ae2bfb054e276b40816d8ac1da04eb376468ed7"
EMBEDDING_VERSION = "sha256:" + EXPECTED_MODEL_MANIFEST_SHA256
COLLECTION = "rag_chunks_RAG-R1"
ALIAS = "rag_chunks_current"
RELEASE_ID = "RAG-R1"
TENANT_ID = "default"
SHARD_SIZE = 128
INFERENCE_BATCH_SIZE = 16
UPSERT_BATCH_SIZE = 16
RETRIEVE_BATCH_SIZE = 1024
RETRIEVE_MIN_BATCH_SIZE = 64
NAMESPACE = uuid.UUID("53eaee8d-794f-4a90-b8c6-1efda7fe51ff")
TOKEN_RE = re.compile(r"[\u3400-\u9fff]+|[a-z0-9]+(?:[._-][a-z0-9]+)*")
PAYLOAD_INDEXES: tuple[tuple[str, str], ...] = (
    ("tenant_id", "keyword"),
    ("release_id", "keyword"),
    ("status", "keyword"),
    ("acl_fingerprint", "keyword"),
    ("acl_public", "bool"),
    ("acl_user_ids", "keyword"),
    ("acl_roles", "keyword"),
    ("valid_from", "datetime"),
    ("valid_to", "datetime"),
    ("embedding_provider", "keyword"),
    ("embedding_model", "keyword"),
    ("embedding_version", "keyword"),
    ("embedding_dimension", "integer"),
    ("sparse_profile", "keyword"),
    ("domain", "keyword"),
    ("source_type", "keyword"),
    ("document_id", "keyword"),
    ("version_id", "keyword"),
    ("chunk_id", "keyword"),
    ("parent_chunk_id", "keyword"),
    ("content_hash", "keyword"),
)


class CandidateCollectionError(RuntimeError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def tokenize_zh(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    tokens: list[str] = []
    for match in TOKEN_RE.finditer(normalized):
        value = match.group(0)
        if "\u3400" <= value[0] <= "\u9fff":
            tokens.extend(value)
            tokens.extend(value[index : index + 2] for index in range(len(value) - 1))
        else:
            tokens.append(value)
    return tuple(tokens)


def build_bm25_profile(chunks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    document_frequency: Counter[str] = Counter()
    lengths: list[int] = []
    for chunk in chunks:
        tokens = tokenize_zh(str(chunk["content"]))
        lengths.append(len(tokens))
        document_frequency.update(set(tokens))
    count = len(chunks)
    vocabulary = sorted(document_frequency)
    idf = [
        round(math.log(1.0 + (count - document_frequency[token] + 0.5) / (document_frequency[token] + 0.5)), 8)
        for token in vocabulary
    ]
    profile_base = {
        "profile": "bm25-zh-v1",
        "tokenizer": "nfkc-lower-cjk-unigram-bigram-alnum/v1",
        "k1": 1.2,
        "b": 0.75,
        "chunk_count": count,
        "empty_sparse_chunks": sum(length == 0 for length in lengths),
        "average_document_length": round(sum(lengths) / count, 8),
        "vocabulary": vocabulary,
        "idf": idf,
    }
    return profile_base | {"profile_sha256": _sha256_bytes(_canonical_bytes(profile_base))}


def sparse_vector(text: str, profile: Mapping[str, Any]) -> dict[str, list[Any]]:
    vocabulary = profile["vocabulary"]
    idf = profile["idf"]
    lookup = {token: index + 1 for index, token in enumerate(vocabulary)}
    idf_by_index = {index + 1: float(value) for index, value in enumerate(idf)}
    counts = Counter(token for token in tokenize_zh(text) if token in lookup)
    length = sum(counts.values())
    if not counts or length < 1:
        return {"indices": [], "values": []}
    denominator_scale = float(profile["k1"]) * (
        1.0 - float(profile["b"])
        + float(profile["b"]) * length / float(profile["average_document_length"])
    )
    weighted = []
    for token, frequency in counts.items():
        index = lookup[token]
        value = idf_by_index[index] * (
            (frequency * (float(profile["k1"]) + 1.0)) / (frequency + denominator_scale)
        )
        weighted.append((index, round(value, 8)))
    weighted.sort()
    return {
        "indices": [item[0] for item in weighted],
        "values": [item[1] for item in weighted],
    }


def _ordered_chunks(artifact: Mapping[str, Any]) -> list[dict[str, Any]]:
    chunks = [dict(item) for item in artifact["candidate_manifest"]["chunks"]]
    ordered = sorted(chunks, key=lambda item: (int(item["token_count"]), str(item["chunk_id"])))
    if len(ordered) != 8339 or len({item["chunk_id"] for item in ordered}) != len(ordered):
        raise CandidateCollectionError("candidate_chunk_set_invalid")
    return ordered


def _parent_contents(chunks: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        grouped[str(chunk["parent_chunk_id"])].append(chunk)
    parents: dict[str, str] = {}
    for parent_id, children in grouped.items():
        ordered = sorted(children, key=lambda item: int(item["citation"]["char_start"]))
        expected = 0
        parts: list[str] = []
        for child in ordered:
            citation = child["citation"]
            if int(citation["char_start"]) != expected:
                raise CandidateCollectionError("parent_locator_gap_or_overlap")
            quote_value = str(citation["quote"])
            expected = int(citation["char_end"])
            if expected - int(citation["char_start"]) != len(quote_value):
                raise CandidateCollectionError("parent_locator_quote_mismatch")
            parts.append(quote_value)
        parents[parent_id] = "".join(parts)
    return parents


def _acl_fingerprint(acl: Mapping[str, Any]) -> str:
    value = {
        "visibility": acl["visibility"],
        "roles": sorted(acl["roles"]),
        "users": sorted(acl["users"]),
    }
    return _sha256_bytes(_canonical_bytes(value))


def build_payloads(
    artifact: Mapping[str, Any],
    ledger_rows: Sequence[Mapping[str, Any]],
    candidate_file_sha256: str,
) -> dict[str, dict[str, Any]]:
    manifest = artifact["candidate_manifest"]
    documents = {item["document_id"]: item for item in manifest["documents"]}
    versions = {item["version_id"]: item for item in artifact["versions"]}
    ledger = {item["source_id"]: item for item in ledger_rows}
    parents = _parent_contents(manifest["chunks"])
    payloads: dict[str, dict[str, Any]] = {}
    for chunk in manifest["chunks"]:
        document = documents[chunk["document_id"]]
        version = versions[chunk["version_id"]]
        source = ledger[version["source_id"]]
        acl = document["acl"]
        payloads[chunk["chunk_id"]] = {
            "tenant_id": TENANT_ID,
            "release_id": RELEASE_ID,
            "status": "published",
            "source_id": version["source_id"],
            "source_type": source["detected_format"],
            "document_id": chunk["document_id"],
            "version_id": chunk["version_id"],
            "chunk_id": chunk["chunk_id"],
            "parent_chunk_id": chunk["parent_chunk_id"],
            "title": document["title"],
            "domain": document["domain"],
            "content": chunk["content"],
            "parent_content": parents[chunk["parent_chunk_id"]],
            "content_hash": chunk["content_hash"],
            "token_count": chunk["token_count"],
            "citation": chunk["citation"],
            "acl_fingerprint": _acl_fingerprint(acl),
            "acl_public": acl["visibility"] == "tenant",
            "acl_roles": sorted(acl["roles"]),
            "acl_user_ids": sorted(acl["users"]),
            "valid_from": document["effective_from"],
            "valid_to": document.get("effective_to"),
            "embedding_provider": "sentence_transformers",
            "embedding_model": "BAAI/bge-large-zh-v1.5",
            "embedding_version": EMBEDDING_VERSION,
            "embedding_dimension": 1024,
            "sparse_profile": "bm25-zh-v1",
            "candidate_file_sha256": candidate_file_sha256,
        }
    if len(payloads) != len(manifest["chunks"]):
        raise CandidateCollectionError("candidate_payload_set_invalid")
    return payloads


def _load_inputs(candidate_path: Path, ledger_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], bytes, bytes]:
    try:
        candidate_bytes = candidate_path.read_bytes()
        ledger_bytes = ledger_path.read_bytes()
        artifact_value = json.loads(candidate_bytes)
        ledger_rows = [json.loads(line) for line in ledger_bytes.decode("utf-8").splitlines() if line]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateCollectionError("candidate_collection_input_invalid") from exc
    if _sha256_bytes(candidate_bytes) != EXPECTED_CANDIDATE_FILE_SHA256:
        raise CandidateCollectionError("candidate_file_hash_mismatch")
    if _sha256_bytes(ledger_bytes) != EXPECTED_LEDGER_SHA256 or len(ledger_rows) != 83:
        raise CandidateCollectionError("candidate_ledger_mismatch")
    approval = ApprovedEmbeddingArtifact(
        "sentence_transformers",
        "BAAI/bge-large-zh-v1.5",
        EMBEDDING_VERSION,
        1024,
        EXPECTED_MODEL_MANIFEST_SHA256,
        "bm25-zh-v1",
    )
    envelope = build_candidate_release_envelope(
        CandidateCorpusArtifact(artifact_value),
        serialized_ledger=ledger_bytes,
        expected_tenant_id=TENANT_ID,
        expected_release_id=RELEASE_ID,
        approved_embedding=approval,
    ).to_json_bytes()
    return artifact_value, ledger_rows, candidate_bytes, envelope


def _validate_shard(path: Path, expected_ids: Sequence[str]) -> np.ndarray:
    try:
        with np.load(path, allow_pickle=False) as payload:
            if set(payload.files) != {"chunk_ids", "vectors"}:
                raise ValueError("shard_keys")
            ids = payload["chunk_ids"].astype(str).tolist()
            vectors = np.asarray(payload["vectors"], dtype=np.float32)
    except Exception as exc:
        raise CandidateCollectionError(f"embedding_shard_invalid:{path.name}") from exc
    if ids != list(expected_ids) or vectors.shape != (len(ids), 1024) or not np.isfinite(vectors).all():
        raise CandidateCollectionError(f"embedding_shard_contract_invalid:{path.name}")
    norms = np.linalg.norm(vectors, axis=1)
    if not np.allclose(norms, 1.0, atol=1e-5):
        raise CandidateCollectionError(f"embedding_shard_norm_invalid:{path.name}")
    return vectors


def _write_shard(path: Path, ids: Sequence[str], vectors: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            np.savez(handle, chunk_ids=np.asarray(ids, dtype=str), vectors=np.asarray(vectors, dtype=np.float32))
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise CandidateCollectionError(f"embedding_shard_write_race:{path.name}") from exc


def prepare_assets(
    artifact: Mapping[str, Any],
    envelope: bytes,
    release_root: Path,
    model_root: Path,
) -> dict[str, Any]:
    if model_manifest_sha256(model_root) != EXPECTED_MODEL_MANIFEST_SHA256:
        raise CandidateCollectionError("embedding_model_manifest_mismatch")
    chunks = _ordered_chunks(artifact)
    bm25 = build_bm25_profile(chunks)
    write_immutable(
        release_root / "bm25_profile.json",
        (json.dumps(bm25, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"),
    )
    write_immutable(release_root / "candidate_release_envelope.json", envelope)

    model = None
    shard_records: list[dict[str, Any]] = []
    shard_root = release_root / "embedding_shards"
    for start in range(0, len(chunks), SHARD_SIZE):
        batch = chunks[start : start + SHARD_SIZE]
        end = start + len(batch) - 1
        path = shard_root / f"dense_{start:06d}_{end:06d}.npz"
        ids = [item["chunk_id"] for item in batch]
        if path.exists():
            _validate_shard(path, ids)
            disposition = "unchanged"
        else:
            if model is None:
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                import torch
                from sentence_transformers import SentenceTransformer

                random.seed(0)
                np.random.seed(0)
                torch.manual_seed(0)
                torch.set_num_threads(6)
                torch.set_num_interop_threads(1)
                torch.use_deterministic_algorithms(True)
                model = SentenceTransformer(
                    str(model_root), device="cpu", local_files_only=True, trust_remote_code=False
                )
                model.max_seq_length = 512
            vectors = model.encode(
                [item["content"] for item in batch],
                batch_size=INFERENCE_BATCH_SIZE,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            vectors = np.asarray(vectors, dtype=np.float32)
            if vectors.shape != (len(batch), 1024) or not np.isfinite(vectors).all():
                raise CandidateCollectionError("embedding_output_invalid")
            if not np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5):
                raise CandidateCollectionError("embedding_norm_invalid")
            _write_shard(path, ids, vectors)
            _validate_shard(path, ids)
            disposition = "created"
        shard_records.append(
            {
                "path": path.relative_to(release_root).as_posix(),
                "start": start,
                "end": end,
                "count": len(batch),
                "sha256": _sha256_file(path),
            }
        )
        print(json.dumps({"stage": "embedding", "start": start, "end": end, "status": disposition}), flush=True)
    ordered_ids = [item["chunk_id"] for item in chunks]
    manifest_base = {
        "schema_version": "rag-embedding-shards/v1",
        "release_id": RELEASE_ID,
        "candidate_file_sha256": EXPECTED_CANDIDATE_FILE_SHA256,
        "model_manifest_sha256": EXPECTED_MODEL_MANIFEST_SHA256,
        "embedding_version": EMBEDDING_VERSION,
        "dimension": 1024,
        "normalized": True,
        "chunk_count": len(chunks),
        "ordered_chunk_ids_sha256": _sha256_bytes(_canonical_bytes(ordered_ids)),
        "shards": shard_records,
    }
    manifest = manifest_base | {"manifest_sha256": _sha256_bytes(_canonical_bytes(manifest_base))}
    write_immutable(
        release_root / "embedding_manifest.json",
        (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"),
    )
    return manifest


def _load_dense_vectors(release_root: Path, chunks: Sequence[Mapping[str, Any]]) -> dict[str, np.ndarray]:
    try:
        manifest = json.loads((release_root / "embedding_manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateCollectionError("embedding_manifest_unavailable") from exc
    base = dict(manifest)
    stored_hash = base.pop("manifest_sha256", "")
    if (
        stored_hash != _sha256_bytes(_canonical_bytes(base))
        or manifest.get("candidate_file_sha256") != EXPECTED_CANDIDATE_FILE_SHA256
        or manifest.get("model_manifest_sha256") != EXPECTED_MODEL_MANIFEST_SHA256
        or manifest.get("chunk_count") != len(chunks)
    ):
        raise CandidateCollectionError("embedding_manifest_invalid")
    output: dict[str, np.ndarray] = {}
    for record in manifest["shards"]:
        expected = chunks[int(record["start"]) : int(record["end"]) + 1]
        ids = [item["chunk_id"] for item in expected]
        path = (release_root / record["path"]).resolve()
        try:
            path.relative_to(release_root)
        except ValueError as exc:
            raise CandidateCollectionError("embedding_shard_escaped_root") from exc
        if _sha256_file(path) != record["sha256"]:
            raise CandidateCollectionError("embedding_shard_hash_mismatch")
        vectors = _validate_shard(path, ids)
        output.update(zip(ids, vectors))
    if set(output) != {item["chunk_id"] for item in chunks}:
        raise CandidateCollectionError("embedding_vector_set_mismatch")
    return output


class QdrantHttp:
    def __init__(self, env_file: Path):
        values = {key: str(value or "") for key, value in dotenv_values(env_file).items()}
        required = {"RAG_R1_QDRANT_ROOT", "QDRANT_ADMIN_API_KEY", "QDRANT_READ_ONLY_API_KEY", "QDRANT_IMAGE_DIGEST"}
        if any(not values.get(key) for key in required):
            raise CandidateCollectionError("qdrant_configuration_incomplete")
        root = Path(values["RAG_R1_QDRANT_ROOT"]).resolve()
        if root != EXPECTED_QDRANT_ROOT:
            raise CandidateCollectionError("qdrant_root_rejected")
        ca_path = root / "tls" / "ca-cert.pem"
        if not ca_path.is_file():
            raise CandidateCollectionError("qdrant_ca_missing")
        self.endpoint = "https://127.0.0.1:6333"
        self.context = ssl.create_default_context(cafile=str(ca_path))
        self.admin = values["QDRANT_ADMIN_API_KEY"]
        self.reader = values["QDRANT_READ_ONLY_API_KEY"]
        self.image_digest = values["QDRANT_IMAGE_DIGEST"]

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: Mapping[str, Any] | None = None,
        reader: bool = False,
        timeout: int = 180,
    ) -> tuple[int, dict[str, Any]]:
        headers = {"accept": "application/json", "api-key": self.reader if reader else self.admin}
        data = None
        if payload is not None:
            headers["content-type"] = "application/json"
            data = _canonical_bytes(payload)
        request = Request(self.endpoint + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, context=self.context, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                return response.status, json.loads(body) if body else {}
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body) if body else {}
            except json.JSONDecodeError:
                parsed = {}
            return exc.code, parsed


def collection_create_payload() -> dict[str, Any]:
    return {
        "vectors": {"dense": {"size": 1024, "distance": "Cosine"}},
        "sparse_vectors": {"bm25": {"index": {"on_disk": True}}},
        "on_disk_payload": True,
        "strict_mode_config": {"enabled": True},
    }


def _aliases(client: QdrantHttp) -> dict[str, str]:
    status, body = client.request("/aliases", reader=True)
    if status != 200:
        raise CandidateCollectionError(f"qdrant_alias_read_failed:{status}")
    return {
        str(item["alias_name"]): str(item["collection_name"])
        for item in body.get("result", {}).get("aliases", [])
    }


def _collection_result(client: QdrantHttp) -> dict[str, Any] | None:
    status, body = client.request(f"/collections/{quote(COLLECTION)}")
    if status == 404:
        return None
    if status != 200:
        raise CandidateCollectionError(f"qdrant_collection_read_failed:{status}")
    return body.get("result", {})


def _validate_collection_config(result: Mapping[str, Any]) -> None:
    params = result.get("config", {}).get("params", {})
    dense = params.get("vectors", {}).get("dense", {})
    sparse = params.get("sparse_vectors", {})
    strict = result.get("strict_mode_config") or result.get("config", {}).get("strict_mode_config", {})
    if (
        dense.get("size") != 1024
        or str(dense.get("distance", "")).lower() != "cosine"
        or "bm25" not in sparse
        or strict.get("enabled") is not True
    ):
        raise CandidateCollectionError("qdrant_collection_config_mismatch")


def _create_or_validate_collection(client: QdrantHttp, expected_count: int) -> str:
    result = _collection_result(client)
    if result is None:
        status, _ = client.request(
            f"/collections/{quote(COLLECTION)}",
            method="PUT",
            payload=collection_create_payload(),
        )
        if status != 200:
            raise CandidateCollectionError(f"qdrant_collection_create_failed:{status}")
        result = _collection_result(client)
        disposition = "created"
    else:
        disposition = "existing"
    if result is None:
        raise CandidateCollectionError("qdrant_collection_missing_after_create")
    _validate_collection_config(result)
    if int(result.get("points_count") or 0) > expected_count:
        raise CandidateCollectionError("qdrant_collection_has_extra_points")
    return disposition


def _create_payload_indexes(client: QdrantHttp) -> None:
    result = _collection_result(client)
    if result is None:
        raise CandidateCollectionError("qdrant_collection_missing_before_indexes")
    existing = result.get("payload_schema", {})
    for field_name, field_schema in PAYLOAD_INDEXES:
        current = existing.get(field_name)
        if current is not None:
            current_type = current.get("data_type") if isinstance(current, Mapping) else current
            if current_type != field_schema:
                raise CandidateCollectionError(f"qdrant_payload_index_mismatch:{field_name}")
            continue
        status, _ = client.request(
            f"/collections/{quote(COLLECTION)}/index?wait=true",
            method="PUT",
            payload={"field_name": field_name, "field_schema": field_schema},
        )
        if status != 200:
            raise CandidateCollectionError(f"qdrant_payload_index_failed:{field_name}:{status}")


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{RELEASE_ID}\0{chunk_id}"))


def _retrieve_payloads(client: QdrantHttp, expected_ids: set[str]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    ordered_ids = sorted(expected_ids)
    pending = [
        ordered_ids[start : start + RETRIEVE_BATCH_SIZE]
        for start in range(0, len(ordered_ids), RETRIEVE_BATCH_SIZE)
    ]
    while pending:
        batch = pending.pop(0)
        chunk_ids_by_point_id = {_point_id(chunk_id): chunk_id for chunk_id in batch}
        status, body = client.request(
            f"/collections/{quote(COLLECTION)}/points",
            method="POST",
            payload={
                "ids": list(chunk_ids_by_point_id),
                "with_payload": [
                    "chunk_id", "tenant_id", "release_id", "status", "candidate_file_sha256",
                    "embedding_provider", "embedding_model", "embedding_version", "embedding_dimension",
                    "sparse_profile",
                ],
                "with_vector": False,
            },
        )
        if status >= 500 and len(batch) > RETRIEVE_MIN_BATCH_SIZE:
            midpoint = len(batch) // 2
            pending[0:0] = [batch[:midpoint], batch[midpoint:]]
            continue
        if status != 200:
            raise CandidateCollectionError(f"qdrant_retrieve_failed:{status}")
        result = body.get("result", [])
        if not isinstance(result, list):
            raise CandidateCollectionError("qdrant_retrieve_result_invalid")
        for point in result:
            payload = point.get("payload") or {}
            chunk_id = str(payload.get("chunk_id") or "")
            point_id = str(point.get("id"))
            if not chunk_id or chunk_id in output or chunk_ids_by_point_id.get(point_id) != chunk_id:
                raise CandidateCollectionError("qdrant_point_identity_invalid")
            output[chunk_id] = payload
    return output


def _validate_payload_facts(existing: Mapping[str, Mapping[str, Any]], expected_ids: set[str]) -> None:
    if set(existing) - expected_ids:
        raise CandidateCollectionError("qdrant_unknown_point_detected")
    for payload in existing.values():
        if (
            payload.get("tenant_id") != TENANT_ID
            or payload.get("release_id") != RELEASE_ID
            or payload.get("status") != "published"
            or payload.get("candidate_file_sha256") != EXPECTED_CANDIDATE_FILE_SHA256
            or payload.get("embedding_provider") != "sentence_transformers"
            or payload.get("embedding_model") != "BAAI/bge-large-zh-v1.5"
            or payload.get("embedding_version") != EMBEDDING_VERSION
            or payload.get("embedding_dimension") != 1024
            or payload.get("sparse_profile") != "bm25-zh-v1"
        ):
            raise CandidateCollectionError("qdrant_payload_fact_mismatch")


def _query_smoke(
    client: QdrantHttp,
    first_chunk: Mapping[str, Any],
    dense: np.ndarray,
    sparse: Mapping[str, Any],
) -> dict[str, Any]:
    base = {
        "filter": {
            "must": [
                {"key": "tenant_id", "match": {"value": TENANT_ID}},
                {"key": "release_id", "match": {"value": RELEASE_ID}},
                {"key": "status", "match": {"value": "published"}},
            ]
        },
        "limit": 10,
        "with_payload": ["chunk_id"],
        "with_vector": False,
    }
    checks = {}
    for mode, query_value in (("dense", dense.astype(np.float32).tolist()), ("bm25", sparse)):
        status, body = client.request(
            f"/collections/{quote(COLLECTION)}/points/query",
            method="POST",
            reader=True,
            payload={**base, "query": query_value, "using": mode},
        )
        points = body.get("result", {}).get("points", [])
        ids = [str((item.get("payload") or {}).get("chunk_id") or "") for item in points]
        checks[mode] = status == 200 and first_chunk["chunk_id"] in ids
    if not all(checks.values()):
        raise CandidateCollectionError("qdrant_candidate_query_smoke_failed")
    return checks


def upload_collection(
    artifact: Mapping[str, Any],
    ledger_rows: Sequence[Mapping[str, Any]],
    release_root: Path,
    client: QdrantHttp,
) -> dict[str, Any]:
    chunks = _ordered_chunks(artifact)
    dense = _load_dense_vectors(release_root, chunks)
    try:
        bm25 = json.loads((release_root / "bm25_profile.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateCollectionError("bm25_profile_unavailable") from exc
    base = dict(bm25)
    stored_profile_hash = base.pop("profile_sha256", "")
    if stored_profile_hash != _sha256_bytes(_canonical_bytes(base)) or bm25.get("chunk_count") != len(chunks):
        raise CandidateCollectionError("bm25_profile_invalid")
    payloads = build_payloads(artifact, ledger_rows, EXPECTED_CANDIDATE_FILE_SHA256)
    alias_before = _aliases(client).get(ALIAS)
    if alias_before == COLLECTION:
        raise CandidateCollectionError("candidate_collection_already_aliased")
    _create_or_validate_collection(client, len(chunks))
    collection_before = _collection_result(client)
    if collection_before is None:
        raise CandidateCollectionError("qdrant_collection_missing_before_audit")
    existing = _retrieve_payloads(client, set(payloads))
    if len(existing) != int(collection_before.get("points_count") or 0):
        raise CandidateCollectionError("qdrant_unknown_point_detected")
    _validate_payload_facts(existing, set(payloads))
    _create_payload_indexes(client)

    input_hash = hashlib.sha256()
    first_sparse: tuple[Mapping[str, Any], dict[str, Any]] | None = None
    sparse_point_count = 0
    for start in range(0, len(chunks), UPSERT_BATCH_SIZE):
        batch = chunks[start : start + UPSERT_BATCH_SIZE]
        points = []
        for chunk in batch:
            chunk_id = str(chunk["chunk_id"])
            vector = dense[chunk_id]
            sparse = sparse_vector(str(chunk["content"]), bm25)
            if sparse["indices"]:
                sparse_point_count += 1
                if first_sparse is None:
                    first_sparse = (chunk, sparse)
            payload = payloads[chunk_id]
            input_hash.update(chunk_id.encode("utf-8"))
            input_hash.update(vector.astype("<f4", copy=False).tobytes())
            input_hash.update(np.asarray(sparse["indices"], dtype="<u4").tobytes())
            input_hash.update(np.asarray(sparse["values"], dtype="<f4").tobytes())
            input_hash.update(_canonical_bytes(payload))
            named_vectors: dict[str, Any] = {"dense": vector.tolist()}
            if sparse["indices"]:
                named_vectors["bm25"] = sparse
            points.append({"id": _point_id(chunk_id), "vector": named_vectors, "payload": payload})
        status, _ = client.request(
            f"/collections/{quote(COLLECTION)}/points?wait=true",
            method="PUT",
            payload={"points": points},
        )
        if status != 200:
            raise CandidateCollectionError(f"qdrant_upsert_failed:{start}:{status}")
        print(json.dumps({"stage": "qdrant_upsert", "processed": start + len(batch), "total": len(chunks)}), flush=True)

    result = _collection_result(client)
    if result is None:
        raise CandidateCollectionError("qdrant_collection_missing_after_upsert")
    _validate_collection_config(result)
    if int(result.get("points_count") or 0) != len(chunks):
        raise CandidateCollectionError("qdrant_point_count_mismatch")
    payload_schema = result.get("payload_schema", {})
    if set(name for name, _ in PAYLOAD_INDEXES) - set(payload_schema):
        raise CandidateCollectionError("qdrant_payload_indexes_incomplete")
    final_payloads = _retrieve_payloads(client, set(payloads))
    if set(final_payloads) != set(payloads):
        raise CandidateCollectionError("qdrant_final_point_set_mismatch")
    _validate_payload_facts(final_payloads, set(payloads))
    status, snapshot_body = client.request(f"/collections/{quote(COLLECTION)}/snapshots", reader=True)
    if status != 200 or snapshot_body.get("result") not in ([], None):
        raise CandidateCollectionError("candidate_snapshot_boundary_violated")
    alias_after = _aliases(client).get(ALIAS)
    if alias_after != alias_before:
        raise CandidateCollectionError("candidate_alias_mutated")
    if first_sparse is None:
        raise CandidateCollectionError("candidate_first_sparse_missing")
    sparse_chunk, sparse_query = first_sparse
    smoke = _query_smoke(
        client, sparse_chunk, dense[sparse_chunk["chunk_id"]], sparse_query
    )
    report = {
        "status": "PASS",
        "scope": "candidate_collection_only",
        "release_id": RELEASE_ID,
        "tenant_id": TENANT_ID,
        "collection": COLLECTION,
        "alias": ALIAS,
        "alias_before": alias_before,
        "alias_after": alias_after,
        "collection_state": "ready",
        "point_count": len(chunks),
        "dense": {
            "name": "dense",
            "dimension": 1024,
            "distance": "Cosine",
            "provider": "sentence_transformers",
            "model": "BAAI/bge-large-zh-v1.5",
            "version": EMBEDDING_VERSION,
            "normalized": True,
        },
        "sparse": {
            "name": "bm25",
            "profile": "bm25-zh-v1",
            "profile_sha256": bm25["profile_sha256"],
            "vocabulary_size": len(bm25["vocabulary"]),
            "point_count": sparse_point_count,
            "empty_point_count": len(chunks) - sparse_point_count,
        },
        "strict_mode_enabled": True,
        "payload_indexes": [name for name, _ in PAYLOAD_INDEXES],
        "payload_statuses": ["published"],
        "payload_release_ids": [RELEASE_ID],
        "payload_tenant_ids": [TENANT_ID],
        "candidate_file_sha256": EXPECTED_CANDIDATE_FILE_SHA256,
        "collection_input_sha256": input_hash.hexdigest(),
        "query_smoke": smoke,
        "snapshot_count": 0,
        "image_version": "1.18.2",
        "image_digest": client.image_digest,
        "admin_key_emitted": False,
        "network_calls_external": 0,
    }
    write_immutable(
        release_root / "candidate_collection_report.json",
        (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"),
    )
    return report


def _validate_paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    release_root = args.release_root.resolve()
    model_root = args.model_root.resolve()
    candidate_path = args.candidate.resolve()
    env_file = args.env_file.resolve()
    if release_root != EXPECTED_RELEASE_ROOT or model_root != EXPECTED_MODEL_ROOT:
        raise CandidateCollectionError("candidate_collection_path_rejected")
    if candidate_path != release_root / "candidate_corpus.json":
        raise CandidateCollectionError("candidate_path_rejected")
    if env_file != EXPECTED_QDRANT_ROOT / "secrets" / "runtime.env":
        raise CandidateCollectionError("qdrant_env_path_rejected")
    if not release_root.is_dir() or not model_root.is_dir() or not env_file.is_file():
        raise CandidateCollectionError("candidate_collection_input_unavailable")
    return release_root, model_root, candidate_path, env_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare and upload the RAG-R1 Candidate Collection.")
    parser.add_argument("--phase", choices=("prepare", "upload", "all"), default="all")
    parser.add_argument("--release-root", type=Path, default=EXPECTED_RELEASE_ROOT)
    parser.add_argument("--candidate", type=Path, default=EXPECTED_RELEASE_ROOT / "candidate_corpus.json")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, default=EXPECTED_MODEL_ROOT)
    parser.add_argument("--env-file", type=Path, default=EXPECTED_QDRANT_ROOT / "secrets" / "runtime.env")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    release_root, model_root, candidate_path, env_file = _validate_paths(args)
    artifact, ledger_rows, _, envelope = _load_inputs(candidate_path, args.ledger.resolve())
    result: dict[str, Any] = {"status": "PASS", "phase": args.phase, "release_id": RELEASE_ID}
    if args.phase in {"prepare", "all"}:
        manifest = prepare_assets(artifact, envelope, release_root, model_root)
        result["embedding_shards"] = len(manifest["shards"])
        result["embedding_chunks"] = manifest["chunk_count"]
    if args.phase in {"upload", "all"}:
        report = upload_collection(artifact, ledger_rows, release_root, QdrantHttp(env_file))
        result["collection"] = report["collection"]
        result["point_count"] = report["point_count"]
        result["alias_after"] = report["alias_after"]
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
