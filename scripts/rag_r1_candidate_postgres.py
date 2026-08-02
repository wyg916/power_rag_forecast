from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import create_engine, text

from scripts.rag_r1_database_snapshot import _load_url


EXPECTED_RELEASE_ROOT = Path("E:/智能运营分析项目/.runtime/rag/releases/RAG-R1").resolve()
EXPECTED_LEDGER_SHA256 = "ee61af9a0aa4509b2e7947e37c99004e2029fbfd69a55fe663e8acacafebf7d6"
EXPECTED_CANDIDATE_FILE_SHA256 = "ed5f62ad50a36207ca7d0e729ae2bfb054e276b40816d8ac1da04eb376468ed7"
EXPECTED_EMBEDDING_MANIFEST_SHA256 = "a6854a4b265bc6c7159d02927ece3548e63e7b57cf49deee2a77b94bbb0ec3fa"
EXPECTED_RERANKER_MANIFEST_SHA256 = "2a581f058542bd175695f8f92097b7aa4fbdac637ad486739f26e4cbc11ca159"
RELEASE_ID = "RAG-R1"
TENANT_ID = "default"
COLLECTION = "rag_chunks_RAG-R1"
ALIAS = "rag_chunks_current"
RUN_ID = "run_rag_r1_final_candidate_20260802"
TRACE_ID = "trace_rag_r1_final_candidate_20260802"
ACTOR_ID = "codex-rag-r1-final"


class CandidatePostgresError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidatePostgresError(f"json_unavailable:{path.name}") from exc
    if not isinstance(value, dict):
        raise CandidatePostgresError(f"json_object_required:{path.name}")
    return value


