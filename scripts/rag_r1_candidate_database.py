from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from sqlalchemy.engine import URL, make_url


EXPECTED_TARGET = {
    "host": "localhost",
    "port": 5432,
    "database": "postgres",
    "user": "postgres",
}
EXPECTED_RELEASE_ROOT = Path("E:/智能运营分析项目/.runtime/rag/releases/RAG-R1").resolve()
EXPECTED_LEDGER_SHA256 = "ee61af9a0aa4509b2e7947e37c99004e2029fbfd69a55fe663e8acacafebf7d6"
EXPECTED_EMBEDDING_SHA256 = "a6854a4b265bc6c7159d02927ece3548e63e7b57cf49deee2a77b94bbb0ec3fa"
EXPECTED_RERANKER_SHA256 = "2a581f058542bd175695f8f92097b7aa4fbdac637ad486739f26e4cbc11ca159"
TENANT_ID = "default"
RELEASE_ID = "RAG-R1"
COLLECTION = "rag_chunks_RAG-R1"
ACTOR_ID = "codex-rag-r1-final"
RUN_ID = "run_rag_r1_final_candidate_20260802"
TRACE_ID = "trace_rag_r1_final_candidate_20260802"


class CandidateDatabaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class CandidateFacts:
    corpus: dict[str, Any]
    envelope: dict[str, Any]
    ledger: tuple[dict[str, Any], ...]
    admission: dict[str, Any]
    documents: tuple[dict[str, Any], ...]
    versions: tuple[dict[str, Any], ...]
    chunks: tuple[dict[str, Any], ...]
    release_items: tuple[dict[str, Any], ...]
    manifest_sha256: str
    artifact_sha256: str
    ledger_sha256: str


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateDatabaseError(f"json_input_invalid:{path.name}") from exc
    if not isinstance(value, dict):
        raise CandidateDatabaseError(f"json_input_not_object:{path.name}")
    return value


