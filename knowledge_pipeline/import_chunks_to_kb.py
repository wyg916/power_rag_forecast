from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from backend.app.repositories.base import dumps_json, postgres_engine
from backend.app.repositories.knowledge_repository import tokenize
from backend.app.services.embedding_service import embed_batch_with_metadata, get_embedding_provider


SOURCE_TYPE = "knowledge_pipeline_jsonl"
EXPECTED_EMBEDDING_DIM = 1024
DEFAULT_INPUT = ROOT / "knowledge_pipeline" / "output" / "chunks.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "knowledge_pipeline" / "output"
DEFAULT_TARGET_CHUNKS = 240
DEFAULT_MIN_CHARS = 120
DEFAULT_MAX_CHARS = 1600

CATEGORY_DOMAIN_MAP = {
    "新能源政策": "renewable_policy",
    "绿证交易": "green_certificate",
    "电力现货交易": "electricity_market",
    "模型与预测方法": "price_forecast",
    "电力市场规则": "electricity_market",
    "交易策略": "trading_strategy",
    "项目申报与建设": "project_policy",
    "电价政策": "electricity_policy",
    "其他": "general_knowledge",
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def safe_print(value: Any) -> None:
    text_value = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    try:
        print(text_value)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(text_value.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def make_doc_id(source_path: str, document_version: str) -> str:
    return "kpdoc_" + sha1_text(f"{source_path}\n{document_version}")[:20]


def make_chunk_id(document_id: str, content_hash: str) -> str:
    return f"{document_id}_{content_hash[:16]}"


def load_jsonl(path: Path, limit: int = 0) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    required = {"chunk_id", "source_file", "source_path", "title", "chunk_index", "chunk_total", "text", "text_hash"}
    if not path.exists():
        return [], [{"line_no": 0, "reason": "input_not_found", "detail": str(path)}]
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                item = json.loads(stripped)
            except json.JSONDecodeError as exc:
                failures.append({"line_no": line_no, "reason": "json_decode_error", "detail": str(exc)[:300]})
                continue
            missing = sorted(key for key in required if item.get(key) in (None, ""))
            if missing:
                failures.append(
                    {
                        "line_no": line_no,
                        "chunk_id": item.get("chunk_id") or "",
                        "reason": "missing_required_fields",
                        "detail": ",".join(missing),
                    }
                )
                continue
            if not str(item.get("text") or "").strip():
                failures.append(
                    {
                        "line_no": line_no,
                        "chunk_id": item.get("chunk_id") or "",
                        "reason": "empty_text",
                        "detail": "",
                    }
                )
                continue
            item["_line_no"] = line_no
            rows.append(item)
            if limit and len(rows) >= limit:
                break
    return rows, failures


def assign_document_identities(rows: list[dict[str, Any]]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("source_path") or "")].append(row)
    for source_path, items in grouped.items():
        joined = "\n".join(
            str(item.get("text") or "")
            for item in sorted(items, key=lambda value: int(value.get("chunk_index") or 0))
        )
        document_version = f"sha256:{sha256_text(joined)[:12]}"
        doc_id = make_doc_id(source_path, document_version)
        for item in items:
            item["_doc_id"] = doc_id
            item["_document_version"] = document_version
            content_hash = str(item.get("text_hash") or sha256_text(str(item.get("text") or "")))
            item["_db_chunk_id"] = make_chunk_id(doc_id, content_hash)


def evidence_source_type(row: dict[str, Any]) -> str:
    title = str(row.get("title") or row.get("source_file") or "")
    if title.startswith("AI-项目进展与分析"):
        return "derived"
    explicit_years = [int(value) for value in re.findall(r"(?<!\d)(20\d{2})年", title)]
    if explicit_years and max(explicit_years) < datetime.now().year:
        return "historical"
    return "real"


def select_curated_rows(
    rows: list[dict[str, Any]],
    *,
    target_chunks: int,
    min_chars: int,
    max_chars: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    accepted: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    stats = {
        "input": len(rows),
        "too_short": 0,
        "too_long": 0,
        "duplicate_content": 0,
        "missing_identity": 0,
    }
    for row in rows:
        text_value = str(row.get("text") or "").strip()
        if len(text_value) < min_chars:
            stats["too_short"] += 1
            continue
        if len(text_value) > max_chars:
            stats["too_long"] += 1
            continue
        content_hash = str(row.get("text_hash") or sha256_text(text_value))
        if content_hash in seen_hashes:
            stats["duplicate_content"] += 1
            continue
        if not row.get("source_path") or not row.get("title") or not row.get("category"):
            stats["missing_identity"] += 1
            continue
        seen_hashes.add(content_hash)
        accepted.append(row)
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in accepted:
        buckets[str(row.get("category") or "其他")].append(row)
    selected: list[dict[str, Any]] = []
    categories = sorted(buckets)
    while categories and len(selected) < max(0, target_chunks):
        next_categories: list[str] = []
        for category in categories:
            bucket = buckets[category]
            if bucket and len(selected) < target_chunks:
                selected.append(bucket.pop(0))
            if bucket:
                next_categories.append(category)
        categories = next_categories
    stats["eligible"] = len(accepted)
    stats["selected"] = len(selected)
    return selected, stats


def get_db_counts() -> dict[str, int | bool | str]:
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "documents": 0, "chunks": 0, "imported_documents": 0, "imported_chunks": 0}
    with engine.connect() as conn:
        documents = int(conn.execute(text("SELECT COUNT(*) FROM kb_documents")).scalar() or 0)
        chunks = int(conn.execute(text("SELECT COUNT(*) FROM kb_chunks")).scalar() or 0)
        imported_documents = int(
            conn.execute(text("SELECT COUNT(*) FROM kb_documents WHERE source_type = :source_type"), {"source_type": SOURCE_TYPE}).scalar()
            or 0
        )
        imported_chunks = int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM kb_chunks c
                    JOIN kb_documents d ON d.doc_id = c.doc_id
                    WHERE d.source_type = :source_type
                    """
                ),
                {"source_type": SOURCE_TYPE},
            ).scalar()
            or 0
        )
    return {
        "available": True,
        "documents": documents,
        "chunks": chunks,
        "imported_documents": imported_documents,
        "imported_chunks": imported_chunks,
    }


def existing_chunk_ids() -> set[str]:
    engine = postgres_engine()
    if engine is None:
        return set()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT c.chunk_id
                FROM kb_chunks c
                JOIN kb_documents d ON d.doc_id = c.doc_id
                WHERE d.source_type = :source_type
                """
            ),
            {"source_type": SOURCE_TYPE},
        ).scalars().all()
    return {str(row) for row in rows}


