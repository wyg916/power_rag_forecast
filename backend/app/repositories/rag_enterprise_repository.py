from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app.knowledge_enterprise_contracts import (
    EmbeddingProfileContract,
    ReleaseContract,
    ReleaseState,
)
from backend.app.repositories.base import postgres_engine


class EnterpriseReleaseReadError(RuntimeError):
    pass


class PostgresReleaseContractReader:
    """Read-only adapter for public RAG release facts."""

    def __init__(
        self, engine_provider: Callable[[], Engine | None] = postgres_engine
    ) -> None:
        self._engine_provider = engine_provider

    @staticmethod
    def _contract(row: Any) -> ReleaseContract:
        value = dict(row)
        return ReleaseContract(
            release_id=value["release_id"],
            tenant_id=value["tenant_id"],
            status=ReleaseState(value["status"]),
            collection=value["collection_name"],
            alias="rag_chunks_current",
            manifest_sha256=value["manifest_sha256"],
            embedding_profile=EmbeddingProfileContract(
                provider=value["embedding_provider"],
                model=value["embedding_model"],
                version=value["embedding_version"],
                dimension=value["embedding_dimension"],
                sparse_profile=value["sparse_profile"],
            ),
            gates=[],
            run_id=value["run_id"],
            trace_id=value["trace_id"],
            created_at=value["created_at"],
            updated_at=value["updated_at"],
        )

    def list_releases(self, *, tenant_id: str) -> list[ReleaseContract]:
        if tenant_id != "default":
            raise EnterpriseReleaseReadError("release_tenant_rejected")
        engine = self._engine_provider()
        if engine is None or engine.dialect.name != "postgresql":
            raise EnterpriseReleaseReadError("release_database_unavailable")
        try:
            with engine.connect() as connection:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                rows = connection.execute(
                    text(
                        """
                        SELECT tenant_id, release_id, status, collection_name,
                               manifest_sha256, embedding_provider, embedding_model,
                               embedding_version, embedding_dimension, sparse_profile,
                               run_id, trace_id, created_at, updated_at
                        FROM kb_releases
                        WHERE tenant_id = :tenant_id
                        ORDER BY created_at DESC, release_id
                        """
                    ),
                    {"tenant_id": tenant_id},
                ).mappings().all()
                connection.rollback()
        except Exception as exc:
            raise EnterpriseReleaseReadError("release_fact_read_failed") from exc
        try:
            return [self._contract(row) for row in rows]
        except Exception as exc:
            raise EnterpriseReleaseReadError("release_fact_contract_invalid") from exc

    def current_published_release(self, *, tenant_id: str) -> ReleaseContract | None:
        if tenant_id != "default":
            raise EnterpriseReleaseReadError("release_tenant_rejected")
        engine = self._engine_provider()
        if engine is None or engine.dialect.name != "postgresql":
            raise EnterpriseReleaseReadError("release_database_unavailable")
        try:
            with engine.connect() as connection:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                rows = connection.execute(
                    text(
                        """
                        SELECT tenant_id, release_id, status, collection_name,
                               manifest_sha256, embedding_provider, embedding_model,
                               embedding_version, embedding_dimension, sparse_profile,
                               run_id, trace_id, created_at, updated_at
                        FROM kb_releases
                        WHERE tenant_id = :tenant_id
                          AND status = 'published'
                          AND is_current IS TRUE
                        ORDER BY created_at DESC, release_id
                        """
                    ),
                    {"tenant_id": tenant_id},
                ).mappings().all()
                connection.rollback()
        except Exception as exc:
            raise EnterpriseReleaseReadError("release_fact_read_failed") from exc
        if len(rows) > 1:
            raise EnterpriseReleaseReadError("release_current_not_unique")
        if not rows:
            return None
        try:
            return self._contract(rows[0])
        except Exception as exc:
            raise EnterpriseReleaseReadError("release_fact_contract_invalid") from exc
