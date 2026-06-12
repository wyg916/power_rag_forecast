from __future__ import annotations

import argparse
import csv
import hashlib
import json
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


def make_doc_id(source_path: str) -> str:
    return "kpdoc_" + sha1_text(source_path)[:20]


def make_chunk_id(original_chunk_id: str, source_path: str, chunk_index: int) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_:-]+", "_", original_chunk_id or "").strip("_")
    candidate = f"kp_{normalized}" if normalized else ""
    if candidate and len(candidate) <= 96:
        return candidate
    return f"kp_{sha1_text(source_path)[:16]}_{int(chunk_index or 0):04d}"


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
            item["_doc_id"] = make_doc_id(str(item.get("source_path") or ""))
            item["_db_chunk_id"] = make_chunk_id(
                str(item.get("chunk_id") or ""),
                str(item.get("source_path") or ""),
                int(item.get("chunk_index") or 0),
            )
            rows.append(item)
            if limit and len(rows) >= limit:
                break
    return rows, failures


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
        docs[doc_id] = {
            "doc_id": doc_id,
            "title": str(first.get("title") or first.get("source_file") or doc_id)[:255],
            "source_type": SOURCE_TYPE,
            "source_path": str(first.get("source_path") or ""),
            "checksum": sha256_text(joined),
            "metadata": {
                "import_source": SOURCE_TYPE,
                "import_batch": import_batch,
                "input_path": str(input_path),
                "source_file": first.get("source_file") or "",
                "source_path": first.get("source_path") or "",
                "file_type": first.get("file_type") or "",
                "category": first.get("category") or "其他",
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
    return True, vector, metadata, ""


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
        "title": row.get("title") or "",
        "chunk_index": int(row.get("chunk_index") or 0),
        "chunk_total": int(row.get("chunk_total") or 0),
        "keywords": keywords,
        "text_hash": row.get("text_hash") or sha256_text(str(row.get("text") or "")),
        "created_at": row.get("created_at") or "",
        "line_no": row.get("_line_no") or 0,
        "embedding": embedding_meta,
    }
    return {
        "chunk_id": row["_db_chunk_id"],
        "doc_id": row["_doc_id"],
        "chunk_index": int(row.get("chunk_index") or 0),
        "content": str(row.get("text") or ""),
        "keywords": keywords,
        "embedding": embedding,
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
    if mode == "replace" and not records:
        return 0, 0, skipped
    with engine.begin() as conn:
        if mode == "replace":
            conn.execute(text("DELETE FROM kb_documents WHERE source_type = :source_type"), {"source_type": SOURCE_TYPE})
        for doc in docs_to_insert.values():
            metadata = dict(doc["metadata"])
            metadata["import_batch"] = import_batch
            conn.execute(
                text(
                    """
                    INSERT INTO kb_documents (
                        doc_id, title, source_type, source_path, checksum,
                        metadata_json, indexed_at, updated_at
                    )
                    VALUES (
                        :doc_id, :title, :source_type, :source_path, :checksum,
                        CAST(:metadata_json AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
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
                    "doc_id": doc["doc_id"],
                    "title": doc["title"],
                    "source_type": SOURCE_TYPE,
                    "source_path": doc["source_path"],
                    "checksum": doc["checksum"],
                    "metadata_json": dumps_json(metadata),
                },
            )
        for record in records:
            conn.execute(
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
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        doc_id = EXCLUDED.doc_id,
                        chunk_index = EXCLUDED.chunk_index,
                        content = EXCLUDED.content,
                        keywords_json = EXCLUDED.keywords_json,
                        embedding_json = EXCLUDED.embedding_json,
                        metadata_json = EXCLUDED.metadata_json,
                        updated_at = CURRENT_TIMESTAMP
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
    return len(docs_to_insert), len(records), skipped


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
    rows, validation_failures = load_jsonl(input_path, limit=max(0, int(args.limit or 0)))
    category_distribution = Counter(str(row.get("category") or "其他") for row in rows)
    db_chunk_ids = [row["_db_chunk_id"] for row in rows]
    duplicate_db_chunk_ids = [chunk_id for chunk_id, count in Counter(db_chunk_ids).items() if count > 1]
    before_counts = get_db_counts()
    provider = get_embedding_provider()
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
        "validation_failures": len(validation_failures),
        "duplicate_db_chunk_ids": duplicate_db_chunk_ids,
        "before_counts": before_counts,
        "after_counts": before_counts,
        "imported_documents": 0,
        "imported_chunks": 0,
        "skipped_chunks": 0,
        "embedding_success": 0,
        "embedding_failed": 0,
        "embedding_dim": EXPECTED_EMBEDDING_DIM,
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
    success_records, embedding_failures, dim_counter = embed_rows(
        rows,
        batch_size=max(1, int(args.batch_size or 32)),
        import_batch=import_batch,
        input_path=input_path,
        verbose=bool(args.verbose),
    )
    failures.extend(embedding_failures)
    report["embedding_success"] = len(success_records)
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
    report["can_run_smoke_test"] = imported_chunks > 0 and report["embedding_failed"] == 0
    report["duration_seconds"] = round(time.time() - start_time, 3)
    write_reports(output_dir, report, failures)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导入 knowledge_pipeline/output/chunks.jsonl 到现有 PostgreSQL RAG 知识库。")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="chunks.jsonl 路径")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR, help="报告输出目录")
    parser.add_argument("--mode", choices=["append", "replace"], default="append", help="append 追加/更新；replace 仅替换本脚本导入的数据")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--dry-run", action="store_true", help="只校验 JSONL 和数据库状态，不入库、不生成 embedding")
    parser.add_argument("--limit", type=int, default=0, help="限制导入 chunks 数，用于小批量测试")
    parser.add_argument("--resume", action="store_true", help="跳过已存在的本脚本导入 chunk")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = run_import(args)
    safe_print(report)
    return 0 if not report.get("validation_failures") and not report.get("duplicate_db_chunk_ids") else 1


if __name__ == "__main__":
    raise SystemExit(main())
