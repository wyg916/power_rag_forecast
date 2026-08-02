from __future__ import annotations

import hashlib
import json
import os
import uuid
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.main import app
from backend.app.repositories.base import postgres_engine
from backend.app.repositories.knowledge_repository import get_chunks_by_ids, get_vector_index_rows
from backend.app.services.vector_index_service import query_vector_index
from backend.app.services.vector_index_service import build_vector_index
from knowledge_pipeline import import_chunks_to_kb as importer


TARGET_DATABASE = "postgres"
REQUIRED_DOCUMENT_FIELDS = {
    "document_id", "document_version", "title", "domain", "evidence_source_type",
    "source_name", "effective_at", "expires_at", "generated_at", "content_hash",
    "language", "status", "tags", "evidence_level",
}
REQUIRED_CHUNK_FIELDS = {
    "db_chunk_id", "chunk_index", "section_title", "content_hash", "token_count",
    "domain", "source_type", "embedding_status", "embedding_version", "status",
}


def _engine():
    engine = postgres_engine()
    assert engine is not None
    with engine.connect() as conn:
        assert conn.execute(text("select current_database()" )).scalar() == TARGET_DATABASE
        if os.environ.get("BETA10D_TEST_ISOLATION_ACTIVE") == "1":
            assert conn.execute(text("select current_schema()" )).scalar() == os.environ["BETA10D_TEST_SCHEMA"]
    return engine


