from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from config_loader import load_dotenv
from backend.app.repositories.base import loads_json, mapping_list, postgres_engine
from backend.app.services.embedding_service import get_embedding_provider
from backend.app.services.rerank_service import get_reranker


EXPECTED_BGE_LARGE_DIM = 1024


def _env(name: str, default: str = "") -> str:
    load_dotenv()
    return os.environ.get(name, default).strip()


def _path_info(path_value: str) -> dict[str, Any]:
    path = Path(path_value) if path_value else None
    exists = bool(path and path.exists())
    is_dir = bool(path and path.is_dir())
    return {
        "path": path_value,
        "exists": exists,
        "is_dir": is_dir,
        "readable": bool(is_dir and os.access(str(path), os.R_OK)) if path else False,
    }


def _provider_state() -> dict[str, Any]:
    embedding_provider_env = (_env("RAG_EMBEDDING_PROVIDER", "local") or "local").lower()
    embedding_model_path = _env("RAG_EMBEDDING_MODEL_PATH", "")
    embedding_path = _path_info(embedding_model_path)
    embedding_dim_env = _env("RAG_EMBEDDING_DIM", "")
    embedding_dim = int(embedding_dim_env) if embedding_dim_env.isdigit() else 0
    try:
        provider = get_embedding_provider()
        embedding_provider = getattr(provider, "name", embedding_provider_env)
        embedding_model = getattr(provider, "model", _env("RAG_EMBEDDING_MODEL", ""))
        embedding_dim = int(getattr(provider, "dimensions", 0) or embedding_dim or 0)
    except Exception as exc:
        embedding_provider = "provider_error"
        embedding_model = _env("RAG_EMBEDDING_MODEL", "")
        embedding_error = exc.__class__.__name__
    else:
        embedding_error = ""

    rerank_provider_env = (_env("RAG_RERANK_PROVIDER", "local") or "local").lower()
    rerank_model_path = _env("RAG_RERANK_MODEL_PATH", "")
    rerank_path = _path_info(rerank_model_path)
    try:
        reranker = get_reranker()
        rerank_provider = getattr(reranker, "name", rerank_provider_env)
    except Exception as exc:
        rerank_provider = "provider_error"
        rerank_error = exc.__class__.__name__
    else:
        rerank_error = ""

    embedding_requires_path = embedding_provider_env in {"sentence_transformers", "sentence-transformers", "sentence_transformer", "bge"}
    rerank_requires_path = rerank_provider_env in {"bge", "bge_reranker", "transformers", "local_bge"}
    fallback_reasons: list[str] = []
    if embedding_provider in {"local_hash", "disabled"}:
        fallback_reasons.append(f"embedding_provider={embedding_provider}")
    if embedding_requires_path and not embedding_path["exists"]:
        fallback_reasons.append("embedding_model_path_missing")
    if embedding_dim and embedding_dim != EXPECTED_BGE_LARGE_DIM and embedding_provider_env in {"bge", "sentence_transformers", "sentence-transformers"}:
        fallback_reasons.append(f"embedding_dim={embedding_dim}, expected={EXPECTED_BGE_LARGE_DIM}")
    if rerank_provider in {"local_heuristic", "local_heuristic_fallback", "disabled"}:
        fallback_reasons.append(f"rerank_provider={rerank_provider}")
    if rerank_requires_path and not rerank_path["exists"]:
        fallback_reasons.append("rerank_model_path_missing")
    if embedding_error:
        fallback_reasons.append(f"embedding_error={embedding_error}")
    if rerank_error:
        fallback_reasons.append(f"rerank_error={rerank_error}")

    return {
        "embedding_provider": embedding_provider,
        "embedding_provider_config": embedding_provider_env,
        "embedding_model": embedding_model,
        "embedding_model_path": embedding_model_path,
        "embedding_model_path_exists": embedding_path["exists"],
        "embedding_model_path_readable": embedding_path["readable"],
        "embedding_dim": embedding_dim,
        "rerank_provider": rerank_provider,
        "rerank_provider_config": rerank_provider_env,
        "rerank_model_path": rerank_model_path,
        "rerank_model_path_exists": rerank_path["exists"],
        "rerank_model_path_readable": rerank_path["readable"],
        "fallback_enabled": bool(fallback_reasons),
        "fallback_reasons": fallback_reasons,
    }


