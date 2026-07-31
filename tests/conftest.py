from __future__ import annotations

import os

import pytest
from fastapi import Request


# Unit tests should not load local multi-GB embedding/reranker models or call
# external LLM providers. Integration/evaluation scripts exercise those paths.
os.environ["AI_ASSISTANT_LLM_ENABLED"] = "0"
os.environ["RAG_EMBEDDING_PROVIDER"] = "local"
os.environ["RAG_EMBEDDING_MODEL"] = "local-hash-bge-small-zh-v1.5-compatible"
os.environ["RAG_EMBEDDING_DIM"] = "256"
os.environ["RAG_RERANK_ENABLED"] = "1"
os.environ["RAG_RERANK_PROVIDER"] = "local"
os.environ["RAG_RERANK_MODEL"] = "bge-reranker-base"
os.environ["RAG_CACHE_ENABLED"] = "0"

from backend.app.core.config import get_settings  # noqa: E402
from backend.app.core.security import CurrentUser, get_current_user  # noqa: E402
from backend.app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _authenticated_legacy_client(request):
    """Give legacy business tests an explicit in-memory admin identity.

    Security-boundary tests opt out with ``no_legacy_auth``. Explicit Bearer
    tokens and development identity headers always exercise the real resolver.
    """
    if request.node.get_closest_marker("no_legacy_auth"):
        yield
        return

    admin = CurrentUser(
        user_id="pytest-admin",
        username="pytest-admin",
        role="admin",
        permissions=["*"],
        auth_mode="dependency_override",
    )

    def resolver(http_request: Request):
        if (
            http_request.headers.get("Authorization")
            or http_request.headers.get("X-User")
            or get_settings().auth_required
        ):
            return get_current_user(http_request)
        return admin

    app.dependency_overrides[get_current_user] = resolver
    try:
        yield
    finally:
        if app.dependency_overrides.get(get_current_user) is resolver:
            app.dependency_overrides.pop(get_current_user, None)
