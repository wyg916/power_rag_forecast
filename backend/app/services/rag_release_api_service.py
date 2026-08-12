from __future__ import annotations

import json
import os
import ssl
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from sqlalchemy import text

from backend.app.knowledge_enterprise_contracts import ReleaseCreateRequest
from backend.app.repositories.base import postgres_engine
from backend.app.services.knowledge_enterprise_service import (
    EnterpriseKnowledgeConflict,
    EnterpriseKnowledgeUnavailable,
    EnterpriseRequestContext,
)


PUBLIC_RELEASE_STATUSES = frozenset(
    {"candidate", "validated", "published", "superseded", "rolled_back", "failed"}
)
WORKER_ACTIONS = frozenset({"create", "validate", "publish", "rollback"})


class EnterpriseKnowledgeNotFound(LookupError):
    pass


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)


def _public_release(row: Mapping[str, Any]) -> dict[str, Any]:
    status = str(row.get("status") or "")
    if status not in PUBLIC_RELEASE_STATUSES:
        raise EnterpriseKnowledgeUnavailable("release_status_invalid")
    gate_total = int(row.get("gate_total") or 0)
    gate_passed = int(row.get("gate_passed") or 0)
    return {
        "release_id": str(row["release_id"]),
        "status": status,
        "is_current": bool(row.get("is_current")),
        "documents": int(row.get("document_count") or 0),
        "chunks": int(row.get("chunk_count") or 0),
        "isolated": int(row.get("isolated_count") or 0),
        "duplicates": int(row.get("duplicate_count") or 0),
        "gates": {
            "passed": gate_passed,
            "total": gate_total,
            "ready": gate_total > 0 and gate_passed == gate_total,
        },
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "validated_at": _iso(row.get("validated_at")),
        "published_at": _iso(row.get("published_at")),
        "rolled_back_at": _iso(row.get("rolled_back_at")),
    }


