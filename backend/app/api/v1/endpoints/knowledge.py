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
    get_knowledge_citation,
    get_knowledge_document,
    knowledge_stats,
    list_knowledge_chunks,
    list_knowledge_documents,
    record_search_result,
    run_qa_from_search,
    upsert_document,
)
from ....services.rag_health_service import rag_health
from ....services.rag_qdrant_transport import enterprise_runtime_for_user
from ....services.rag_release_api_service import (
    EnterpriseKnowledgeNotFound,
    release_control,
)
from ....services.knowledge_enterprise_service import (
    EnterpriseKnowledgeConflict,
    EnterpriseKnowledgeUnavailable,
    EnterpriseRequestContext,
)
from ....knowledge_enterprise_contracts import ReleaseCreateRequest
from ....services.rag_runtime_contract import enterprise_mode
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


def _tenant_scope(user: CurrentUser | None) -> dict[str, str]:
    if user is None or user.tenant_id == "default":
        return {}
    return {"tenant_id": user.tenant_id}


def _release_context(request: Request, user: CurrentUser) -> EnterpriseRequestContext:
    trace_id = str(request.headers.get("X-Trace-Id") or f"trace_{uuid.uuid4().hex}")[:128]
    run_id = str(request.headers.get("X-Run-Id") or f"run_{uuid.uuid4().hex}")[:128]
    return EnterpriseRequestContext(user.tenant_id, user.user_id, run_id, trace_id)


def _release_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EnterpriseKnowledgeNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, EnterpriseKnowledgeConflict):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=503, detail=str(exc))


@router.get("/api/knowledge/ingestions/{ingestion_id}")
def get_knowledge_ingestion(
    ingestion_id: str,
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:write"))],
) -> dict:
    try:
        return release_control.get_ingestion(tenant_id=user.tenant_id, ingestion_id=ingestion_id)
    except (EnterpriseKnowledgeNotFound, EnterpriseKnowledgeUnavailable) as exc:
        raise _release_error(exc) from exc


@router.get("/api/knowledge/releases")
def get_knowledge_releases(
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
) -> dict:
    try:
        items = release_control.list_releases(tenant_id=user.tenant_id)
    except EnterpriseKnowledgeUnavailable as exc:
        raise _release_error(exc) from exc
    return {"items": items, "total": len(items)}


@router.post("/api/knowledge/releases")
def create_knowledge_release(
    payload: ReleaseCreateRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:publish"))],
) -> dict:
    try:
        return release_control.create_release(
            context=_release_context(request, user), request=payload
        )
    except (EnterpriseKnowledgeConflict, EnterpriseKnowledgeUnavailable) as exc:
        raise _release_error(exc) from exc


def _act_release(action: str, release_id: str, request: Request, user: CurrentUser) -> dict:
    try:
        return release_control.act(
            action=action,
            context=_release_context(request, user),
            release_id=release_id,
        )
    except (EnterpriseKnowledgeConflict, EnterpriseKnowledgeUnavailable) as exc:
        raise _release_error(exc) from exc


@router.post("/api/knowledge/releases/{release_id}/validate")
def validate_knowledge_release(
    release_id: str,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:publish"))],
) -> dict:
    return _act_release("validate", release_id, request, user)


@router.post("/api/knowledge/releases/{release_id}/publish")
def publish_knowledge_release(
    release_id: str,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:publish"))],
) -> dict:
    return _act_release("publish", release_id, request, user)


@router.post("/api/knowledge/releases/{release_id}/rollback")
def rollback_knowledge_release(
    release_id: str,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:publish"))],
) -> dict:
    return _act_release("rollback", release_id, request, user)


def _safe_filename(filename: str | None) -> str:
    raw = (filename or "knowledge_document").strip()
    safe = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", raw, flags=re.UNICODE).strip("._")
    return safe or "knowledge_document"


def _search_payload(payload: dict[str, Any] | None) -> tuple[str, int, dict[str, Any]]:
    data = payload or {}
    if "tenant_id" in data or "tenantId" in data:
        raise HTTPException(status_code=400, detail="tenant_override_forbidden")
    query = str(data.get("q") or data.get("query") or data.get("question") or "").strip()
    top_k = int(data.get("top_k") or data.get("topK") or 5)
    source_types = data.get("source_types") or data.get("sourceTypes") or []
    if isinstance(source_types, str):
        source_types = [item.strip() for item in source_types.split(",") if item.strip()]
    return (
        query[:500],
        max(1, min(top_k, 20)),
        {
            "domain": str(data.get("domain") or "").strip(),
            "source_types": [str(item).strip() for item in source_types if str(item).strip()],
            "include_historical": bool(data.get("include_historical", False)),
            "include_demo": bool(data.get("include_demo", False)),
        },
    )

