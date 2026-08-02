from dataclasses import FrozenInstanceError

import pytest

from backend.app.services.knowledge_enterprise_service import (
    EnterpriseKnowledgeUnavailable,
    EnterpriseRequestContext,
    get_enterprise_knowledge_application,
)


def test_request_context_is_immutable_and_tenant_scoped():
    context = EnterpriseRequestContext("tenant-a", "actor-a", "run-a", "trace-a")
    assert context.tenant_id == "tenant-a"
    with pytest.raises(FrozenInstanceError):
        context.tenant_id = "tenant-b"  # type: ignore[misc]


@pytest.mark.parametrize(
    "method,kwargs",
    [
        ("create_ingestion", {}),
        ("get_ingestion", {}),
        ("list_releases", {}),
        ("create_release", {}),
        ("validate_release", {}),
        ("publish_release", {}),
        ("rollback_release", {}),
    ],
)
def test_unconfigured_enterprise_service_fails_closed(method: str, kwargs: dict):
    application = get_enterprise_knowledge_application()
    assert application.available is False
    with pytest.raises(
        EnterpriseKnowledgeUnavailable,
        match="^enterprise_knowledge_repository_not_configured$",
    ):
        getattr(application, method)(**kwargs)


def test_unavailable_application_is_stable_and_has_no_install_side_effect():
    first = get_enterprise_knowledge_application()
    second = get_enterprise_knowledge_application()
    assert first is second
    assert first.available is False