def build_document_metadata(rows: list[dict[str, Any]], input_path: Path, import_batch: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["_doc_id"])].append(row)
    docs: dict[str, dict[str, Any]] = {}
    for doc_id, items in grouped.items():
        first = items[0]
        categories = sorted({str(item.get("category") or "其他") for item in items})
        keywords = []
        for item in items:
            for keyword in item.get("keywords") or []:
                if keyword not in keywords:
                    keywords.append(keyword)
        joined = "\n".join(str(item.get("text") or "") for item in sorted(items, key=lambda row: int(row.get("chunk_index") or 0)))
        category = str(first.get("category") or "其他")
        domain = CATEGORY_DOMAIN_MAP.get(category, "general_knowledge")
        title = str(first.get("title") or first.get("source_file") or doc_id)[:255]
        evidence_type = evidence_source_type(first)
        temporal_scope = {
            "derived": "project_derived",
            "historical": "historical_as_published",
            "real": "document_as_published",
        }[evidence_type]
        docs[doc_id] = {
            "doc_id": doc_id,
            "title": title,
            "source_type": SOURCE_TYPE,
            "source_path": str(first.get("source_path") or ""),
            "checksum": sha256_text(joined),
            "metadata": {
                "document_id": doc_id,
                "document_version": str(first.get("_document_version") or f"sha256:{sha256_text(joined)[:12]}"),
                "title": title,
                "domain": domain,
                "evidence_source_type": evidence_type,
                "source_name": str(first.get("source_file") or title),
                "source_uri": "",
                "effective_at": None,
                "expires_at": None,
                "generated_at": now_text(),
                "content_hash": sha256_text(joined),
                "language": "zh-CN",
                "status": "active",
                "tags": categories,
                "evidence_level": "project_internal_document" if evidence_type == "derived" else "public_document",
                "data_origin": "project_internal" if evidence_type == "derived" else "imported_public_document",
                "temporal_scope": temporal_scope,
                "import_source": SOURCE_TYPE,
                "import_batch": import_batch,
                "input_path": str(input_path),
                "source_file": first.get("source_file") or "",
                "source_path": first.get("source_path") or "",
                "file_type": first.get("file_type") or "",
                "category": category,
                "categories": categories,
                "title": first.get("title") or "",
                "chunk_count": len(items),
                "keywords": keywords[:80],
                "text_checksum": sha256_text(joined),
                "created_at": first.get("created_at") or "",
            },
        }
    return docs


