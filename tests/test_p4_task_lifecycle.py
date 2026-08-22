from __future__ import annotations

import importlib
from datetime import datetime, timezone

from backend.app.core import config
from backend.app.services.task_runtime import normalize_task_kind, queue_for_kind, task_policy
from backend.app.workers import dispatcher


def test_p4_alembic_revision_id_fits_version_column():
    migration = importlib.import_module("migrations.versions.0007_task_runtime_productionization")
    assert len(migration.revision) <= 32


def test_task_runtime_policies_cover_required_task_types():
    assert task_policy("knowledge_import").timeout_seconds == 1800
    assert task_policy("embedding_refresh").queue_name == "embedding"
    assert task_policy("report_generate").max_retries == 2
    assert task_policy("data_sync").max_retries == 3
    assert task_policy("price_predict").queue_name == "price_predict"
    assert task_policy("report_daily").queue_name == "report_daily"
    assert task_policy("forecast_run").queue_name == "price_predict"
    assert normalize_task_kind("data_sync") == "data_sync"
    assert normalize_task_kind("forecast_run") == "price_predict"
    assert normalize_task_kind("fast_forecast") == "price_predict"
    assert queue_for_kind("knowledge_import") == "rag"


def test_forecast_business_idempotency_binds_input_and_model_identity():
    from backend.app.services.forecast_transaction_service import (
        ForecastRunRequest,
        ForecastTransactionService,
    )

    request = ForecastRunRequest(
        domain="price",
        target_name="da_price",
        input_start_at=datetime(2026, 6, 17, tzinfo=timezone.utc),
        input_end_at=datetime(2026, 6, 18, tzinfo=timezone.utc),
        input_hash="input-a",
        environment_hash="env-a",
        idempotency_key="request-001",
    )
    model = {
        "model_version": "model-a",
        "artifact_hash": "artifact-a",
        "feature_version": "features-a",
        "schema_hash": "schema-a",
    }

    first = ForecastTransactionService._input_idempotency_key(request, model)
    second = ForecastTransactionService._input_idempotency_key(request, model)
    changed = ForecastTransactionService._input_idempotency_key(
        ForecastRunRequest(**{**request.__dict__, "input_hash": "input-b"}),
        model,
    )

    assert len(first) == 64
    assert first == second
    assert changed != first


def test_forecast_queue_can_be_isolated_from_historical_backlog(monkeypatch):
    monkeypatch.setenv("FORECAST_CELERY_QUEUE", "forecast_final_rc")

    assert queue_for_kind("forecast_run") == "forecast_final_rc"
    assert queue_for_kind("today_analysis") == "forecast_final_rc"
    assert queue_for_kind("report_generate") == "report"


def test_create_specialized_task_records_lifecycle_defaults(monkeypatch):
    monkeypatch.setenv("TASK_EXECUTION_MODE", "local_thread")
    config.reset_settings_cache()
    monkeypatch.setattr(dispatcher, "celery_available", lambda: False)
    monkeypatch.setattr(dispatcher, "find_active_idempotent_task", lambda *args, **kwargs: None)

    saved: list[dict] = []
    logs: list[dict] = []

    def fake_save(record, status=None, log_text=None):
        saved.append({**record, "save_status": status, "log_text": log_text})
        return True

    class FakeThread:
        def __init__(self, target, args=(), daemon=False):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self):
            return None

    monkeypatch.setattr(dispatcher, "save_task_record", fake_save)
    monkeypatch.setattr(dispatcher, "append_task_log", lambda *args, **kwargs: logs.append({"args": args, **kwargs}) or True)
    monkeypatch.setattr(dispatcher.threading, "Thread", FakeThread)
    try:
        result = dispatcher.enqueue_task("knowledge_import", {"path": "docs/a"})
    finally:
        monkeypatch.delenv("TASK_EXECUTION_MODE", raising=False)
        config.reset_settings_cache()

    assert result["status"] == "pending"
    assert result["execution_mode"] == "local_thread"
    assert saved[-1]["queued_at"]
    assert saved[-1]["timeout_seconds"] == 1800
    assert saved[-1]["max_retries"] == 2
    assert saved[-1]["queue_name"] == "rag"
    assert saved[-1]["idempotency_key"].startswith("knowledge_import:")
    assert logs[-1]["step"] == "prepare"
