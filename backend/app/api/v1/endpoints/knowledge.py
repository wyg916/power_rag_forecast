from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ....core.security import CurrentUser, require_permission
from ....repositories.audit_repository import write_audit_log
from ....repositories.knowledge_repository import knowledge_stats
from ....services.rag_health_service import rag_health
from ....services.rag_service import rag_search
from ....workers.dispatcher import enqueue_task


router = APIRouter()


@router.get("/api/knowledge/stats")
def get_knowledge_stats(
    _: Annotated[CurrentUser, Depends(require_permission("knowledge:read"))],
) -> dict:
    return knowledge_stats()


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
    return rag_search(q, top_k=top_k)


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
