from __future__ import annotations

import csv
import io
import re
import time
import uuid
from typing import Any
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response

from ....core.security import CurrentUser, require_permission
from ....repositories.audit_repository import write_audit_log
from ....repositories.knowledge_repository import (
    ensure_seed_knowledge,
    knowledge_stats,
    list_knowledge_documents,
    record_search_result,
    run_qa_from_search,
    upsert_document,
)
from ....services.rag_health_service import rag_health
from ....services.rag_service import rag_search
from ....workers.dispatcher import enqueue_task


router = APIRouter()

KNOWLEDGE_UPLOAD_LIMIT_BYTES = 8 * 1024 * 1024
KNOWLEDGE_ALLOWED_EXTENSIONS = {".txt", ".md", ".csv", ".json"}
DEFAULT_BATCH_QUESTIONS = [
    "分时电价、现货交易风险和购电建议是什么？",
    "晚高峰供需缺口风险如何识别？",
    "新能源出力回落会怎样影响购电策略？",
]


def _safe_filename(filename: str | None) -> str:
    raw = (filename or "knowledge_document").strip()
    safe = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", raw, flags=re.UNICODE).strip("._")
    return safe or "knowledge_document"


def _search_payload(payload: dict[str, Any] | None) -> tuple[str, int]:
    data = payload or {}
    query = str(data.get("q") or data.get("query") or data.get("question") or "").strip()
    top_k = int(data.get("top_k") or data.get("topK") or 5)
    return query[:500], max(1, min(top_k, 20))


@router.get("/api/knowledge/stats")
def get_knowledge_stats(
    _: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
) -> dict:
    return knowledge_stats()


@router.get("/api/knowledge/documents")
def get_knowledge_documents(
    _: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str = Query(default="", max_length=200),
) -> dict:
    return list_knowledge_documents(page=page, page_size=page_size, search=search)


@router.get("/api/knowledge/health")
def get_rag_health(
    _: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
) -> dict:
    return rag_health()


@router.get("/api/knowledge/search")
def search_knowledge(
    _: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
    q: str = Query(default="", max_length=500),
    top_k: int = Query(default=5, ge=1, le=20),
) -> dict:
    ensure_seed_knowledge()
    return rag_search(q, top_k=top_k)


@router.post("/api/knowledge/search")
def search_knowledge_post(
    _: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict:
    query, top_k = _search_payload(payload)
    ensure_seed_knowledge()
    result = rag_search(query, top_k=top_k)
    result["search_record"] = record_search_result(query, top_k, result)
    return result


@router.post("/api/knowledge/qa-test")
def qa_test_knowledge(
    _: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict:
    query, top_k = _search_payload(payload)
    if not query:
        raise HTTPException(status_code=400, detail="问题不能为空")
    ensure_seed_knowledge()
    started = time.perf_counter()
    result = rag_search(query, top_k=top_k)
    result["search_record"] = record_search_result(query, top_k, result)
    return run_qa_from_search(query, top_k, result, started)


@router.post("/api/knowledge/batch-validate")
def batch_validate_knowledge(
    _: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict:
    questions = payload.get("questions") if isinstance(payload, dict) else None
    values = [str(item).strip() for item in questions or DEFAULT_BATCH_QUESTIONS if str(item).strip()]
    top_k = max(1, min(int((payload or {}).get("top_k") or 5), 20))
    ensure_seed_knowledge()
    items: list[dict[str, Any]] = []
    for question in values[:20]:
        started = time.perf_counter()
        result = rag_search(question, top_k=top_k)
        result["search_record"] = record_search_result(question, top_k, result)
        qa = run_qa_from_search(question, top_k, result, started)
        items.append(
            {
                "question": question,
                "passed": bool(qa.get("passed")),
                "result_count": len(qa.get("items") or []),
                "confidence": qa.get("confidence"),
                "qa_test": qa.get("qa_test"),
            }
        )
    passed = sum(1 for item in items if item.get("passed"))
    return {"items": items, "total": len(items), "passed": passed, "pass_rate": round((passed / len(items)) * 100, 2) if items else 0.0}


@router.post("/api/knowledge/upload")
async def upload_knowledge_document(
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:write"))],
    file: UploadFile = File(...),
    source_type: str = Form("uploaded_document"),
) -> dict:
    content = await file.read()
    if len(content) > KNOWLEDGE_UPLOAD_LIMIT_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 8MB")
    safe_name = _safe_filename(file.filename)
    suffix = "." + safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if suffix not in KNOWLEDGE_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="当前仅支持 txt、md、csv、json 文本文件")
    text_content = content.decode("utf-8", errors="ignore").strip()
    if not text_content:
        raise HTTPException(status_code=400, detail="文件内容为空")
    source_path = f"upload://knowledge/{uuid.uuid4().hex}_{safe_name}"
    result = upsert_document(
        title=safe_name.rsplit(".", 1)[0],
        source_type=source_type or "uploaded_document",
        source_path=source_path,
        content=text_content,
        metadata={"data_origin": "uploaded", "filename": safe_name, "content_type": file.content_type or "text/plain"},
    )
    write_audit_log(
        action="knowledge.upload",
        user=user,
        resource_type="knowledge",
        status="success" if result.get("available") else "failed",
        ip_address=request.client.host if request.client else "",
        metadata={"filename": safe_name, **result},
    )
    if not result.get("available"):
        raise HTTPException(status_code=500, detail=result.get("message") or "文档写入失败")
    return result


@router.get("/api/knowledge/export")
def export_knowledge(
    _: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
) -> Response:
    payload = list_knowledge_documents(page=1, page_size=100)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["doc_id", "title", "source_type", "category", "chunk_count", "embedded_count", "status", "updated_at"])
    for item in payload.get("items") or []:
        writer.writerow(
            [
                item.get("doc_id"),
                item.get("title"),
                item.get("source_type"),
                item.get("category"),
                item.get("chunk_count"),
                item.get("embedded_count"),
                item.get("status"),
                item.get("updated_at"),
            ]
        )
    return Response(
        buffer.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="knowledge_export.csv"'},
    )


@router.post("/api/knowledge/index-local")
def index_knowledge(
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:write"))],
) -> dict:
    try:
        result = enqueue_task("knowledge_import", {})
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    write_audit_log(
        action="knowledge.index_local",
        user=user,
        resource_type="knowledge",
        status="success" if result.get("task_id") else "failed",
        ip_address=request.client.host if request.client else "",
        metadata=result,
    )
    return result


@router.post("/api/knowledge/embedding-refresh")
def refresh_knowledge_embeddings(
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:write"))],
) -> dict:
    try:
        result = enqueue_task("embedding_refresh", {})
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    write_audit_log(
        action="knowledge.embedding_refresh",
        user=user,
        resource_type="knowledge",
        status="success" if result.get("task_id") else "failed",
        ip_address=request.client.host if request.client else "",
        metadata=result,
    )
    return result