def validate_embedding_result(row: dict[str, Any], embedding_result: dict[str, Any]) -> tuple[bool, list[float], dict[str, Any], str]:
    vector = embedding_result.get("embedding") or []
    metadata = embedding_result.get("metadata") or {}
    if not isinstance(vector, list) or not vector:
        return False, [], metadata if isinstance(metadata, dict) else {}, "empty_embedding"
    if not isinstance(metadata, dict):
        metadata = {}
    if metadata.get("fallback"):
        return False, vector, metadata, "embedding_fallback_not_allowed"
    if metadata.get("provider") != "sentence_transformers":
        return False, vector, metadata, f"unexpected_provider:{metadata.get('provider')}"
    if metadata.get("model") != "bge-large-zh-v1.5":
        return False, vector, metadata, f"unexpected_model:{metadata.get('model')}"
    if len(vector) != EXPECTED_EMBEDDING_DIM:
        return False, vector, metadata, f"unexpected_dim:{len(vector)}"
    if int(metadata.get("dim") or 0) != EXPECTED_EMBEDDING_DIM:
        return False, vector, metadata, f"unexpected_metadata_dim:{metadata.get('dim')}"
    if not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in vector):
        return False, vector, metadata, "non_finite_embedding"
    return True, vector, metadata, ""


