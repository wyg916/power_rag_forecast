from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

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


class UnavailableEnterpriseKnowledgeApplication:
    available = False

    @staticmethod
    def _raise() -> None:
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


def get_enterprise_knowledge_application() -> EnterpriseKnowledgeApplication:
    """Return the fail-closed seam until the database implementation is installed."""

    return _UNAVAILABLE_APPLICATION
