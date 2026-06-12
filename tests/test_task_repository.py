from __future__ import annotations

from backend.app.repositories import task_repository


def test_task_repository_no_postgres_is_safe(monkeypatch):
    monkeypatch.setattr(task_repository, "postgres_engine", lambda: None)
    assert task_repository.save_task_record({"task_id": "task_test", "kind": "knowledge_import"}) is False
    assert task_repository.list_recent_tasks() == []
    assert task_repository.get_task_record("missing") is None
    assert task_repository.task_log_text("missing") is None
