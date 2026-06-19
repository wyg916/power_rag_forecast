from __future__ import annotations

import importlib

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
    assert task_policy("forecast_run").queue_name == "forecast"
    assert normalize_task_kind("data_sync") == "sync_core_data"
    assert normalize_task_kind("forecast_run") == "fast_forecast"
    assert queue_for_kind("knowledge_import") == "rag"


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