def _knowledge_fingerprint() -> str:
    engine = _engine()
    with engine.connect() as conn:
        docs = conn.execute(
            text(
                "select doc_id, title, source_type, source_path, checksum, "
                "metadata_json::text, indexed_at, created_at, updated_at "
                "from kb_documents order by doc_id"
            )
        ).all()
        chunks = conn.execute(
            text(
                "select chunk_id, doc_id, chunk_index, content, keywords_json::text, "
                "embedding_json::text, metadata_json::text, created_at, updated_at "
                "from kb_chunks order by chunk_id"
            )
        ).all()
    payload = json.dumps(
        {"documents": [tuple(row) for row in docs], "chunks": [tuple(row) for row in chunks]},
        default=str,
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _active_ready_embedding_count() -> int:
    with _engine().connect() as conn:
        return int(
            conn.execute(
                text(
                    """
                    select count(*)
                    from kb_chunks c
                    join kb_documents d on d.doc_id = c.doc_id
                    where c.embedding_json is not null
                      and coalesce(c.metadata_json->>'embedding_status', '') = 'ready'
                      and coalesce(c.metadata_json->>'status', '') = 'active'
                      and coalesce(d.metadata_json->>'status', 'active') = 'active'
                      and coalesce(d.metadata_json->>'data_origin', '') <> 'seed'
                      and coalesce(d.metadata_json->>'domain', '') <> ''
                      and coalesce(c.metadata_json->>'domain', '') = coalesce(d.metadata_json->>'domain', '')
                      and coalesce(c.metadata_json->>'source_type', '') = coalesce(d.metadata_json->>'evidence_source_type', 'real')
                      and coalesce(d.metadata_json->>'evidence_source_type', 'real') <> 'fallback'
                    """
                )
            ).scalar_one()
        )


def _fixture_doc(doc_id: str, source_path: str, status: str = "active") -> dict:
    return {
        "doc_id": doc_id,
        "title": "PHASE5 事务测试文档",
        "source_type": importer.SOURCE_TYPE,
        "source_path": source_path,
        "checksum": "fixture-checksum-" + doc_id,
        "metadata": {
            "document_id": doc_id,
            "document_version": "fixture-v1",
            "title": "PHASE5 事务测试文档",
            "domain": "phase5_test",
            "evidence_source_type": "real",
            "data_origin": "official",
            "source_name": "PHASE5 integration fixture",
            "source_uri": "",
            "source_path": source_path,
            "effective_at": None,
            "expires_at": None,
            "generated_at": "2026-07-18T00:00:00",
            "applicability_scope": "isolated_test_fixture",
            "content_hash": "fixture-content-hash-" + doc_id,
            "language": "zh-CN",
            "status": status,
            "tags": ["phase5", "integration"],
            "evidence_level": "test_fixture",
        },
    }


def _fixture_chunk(
    chunk_id: str, doc_id: str, index: int = 0, *, embedding: list[float] | None = None
) -> dict:
    content = f"PHASE5 隔离数据库事务回滚测试内容：{chunk_id}。"
    return {
        "chunk_id": chunk_id,
        "doc_id": doc_id,
        "chunk_index": index,
        "content": content,
        "keywords": ["PHASE5", "rollback"],
        "embedding": embedding,
        "metadata": {
            "db_chunk_id": chunk_id,
            "chunk_index": index,
            "section_title": "事务回滚",
            "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "token_count": len(content),
            "domain": "phase5_test",
            "source_type": "real",
            "embedding_status": "ready" if embedding else "pending",
            "embedding_version": "bge-large-zh-v1.5-v1" if embedding else "",
            "embedding": {
                "provider": "sentence_transformers",
                "model": "bge-large-zh-v1.5",
                "version": "bge-large-zh-v1.5-v1",
                "dim": 1024,
                "fallback": False,
            } if embedding else {},
            "status": "active",
        },
    }


@pytest.fixture(scope="module", autouse=True)
def _isolated_phase5_a2_facts():
    if os.environ.get("BETA10D_TEST_ISOLATION_ACTIVE") != "1":
        pytest.fail("PHASE5 A2 tests require the restricted isolated-schema runner")
    previous_runtime_profile = {
        name: os.environ.get(name) for name in ("RAG_PROFILE", "APP_ENV")
    }
    os.environ["RAG_PROFILE"] = "legacy-isolated-test"
    os.environ["APP_ENV"] = "test"
    docs = {
        f"phase5_a2_doc_{index:03d}": _fixture_doc(
            f"phase5_a2_doc_{index:03d}", f"fixture://phase5-a2/{index:03d}"
        )
        for index in range(36)
    }
    records = []
    for index in range(240):
        document_id = f"phase5_a2_doc_{index % 36:03d}"
        vector = [0.0] * 1024
        vector[index] = 1.0
        records.append(
            _fixture_chunk(
                f"phase5_a2_chunk_{index:04d}",
                document_id,
                index // 36,
                embedding=vector,
            )
        )
    inserted_documents, inserted_chunks, skipped = importer.upsert_records(
        mode="append",
        docs=docs,
        records=records,
        resume=False,
        import_batch="phase5_a2_isolated_fixture_v1",
    )
    assert (inserted_documents, inserted_chunks, skipped) == (36, 240, 0)
    root = os.path.join(
        os.path.dirname(__file__), "..", ".codex_tmp", os.environ["BETA10D_TEST_SCHEMA"]
    )
    os.environ["RAG_VECTOR_INDEX_PATH"] = root + ".npz"
    os.environ["RAG_VECTOR_INDEX_METADATA_PATH"] = root + ".json"
    index = build_vector_index()
    assert index["available"] is True and index["indexed"] == 240
    try:
        yield
    finally:
        for name, value in previous_runtime_profile.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_a2_1_database_metadata_and_pending_embeddings():
    engine = _engine()
    with engine.connect() as conn:
        documents = conn.execute(
            text("select doc_id, metadata_json from kb_documents where source_type=:s"),
            {"s": importer.SOURCE_TYPE},
        ).all()
        chunks = conn.execute(
            text(
                "select c.chunk_id, c.content, c.embedding_json, c.metadata_json "
                "from kb_chunks c join kb_documents d on d.doc_id=c.doc_id where d.source_type=:s"
            ),
            {"s": importer.SOURCE_TYPE},
        ).all()

    assert len(documents) == 36
    assert len(chunks) == 240
    assert all(REQUIRED_DOCUMENT_FIELDS <= set(metadata or {}) for _, metadata in documents)
    assert all(REQUIRED_CHUNK_FIELDS <= set(metadata or {}) for _, _, _, metadata in chunks)
    embedding_statuses = {metadata["embedding_status"] for _, _, _, metadata in chunks}
    assert embedding_statuses in ({"pending"}, {"ready"})
    if embedding_statuses == {"pending"}:
        assert all(not embedding for _, _, embedding, _ in chunks)
    else:
        assert all(isinstance(embedding, list) and len(embedding) == 1024 for _, _, embedding, _ in chunks)
        assert {metadata["embedding_version"] for _, _, _, metadata in chunks} == {"bge-large-zh-v1.5-v1"}
    assert all(content and content.strip() for _, content, _, _ in chunks)


def test_a2_1_no_active_content_duplicates_and_stable_order():
    engine = _engine()
    with engine.connect() as conn:
        duplicates = conn.execute(
            text(
                "select c.metadata_json->>'content_hash', count(1) from kb_chunks c "
                "join kb_documents d on d.doc_id=c.doc_id "
                "where coalesce(d.metadata_json->>'status','active')='active' "
                "and coalesce(c.metadata_json->>'status','active')='active' "
                "group by c.metadata_json->>'content_hash' having count(1)>1"
            )
        ).all()
        unstable = conn.execute(
            text(
                "select doc_id from kb_chunks group by doc_id "
                "having count(1) <> count(distinct chunk_index)"
            )
        ).all()
    assert duplicates == []
    assert unstable == []


def test_a2_1_explicit_import_failure_rolls_back_without_half_product():
    token = uuid.uuid4().hex[:12]
    doc_id = f"phase5_fail_doc_{token}"
    chunk_ok = f"phase5_fail_chunk_{token}_ok"
    chunk_bad = f"phase5_fail_chunk_{token}_bad"
    docs = {doc_id: _fixture_doc(doc_id, f"fixture://failure/{token}")}
    records = [_fixture_chunk(chunk_ok, doc_id), _fixture_chunk(chunk_bad, "missing_doc")]

    with pytest.raises(Exception):
        importer.upsert_records(
            mode="append", docs=docs, records=records, resume=False, import_batch=f"failure_{token}"
        )

    engine = _engine()
    with engine.connect() as conn:
        assert not conn.execute(text("select 1 from kb_documents where doc_id=:id"), {"id": doc_id}).scalar()
        assert not conn.execute(
            text("select 1 from kb_chunks where chunk_id in (:a,:b)"), {"a": chunk_ok, "b": chunk_bad}
        ).scalar()


def test_a2_1_content_change_supersedes_old_version_without_delete(monkeypatch):
    token = uuid.uuid4().hex[:12]
    source_path = f"fixture://version/{token}"
    first_doc = f"phase5_version_{token}_v1"
    second_doc = f"phase5_version_{token}_v2"
    engine = _engine()
    conn = engine.connect()
    outer = conn.begin()

    class TransactionProxy:
        @contextmanager
        def begin(self):
            yield conn

    monkeypatch.setattr(importer, "postgres_engine", lambda: TransactionProxy())
    try:
        importer.upsert_records(
            mode="append",
            docs={first_doc: _fixture_doc(first_doc, source_path)},
            records=[_fixture_chunk(f"{first_doc}_chunk", first_doc)],
            resume=False,
            import_batch="version_v1",
        )
        importer.upsert_records(
            mode="append",
            docs={second_doc: _fixture_doc(second_doc, source_path)},
            records=[_fixture_chunk(f"{second_doc}_chunk", second_doc)],
            resume=False,
            import_batch="version_v2",
        )
        rows = conn.execute(
            text("select doc_id, metadata_json->>'status' from kb_documents where source_path=:p order by doc_id"),
            {"p": source_path},
        ).all()
        assert rows == [(first_doc, "superseded"), (second_doc, "active")]
        assert conn.execute(
            text("select count(1) from kb_chunks where doc_id in (:a,:b)"), {"a": first_doc, "b": second_doc}
        ).scalar() == 2
    finally:
        outer.rollback()
        conn.close()


def test_a2_1_get_and_search_100_times_have_no_database_side_effects(monkeypatch):
    monkeypatch.setenv("RAG_ENABLED", "0")
    monkeypatch.setenv("RAG_CACHE_ENABLED", "0")
    monkeypatch.setenv("RAG_RERANK_ENABLED", "0")
    monkeypatch.setenv("RAG_FILE_FALLBACK_ENABLED", "0")
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "disabled")
    before = _knowledge_fingerprint()
    client = TestClient(app)
    headers = {"X-User": "phase5_acceptance", "X-Role": "analyst"}

    for _ in range(100):
        response = client.get("/api/knowledge/documents?page=1&page_size=100", headers=headers)
        assert response.status_code == 200
    for _ in range(100):
        response = client.get("/api/knowledge/search?q=LMP&top_k=5", headers=headers)
        assert response.status_code == 200

    assert _knowledge_fingerprint() == before


