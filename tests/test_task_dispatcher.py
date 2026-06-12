from __future__ import annotations

from backend.app.core import config
from backend.app.workers import dispatcher


def test_celery_mode_requires_celery(monkeypatch):
    monkeypatch.setenv("TASK_EXECUTION_MODE", "celery")
    config.reset_settings_cache()
    monkeypatch.setattr(dispatcher, "celery_available", lambda: False)
    try:
        try:
            dispatcher.enqueue_task("knowledge_import", {})
        except RuntimeError as exc:
            assert "TASK_EXECUTION_MODE=celery" in str(exc)
        else:
            raise AssertionError("expected RuntimeError")
    finally:
        monkeypatch.delenv("TASK_EXECUTION_MODE", raising=False)
        config.reset_settings_cache()


def test_local_thread_mode_uses_specialized_thread(monkeypatch):
    monkeypatch.setenv("TASK_EXECUTION_MODE", "local_thread")
    config.reset_settings_cache()
    monkeypatch.setattr(dispatcher, "celery_available", lambda: True)
    monkeypatch.setattr(dispatcher, "save_task_record", lambda *args, **kwargs: True)

    class FakeThread:
        def __init__(self, target, args=(), daemon=False):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self):
            return None

    monkeypatch.setattr(dispatcher.threading, "Thread", FakeThread)
    try:
        result = dispatcher.enqueue_task("embedding_refresh", {})
        assert result["execution_mode"] == "local_thread"
        assert result["status"] == "pending"
    finally:
        monkeypatch.delenv("TASK_EXECUTION_MODE", raising=False)
        config.reset_settings_cache()