def _knowledge_state() -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {
            "available": False,
            "kb_document_count": 0,
            "kb_chunk_count": 0,
            "embedded_chunk_count": 0,
            "formal_metadata_complete_count": 0,
            "last_embedding_refresh_at": None,
            "embedding_dim_distribution": {},
        }
    try:
        with engine.connect() as conn:
            documents = int(
                conn.execute(text("SELECT COUNT(*) FROM kb_documents WHERE metadata_json->>'data_origin'='official'")).scalar() or 0
            )
            formal_complete = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM kb_documents
                        WHERE metadata_json->>'data_origin'='official'
                          AND COALESCE(metadata_json->>'source_name','') <> ''
                          AND COALESCE(metadata_json->>'document_version','') <> ''
                          AND COALESCE(metadata_json->>'generated_at','') <> ''
                          AND COALESCE(metadata_json->>'domain','') <> ''
                          AND COALESCE(metadata_json->>'applicability_scope','') <> ''
                        """
                    )
                ).scalar()
                or 0
            )
            chunks = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM kb_chunks c
                        JOIN kb_documents d ON d.doc_id=c.doc_id
                        WHERE d.metadata_json->>'data_origin'='official'
                        """
                    )
                ).scalar()
                or 0
            )
            embedded = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM kb_chunks c
                        JOIN kb_documents d ON d.doc_id=c.doc_id
                        WHERE c.embedding_json IS NOT NULL
                          AND jsonb_typeof(c.embedding_json) = 'array'
                          AND jsonb_array_length(c.embedding_json) > 0
                          AND d.metadata_json->>'data_origin'='official'
                        """
                    )
                ).scalar()
                or 0
            )
            last_refresh = conn.execute(
                text(
                    """
                    SELECT MAX(c.updated_at)
                    FROM kb_chunks c
                    JOIN kb_documents d ON d.doc_id=c.doc_id
                    WHERE c.embedding_json IS NOT NULL
                      AND jsonb_typeof(c.embedding_json) = 'array'
                      AND jsonb_array_length(c.embedding_json) > 0
                      AND d.metadata_json->>'data_origin'='official'
                    """
                )
            ).scalar()
            sample_rows = conn.execute(
                text(
                    """
                    SELECT c.embedding_json, c.metadata_json
                    FROM kb_chunks c
                    JOIN kb_documents d ON d.doc_id=c.doc_id
                    WHERE c.embedding_json IS NOT NULL
                      AND jsonb_typeof(c.embedding_json) = 'array'
                      AND jsonb_array_length(c.embedding_json) > 0
                      AND d.metadata_json->>'data_origin'='official'
                    ORDER BY c.updated_at DESC NULLS LAST
                    LIMIT 200
                    """
                )
            ).mappings().all()
    except Exception as exc:
        return {
            "available": False,
            "kb_document_count": 0,
            "kb_chunk_count": 0,
            "embedded_chunk_count": 0,
            "formal_metadata_complete_count": 0,
            "last_embedding_refresh_at": None,
            "embedding_dim_distribution": {},
            "error": str(exc)[:300],
        }

    dim_distribution: dict[str, int] = {}
    fallback_embeddings = 0
    for row in mapping_list(sample_rows):
        vector = loads_json(row.get("embedding_json"), default=[])
        metadata = loads_json(row.get("metadata_json"), default={})
        if isinstance(vector, list):
            dim_distribution[str(len(vector))] = dim_distribution.get(str(len(vector)), 0) + 1
        embedding_meta = metadata.get("embedding") if isinstance(metadata, dict) else {}
        if isinstance(embedding_meta, dict) and embedding_meta.get("fallback"):
            fallback_embeddings += 1
    return {
        "available": True,
        "kb_document_count": documents,
        "kb_chunk_count": chunks,
        "embedded_chunk_count": embedded,
        "formal_metadata_complete_count": formal_complete,
        "last_embedding_refresh_at": last_refresh.isoformat() if isinstance(last_refresh, datetime) else str(last_refresh) if last_refresh else None,
        "embedding_dim_distribution": dim_distribution,
        "sample_fallback_embedding_count": fallback_embeddings,
    }


def rag_health() -> dict[str, Any]:
    provider = _provider_state()
    knowledge = _knowledge_state()
    fallback_reasons = list(provider.get("fallback_reasons") or [])
    if knowledge.get("sample_fallback_embedding_count"):
        fallback_reasons.append(f"fallback_embeddings_in_recent_sample={knowledge['sample_fallback_embedding_count']}")
    embedded = int(knowledge.get("embedded_chunk_count") or 0)
    chunks = int(knowledge.get("kb_chunk_count") or 0)
    documents = int(knowledge.get("kb_document_count") or 0)
    formal_complete = int(knowledge.get("formal_metadata_complete_count") or 0)
    blocking_reasons: list[str] = []
    if not knowledge.get("available"):
        blocking_reasons.append("knowledge_database_unavailable")
    elif documents <= 0:
        blocking_reasons.append("official_knowledge_unavailable")
    elif formal_complete != documents:
        blocking_reasons.append("official_metadata_incomplete")
    if chunks and set(knowledge.get("embedding_dim_distribution") or {}) != {str(EXPECTED_BGE_LARGE_DIM)}:
        blocking_reasons.append("official_embedding_dimension_mismatch")
    if chunks and embedded < chunks:
        blocking_reasons.append("official_embedding_incomplete")
    status = "normal"
    if (_env("RAG_ENABLED", "1") or "1").lower() in {"0", "false", "no", "off"}:
        status = "disabled"
    elif fallback_reasons:
        status = "fallback"
    elif blocking_reasons:
        status = "unavailable"
    elif not provider.get("embedding_model_path_exists") and provider.get("embedding_provider_config") in {"bge", "sentence_transformers", "sentence-transformers"}:
        status = "not_configured"
    return {
        "ok": status == "normal",
        "status": status,
        **provider,
        **knowledge,
        "fallback_enabled": bool(fallback_reasons),
        "fallback_reasons": fallback_reasons,
        "blocking_reasons": blocking_reasons,
    }