def test_a2_2_all_active_chunks_have_stable_finite_embeddings():
    rows = get_vector_index_rows()
    assert rows
    assert len(rows) == _active_ready_embedding_count()
    assert importer.pending_active_chunk_ids() == set()
    assert {len(row["embedding"]) for row in rows} == {1024}
    assert {row["metadata"].get("embedding_version") for row in rows} == {"bge-large-zh-v1.5-v1"}
    assert {row["metadata"].get("embedding_status") for row in rows} == {"ready"}


def test_a2_2_persisted_vector_index_returns_real_filtered_chunks():
    row = get_vector_index_rows()[0]
    result = query_vector_index(row["embedding"], top_k=5)
    assert result["available"] is True
    assert result["metadata"]["dimension"] == 1024
    assert result["metadata"]["row_count"] == _active_ready_embedding_count()
    assert result["items"][0]["chunk_id"] == row["chunk_id"]
    chunks = get_chunks_by_ids([item["chunk_id"] for item in result["items"]])
    assert chunks
    assert all(item["status"] == "active" for item in chunks)
    assert all(item["document_id"] and item["chunk_id"] and item["content"] for item in chunks)


def test_a2_2_vector_index_fail_closed_for_missing_index_and_wrong_dimension(monkeypatch, tmp_path):
    wrong_dim = query_vector_index([0.1, 0.2], top_k=5)
    assert wrong_dim == {"available": False, "reason": "vector_dimension_mismatch", "items": []}
    monkeypatch.setenv("RAG_VECTOR_INDEX_PATH", str(tmp_path / "missing.npz"))
    monkeypatch.setenv("RAG_VECTOR_INDEX_METADATA_PATH", str(tmp_path / "missing.json"))
    missing = query_vector_index([0.0] * 1024, top_k=5)
    assert missing == {"available": False, "reason": "vector_index_unavailable", "items": []}