def _load_ledger(path: Path) -> tuple[dict[str, Any], ...]:
    try:
        payload = path.read_bytes()
        rows = tuple(
            json.loads(line) for line in payload.decode("utf-8").splitlines() if line
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateDatabaseError("source_ledger_invalid") from exc
    if len(rows) != 83 or hashlib.sha256(payload).hexdigest() != EXPECTED_LEDGER_SHA256:
        raise CandidateDatabaseError("source_ledger_identity_mismatch")
    if len({row.get("source_id") for row in rows}) != 83:
        raise CandidateDatabaseError("source_ledger_id_duplicate")
    return rows


def _verified_hash(value: Mapping[str, Any], field: str, error: str) -> str:
    copied = dict(value)
    stored = copied.pop(field, None)
    if stored != _hash(copied):
        raise CandidateDatabaseError(error)
    return str(stored)


def load_candidate_facts(
    release_root: Path, ledger_path: Path, admission_path: Path
) -> CandidateFacts:
    if release_root.resolve() != EXPECTED_RELEASE_ROOT:
        raise CandidateDatabaseError("release_root_rejected")
    corpus = _load_json(release_root / "candidate_corpus.json")
    envelope = _load_json(release_root / "candidate_release_envelope.json")
    admission = _load_json(admission_path)
    ledger = _load_ledger(ledger_path)
    artifact_sha256 = _verified_hash(
        corpus, "artifact_sha256", "candidate_artifact_hash_mismatch"
    )
    _verified_hash(envelope, "envelope_sha256", "candidate_envelope_hash_mismatch")
    manifest = corpus.get("candidate_manifest")
    if not isinstance(manifest, dict):
        raise CandidateDatabaseError("candidate_manifest_missing")
    manifest_base = dict(manifest)
    corpus_sha256 = manifest_base.pop("corpus_sha256", None)
    if corpus_sha256 != _hash(manifest_base):
        raise CandidateDatabaseError("candidate_corpus_hash_mismatch")
    manifest_sha256 = _hash(manifest)
    hashes = envelope.get("hashes", {})
    counts = corpus.get("counts", {})
    if (
        corpus.get("tenant_id") != TENANT_ID
        or corpus.get("candidate_release_id") != RELEASE_ID
        or manifest.get("tenant_id") != TENANT_ID
        or manifest.get("candidate_release_id") != RELEASE_ID
        or manifest.get("release_status") != "candidate"
        or hashes.get("artifact_sha256") != artifact_sha256
        or hashes.get("manifest_sha256") != manifest_sha256
        or hashes.get("ledger_sha256") != EXPECTED_LEDGER_SHA256
        or counts != {
            "ledger": 83,
            "documents": 45,
            "chunks": 8339,
            "assets": 0,
            "duplicates": 14,
            "isolations": 24,
        }
    ):
        raise CandidateDatabaseError("candidate_contract_mismatch")
    models = admission.get("models", {})
    embedding, reranker = models.get("embedding", {}), models.get("reranker", {})
    if (
        admission.get("status") != "PASS"
        or embedding.get("status") != "PASS"
        or reranker.get("status") != "PASS"
        or embedding.get("manifest_sha256") != EXPECTED_EMBEDDING_SHA256
        or reranker.get("manifest_sha256") != EXPECTED_RERANKER_SHA256
    ):
        raise CandidateDatabaseError("model_admission_mismatch")

    ledger_by_source = {row["source_id"]: row for row in ledger}
    manifest_documents = manifest["documents"]
    versions_by_id = {row["version_id"]: row for row in corpus["versions"]}
    document_by_source = {row["source_id"]: row for row in manifest_documents}
    duplicate_by_source = {row["source_id"]: row for row in corpus["duplicates"]}
    isolation_by_source = {row["source_id"]: row for row in corpus["isolations"]}
    chunks_by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in manifest["chunks"]:
        chunks_by_document[chunk["document_id"]].append(chunk)
    if (
        len(document_by_source) != 45
        or len(versions_by_id) != 45
        or len(duplicate_by_source) != 14
        or len(isolation_by_source) != 24
        or set(ledger_by_source)
        != set(document_by_source) | set(duplicate_by_source) | set(isolation_by_source)
    ):
        raise CandidateDatabaseError("candidate_source_partition_mismatch")

    created_at = manifest["created_at"]
    documents: list[dict[str, Any]] = []
    versions: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    release_items: list[dict[str, Any]] = []
    for document in manifest_documents:
        source = ledger_by_source[document["source_id"]]
        version = versions_by_id[document["version_id"]]
        source_type = str(source["detected_format"]).lower()
        documents.append(
            {
                "doc_id": document["document_id"],
                "title": document["title"],
                "source_type": source_type,
                "source_path": source["relative_path"],
                "checksum": document["source_sha256"],
                "tenant_id": TENANT_ID,
                "domain": document["domain"],
                "owner_actor_id": ACTOR_ID,
                "indexed_at": created_at,
                "metadata_json": {
                    "domain": document["domain"],
                    "source_id": document["source_id"],
                    "release_id": RELEASE_ID,
                    "data_origin": "official",
                    "source_name": document["title"],
                    "generated_at": created_at,
                    "release_status": "candidate",
                    "document_version": document["version_id"],
                    "applicability_scope": "enterprise-rag-r1",
                },
            }
        )
        versions.append(
            {
                "tenant_id": TENANT_ID,
                "version_id": version["version_id"],
                "document_id": version["document_id"],
                "source_id": version["source_id"],
                "source_sha256": version["source_sha256"],
                "content_sha256": version["content_sha256"],
                "declared_format": str(source["declared_format"]).lower(),
                "detected_format": source_type,
                "parser_profile": f"rag-r1-{source_type}-v1",
                "schema_version": source["schema_version"],
                "parse_status": "ready",
                "effective_from": document["effective_from"],
                "effective_to": document["effective_to"],
                "metadata_json": {
                    "release_id": RELEASE_ID,
                    "transformed": version["transformed"],
                },
            }
        )
        ordered_chunks = sorted(
            chunks_by_document[document["document_id"]], key=lambda row: row["chunk_id"]
        )
        for chunk_index, chunk in enumerate(ordered_chunks):
            chunks.append(
                {
                    "chunk_id": chunk["chunk_id"],
                    "doc_id": chunk["document_id"],
                    "chunk_index": chunk_index,
                    "content": chunk["content"],
                    "tenant_id": TENANT_ID,
                    "version_id": chunk["version_id"],
                    "parent_chunk_id": chunk["parent_chunk_id"],
                    "chunk_level": "child",
                    "section_path_json": chunk["citation"]["section_path"],
                    "locator_json": chunk["citation"],
                    "content_sha256": chunk["content_hash"],
                    "token_count": chunk["token_count"],
                    "embedding_provider": "sentence_transformers",
                    "embedding_model": "BAAI/bge-large-zh-v1.5",
                    "embedding_version": "sha256:" + EXPECTED_EMBEDDING_SHA256,
                    "embedding_dimension": 1024,
                    "embedding_status": "ready",
                    "metadata_json": {
                        "citation": chunk["citation"],
                        "source_id": document["source_id"],
                        "release_id": RELEASE_ID,
                        "source_type": source_type,
                        "release_status": "candidate",
                    },
                }
            )
        release_items.append(
            _release_item(
                document["source_id"], source["sha256"], "published",
                document=document, chunk_count=len(ordered_chunks)
            )
        )
    for source_id, duplicate in duplicate_by_source.items():
        source = ledger_by_source[source_id]
        release_items.append(
            _release_item(
                source_id, source["sha256"], "duplicate",
                reason=source["isolation_reason"],
                duplicate_of=duplicate["canonical_source_id"],
            )
        )
    for source_id, isolation in isolation_by_source.items():
        source = ledger_by_source[source_id]
        release_items.append(
            _release_item(
                source_id, source["sha256"], "isolated", reason=isolation["reason"]
            )
        )
    return CandidateFacts(
        corpus=corpus,
        envelope=envelope,
        ledger=ledger,
        admission=admission,
        documents=tuple(sorted(documents, key=lambda row: row["doc_id"])),
        versions=tuple(sorted(versions, key=lambda row: row["version_id"])),
        chunks=tuple(sorted(chunks, key=lambda row: row["chunk_id"])),
        release_items=tuple(sorted(release_items, key=lambda row: row["source_id"])),
        manifest_sha256=manifest_sha256,
        artifact_sha256=artifact_sha256,
        ledger_sha256=EXPECTED_LEDGER_SHA256,
    )


def _release_item(
    source_id: str,
    source_sha256: str,
    status: str,
    *,
    document: Mapping[str, Any] | None = None,
    reason: str | None = None,
    duplicate_of: str | None = None,
    chunk_count: int = 0,
) -> dict[str, Any]:
    identity = hashlib.sha256(f"{TENANT_ID}|{RELEASE_ID}|{source_id}".encode()).hexdigest()[:24]
    return {
        "tenant_id": TENANT_ID,
        "item_id": "item_" + identity,
        "release_id": RELEASE_ID,
        "source_id": source_id,
        "document_id": None if document is None else document["document_id"],
        "version_id": None if document is None else document["version_id"],
        "terminal_status": status,
        "reason": reason,
        "duplicate_of_source_id": duplicate_of,
        "chunk_count": chunk_count,
        "asset_count": 0,
        "content_sha256": source_sha256,
    }


def load_database_url(env_file: Path) -> URL:
    values = dotenv_values(env_file)
    raw = str(values.get("MIGRATION_DATABASE_URL") or values.get("DATABASE_URL") or "")
    if not raw:
        raise CandidateDatabaseError("database_url_missing")
    url = make_url(raw)
    actual = {
        "host": url.host or "",
        "port": url.port or 5432,
        "database": url.database or "",
        "user": url.username or "",
    }
    if actual != EXPECTED_TARGET:
        raise CandidateDatabaseError(f"database_target_rejected:{actual}")
    return url


def _connect_kwargs(url: URL, *, read_only: bool) -> dict[str, Any]:
    options = "-c default_transaction_read_only=on" if read_only else ""
    return {
        "host": url.host,
        "hostaddr": "127.0.0.1",
        "port": url.port or 5432,
        "dbname": url.database,
        "user": url.username,
        "password": url.password,
        "connect_timeout": 5,
        "options": options,
        "row_factory": dict_row,
    }


def _database_presence(cursor: Any) -> dict[str, int]:
    cursor.execute(
        """
        SELECT
          (SELECT count(*) FROM kb_releases WHERE tenant_id=%s AND release_id=%s) AS releases,
          (SELECT count(*) FROM kb_documents WHERE metadata_json->>'release_id'=%s) AS documents,
          (SELECT count(*) FROM kb_document_versions WHERE metadata_json->>'release_id'=%s) AS versions,
          (SELECT count(*) FROM kb_chunks WHERE metadata_json->>'release_id'=%s) AS chunks,
          (SELECT count(*) FROM kb_release_items WHERE tenant_id=%s AND release_id=%s) AS release_items
        """,
        (TENANT_ID, RELEASE_ID, RELEASE_ID, RELEASE_ID, RELEASE_ID, TENANT_ID, RELEASE_ID),
    )
    return {key: int(value) for key, value in cursor.fetchone().items()}


def _mismatch_count(expected: Mapping[str, Any], actual: Mapping[str, Any], fields: Sequence[str]) -> int:
    return sum(actual.get(field) != expected.get(field) for field in fields)


def verify_candidate(cursor: Any, facts: CandidateFacts, *, allow_legacy_manifest: bool) -> dict[str, Any]:
    issues: list[str] = []
    cursor.execute(
        "SELECT * FROM kb_releases WHERE tenant_id=%s AND release_id=%s",
        (TENANT_ID, RELEASE_ID),
    )
    release = cursor.fetchone()
    if release is None:
        issues.append("release_missing")
    else:
        expected_release = {
            "tenant_id": TENANT_ID,
            "release_id": RELEASE_ID,
            "status": "candidate",
            "is_current": False,
            "collection_name": COLLECTION,
            "source_ledger_sha256": facts.ledger_sha256,
            "embedding_provider": "sentence_transformers",
            "embedding_model": "BAAI/bge-large-zh-v1.5",
            "embedding_version": "sha256:" + EXPECTED_EMBEDDING_SHA256,
            "embedding_dimension": 1024,
            "embedding_model_sha256": EXPECTED_EMBEDDING_SHA256,
            "reranker_model": "BAAI/bge-reranker-v2-m3",
            "reranker_version": "sha256:" + EXPECTED_RERANKER_SHA256,
            "reranker_model_sha256": EXPECTED_RERANKER_SHA256,
            "sparse_profile": "bm25-zh-v1",
        }
        release_fields = tuple(expected_release)
        if _mismatch_count(expected_release, release, release_fields):
            issues.append("release_contract_mismatch")
        manifest = release.get("manifest_sha256")
        if manifest != facts.manifest_sha256:
            if allow_legacy_manifest and manifest == facts.artifact_sha256:
                issues.append("release_manifest_legacy")
            else:
                issues.append("release_manifest_mismatch")

    comparisons = (
        ("documents", "doc_id", facts.documents, "kb_documents", "metadata_json->>'release_id'=%s", (
            "title", "source_type", "checksum", "tenant_id", "domain", "owner_actor_id", "metadata_json"
        )),
        ("versions", "version_id", facts.versions, "kb_document_versions", "metadata_json->>'release_id'=%s", (
            "document_id", "source_id", "source_sha256", "content_sha256", "declared_format", "detected_format",
            "parser_profile", "schema_version", "parse_status", "effective_to", "metadata_json"
        )),
        ("chunks", "chunk_id", facts.chunks, "kb_chunks", "metadata_json->>'release_id'=%s", (
            "doc_id", "chunk_index", "content", "tenant_id", "version_id", "parent_chunk_id", "chunk_level",
            "section_path_json", "locator_json", "content_sha256", "token_count", "embedding_provider",
            "embedding_model", "embedding_version", "embedding_dimension", "embedding_status", "metadata_json"
        )),
        ("release_items", "source_id", facts.release_items, "kb_release_items", "tenant_id=%s AND release_id='RAG-R1'", (
            "document_id", "version_id", "terminal_status", "reason", "duplicate_of_source_id", "chunk_count",
            "asset_count", "content_sha256"
        )),
    )
    counts: dict[str, Any] = {}
    for label, identity, expected_rows, table, predicate, fields in comparisons:
        parameter = TENANT_ID if label == "release_items" else RELEASE_ID
        cursor.execute(f"SELECT * FROM {table} WHERE {predicate}", (parameter,))
        actual_rows = {row[identity]: row for row in cursor.fetchall()}
        expected_by_id = {row[identity]: row for row in expected_rows}
        missing = set(expected_by_id) - set(actual_rows)
        extra = set(actual_rows) - set(expected_by_id)
        mismatches = sum(
            _mismatch_count(expected_by_id[key], actual_rows[key], fields)
            for key in set(expected_by_id) & set(actual_rows)
        )
        counts[label] = {
            "expected": len(expected_by_id), "actual": len(actual_rows),
            "missing": len(missing), "extra": len(extra), "field_mismatches": mismatches,
        }
        if missing or extra or mismatches:
            issues.append(f"{label}_mismatch")
    return {
        "status": "PASS" if not issues else "DRIFT",
        "issues": sorted(set(issues)),
        "counts": counts,
        "manifest_sha256": None if release is None else release.get("manifest_sha256"),
        "expected_manifest_sha256": facts.manifest_sha256,
    }


def repair_manifest(cursor: Any, facts: CandidateFacts) -> int:
    cursor.execute(
        """
        UPDATE kb_releases
        SET manifest_sha256=%s, updated_at=CURRENT_TIMESTAMP
        WHERE tenant_id=%s AND release_id=%s AND status='candidate' AND is_current=false
          AND manifest_sha256=%s
        """,
        (facts.manifest_sha256, TENANT_ID, RELEASE_ID, facts.artifact_sha256),
    )
    if cursor.rowcount not in {0, 1}:
        raise CandidateDatabaseError("manifest_repair_cardinality_invalid")
    return int(cursor.rowcount)


def _append_audit(cursor: Any, event_type: str, details: Mapping[str, Any]) -> int:
    event_id = "evt_" + hashlib.sha256(
        f"{TENANT_ID}|{RELEASE_ID}|{event_type}".encode()
    ).hexdigest()[:24]
    cursor.execute(
        """
        INSERT INTO kb_rag_audit_events
          (tenant_id, event_id, event_type, actor_id, resource_type, resource_id,
           release_id, run_id, trace_id, status, details_json)
        VALUES (%s,%s,%s,%s,'knowledge_release',%s,%s,%s,%s,'success',%s)
        ON CONFLICT (tenant_id, event_id) DO NOTHING
        """,
        (
            TENANT_ID, event_id, event_type, ACTOR_ID, RELEASE_ID, RELEASE_ID,
            RUN_ID, TRACE_ID, Jsonb(dict(details)),
        ),
    )
    return int(cursor.rowcount)


def _insert_fresh(cursor: Any, facts: CandidateFacts) -> dict[str, int]:
    cursor.executemany(
        """
        INSERT INTO kb_documents
          (doc_id,title,source_type,source_path,checksum,metadata_json,indexed_at,
           tenant_id,domain,owner_actor_id)
        VALUES (%(doc_id)s,%(title)s,%(source_type)s,%(source_path)s,%(checksum)s,
                %(metadata_json)s,%(indexed_at)s,%(tenant_id)s,%(domain)s,%(owner_actor_id)s)
        ON CONFLICT (doc_id) DO NOTHING
        """,
        [row | {"metadata_json": Jsonb(row["metadata_json"])} for row in facts.documents],
    )
    cursor.executemany(
        """
        INSERT INTO kb_document_versions
          (tenant_id,version_id,document_id,source_id,source_sha256,content_sha256,
           declared_format,detected_format,parser_profile,schema_version,parse_status,
           effective_from,effective_to,metadata_json)
        VALUES (%(tenant_id)s,%(version_id)s,%(document_id)s,%(source_id)s,%(source_sha256)s,
                %(content_sha256)s,%(declared_format)s,%(detected_format)s,%(parser_profile)s,
                %(schema_version)s,%(parse_status)s,%(effective_from)s,%(effective_to)s,%(metadata_json)s)
        ON CONFLICT (tenant_id,version_id) DO NOTHING
        """,
        [row | {"metadata_json": Jsonb(row["metadata_json"])} for row in facts.versions],
    )
    cursor.executemany(
        """
        INSERT INTO kb_chunks
          (chunk_id,doc_id,chunk_index,content,metadata_json,tenant_id,version_id,parent_chunk_id,
           chunk_level,section_path_json,locator_json,content_sha256,token_count,embedding_provider,
           embedding_model,embedding_version,embedding_dimension,embedding_status)
        VALUES (%(chunk_id)s,%(doc_id)s,%(chunk_index)s,%(content)s,%(metadata_json)s,%(tenant_id)s,
                %(version_id)s,%(parent_chunk_id)s,%(chunk_level)s,%(section_path_json)s,%(locator_json)s,
                %(content_sha256)s,%(token_count)s,%(embedding_provider)s,%(embedding_model)s,
                %(embedding_version)s,%(embedding_dimension)s,%(embedding_status)s)
        ON CONFLICT (chunk_id) DO NOTHING
        """,
        [
            row
            | {
                "metadata_json": Jsonb(row["metadata_json"]),
                "section_path_json": Jsonb(row["section_path_json"]),
                "locator_json": Jsonb(row["locator_json"]),
            }
            for row in facts.chunks
        ],
    )
    cursor.execute(
        """
        INSERT INTO kb_releases
          (tenant_id,release_id,status,is_current,collection_name,manifest_sha256,source_ledger_sha256,
           embedding_provider,embedding_model,embedding_version,embedding_dimension,embedding_model_sha256,
           reranker_model,reranker_version,reranker_model_sha256,sparse_profile,run_id,trace_id,created_by)
        VALUES (%s,%s,'candidate',false,%s,%s,%s,'sentence_transformers','BAAI/bge-large-zh-v1.5',
                %s,1024,%s,'BAAI/bge-reranker-v2-m3',%s,%s,'bm25-zh-v1',%s,%s,%s)
        """,
        (
            TENANT_ID, RELEASE_ID, COLLECTION, facts.manifest_sha256, facts.ledger_sha256,
            "sha256:" + EXPECTED_EMBEDDING_SHA256, EXPECTED_EMBEDDING_SHA256,
            "sha256:" + EXPECTED_RERANKER_SHA256, EXPECTED_RERANKER_SHA256,
            RUN_ID, TRACE_ID, ACTOR_ID,
        ),
    )
    cursor.executemany(
        """
        INSERT INTO kb_release_items
          (tenant_id,item_id,release_id,source_id,document_id,version_id,terminal_status,reason,
           duplicate_of_source_id,chunk_count,asset_count,content_sha256)
        VALUES (%(tenant_id)s,%(item_id)s,%(release_id)s,%(source_id)s,%(document_id)s,%(version_id)s,
                %(terminal_status)s,%(reason)s,%(duplicate_of_source_id)s,%(chunk_count)s,
                %(asset_count)s,%(content_sha256)s)
        ON CONFLICT (tenant_id,item_id) DO NOTHING
        """,
        list(facts.release_items),
    )
    audit = _append_audit(cursor, "candidate_imported", {"point_count": 8339, "alias_mutated": False})
    return {"documents": 45, "versions": 45, "chunks": 8339, "release_items": 83, "audit": audit}


def run_operation(url: URL, facts: CandidateFacts, mode: str) -> dict[str, Any]:
    if mode == "verify":
        with psycopg.connect(**_connect_kwargs(url, read_only=True)) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                result = verify_candidate(cursor, facts, allow_legacy_manifest=False)
            connection.rollback()
        return result | {"mode": mode, "database_write_count": 0}

    if mode == "rollback-probe":
        with psycopg.connect(**_connect_kwargs(url, read_only=False)) as connection:
            with connection.cursor() as cursor:
                before = verify_candidate(cursor, facts, allow_legacy_manifest=True)
                if before["issues"] != ["release_manifest_legacy"]:
                    raise CandidateDatabaseError(f"rollback_probe_precondition_failed:{before['issues']}")
                changed = repair_manifest(cursor, facts)
                if changed != 1:
                    raise CandidateDatabaseError("rollback_probe_update_missing")
            connection.rollback()
        with psycopg.connect(**_connect_kwargs(url, read_only=True)) as connection:
            with connection.cursor() as cursor:
                after = verify_candidate(cursor, facts, allow_legacy_manifest=True)
            connection.rollback()
        if after["issues"] != ["release_manifest_legacy"]:
            raise CandidateDatabaseError("rollback_probe_not_restored")
        return {
            "status": "PASS", "mode": mode, "transaction_rolled_back": True,
            "database_write_count": 0, "restored_manifest_sha256": facts.artifact_sha256,
        }

    with psycopg.connect(**_connect_kwargs(url, read_only=False)) as connection:
        with connection.cursor() as cursor:
            presence = _database_presence(cursor)
            writes: dict[str, int]
            if presence["releases"] == 0:
                if any(presence.values()):
                    raise CandidateDatabaseError(f"partial_candidate_state_rejected:{presence}")
                writes = _insert_fresh(cursor, facts)
            elif presence["releases"] == 1:
                before = verify_candidate(cursor, facts, allow_legacy_manifest=True)
                if before["issues"] not in ([], ["release_manifest_legacy"]):
                    raise CandidateDatabaseError(f"candidate_drift_rejected:{before['issues']}")
                repaired = repair_manifest(cursor, facts)
                audit = 0
                if repaired:
                    audit = _append_audit(
                        cursor,
                        "candidate_manifest_reconciled",
                        {
                            "before_sha256": facts.artifact_sha256,
                            "after_sha256": facts.manifest_sha256,
                            "alias_mutated": False,
                        },
                    )
                writes = {"release_updated": repaired, "audit_inserted": audit}
            else:
                raise CandidateDatabaseError("candidate_release_cardinality_invalid")
            verified = verify_candidate(cursor, facts, allow_legacy_manifest=False)
            if verified["issues"]:
                raise CandidateDatabaseError(f"post_write_verification_failed:{verified['issues']}")
        connection.commit()
    with psycopg.connect(**_connect_kwargs(url, read_only=True)) as connection:
        with connection.cursor() as cursor:
            final = verify_candidate(cursor, facts, allow_legacy_manifest=False)
        connection.rollback()
    if final["issues"]:
        raise CandidateDatabaseError(f"post_commit_verification_failed:{final['issues']}")
    return {
        "status": "PASS", "mode": mode, "writes": writes,
        "idempotent": sum(writes.values()) == 0,
        "database_write_count": sum(writes.values()), "verification": final,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import or reconcile RAG-R1 Candidate metadata.")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, default=EXPECTED_RELEASE_ROOT)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--mode", choices=("verify", "rollback-probe", "apply"), required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        facts = load_candidate_facts(args.release_root, args.ledger, args.admission)
        result = run_operation(load_database_url(args.env_file), facts, args.mode)
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
