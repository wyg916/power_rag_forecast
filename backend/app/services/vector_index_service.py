from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import text

from backend.app.config import PROJECT_ROOT
from backend.app.repositories.base import postgres_engine
from backend.app.repositories.knowledge_repository import get_vector_index_rows


DEFAULT_INDEX_PATH = PROJECT_ROOT / "knowledge_pipeline" / "output" / "rag_vector_index.npz"
DEFAULT_METADATA_PATH = PROJECT_ROOT / "knowledge_pipeline" / "output" / "rag_vector_index.json"


def _paths() -> tuple[Path, Path]:
    index_path = Path(os.getenv("RAG_VECTOR_INDEX_PATH", str(DEFAULT_INDEX_PATH)))
    metadata_path = Path(os.getenv("RAG_VECTOR_INDEX_METADATA_PATH", str(DEFAULT_METADATA_PATH)))
    return index_path, metadata_path


def _digest(chunk_ids: list[str], matrix: np.ndarray) -> str:
    digest = hashlib.sha256()
    for chunk_id in chunk_ids:
        digest.update(chunk_id.encode("utf-8"))
        digest.update(b"\0")
    digest.update(matrix.tobytes(order="C"))
    return digest.hexdigest()


def build_vector_index(expected_dim: int = 1024) -> dict[str, Any]:
    rows = get_vector_index_rows()
    if not rows:
        return {"available": False, "indexed": 0, "reason": "no_ready_embeddings"}
    chunk_ids: list[str] = []
    vectors: list[list[float]] = []
    versions: set[str] = set()
    models: set[str] = set()
    seen_hashes: set[str] = set()
    for row in rows:
        metadata = row.get("metadata") or {}
        content_hash = str(metadata.get("content_hash") or "")
        vector = row.get("embedding") or []
        if not content_hash or content_hash in seen_hashes:
            continue
        if len(vector) != expected_dim:
            raise RuntimeError(f"embedding_dimension_mismatch:{row.get('chunk_id')}:{len(vector)}")
        array = np.asarray(vector, dtype=np.float32)
        if not np.isfinite(array).all():
            raise RuntimeError(f"non_finite_embedding:{row.get('chunk_id')}")
        norm = float(np.linalg.norm(array))
        if norm <= 0:
            raise RuntimeError(f"zero_norm_embedding:{row.get('chunk_id')}")
        embedding_meta = metadata.get("embedding") or {}
        versions.add(str(metadata.get("embedding_version") or embedding_meta.get("version") or ""))
        models.add(str(embedding_meta.get("model") or ""))
        seen_hashes.add(content_hash)
        chunk_ids.append(str(row.get("chunk_id") or ""))
        vectors.append((array / norm).tolist())
    if len(versions) != 1 or "" in versions:
        raise RuntimeError(f"embedding_version_not_stable:{sorted(versions)}")
    if len(models) != 1 or "" in models:
        raise RuntimeError(f"embedding_model_not_stable:{sorted(models)}")
    matrix = np.asarray(vectors, dtype=np.float32)
    index_path, metadata_path = _paths()
    index_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    temp_index = index_path.with_suffix(".tmp.npz")
    temp_metadata = metadata_path.with_suffix(".tmp.json")
    np.savez_compressed(temp_index, vectors=matrix, chunk_ids=np.asarray(chunk_ids, dtype=str))
    engine = postgres_engine()
    database = ""
    if engine is not None:
        with engine.connect() as conn:
            database = str(conn.execute(text("SELECT current_database()" )).scalar() or "")
    metadata = {
        "format": "numpy_exact_cosine_v1",
        "database": database,
        "dimension": int(matrix.shape[1]),
        "row_count": int(matrix.shape[0]),
        "embedding_model": next(iter(models)),
        "embedding_version": next(iter(versions)),
        "content_digest": _digest(chunk_ids, matrix),
        "built_at_epoch": round(time.time(), 3),
    }
    temp_metadata.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_index, index_path)
    os.replace(temp_metadata, metadata_path)
    return {"available": True, "indexed": len(chunk_ids), "index_path": str(index_path), **metadata}


def query_vector_index(query_embedding: list[float], top_k: int = 50) -> dict[str, Any]:
    index_path, metadata_path = _paths()
    if not index_path.is_file() or not metadata_path.is_file():
        return {"available": False, "reason": "vector_index_unavailable", "items": []}
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        with np.load(index_path, allow_pickle=False) as payload:
            matrix = np.asarray(payload["vectors"], dtype=np.float32)
            chunk_ids = [str(item) for item in payload["chunk_ids"].tolist()]
        query = np.asarray(query_embedding, dtype=np.float32)
        expected_dim = int(metadata.get("dimension") or 0)
        if query.ndim != 1 or len(query) != expected_dim or matrix.ndim != 2 or matrix.shape[1] != expected_dim:
            return {"available": False, "reason": "vector_dimension_mismatch", "items": []}
        if not np.isfinite(query).all() or not np.isfinite(matrix).all():
            return {"available": False, "reason": "non_finite_vector", "items": []}
        if _digest(chunk_ids, matrix) != metadata.get("content_digest"):
            return {"available": False, "reason": "vector_index_digest_mismatch", "items": []}
        norm = float(np.linalg.norm(query))
        if norm <= 0:
            return {"available": False, "reason": "zero_norm_query", "items": []}
        scores = matrix @ (query / norm)
        count = max(1, min(int(top_k or 50), len(chunk_ids)))
        indices = np.argsort(-scores, kind="stable")[:count]
        items = [{"chunk_id": chunk_ids[int(index)], "vector_score": round(float(scores[int(index)]), 6)} for index in indices]
        return {"available": True, "reason": "", "items": items, "metadata": metadata}
    except Exception as exc:
        return {"available": False, "reason": f"vector_index_error:{exc.__class__.__name__}", "items": []}
