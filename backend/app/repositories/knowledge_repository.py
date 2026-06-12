from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

from sqlalchemy import text

from .base import dumps_json, jsonable, loads_json, mapping_list, postgres_engine
from backend.app.services.embedding_service import embed_batch_with_metadata, embed_text_with_metadata, get_embedding_provider


def tokenize(text_value: str) -> list[str]:
    compact = re.sub(r"\s+", "", (text_value or "").lower())
    tokens = [item for item in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", compact) if item]
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        if re.fullmatch(r"[\u4e00-\u9fa5]{4,}", token):
            expanded.extend(token[index : index + 2] for index in range(0, len(token) - 1))
    return list(dict.fromkeys(expanded))[:80]


def document_id(source_path: str, content: str) -> str:
    digest = hashlib.sha1(f"{source_path}\n{content}".encode("utf-8", errors="ignore")).hexdigest()
    return "kb_" + digest[:20]


def checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()


def split_chunks(content: str, chunk_size: int = 900) -> list[str]:
    parts = [part.strip() for part in re.split(r"\n\s*\n", content or "") if part.strip()]
    chunks: list[str] = []
    current = ""
    for part in parts or [content]:
        normalized = re.sub(r"\s+", " ", part).strip()
        if not normalized:
            continue
        if len(current) + len(normalized) <= chunk_size:
            current = f"{current}\n{normalized}".strip()
        else:
            if current:
                chunks.append(current)
            current = normalized
    if current:
        chunks.append(current)
    output: list[str] = []
    for chunk in chunks:
        if len(chunk) <= chunk_size * 1.4:
            output.append(chunk)
            continue
        for index in range(0, len(chunk), chunk_size):
            output.append(chunk[index : index + chunk_size])
    return output[:200]


def _chunk_metadata(metadata: dict[str, Any] | None, embedding_meta: dict[str, Any] | None) -> dict[str, Any]:
    value = dict(metadata or {})
    if embedding_meta:
        value["embedding"] = embedding_meta
    return value


def upsert_document(
    *,
    title: str,
    source_type: str,
    source_path: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "message": "PostgreSQL 不可用"}
    doc_id = document_id(source_path, content)
    chunks = split_chunks(content)
    embedding_results = embed_batch_with_metadata([f"{title}\n{chunk}" for chunk in chunks])
    now = datetime.now()
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO kb_documents (
                        doc_id, title, source_type, source_path, checksum,
                        metadata_json, indexed_at, updated_at
                    )
                    VALUES (
                        :doc_id, :title, :source_type, :source_path, :checksum,
                        CAST(:metadata_json AS jsonb), :indexed_at, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (doc_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        source_type = EXCLUDED.source_type,
                        source_path = EXCLUDED.source_path,
                        checksum = EXCLUDED.checksum,
                        metadata_json = EXCLUDED.metadata_json,
                        indexed_at = EXCLUDED.indexed_at,
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    "doc_id": doc_id,
                    "title": title,
                    "source_type": source_type,
                    "source_path": source_path,
                    "checksum": checksum(content),
                    "metadata_json": dumps_json(metadata or {}),
                    "indexed_at": now,
                },
            )
            conn.execute(text("DELETE FROM kb_chunks WHERE doc_id = :doc_id"), {"doc_id": doc_id})
            for index, chunk in enumerate(chunks):
                embedding_result = embedding_results[index] if index < len(embedding_results) else {"embedding": [], "metadata": {}}
                embedding = embedding_result.get("embedding") or []
                metadata_with_embedding = _chunk_metadata(metadata, embedding_result.get("metadata") or {})
                conn.execute(
                    text(
                        """
                        INSERT INTO kb_chunks (
                            chunk_id, doc_id, chunk_index, content,
                            keywords_json, embedding_json, metadata_json
                        )
                        VALUES (
                            :chunk_id, :doc_id, :chunk_index, :content,
                            CAST(:keywords_json AS jsonb), CAST(:embedding_json AS jsonb),
                            CAST(:metadata_json AS jsonb)
                        )
                        """
                    ),
                    {
                        "chunk_id": f"{doc_id}_{index:04d}",
                        "doc_id": doc_id,
                        "chunk_index": index,
                        "content": chunk,
                        "keywords_json": dumps_json(tokenize(f"{title} {chunk}")),
                        "embedding_json": dumps_json(embedding),
                        "metadata_json": dumps_json(metadata_with_embedding),
                    },
                )
        return {"available": True, "doc_id": doc_id, "chunks": len(chunks)}
    except Exception as exc:
        return {"available": False, "message": str(exc), "doc_id": doc_id}


def search_keyword_chunks(query: str, top_k: int = 20) -> list[dict[str, Any]]:
    engine = postgres_engine()
    if engine is None:
        return []
    tokens = tokenize(query)
    if not tokens:
        return []
    params = {f"token_{idx}": f"%{token}%" for idx, token in enumerate(tokens[:8])}
    predicates = " OR ".join([f"c.content ILIKE :token_{idx} OR d.title ILIKE :token_{idx}" for idx in range(len(params))])
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT c.chunk_id, c.doc_id, c.chunk_index, c.content,
                           c.keywords_json, c.embedding_json, c.metadata_json,
                           d.title, d.source_type, d.source_path
                    FROM kb_chunks c
                    JOIN kb_documents d ON d.doc_id = c.doc_id
                    WHERE {predicates}
                    LIMIT 200
                    """
                ),
                params,
            ).mappings().all()
    except Exception:
        return []
    scored: list[dict[str, Any]] = []
    q_tokens = set(tokens)
    for row in mapping_list(rows):
        keywords = loads_json(row.get("keywords_json"), default=[])
        keyword_set = set(str(item) for item in keywords) if isinstance(keywords, list) else set()
        content = str(row.get("content") or "")
        score = len(q_tokens & keyword_set) + sum(content.lower().count(token.lower()) for token in tokens[:8])
        if score <= 0:
            continue
        scored.append(
            jsonable(
                {
                    "chunk_id": row.get("chunk_id"),
                    "doc_id": row.get("doc_id"),
                    "title": row.get("title"),
                    "source": row.get("source_path"),
                    "source_type": row.get("source_type"),
                    "chunk_index": row.get("chunk_index"),
                    "content": content[:700],
                    "keyword_score": float(score),
                    "vector_score": 0.0,
                    "rerank_score": 0.0,
                    "final_score": float(score),
                    "score": score,
                    "metadata": loads_json(row.get("metadata_json"), default={}),
                }
            )
        )
    scored.sort(key=lambda item: item["keyword_score"], reverse=True)
    return scored[: max(1, min(int(top_k or 20), 100))]


def list_embedded_chunks(limit: int = 2000) -> list[dict[str, Any]]:
    engine = postgres_engine()
    if engine is None:
        return []
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT c.chunk_id, c.doc_id, c.chunk_index, c.content,
                           c.keywords_json, c.embedding_json, c.metadata_json,
                           d.title, d.source_type, d.source_path
                    FROM kb_chunks c
                    JOIN kb_documents d ON d.doc_id = c.doc_id
                    WHERE c.embedding_json IS NOT NULL
                    ORDER BY d.updated_at DESC NULLS LAST, c.created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": max(1, min(int(limit or 2000), 10000))},
            ).mappings().all()
    except Exception:
        return []
    items: list[dict[str, Any]] = []
    for row in mapping_list(rows):
        embedding = loads_json(row.get("embedding_json"), default=[])
        if not isinstance(embedding, list) or not embedding:
            continue
        metadata = loads_json(row.get("metadata_json"), default={})
        embedding_meta = metadata.get("embedding") if isinstance(metadata, dict) else {}
        items.append(
            jsonable(
                {
                    "chunk_id": row.get("chunk_id"),
                    "doc_id": row.get("doc_id"),
                    "title": row.get("title"),
                    "source": row.get("source_path"),
                    "source_type": row.get("source_type"),
                    "chunk_index": row.get("chunk_index"),
                    "content": str(row.get("content") or "")[:900],
                    "embedding": embedding,
                    "embedding_meta": embedding_meta if isinstance(embedding_meta, dict) else {},
                    "keyword_score": 0.0,
                    "vector_score": 0.0,
                    "rerank_score": 0.0,
                    "final_score": 0.0,
                    "metadata": metadata,
                }
            )
        )
    return items


def backfill_missing_embeddings(limit: int = 5000) -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "updated": 0, "message": "PostgreSQL 不可用"}
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT c.chunk_id, c.content, c.metadata_json, d.title
                    FROM kb_chunks c
                    JOIN kb_documents d ON d.doc_id = c.doc_id
                    WHERE c.embedding_json IS NULL
                       OR (
                            jsonb_typeof(c.embedding_json) = 'array'
                            AND jsonb_array_length(c.embedding_json) = 0
                       )
                    LIMIT :limit
                    """
                ),
                {"limit": max(1, min(int(limit or 5000), 20000))},
            ).mappings().all()
            updated = 0
            for row in mapping_list(rows):
                embedding_result = embed_text_with_metadata(f"{row.get('title') or ''}\n{row.get('content') or ''}")
                embedding = embedding_result.get("embedding") or []
                if not embedding:
                    continue
                existing_metadata = loads_json(row.get("metadata_json"), default={})
                metadata_with_embedding = _chunk_metadata(
                    existing_metadata if isinstance(existing_metadata, dict) else {},
                    embedding_result.get("metadata") or {},
                )
                conn.execute(
                    text(
                        """
                        UPDATE kb_chunks
                        SET embedding_json = CAST(:embedding_json AS jsonb),
                            metadata_json = CAST(:metadata_json AS jsonb),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE chunk_id = :chunk_id
                        """
                    ),
                    {
                        "chunk_id": row.get("chunk_id"),
                        "embedding_json": dumps_json(embedding),
                        "metadata_json": dumps_json(metadata_with_embedding),
                    },
                )
                updated += 1
        return {"available": True, "updated": updated}
    except Exception as exc:
        return {"available": False, "updated": 0, "message": str(exc)[:300]}