def pending_active_chunk_ids() -> set[str]:
    engine = postgres_engine()
    if engine is None:
        return set()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT c.chunk_id
                FROM kb_chunks c
                JOIN kb_documents d ON d.doc_id = c.doc_id
                WHERE COALESCE(d.metadata_json->>'status', 'active') = 'active'
                  AND COALESCE(c.metadata_json->>'status', '') = 'active'
                  AND COALESCE(c.metadata_json->>'embedding_status', 'pending') = 'pending'
                """
            )
        ).scalars().all()
    return {str(item) for item in rows}


def mark_embedding_failures(failures: list[dict[str, Any]]) -> int:
    chunk_ids = sorted({str(item.get("db_chunk_id") or "") for item in failures if item.get("db_chunk_id")})
    if not chunk_ids:
        return 0
    engine = postgres_engine()
    if engine is None:
        return 0
    updated = 0
    with engine.begin() as conn:
        for chunk_id_value in chunk_ids:
            result = conn.execute(
                text(
                    """
                    UPDATE kb_chunks
                    SET metadata_json = jsonb_set(metadata_json, '{embedding_status}', '"failed"'::jsonb, true),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE chunk_id = :chunk_id
                      AND COALESCE(metadata_json->>'status', '') = 'active'
                      AND COALESCE(metadata_json->>'embedding_status', 'pending') = 'pending'
                    """
                ),
                {"chunk_id": chunk_id_value},
            )
            updated += max(0, int(result.rowcount or 0))
    return updated


def build_chunk_record(
    row: dict[str, Any],
    embedding: list[float],
    embedding_meta: dict[str, Any],
    import_batch: str,
    input_path: Path,
) -> dict[str, Any]:
    keywords = row.get("keywords")
    if not isinstance(keywords, list) or not keywords:
        keywords = tokenize(f"{row.get('title') or ''} {row.get('text') or ''}")
    embedding_ready = bool(embedding and int(embedding_meta.get("dim") or 0) > 0)
    metadata = {
        "import_source": SOURCE_TYPE,
        "import_batch": import_batch,
        "input_path": str(input_path),
        "original_chunk_id": row.get("chunk_id") or "",
        "db_chunk_id": row.get("_db_chunk_id") or "",
        "source_file": row.get("source_file") or "",
        "source_path": row.get("source_path") or "",
        "file_type": row.get("file_type") or "",
        "category": row.get("category") or "其他",
        "domain": CATEGORY_DOMAIN_MAP.get(str(row.get("category") or "其他"), "general_knowledge"),
        "source_type": evidence_source_type(row),
        "title": row.get("title") or "",
        "section_title": row.get("title") or "",
        "chunk_index": int(row.get("chunk_index") or 0),
        "chunk_total": int(row.get("chunk_total") or 0),
        "keywords": keywords,
        "text_hash": row.get("text_hash") or sha256_text(str(row.get("text") or "")),
        "content_hash": row.get("text_hash") or sha256_text(str(row.get("text") or "")),
        "token_count": len(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+", str(row.get("text") or ""))),
        "embedding_status": "ready" if embedding_ready else "pending",
        "embedding_version": str(embedding_meta.get("version") or "") if embedding_ready else "",
        "status": "active",
        "created_at": row.get("created_at") or "",
        "line_no": row.get("_line_no") or 0,
        "embedding": embedding_meta if embedding_ready else {},
    }
    return {
        "chunk_id": row["_db_chunk_id"],
        "doc_id": row["_doc_id"],
        "chunk_index": int(row.get("chunk_index") or 0),
        "content": str(row.get("text") or ""),
        "keywords": keywords,
        "embedding": embedding if embedding_ready else None,
        "metadata": metadata,
    }


def embed_rows(
    rows: list[dict[str, Any]],
    *,
    batch_size: int,
    import_batch: str,
    input_path: Path,
    verbose: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Counter]:
    success_records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    dim_counter: Counter = Counter()
    total = len(rows)
    for start in range(0, total, max(1, batch_size)):
        batch = rows[start : start + max(1, batch_size)]
        texts = [f"{item.get('title') or ''}\n{item.get('text') or ''}" for item in batch]
        try:
            embedding_results = embed_batch_with_metadata(texts)
        except Exception as exc:
            embedding_results = []
            for item in batch:
                failures.append(
                    {
                        "chunk_id": item.get("chunk_id") or "",
                        "db_chunk_id": item.get("_db_chunk_id") or "",
                        "source_file": item.get("source_file") or "",
                        "source_path": item.get("source_path") or "",
                        "category": item.get("category") or "",
                        "reason": "embedding_batch_exception",
                        "detail": str(exc)[:300],
                        "text_hash": item.get("text_hash") or "",
                    }
                )
        if embedding_results:
            for item, embedding_result in zip(batch, embedding_results):
                ok, vector, embedding_meta, reason = validate_embedding_result(item, embedding_result)
                dim_counter[len(vector)] += 1
                if not ok:
                    failures.append(
                        {
                            "chunk_id": item.get("chunk_id") or "",
                            "db_chunk_id": item.get("_db_chunk_id") or "",
                            "source_file": item.get("source_file") or "",
                            "source_path": item.get("source_path") or "",
                            "category": item.get("category") or "",
                            "reason": reason,
                            "detail": dumps_json(embedding_meta),
                            "text_hash": item.get("text_hash") or "",
                        }
                    )
                    continue
                success_records.append(build_chunk_record(item, vector, embedding_meta, import_batch, input_path))
        if verbose:
            safe_print(f"embedded {min(start + len(batch), total)}/{total}; success={len(success_records)}; failed={len(failures)}")
    return success_records, failures, dim_counter


def write_failure_csv(path: Path, failures: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["chunk_id", "db_chunk_id", "source_file", "source_path", "category", "reason", "detail", "text_hash"]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for item in failures:
            writer.writerow({field: item.get(field, "") for field in fields})


def write_reports(output_dir: Path, report: dict[str, Any], failures: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "import_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_failure_csv(output_dir / "import_failed_chunks.csv", failures)
    lines = [
        "# knowledge_pipeline chunks 导入报告",
        "",
        f"- 生成时间：{now_text()}",
        f"- 输入文件：`{report.get('input_path')}`",
        f"- 导入模式：{report.get('mode')}",
        f"- dry-run：{report.get('dry_run')}",
        f"- limit：{report.get('limit')}",
        f"- 导入批次：{report.get('import_batch')}",
        f"- 导入耗时秒：{report.get('duration_seconds')}",
        "",
        "## 数据库数量对比",
        "",
        "| 指标 | 导入前 | 导入后 |",
        "|---|---:|---:|",
        f"| kb_documents | {report.get('before_counts', {}).get('documents', 0)} | {report.get('after_counts', {}).get('documents', 0)} |",
        f"| kb_chunks | {report.get('before_counts', {}).get('chunks', 0)} | {report.get('after_counts', {}).get('chunks', 0)} |",
        f"| 本脚本导入 documents | {report.get('before_counts', {}).get('imported_documents', 0)} | {report.get('after_counts', {}).get('imported_documents', 0)} |",
        f"| 本脚本导入 chunks | {report.get('before_counts', {}).get('imported_chunks', 0)} | {report.get('after_counts', {}).get('imported_chunks', 0)} |",
        "",
        "## 导入结果",
        "",
        f"- 输入 chunks 数：{report.get('input_chunks', 0)}",
        f"- 成功导入 documents 数：{report.get('imported_documents', 0)}",
        f"- 成功导入 chunks 数：{report.get('imported_chunks', 0)}",
        f"- 跳过重复 chunks 数：{report.get('skipped_chunks', 0)}",
        f"- embedding 成功数量：{report.get('embedding_success', 0)}",
        f"- embedding 失败数量：{report.get('embedding_failed', 0)}",
        f"- 向量维度：{report.get('embedding_dim', 0)}",
        f"- 维度分布：{report.get('embedding_dim_distribution', {})}",
        f"- 是否清理 cache：{report.get('cache_clear', {}).get('cleared', False)}",
        f"- cache 说明：{report.get('cache_clear', {}).get('message', '')}",
        f"- 是否可以进入 RAG smoke test：{report.get('can_run_smoke_test', False)}",
        "",
        "## 类别分布",
        "",
        "| 类别 | chunks |",
        "|---|---:|",
    ]
    for category, count in sorted((report.get("category_distribution") or {}).items()):
        lines.append(f"| {category} | {count} |")
    lines.extend(["", "## 失败 chunk 预览", ""])
    if failures:
        lines.extend(["| chunk_id | source_file | category | reason |", "|---|---|---|---|"])
        for item in failures[:50]:
            lines.append(f"| {item.get('chunk_id', '')} | {item.get('source_file', '')} | {item.get('category', '')} | {item.get('reason', '')} |")
    else:
        lines.append("无。")
    (output_dir / "import_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def upsert_records(
    *,
    mode: str,
    docs: dict[str, dict[str, Any]],
    records: list[dict[str, Any]],
    resume: bool,
    import_batch: str,
) -> tuple[int, int, int]:
    engine = postgres_engine()
    if engine is None:
        raise RuntimeError("PostgreSQL 不可用，无法导入 kb_documents/kb_chunks")
    skipped = 0
    if resume:
        existing = existing_chunk_ids()
        before_ids = {record["chunk_id"] for record in records}
        skipped = len(before_ids & existing)
        records = [record for record in records if record["chunk_id"] not in existing]
    docs_to_insert = {doc_id: docs[doc_id] for doc_id in {record["doc_id"] for record in records} if doc_id in docs}
    if mode != "append":
        raise RuntimeError("Destructive replace mode is disabled; use append/resume with versioned identities.")
    inserted_docs = 0
    inserted_chunks = 0
    with engine.begin() as conn:
        for doc in docs_to_insert.values():
            metadata = dict(doc["metadata"])
            metadata["import_batch"] = import_batch
            conn.execute(
                text(
                    """
                    UPDATE kb_documents
                    SET metadata_json = jsonb_set(metadata_json, '{status}', '"superseded"'::jsonb, true),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE source_path = :source_path
                      AND doc_id <> :doc_id
                      AND COALESCE(metadata_json->>'status', 'active') = 'active'
                    """
                ),
                {"source_path": doc["source_path"], "doc_id": doc["doc_id"]},
            )
            result = conn.execute(
                text(
                    """
                    INSERT INTO kb_documents (
                        doc_id, title, source_type, source_path, checksum,
                        metadata_json, indexed_at, updated_at
                    )
                    VALUES (
                        :doc_id, :title, :source_type, :source_path, :checksum,
                        CAST(:metadata_json AS jsonb), NULL, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (doc_id) DO NOTHING
                    """
                ),
                {
                    "doc_id": doc["doc_id"],
                    "title": doc["title"],
                    "source_type": SOURCE_TYPE,
                    "source_path": doc["source_path"],
                    "checksum": doc["checksum"],
                    "metadata_json": dumps_json(metadata),
                },
            )
            inserted_docs += max(0, int(result.rowcount or 0))
        for record in records:
            result = conn.execute(
                text(
                    """
                    INSERT INTO kb_chunks (
                        chunk_id, doc_id, chunk_index, content,
                        keywords_json, embedding_json, metadata_json, updated_at
                    )
                    VALUES (
                        :chunk_id, :doc_id, :chunk_index, :content,
                        CAST(:keywords_json AS jsonb), CAST(:embedding_json AS jsonb),
                        CAST(:metadata_json AS jsonb), CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (chunk_id) DO UPDATE
                    SET embedding_json = EXCLUDED.embedding_json,
                        metadata_json = EXCLUDED.metadata_json,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE COALESCE(kb_chunks.metadata_json->>'embedding_status', 'pending') = 'pending'
                      AND COALESCE(EXCLUDED.metadata_json->>'embedding_status', '') = 'ready'
                    """
                ),
                {
                    "chunk_id": record["chunk_id"],
                    "doc_id": record["doc_id"],
                    "chunk_index": record["chunk_index"],
                    "content": record["content"],
                    "keywords_json": dumps_json(record["keywords"]),
                    "embedding_json": dumps_json(record["embedding"]),
                    "metadata_json": dumps_json(record["metadata"]),
                },
            )
            inserted_chunks += max(0, int(result.rowcount or 0))
    return inserted_docs, inserted_chunks, skipped + len(records) - inserted_chunks


def clear_rag_cache() -> dict[str, Any]:
    try:
        from backend.app.services import rag_service

        rag_service._rag_search_cached.cache_clear()
        return {
            "cleared": True,
            "message": "已清理当前脚本进程内的 RAG cache；如果后端服务已在运行，仍建议重启后端或手动清理该进程 cache。",
        }
    except Exception as exc:
        return {
            "cleared": False,
            "message": f"当前脚本未能清理 RAG cache：{exc.__class__.__name__}；导入后需要重启后端服务或手动清理 RAG cache。",
        }


def run_import(args: argparse.Namespace) -> dict[str, Any]:
    start_time = time.time()
    input_path = args.input.resolve()
    output_dir = args.output.resolve()
    import_batch = f"kp_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{sha1_text(str(input_path))[:8]}"
    raw_rows, validation_failures = load_jsonl(input_path, limit=0)
    assign_document_identities(raw_rows)
    target_chunks = max(1, int(args.target_chunks or DEFAULT_TARGET_CHUNKS))
    rows, curation_stats = select_curated_rows(
        raw_rows,
        target_chunks=target_chunks,
        min_chars=max(1, int(args.min_chars or DEFAULT_MIN_CHARS)),
        max_chars=max(1, int(args.max_chars or DEFAULT_MAX_CHARS)),
    )
    if args.limit:
        rows = rows[: max(0, int(args.limit))]
    category_distribution = Counter(str(row.get("category") or "其他") for row in rows)
    db_chunk_ids = [row["_db_chunk_id"] for row in rows]
    duplicate_db_chunk_ids = [chunk_id for chunk_id, count in Counter(db_chunk_ids).items() if count > 1]
    before_counts = get_db_counts()
    embedding_mode = str(getattr(args, "embedding_mode", "pending") or "pending")
    provider = get_embedding_provider() if embedding_mode == "ready" else None
    report: dict[str, Any] = {
        "input_path": str(input_path),
        "output_dir": str(output_dir),
        "mode": args.mode,
        "dry_run": bool(args.dry_run),
        "resume": bool(args.resume),
        "limit": int(args.limit or 0),
        "batch_size": int(args.batch_size or 32),
        "import_batch": import_batch,
        "source_type": SOURCE_TYPE,
        "input_chunks": len(rows),
        "raw_input_chunks": len(raw_rows),
        "target_chunks": target_chunks,
        "curation_stats": curation_stats,
        "validation_failures": len(validation_failures),
        "duplicate_db_chunk_ids": duplicate_db_chunk_ids,
        "before_counts": before_counts,
        "after_counts": before_counts,
        "imported_documents": 0,
        "imported_chunks": 0,
        "skipped_chunks": 0,
        "embedding_success": 0,
        "embedding_failed": 0,
        "embedding_mode": embedding_mode,
        "embedding_dim": EXPECTED_EMBEDDING_DIM if embedding_mode == "ready" else 0,
        "embedding_dim_distribution": {},
        "embedding_provider": getattr(provider, "name", ""),
        "embedding_model": getattr(provider, "model", ""),
        "category_distribution": dict(category_distribution),
        "duration_seconds": 0,
        "cache_clear": {"cleared": False, "message": "dry-run 未执行导入，无需清理 cache。"},
        "can_run_smoke_test": False,
    }
    failures = list(validation_failures)
    if duplicate_db_chunk_ids:
        failures.extend(
            {
                "chunk_id": "",
                "db_chunk_id": chunk_id,
                "source_file": "",
                "source_path": "",
                "category": "",
                "reason": "duplicate_db_chunk_id",
                "detail": "导入命名空间 chunk_id 重复",
                "text_hash": "",
            }
            for chunk_id in duplicate_db_chunk_ids
        )
    if args.dry_run:
        report["duration_seconds"] = round(time.time() - start_time, 3)
        report["can_run_smoke_test"] = False
        write_reports(output_dir, report, failures)
        return report
    if not before_counts.get("available"):
        failures.append({"reason": "database_unavailable", "detail": "PostgreSQL 不可用"})
        report["duration_seconds"] = round(time.time() - start_time, 3)
        write_reports(output_dir, report, failures)
        return report
    if duplicate_db_chunk_ids:
        report["duration_seconds"] = round(time.time() - start_time, 3)
        write_reports(output_dir, report, failures)
        return report

    docs = build_document_metadata(rows, input_path, import_batch)
    if embedding_mode == "ready":
        pending_ids = pending_active_chunk_ids()
        rows = [row for row in rows if row["_db_chunk_id"] in pending_ids]
        unique_by_hash: dict[str, dict[str, Any]] = {}
        for row in rows:
            unique_by_hash.setdefault(str(row.get("text_hash") or ""), row)
        rows = list(unique_by_hash.values())
        success_records, embedding_failures, dim_counter = embed_rows(
            rows,
            batch_size=max(1, int(args.batch_size or 32)),
            import_batch=import_batch,
            input_path=input_path,
            verbose=bool(args.verbose),
        )
    else:
        success_records = [build_chunk_record(row, [], {}, import_batch, input_path) for row in rows]
        embedding_failures = []
        dim_counter = Counter()
    failures.extend(embedding_failures)
    report["embedding_failed_marked"] = mark_embedding_failures(embedding_failures) if embedding_mode == "ready" else 0
    report["prepared_records"] = len(success_records)
    report["embedding_success"] = len(success_records) if embedding_mode == "ready" else 0
    report["embedding_failed"] = len(embedding_failures)
    report["embedding_dim_distribution"] = {str(key): value for key, value in sorted(dim_counter.items())}
    if not success_records:
        report["duration_seconds"] = round(time.time() - start_time, 3)
        report["after_counts"] = get_db_counts()
        write_reports(output_dir, report, failures)
        return report

    imported_docs, imported_chunks, skipped = upsert_records(
        mode=args.mode,
        docs=docs,
        records=success_records,
        resume=bool(args.resume),
        import_batch=import_batch,
    )
    report["imported_documents"] = imported_docs
    report["imported_chunks"] = imported_chunks
    report["skipped_chunks"] = skipped
    report["after_counts"] = get_db_counts()
    report["cache_clear"] = clear_rag_cache()
    report["can_run_smoke_test"] = embedding_mode == "ready" and imported_chunks > 0 and report["embedding_failed"] == 0
    report["duration_seconds"] = round(time.time() - start_time, 3)
    write_reports(output_dir, report, failures)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导入 knowledge_pipeline/output/chunks.jsonl 到现有 PostgreSQL RAG 知识库。")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="chunks.jsonl 路径")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR, help="报告输出目录")
    parser.add_argument("--mode", choices=["append"], default="append", help="仅允许 append；历史文档和 chunk 不删除。")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--embedding-mode",
        choices=["pending", "ready"],
        default="pending",
        help="pending 仅导入文档与 Chunk；ready 是 A2.2 的显式 Embedding 操作。",
    )
    parser.add_argument("--dry-run", action="store_true", help="只校验 JSONL 和数据库状态，不入库、不生成 embedding")
    parser.add_argument("--target-chunks", type=int, default=DEFAULT_TARGET_CHUNKS, help="平衡选择的目标有效 chunk 数。")
    parser.add_argument("--min-chars", type=int, default=DEFAULT_MIN_CHARS)
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    parser.add_argument("--limit", type=int, default=0, help="在平衡筛选后进一步限制，用于小批量测试。")
    parser.add_argument("--resume", action="store_true", help="跳过已存在的本脚本导入 chunk")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = run_import(args)
    safe_print(report)
    return 0 if not report.get("validation_failures") and not report.get("duplicate_db_chunk_ids") and not report.get("embedding_failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