def _read_ledger(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidatePostgresError("ledger_unavailable") from exc
    if len(rows) != 83 or any(not isinstance(row, dict) for row in rows):
        raise CandidatePostgresError("ledger_count_invalid")
    if _sha256_file(path) != EXPECTED_LEDGER_SHA256:
        raise CandidatePostgresError("ledger_hash_mismatch")
    return rows


def _validate_inputs(
    release_root: Path,
    ledger_path: Path,
    schema_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    if release_root.resolve() != EXPECTED_RELEASE_ROOT:
        raise CandidatePostgresError("release_root_rejected")
    candidate_path = release_root / "candidate_corpus.json"
    report_path = release_root / "candidate_collection_report.json"
    if _sha256_file(candidate_path) != EXPECTED_CANDIDATE_FILE_SHA256:
        raise CandidatePostgresError("candidate_file_hash_mismatch")
    candidate = _read_json(candidate_path)
    schema = _read_json(schema_path)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(
        candidate.get("candidate_manifest")
    )
    ledger = _read_ledger(ledger_path)
    report = _read_json(report_path)
    manifest = candidate["candidate_manifest"]
    profile = candidate["embedding_profile"]
    conditions = (
        candidate.get("candidate_release_id") == RELEASE_ID,
        candidate.get("tenant_id") == TENANT_ID,
        candidate.get("source_ledger", {}).get("sha256") == EXPECTED_LEDGER_SHA256,
        profile.get("model_sha256") == EXPECTED_EMBEDDING_MANIFEST_SHA256,
        profile.get("dimension") == 1024,
        manifest.get("release_status") == "candidate",
        manifest.get("counts", candidate.get("counts")) is not None,
        len(manifest.get("documents", [])) == 45,
        len(manifest.get("chunks", [])) == 8339,
        report.get("status") == "PASS",
        report.get("collection") == COLLECTION,
        report.get("alias") == ALIAS,
        report.get("point_count") == 8339,
        report.get("alias_before") == report.get("alias_after"),
        report.get("alias_after") != COLLECTION,
        report.get("snapshot_count") == 0,
    )
    if not all(conditions):
        raise CandidatePostgresError("candidate_admission_failed")
    return candidate, ledger, report


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise CandidatePostgresError("timezone_required")
    return parsed


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _item_id(source_id: str) -> str:
    digest = hashlib.sha256(f"{RELEASE_ID}\0{source_id}".encode()).hexdigest()[:24]
    return f"itm_{digest}"


def _build_rows(
    candidate: Mapping[str, Any], ledger: Sequence[Mapping[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    manifest = candidate["candidate_manifest"]
    documents = list(manifest["documents"])
    chunks = list(manifest["chunks"])
    versions = list(candidate["versions"])
    ledger_by_source = {str(row["source_id"]): row for row in ledger}
    document_by_source = {str(row["source_id"]): row for row in documents}
    version_by_source = {str(row["source_id"]): row for row in versions}
    version_by_id = {str(row["version_id"]): row for row in versions}
    chunk_counts = Counter(str(row["version_id"]) for row in chunks)
    isolation_by_source = {
        str(row["source_id"]): str(row["reason"])
        for row in candidate.get("isolations", [])
    }
    duplicate_by_source = {
        str(row["source_id"]): str(row["canonical_source_id"])
        for row in candidate.get("duplicates", [])
    }
    created_at = _dt(str(candidate["created_at"]))
    profile = candidate["embedding_profile"]

    document_rows: list[dict[str, Any]] = []
    version_rows: list[dict[str, Any]] = []
    for document in documents:
        source_id = str(document["source_id"])
        version = version_by_source[source_id]
        source = ledger_by_source[source_id]
        metadata = {
            "data_origin": "official",
            "source_name": document["title"],
            "document_version": version["version_id"],
            "generated_at": candidate["created_at"],
            "domain": document["domain"],
            "applicability_scope": "enterprise-rag-r1",
            "release_id": RELEASE_ID,
            "release_status": "candidate",
            "source_id": source_id,
        }
        document_rows.append(
            {
                "doc_id": document["document_id"],
                "title": document["title"],
                "source_type": source["detected_format"],
                "source_path": source["relative_path"],
                "checksum": source["sha256"],
                "metadata_json": _json(metadata),
                "indexed_at": created_at,
                "tenant_id": TENANT_ID,
                "domain": document["domain"],
                "owner_actor_id": ACTOR_ID,
            }
        )
        version_rows.append(
            {
                "tenant_id": TENANT_ID,
                "version_id": version["version_id"],
                "document_id": version["document_id"],
                "source_id": source_id,
                "source_sha256": version["source_sha256"],
                "content_sha256": version["content_sha256"],
                "declared_format": source["declared_format"],
                "detected_format": source["detected_format"],
                "parser_profile": f"rag-r1-{source['detected_format']}-v1",
                "schema_version": source["schema_version"],
                "parse_status": "ready",
                "effective_from": _dt(document["effective_from"]),
                "effective_to": _dt(document.get("effective_to")),
                "metadata_json": _json(
                    {"transformed": version["transformed"], "release_id": RELEASE_ID}
                ),
            }
        )

    indices: Counter[str] = Counter()
    chunk_rows: list[dict[str, Any]] = []
    for chunk in chunks:
        version = version_by_id[str(chunk["version_id"])]
        source = ledger_by_source[str(version["source_id"])]
        citation = chunk["citation"]
        index = indices[str(chunk["document_id"])]
        indices[str(chunk["document_id"])] += 1
        chunk_rows.append(
            {
                "chunk_id": chunk["chunk_id"],
                "doc_id": chunk["document_id"],
                "chunk_index": index,
                "content": chunk["content"],
                "keywords_json": "[]",
                "metadata_json": _json(
                    {
                        "citation": citation,
                        "source_id": version["source_id"],
                        "source_type": source["detected_format"],
                        "release_id": RELEASE_ID,
                        "release_status": "candidate",
                    }
                ),
                "tenant_id": TENANT_ID,
                "version_id": chunk["version_id"],
                "parent_chunk_id": chunk["parent_chunk_id"],
                "chunk_level": "child",
                "section_path_json": _json(citation["section_path"]),
                "locator_json": _json(citation),
                "content_sha256": chunk["content_hash"],
                "token_count": chunk["token_count"],
                "embedding_provider": profile["provider"],
                "embedding_model": profile["model"],
                "embedding_version": "sha256:" + profile["model_sha256"],
                "embedding_dimension": profile["dimension"],
                "embedding_status": "ready",
            }
        )

    release_items: list[dict[str, Any]] = []
    for source in ledger:
        source_id = str(source["source_id"])
        admission = str(source["admission_status"])
        version = version_by_source.get(source_id)
        document = document_by_source.get(source_id)
        if source_id in duplicate_by_source or admission == "duplicate":
            terminal, reason = "duplicate", "duplicate_content"
        elif source_id in isolation_by_source or admission == "quarantined":
            terminal = "isolated"
            reason = isolation_by_source.get(source_id) or str(source["isolation_reason"])
        elif version and document:
            terminal, reason = "published", None
        else:
            terminal, reason = "isolated", "candidate_version_missing"
        release_items.append(
            {
                "tenant_id": TENANT_ID,
                "item_id": _item_id(source_id),
                "release_id": RELEASE_ID,
                "source_id": source_id,
                "document_id": document["document_id"] if document else None,
                "version_id": version["version_id"] if version else None,
                "terminal_status": terminal,
                "reason": reason,
                "duplicate_of_source_id": duplicate_by_source.get(source_id)
                or source.get("duplicate_of_source_id")
                or None,
                "chunk_count": chunk_counts[version["version_id"]] if version else 0,
                "asset_count": 0,
                "content_sha256": source["sha256"],
            }
        )
    return {
        "documents": document_rows,
        "versions": version_rows,
        "chunks": chunk_rows,
        "release_items": release_items,
    }


def _insert_batches(connection: Any, rows: Mapping[str, list[dict[str, Any]]]) -> None:
    connection.execute(
        text(
            """
            INSERT INTO kb_documents
              (doc_id,title,source_type,source_path,checksum,metadata_json,indexed_at,
               tenant_id,domain,owner_actor_id)
            VALUES
              (:doc_id,:title,:source_type,:source_path,:checksum,CAST(:metadata_json AS jsonb),
               :indexed_at,:tenant_id,:domain,:owner_actor_id)
            ON CONFLICT (doc_id) DO NOTHING
            """
        ),
        rows["documents"],
    )
    connection.execute(
        text(
            """
            INSERT INTO kb_document_versions
              (tenant_id,version_id,document_id,source_id,source_sha256,content_sha256,
               declared_format,detected_format,parser_profile,schema_version,parse_status,
               effective_from,effective_to,metadata_json)
            VALUES
              (:tenant_id,:version_id,:document_id,:source_id,:source_sha256,:content_sha256,
               :declared_format,:detected_format,:parser_profile,:schema_version,:parse_status,
               :effective_from,:effective_to,CAST(:metadata_json AS jsonb))
            ON CONFLICT (tenant_id,version_id) DO NOTHING
            """
        ),
        rows["versions"],
    )
    connection.execute(
        text(
            """
            INSERT INTO kb_chunks
              (chunk_id,doc_id,chunk_index,content,keywords_json,metadata_json,tenant_id,
               version_id,parent_chunk_id,chunk_level,section_path_json,locator_json,
               content_sha256,token_count,embedding_provider,embedding_model,
               embedding_version,embedding_dimension,embedding_status)
            VALUES
              (:chunk_id,:doc_id,:chunk_index,:content,CAST(:keywords_json AS jsonb),
               CAST(:metadata_json AS jsonb),:tenant_id,:version_id,:parent_chunk_id,
               :chunk_level,CAST(:section_path_json AS jsonb),CAST(:locator_json AS jsonb),
               :content_sha256,:token_count,:embedding_provider,:embedding_model,
               :embedding_version,:embedding_dimension,:embedding_status)
            ON CONFLICT (chunk_id) DO NOTHING
            """
        ),
        rows["chunks"],
    )


def import_candidate(
    env_file: Path,
    release_root: Path,
    ledger_path: Path,
    schema_path: Path,
) -> dict[str, Any]:
    candidate, ledger, report = _validate_inputs(release_root, ledger_path, schema_path)
    rows = _build_rows(candidate, ledger)
    url = _load_url(env_file)
    engine = create_engine(url, pool_pre_ping=True, future=True, connect_args={"hostaddr": "127.0.0.1"})
    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": "rag-r1-candidate-import"})
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if revision != "0018_rag_enterprise_r1":
                raise CandidatePostgresError("database_revision_invalid")
            existing = connection.execute(
                text("SELECT status,manifest_sha256,is_current FROM kb_releases WHERE tenant_id=:tenant AND release_id=:release"),
                {"tenant": TENANT_ID, "release": RELEASE_ID},
            ).mappings().one_or_none()
            if existing is None:
                _insert_batches(connection, rows)
                profile = candidate["embedding_profile"]
                connection.execute(
                    text(
                        """
                        INSERT INTO kb_releases
                          (tenant_id,release_id,status,is_current,collection_name,manifest_sha256,
                           source_ledger_sha256,embedding_provider,embedding_model,embedding_version,
                           embedding_dimension,embedding_model_sha256,reranker_model,
                           reranker_version,reranker_model_sha256,sparse_profile,run_id,trace_id,created_by)
                        VALUES
                          (:tenant_id,:release_id,'candidate',false,:collection_name,:manifest_sha256,
                           :source_ledger_sha256,:embedding_provider,:embedding_model,:embedding_version,
                           1024,:embedding_model_sha256,:reranker_model,:reranker_version,
                           :reranker_model_sha256,:sparse_profile,:run_id,:trace_id,:created_by)
                        """
                    ),
                    {
                        "tenant_id": TENANT_ID,
                        "release_id": RELEASE_ID,
                        "collection_name": COLLECTION,
                        "manifest_sha256": candidate["artifact_sha256"],
                        "source_ledger_sha256": EXPECTED_LEDGER_SHA256,
                        "embedding_provider": profile["provider"],
                        "embedding_model": profile["model"],
                        "embedding_version": "sha256:" + profile["model_sha256"],
                        "embedding_model_sha256": profile["model_sha256"],
                        "reranker_model": "BAAI/bge-reranker-v2-m3",
                        "reranker_version": "sha256:" + EXPECTED_RERANKER_MANIFEST_SHA256,
                        "reranker_model_sha256": EXPECTED_RERANKER_MANIFEST_SHA256,
                        "sparse_profile": profile["sparse_profile"],
                        "run_id": RUN_ID,
                        "trace_id": TRACE_ID,
                        "created_by": ACTOR_ID,
                    },
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO kb_release_items
                          (tenant_id,item_id,release_id,source_id,document_id,version_id,
                           terminal_status,reason,duplicate_of_source_id,chunk_count,asset_count,content_sha256)
                        VALUES
                          (:tenant_id,:item_id,:release_id,:source_id,:document_id,:version_id,
                           :terminal_status,:reason,:duplicate_of_source_id,:chunk_count,:asset_count,:content_sha256)
                        ON CONFLICT (tenant_id,item_id) DO NOTHING
                        """
                    ),
                    rows["release_items"],
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO kb_rag_audit_events
                          (tenant_id,event_id,event_type,actor_id,resource_type,resource_id,
                           release_id,run_id,trace_id,status,details_json)
                        VALUES
                          (:tenant_id,:event_id,'candidate_imported',:actor_id,'knowledge_release',
                           :release_id,:release_id,:run_id,:trace_id,'success',CAST(:details_json AS jsonb))
                        """
                    ),
                    {
                        "tenant_id": TENANT_ID,
                        "event_id": "evt_" + uuid.uuid5(uuid.NAMESPACE_URL, TRACE_ID).hex[:24],
                        "actor_id": ACTOR_ID,
                        "release_id": RELEASE_ID,
                        "run_id": RUN_ID,
                        "trace_id": TRACE_ID,
                        "details_json": _json({"point_count": report["point_count"], "alias_mutated": False}),
                    },
                )
                disposition = "created"
            else:
                if (
                    existing["status"] != "candidate"
                    or existing["manifest_sha256"] != candidate["artifact_sha256"]
                    or bool(existing["is_current"])
                ):
                    raise CandidatePostgresError("existing_release_conflict")
                disposition = "unchanged"

            counts = {
                table: int(
                    connection.execute(
                        text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id=:tenant" + (" AND release_id=:release" if table in {"kb_release_items", "kb_releases"} else "")),
                        {"tenant": TENANT_ID, "release": RELEASE_ID},
                    ).scalar_one()
                )
                for table in ("kb_document_versions", "kb_release_items", "kb_releases")
            }
            candidate_chunks = int(
                connection.execute(
                    text("SELECT COUNT(*) FROM kb_chunks WHERE tenant_id=:tenant AND embedding_version=:version"),
                    {"tenant": TENANT_ID, "version": "sha256:" + EXPECTED_EMBEDDING_MANIFEST_SHA256},
                ).scalar_one()
            )
            if counts["kb_release_items"] != 83 or counts["kb_releases"] != 1 or candidate_chunks != 8339:
                raise CandidatePostgresError("candidate_database_counts_invalid")
    finally:
        engine.dispose()
    return {
        "status": "PASS",
        "scope": "candidate_only",
        "release_id": RELEASE_ID,
        "release_status": "candidate",
        "is_current": False,
        "collection": COLLECTION,
        "alias_mutated": False,
        "disposition": disposition,
        "documents": 45,
        "chunks": candidate_chunks,
        "release_items": counts["kb_release_items"],
        "database_revision": "0018_rag_enterprise_r1",
        "production_switch": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the verified RAG-R1 Candidate into PostgreSQL.")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, default=EXPECTED_RELEASE_ROOT)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("docs/codex/contracts/rag_candidate_corpus_v1.schema.json"),
    )
    parser.add_argument("--confirm-local-candidate-write", action="store_true")
    args = parser.parse_args()
    if not args.confirm_local_candidate_write:
        raise SystemExit("candidate_write_confirmation_required")
    result = import_candidate(
        args.env_file.resolve(),
        args.release_root.resolve(),
        args.ledger.resolve(),
        args.schema.resolve(),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
