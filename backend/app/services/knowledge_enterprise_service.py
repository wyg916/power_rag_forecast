from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import NoReturn, Protocol

from backend.app.knowledge_enterprise_contracts import (
    IngestionContract,
    IngestionCreateRequest,
    ReleaseContract,
    ReleaseCreateRequest,
)


class EnterpriseKnowledgeUnavailable(RuntimeError):
    pass


class EnterpriseKnowledgeConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class EnterpriseRequestContext:
    tenant_id: str
    actor_id: str
    run_id: str
    trace_id: str


class EnterpriseKnowledgeApplication(Protocol):
    available: bool

    def create_ingestion(
        self,
        *,
        context: EnterpriseRequestContext,
        request: IngestionCreateRequest,
        content: bytes,
    ) -> IngestionContract: ...

    def get_ingestion(
        self, *, context: EnterpriseRequestContext, ingestion_id: str
    ) -> IngestionContract: ...

    def list_releases(
        self, *, context: EnterpriseRequestContext
    ) -> list[ReleaseContract]: ...

    def create_release(
        self,
        *,
        context: EnterpriseRequestContext,
        request: ReleaseCreateRequest,
    ) -> ReleaseContract: ...

    def validate_release(
        self, *, context: EnterpriseRequestContext, release_id: str
    ) -> ReleaseContract: ...

    def publish_release(
        self, *, context: EnterpriseRequestContext, release_id: str
    ) -> ReleaseContract: ...

    def rollback_release(
        self, *, context: EnterpriseRequestContext, release_id: str
    ) -> ReleaseContract: ...


class EnterpriseReleaseReader(Protocol):
    def list_releases(self, *, tenant_id: str) -> list[ReleaseContract]: ...


class UnavailableEnterpriseKnowledgeApplication:
    available = False

    @staticmethod
    def _raise() -> NoReturn:
        raise EnterpriseKnowledgeUnavailable(
            "enterprise_knowledge_repository_not_configured"
        )

    def create_ingestion(self, **_: object) -> IngestionContract:
        self._raise()

    def get_ingestion(self, **_: object) -> IngestionContract:
        self._raise()

    def list_releases(self, **_: object) -> list[ReleaseContract]:
        self._raise()

    def create_release(self, **_: object) -> ReleaseContract:
        self._raise()

    def validate_release(self, **_: object) -> ReleaseContract:
        self._raise()

    def publish_release(self, **_: object) -> ReleaseContract:
        self._raise()

    def rollback_release(self, **_: object) -> ReleaseContract:
        self._raise()


_UNAVAILABLE_APPLICATION = UnavailableEnterpriseKnowledgeApplication()


class PostgresReadOnlyEnterpriseKnowledgeApplication:
    """Expose verified release reads while all enterprise writes remain fail-closed."""

    available = True

    def __init__(self, release_reader: EnterpriseReleaseReader) -> None:
        self.release_reader = release_reader

    @staticmethod
    def _write_unavailable() -> NoReturn:
        raise EnterpriseKnowledgeUnavailable(
            "enterprise_release_write_control_not_configured"
        )

    def create_ingestion(self, **_: object) -> IngestionContract:
        self._write_unavailable()

    def get_ingestion(self, **_: object) -> IngestionContract:
        self._write_unavailable()

    def list_releases(
        self, *, context: EnterpriseRequestContext
    ) -> list[ReleaseContract]:
        if context.tenant_id != "default" or not all(
            (context.actor_id, context.run_id, context.trace_id)
        ):
            raise EnterpriseKnowledgeUnavailable("enterprise_context_invalid")
        try:
            return self.release_reader.list_releases(tenant_id=context.tenant_id)
        except Exception as exc:
            raise EnterpriseKnowledgeUnavailable("release_fact_read_failed") from exc

    def create_release(self, **_: object) -> ReleaseContract:
        self._write_unavailable()

    def validate_release(self, **_: object) -> ReleaseContract:
        self._write_unavailable()

    def publish_release(self, **_: object) -> ReleaseContract:
        self._write_unavailable()

    def rollback_release(self, **_: object) -> ReleaseContract:
        self._write_unavailable()


@lru_cache(maxsize=1)
def get_enterprise_knowledge_application() -> EnterpriseKnowledgeApplication:
    """Install only the read adapter in enterprise mode; writes remain unavailable."""

    from backend.app.core.config import get_settings
    from backend.app.repositories.rag_enterprise_repository import (
        PostgresReleaseContractReader,
    )

    settings = get_settings()
    if settings.rag_profile.strip().lower() == "enterprise" and settings.has_database_url:
        return PostgresReadOnlyEnterpriseKnowledgeApplication(
            PostgresReleaseContractReader()
        )
    return _UNAVAILABLE_APPLICATION
