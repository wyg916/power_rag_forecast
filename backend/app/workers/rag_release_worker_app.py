from __future__ import annotations

import hmac
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine

from backend.app.services.knowledge_enterprise_service import (
    EnterpriseKnowledgeConflict,
    EnterpriseKnowledgeUnavailable,
    EnterpriseRequestContext,
)
from backend.app.services.rag_release_worker_runtime import (
    QdrantReleaseAdmin,
    RagReleaseWorkerRuntime,
)


class WorkerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    actor_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    release_id: str = Field(min_length=1, max_length=128)
    request: dict[str, Any] = Field(default_factory=dict)


app = FastAPI(title="RAG-R1 Release Worker", docs_url=None, redoc_url=None)


def _authorize(authorization: str = Header(default="")) -> None:
    expected = os.environ.get("RAG_RELEASE_WORKER_TOKEN", "").strip()
    supplied = authorization.removeprefix("Bearer ").strip()
    if len(expected) < 24 or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="release_worker_unauthorized")


@lru_cache(maxsize=1)
def get_runtime() -> RagReleaseWorkerRuntime:
    database_url = os.environ.get("RAG_RELEASE_DATABASE_URL", "").strip()
    qdrant_env = os.environ.get("RAG_RELEASE_QDRANT_ENV_FILE", "").strip()
    if not database_url or not qdrant_env:
        raise EnterpriseKnowledgeUnavailable("release_worker_configuration_incomplete")
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        future=True,
        connect_args={"hostaddr": "127.0.0.1"},
    )
    return RagReleaseWorkerRuntime(engine, QdrantReleaseAdmin(Path(qdrant_env)))


def _context(payload: WorkerRequest) -> EnterpriseRequestContext:
    if payload.tenant_id != "default":
        raise HTTPException(status_code=400, detail="tenant_invalid")
    return EnterpriseRequestContext(
        payload.tenant_id, payload.actor_id, payload.run_id, payload.trace_id
    )


def _run(action: str, payload: WorkerRequest) -> dict[str, Any]:
    try:
        release = get_runtime().action(
            action=action,
            context=_context(payload),
            release_id=payload.release_id,
            request_payload=payload.request,
        )
    except EnterpriseKnowledgeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EnterpriseKnowledgeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "PASS", "release": release}


for _action in ("create", "validate", "publish", "rollback"):
    def endpoint(
        payload: WorkerRequest,
        _: None = Depends(_authorize),
        action: str = _action,
    ) -> dict[str, Any]:
        return _run(action, payload)

    endpoint.__name__ = f"release_{_action}"
    app.post(f"/v1/releases/{_action}")(endpoint)


@app.post("/v1/releases/admit")
def admit_release(
    payload: WorkerRequest,
    _: None = Depends(_authorize),
) -> dict[str, Any]:
    report = payload.request.get("gate_report")
    report_sha256 = str(payload.request.get("gate_report_sha256") or "")
    if not isinstance(report, dict):
        raise HTTPException(status_code=400, detail="gate_report_required")
    try:
        release = get_runtime().admit(
            context=_context(payload),
            release_id=payload.release_id,
            gate_report=report,
            gate_report_sha256=report_sha256,
        )
    except EnterpriseKnowledgeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EnterpriseKnowledgeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "PASS", "release": release}
