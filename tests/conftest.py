from __future__ import annotations

import os

import pytest
from fastapi import Request

from scripts.day3_test_database_guard import configure_pytest_database


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

# This must run before importing the application. Normal pytest invocations
# cannot inherit the repository's local PostgreSQL target; database-backed
# tests must use the restricted Day 3 isolated runner.
PYTEST_DATABASE_GUARD = configure_pytest_database()

from backend.app.core.config import get_settings  # noqa: E402
from backend.app.core.security import CurrentUser, get_current_user  # noqa: E402
from backend.app.main import app  # noqa: E402


_ISOLATED_DATABASE_TESTS = {
    "tests/test_ai_assistant.py::test_ai_assistant_forecast_extreme_is_question_specific",
    "tests/test_ai_assistant.py::test_ai_assistant_hour_explain_uses_hour_tool",
    "tests/test_ai_assistant.py::test_ai_assistant_core_intents",
    "tests/test_ai_assistant_accuracy.py::test_weather_data_latest_time_answer",
    "tests/test_ai_assistant_accuracy.py::test_storage_discharge_has_multiple_windows",
    "tests/test_data_trust_service.py::test_controlled_ai_business_query_uses_registered_dataset_and_public_fields",
    "tests/test_data_trust_service.py::test_ai_catalog_empty_dataset_and_readiness_use_dataset_contract",
    "tests/test_data_trust_service.py::test_ai_chat_business_data_query_uses_controlled_tool",
    "tests/test_p6_p1_1a_data_center.py::test_database_target_is_the_authorized_local_postgres_and_not_superuser",
    "tests/test_p6_p1_1a_data_center.py::test_quality_and_sync_reads_do_not_write_protected_tables",
    "tests/test_p6_p1_1a_data_center.py::test_quality_report_uses_registered_dataset_contract",
    "tests/test_p6_p1_1a_data_center.py::test_data_center_read_api_has_dataset_meta_pagination_and_permission",
    "tests/test_p6_p1_1b_data_catalog.py::test_registered_dataset_reads_and_export_remain_read_only",
    "tests/test_p6_p1_1b_data_catalog.py::test_table_and_view_are_addressed_only_by_dataset_id",
    "tests/test_p6_p1_1b_data_catalog.py::test_search_is_parameterized_and_unregistered_objects_fail_closed",
    "tests/test_p6_p1_1b_data_catalog.py::test_dataset_rows_api_has_permission_and_canonical_pagination",
    "tests/test_p6_p1_1b_data_catalog.py::test_export_is_authenticated_memory_csv_and_does_not_create_temp_file",
    "tests/test_p6_p1_2a_forecast_layout.py::test_forecast_24h_uses_real_stale_run_without_read_side_effects",
    "tests/test_p6_p1_2b_forecast_facts.py::test_forecast_fact_endpoints_remain_read_only_and_traceable",
    "tests/test_p6_p1_2b_forecast_facts.py::test_previous_batch_is_not_replaced_by_history_mean",
    "tests/test_p6_p1_3a_strategy_layout.py::test_strategy_get_chain_has_no_strategy_or_audit_write_side_effects",
    "tests/test_p6_p1_3c_strategy_runtime.py::test_unique_database_target_and_migration_head",
    "tests/test_p6_p1_3c_strategy_runtime.py::test_controlled_seed_is_idempotent_and_traceable",
    "tests/test_p6_p1_3c_strategy_runtime.py::test_runtime_read_chain_has_no_write_side_effect",
    "tests/test_web_platform.py::test_database_table_browser_endpoints_are_safe",
}


def pytest_collection_modifyitems(items):
    if PYTEST_DATABASE_GUARD.get("mode") != "disabled-no-database":
        return
    marker = pytest.mark.skip(reason="requires the Day 3 isolated database runner")
    for item in items:
        if item.nodeid in _ISOLATED_DATABASE_TESTS:
            item.add_marker(marker)


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