def _run_search(
    query: str,
    top_k: int,
    options: dict[str, Any] | None = None,
    user: CurrentUser | None = None,
) -> dict:
    normalized = options or {}
    runtime: dict[str, Any] = {}
    if enterprise_mode():
        if user is None:
            raise HTTPException(status_code=503, detail="enterprise_user_context_missing")
        try:
            context, store = enterprise_runtime_for_user(user)
        except Exception as exc:
            return {
                "available": False,
                "items": [],
                "citations": [],
                "release_id": None,
                "retrieval": {"enabled": True, "mode": "enterprise_qdrant_hybrid", "reason": str(exc).split(":", 1)[0]},
            }
        runtime = {"context": context, "enterprise_store": store}
    if not any(
        (
            normalized.get("domain"),
            normalized.get("source_types"),
            normalized.get("include_historical"),
            normalized.get("include_demo"),
        )
    ):
        return rag_search(
            query,
            top_k=top_k,
            **_tenant_scope(user),
            **runtime,
        )
    return rag_search(
        query,
        top_k=top_k,
        **_tenant_scope(user),
        **normalized,
        **runtime,
    )


@router.get("/api/knowledge/stats")
def get_knowledge_stats(
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
) -> dict:
    return knowledge_stats(**_tenant_scope(user))


@router.get("/api/knowledge/documents")
def get_knowledge_documents(
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str = Query(default="", max_length=200),
) -> dict:
    return list_knowledge_documents(
        page=page,
        page_size=page_size,
        search=search,
        **_tenant_scope(user),
    )


@router.get("/api/knowledge/documents/{doc_id}")
def get_knowledge_document_detail(
    doc_id: str,
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
) -> dict:
    result = get_knowledge_document(doc_id, **_tenant_scope(user))
    if not result.get("available") and result.get("reason") == "not_found":
        raise HTTPException(status_code=404, detail="knowledge_document_not_found")
    return result


@router.get("/api/knowledge/documents/{doc_id}/chunks")
def get_knowledge_document_chunks(
    doc_id: str,
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> dict:
    document = get_knowledge_document(doc_id, **_tenant_scope(user))
    if not document.get("available") and document.get("reason") == "not_found":
        raise HTTPException(status_code=404, detail="knowledge_document_not_found")
    return list_knowledge_chunks(
        doc_id,
        page=page,
        page_size=page_size,
        **_tenant_scope(user),
    )


@router.get("/api/knowledge/citations/{chunk_id}")
def get_knowledge_citation_detail(
    chunk_id: str,
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
) -> dict:
    return get_knowledge_citation(chunk_id, **_tenant_scope(user))


@router.get("/api/knowledge/health")
def get_rag_health(
    _: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
) -> dict:
    return rag_health()


@router.get("/api/knowledge/health/diagnostics")
def get_rag_health_diagnostics(
    _: Annotated[CurrentUser, Depends(require_permission("knowledge:diagnose"))],
) -> dict:
    return rag_health(diagnostic=True)


@router.get("/api/knowledge/search")
def search_knowledge(
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
    q: str = Query(default="", max_length=500),
    top_k: int = Query(default=5, ge=1, le=20),
    domain: str = Query(default="", max_length=64),
    source_type: list[str] | None = Query(default=None),
    include_historical: bool = Query(default=False),
    include_demo: bool = Query(default=False),
) -> dict:
    return _run_search(
        q,
        top_k,
        {
            "domain": domain,
            "source_types": source_type or [],
            "include_historical": include_historical,
            "include_demo": include_demo,
        },
        user,
    )


@router.post("/api/knowledge/search")
def search_knowledge_post(
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict:
    query, top_k, options = _search_payload(payload)
    return _run_search(query, top_k, options, user)


@router.post("/api/knowledge/qa-test")
def qa_test_knowledge(
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict:
    query, top_k, options = _search_payload(payload)
    if not query:
        raise HTTPException(status_code=400, detail="问题不能为空")
    started = time.perf_counter()
    result = _run_search(query, top_k, options, user)
    return run_qa_from_search(query, top_k, result, started)


@router.post("/api/knowledge/batch-validate")
def batch_validate_knowledge(
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict:
    questions = payload.get("questions") if isinstance(payload, dict) else None
    values = [str(item).strip() for item in questions or DEFAULT_BATCH_QUESTIONS if str(item).strip()]
    top_k = max(1, min(int((payload or {}).get("top_k") or 5), 20))
    items: list[dict[str, Any]] = []
    for question in values[:20]:
        started = time.perf_counter()
        result = _run_search(question, top_k, user=user)
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
    domain: str = Form("uploaded_knowledge"),
    evidence_source_type: str = Form("real"),
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
        metadata={
            "data_origin": "uploaded",
            "filename": safe_name,
            "content_type": file.content_type or "text/plain",
            "domain": domain,
            "evidence_source_type": evidence_source_type,
            "source_name": safe_name,
            "status": "active",
            "evidence_level": "uploaded_document",
        },
        generate_embeddings=True,
        tenant_id=user.tenant_id,
        owner_actor_id=user.user_id,
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
    user: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
) -> Response:
    payload = list_knowledge_documents(page=1, page_size=100, **_tenant_scope(user))
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