@dataclass(frozen=True)
class ReleaseWorkerClient:
    endpoint: str
    token: str

    @classmethod
    def from_environment(cls) -> "ReleaseWorkerClient":
        endpoint = os.environ.get("RAG_RELEASE_WORKER_URL", "").strip().rstrip("/")
        token = os.environ.get("RAG_RELEASE_WORKER_TOKEN", "").strip()
        if not endpoint or not token:
            raise EnterpriseKnowledgeUnavailable("release_worker_not_configured")
        parsed = urlparse(endpoint)
        local_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
        if parsed.scheme != "https" and not local_http:
            raise EnterpriseKnowledgeUnavailable("release_worker_transport_rejected")
        return cls(endpoint, token)

    def call(
        self,
        *,
        action: str,
        context: EnterpriseRequestContext,
        release_id: str,
        request_payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if action not in WORKER_ACTIONS:
            raise EnterpriseKnowledgeUnavailable("release_worker_action_invalid")
        payload = {
            "tenant_id": context.tenant_id,
            "actor_id": context.actor_id,
            "run_id": context.run_id,
            "trace_id": context.trace_id,
            "release_id": release_id,
            "request": dict(request_payload or {}),
        }
        target = f"{self.endpoint}/v1/releases/{action}"
        outgoing = Request(
            target,
            data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            headers={
                "authorization": f"Bearer {self.token}",
                "content-type": "application/json",
                "accept": "application/json",
            },
            method="POST",
        )
        context_ssl = ssl.create_default_context() if target.startswith("https://") else None
        try:
            with urlopen(outgoing, context=context_ssl, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 409:
                raise EnterpriseKnowledgeConflict("release_worker_conflict") from exc
            raise EnterpriseKnowledgeUnavailable("release_worker_unavailable") from exc
        except (OSError, URLError, UnicodeError, json.JSONDecodeError) as exc:
            raise EnterpriseKnowledgeUnavailable("release_worker_unavailable") from exc
        if not isinstance(body, dict) or body.get("status") != "PASS":
            raise EnterpriseKnowledgeUnavailable("release_worker_response_invalid")
        release = body.get("release")
        if not isinstance(release, dict) or release.get("release_id") != release_id:
            raise EnterpriseKnowledgeUnavailable("release_worker_identity_mismatch")
        return release


class RagReleaseApiService:
    """Public release read model plus a credential-separated publisher client."""

    def _engine(self):
        engine = postgres_engine()
        if engine is None:
            raise EnterpriseKnowledgeUnavailable("postgres_release_store_unavailable")
        return engine

    def list_releases(self, *, tenant_id: str) -> list[dict[str, Any]]:
        if not str(tenant_id or "").strip():
            raise EnterpriseKnowledgeUnavailable("tenant_invalid")
        statement = text(
            """
            WITH item_counts AS (
              SELECT tenant_id, release_id,
                     COUNT(*) FILTER (WHERE terminal_status = 'published') AS document_count,
                     COALESCE(SUM(chunk_count), 0) AS chunk_count,
                     COUNT(*) FILTER (WHERE terminal_status IN ('isolated','damaged')) AS isolated_count,
                     COUNT(*) FILTER (WHERE terminal_status = 'duplicate') AS duplicate_count
              FROM kb_release_items WHERE tenant_id = :tenant GROUP BY tenant_id, release_id
            ), gate_facts AS (
              SELECT DISTINCT ON (tenant_id, release_id) tenant_id, release_id,
                     COALESCE((details_json->>'gate_total')::integer, 0) AS gate_total,
                     COALESCE((details_json->>'gate_passed')::integer, 0) AS gate_passed
              FROM kb_rag_audit_events
              WHERE tenant_id = :tenant AND event_type = 'release_gates_admitted'
              ORDER BY tenant_id, release_id, created_at DESC
            )
            SELECT r.release_id, r.status, r.is_current, r.created_at, r.updated_at,
                   r.validated_at, r.published_at, r.rolled_back_at,
                   COALESCE(i.document_count, 0) AS document_count,
                   COALESCE(i.chunk_count, 0) AS chunk_count,
                   COALESCE(i.isolated_count, 0) AS isolated_count,
                   COALESCE(i.duplicate_count, 0) AS duplicate_count,
                   COALESCE(g.gate_total, 0) AS gate_total,
                   COALESCE(g.gate_passed, 0) AS gate_passed
            FROM kb_releases r
            LEFT JOIN item_counts i USING (tenant_id, release_id)
            LEFT JOIN gate_facts g USING (tenant_id, release_id)
            WHERE r.tenant_id = :tenant
            ORDER BY r.created_at DESC, r.release_id DESC
            """
        )
        try:
            with self._engine().connect() as connection:
                rows = connection.execute(statement, {"tenant": tenant_id}).mappings().all()
        except EnterpriseKnowledgeUnavailable:
            raise
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable("release_fact_read_failed") from exc
        return [_public_release(row) for row in rows]

    def get_ingestion(self, *, tenant_id: str, ingestion_id: str) -> dict[str, Any]:
        if not str(tenant_id or "").strip() or not ingestion_id:
            raise EnterpriseKnowledgeUnavailable("ingestion_identity_invalid")
        statement = text(
            """
            SELECT version_id, document_id, source_id, parse_status, isolation_reason,
                   created_at, metadata_json
            FROM kb_document_versions
            WHERE tenant_id = :tenant AND (version_id = :id OR source_id = :id)
            ORDER BY created_at DESC LIMIT 1
            """
        )
        try:
            with self._engine().connect() as connection:
                row = connection.execute(
                    statement, {"tenant": tenant_id, "id": ingestion_id}
                ).mappings().one_or_none()
        except EnterpriseKnowledgeUnavailable:
            raise
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable("ingestion_fact_read_failed") from exc
        if row is None:
            raise EnterpriseKnowledgeNotFound("ingestion_not_found")
        raw_status = str(row["parse_status"])
        status = {"ready": "ready", "isolated": "quarantined", "duplicate": "quarantined", "damaged": "corrupt"}.get(raw_status)
        if status is None:
            raise EnterpriseKnowledgeUnavailable("ingestion_status_invalid")
        failed = status in {"quarantined", "corrupt"}
        return {
            "ingestion_id": ingestion_id,
            "document_id": str(row["document_id"]),
            "version_id": str(row["version_id"]),
            "status": status,
            "progress": [
                {"component": "parse", "status": "failed" if failed else "succeeded"},
                {"component": "validate", "status": "failed" if failed else "succeeded"},
                {"component": "embedding", "status": "skipped" if failed else "succeeded"},
            ],
            "isolation_reason": str(row.get("isolation_reason") or ""),
            "updated_at": _iso(row.get("created_at")),
        }

    def create_release(
        self, *, context: EnterpriseRequestContext, request: ReleaseCreateRequest
    ) -> dict[str, Any]:
        release = ReleaseWorkerClient.from_environment().call(
            action="create",
            context=context,
            release_id=request.release_id,
            request_payload=request.model_dump(mode="json"),
        )
        return self._public_worker_release(release)

    def act(
        self, *, action: str, context: EnterpriseRequestContext, release_id: str
    ) -> dict[str, Any]:
        release = ReleaseWorkerClient.from_environment().call(
            action=action, context=context, release_id=release_id
        )
        return self._public_worker_release(release)

    @staticmethod
    def _public_worker_release(release: Mapping[str, Any]) -> dict[str, Any]:
        return _public_release(
            {
                "release_id": release.get("release_id"),
                "status": release.get("status"),
                "is_current": release.get("is_current"),
                "document_count": release.get("documents"),
                "chunk_count": release.get("chunks"),
                "isolated_count": release.get("isolated"),
                "duplicate_count": release.get("duplicates"),
                "gate_total": (release.get("gates") or {}).get("total"),
                "gate_passed": (release.get("gates") or {}).get("passed"),
                "created_at": release.get("created_at"),
                "updated_at": release.get("updated_at"),
                "validated_at": release.get("validated_at"),
                "published_at": release.get("published_at"),
                "rolled_back_at": release.get("rolled_back_at"),
            }
        )


release_control = RagReleaseApiService()