def refresh_stale_embeddings(limit: int = 20000) -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "updated": 0, "message": "PostgreSQL 涓嶅彲鐢?"}
    provider = get_embedding_provider()
    expected_provider = getattr(provider, "name", "")
    expected_model = getattr(provider, "model", "")
    expected_version = getattr(provider, "version", "")
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT c.chunk_id, c.content, c.embedding_json, c.metadata_json, d.title
                    FROM kb_chunks c
                    JOIN kb_documents d ON d.doc_id = c.doc_id
                    ORDER BY d.updated_at DESC NULLS LAST, c.created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": max(1, min(int(limit or 20000), 50000))},
            ).mappings().all()
    except Exception as exc:
        return {"available": False, "updated": 0, "message": str(exc)[:300]}

    stale_rows: list[dict[str, Any]] = []
    for row in mapping_list(rows):
        metadata = loads_json(row.get("metadata_json"), default={})
        embedding_meta = metadata.get("embedding") if isinstance(metadata, dict) else {}
        embedding = loads_json(row.get("embedding_json"), default=[])
        if not isinstance(embedding_meta, dict):
            embedding_meta = {}
        is_stale = (
            not isinstance(embedding, list)
            or not embedding
            or embedding_meta.get("provider") != expected_provider
            or embedding_meta.get("model") != expected_model
            or embedding_meta.get("version") != expected_version
        )
        # Do not downgrade existing high-dimensional semantic embeddings to the
        # lightweight local hash provider in test or fallback environments.
        if (
            expected_provider == "local_hash"
            and isinstance(embedding, list)
            and len(embedding) >= 768
            and embedding_meta.get("provider") in {"sentence_transformers", "bge"}
        ):
            is_stale = False
        if is_stale:
            stale_rows.append(row)
    if not stale_rows:
        return {
            "available": True,
            "updated": 0,
            "checked": len(rows),
            "provider": expected_provider,
            "model": expected_model,
            "version": expected_version,
        }

    texts = [f"{row.get('title') or ''}\n{row.get('content') or ''}" for row in stale_rows]
    embedding_results = embed_batch_with_metadata(texts)
    updated = 0
    try:
        with engine.begin() as conn:
            for row, embedding_result in zip(stale_rows, embedding_results):
                embedding = embedding_result.get("embedding") or []
                if not embedding:
                    continue
                existing_metadata = loads_json(row.get("metadata_json"), default={})
                metadata_with_embedding = _chunk_metadata(
                    existing_metadata if isinstance(existing_metadata, dict) else {},
                    embedding_result.get("metadata") or {},
                )
                conn.execute(
                    text(
                        """
                        UPDATE kb_chunks
                        SET embedding_json = CAST(:embedding_json AS jsonb),
                            metadata_json = CAST(:metadata_json AS jsonb),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE chunk_id = :chunk_id
                        """
                    ),
                    {
                        "chunk_id": row.get("chunk_id"),
                        "embedding_json": dumps_json(embedding),
                        "metadata_json": dumps_json(metadata_with_embedding),
                    },
                )
                updated += 1
    except Exception as exc:
        return {"available": False, "updated": updated, "checked": len(rows), "stale": len(stale_rows), "message": str(exc)[:300]}
    return {
        "available": True,
        "updated": updated,
        "checked": len(rows),
        "stale": len(stale_rows),
        "provider": expected_provider,
        "model": expected_model,
        "version": expected_version,
    }


def search_chunks(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    return search_keyword_chunks(query, top_k=top_k)


def knowledge_stats() -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "documents": 0, "chunks": 0}
    try:
        with engine.connect() as conn:
            documents = int(conn.execute(text("SELECT COUNT(*) FROM kb_documents")).scalar() or 0)
            chunks = int(conn.execute(text("SELECT COUNT(*) FROM kb_chunks")).scalar() or 0)
    except Exception:
        return {"available": False, "documents": 0, "chunks": 0}
    return {"available": True, "documents": documents, "chunks": chunks}
