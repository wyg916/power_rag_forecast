from __future__ import annotations

from backend.app.core import config
from backend.app.services.task_runtime import idempotency_key_for, payload_hash
from backend.app.workers import dispatcher


def test_payload_hash_ignores_runtime_only_fields():
    left = payload_hash({"path": "docs/a", "created_by": "alice", "retry_count": 1})
    right = payload_hash({"path": "docs/a", "created_by": "bob", "retry_count": 9, "force_new": True})
    different = payload_hash({"path": "docs/b"})
    assert left == right
    assert left != different


def test_explicit_idempotency_key_is_preserved():
    key, hash_value = idempotency_key_for("embedding_refresh", {"scope": "all", "idempotency_key": "manual-key"})
    assert key == "manual-key"
    assert len(hash_value) == 64


def test_duplicate_active_task_returns_existing_task(monkeypatch):
    monkeypatch.setenv("TASK_EXECUTION_MODE", "local_thread")
    config.reset_settings_cache()
    existing = {
        "task_id": "task_existing",
        "kind": "embedding_refresh",
        "status": "running",
        "deduped": True,
        "message": "已有相同任务正在运行，已返回已有任务",
    }
    monkeypatch.setattr(dispatcher, "find_active_idempotent_task", lambda *args, **kwargs: existing)
    monkeypatch.setattr(dispatcher, "save_task_record", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not save duplicate")))
    try:
        result = dispatcher.enqueue_task("embedding_refresh", {"scope": "all"})
    finally:
        monkeypatch.delenv("TASK_EXECUTION_MODE", raising=False)
        config.reset_settings_cache()

    assert result["task_id"] == "task_existing"
    assert result["deduped"] is True
