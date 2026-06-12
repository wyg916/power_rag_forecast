from __future__ import annotations

import json

from backend.app.core.security import CurrentUser
from backend.app.repositories import audit_repository


class _FakeResult:
    pass


class _FakeConn:
    def __init__(self) -> None:
        self.params = None

    def execute(self, _statement, params=None):
        self.params = params
        return _FakeResult()


class _FakeEngine:
    def __init__(self) -> None:
        self.conn = _FakeConn()

    def begin(self):
        engine = self

        class _Ctx:
            def __enter__(self_inner):
                return engine.conn

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        return _Ctx()


def test_audit_log_masks_sensitive_metadata(monkeypatch):
    engine = _FakeEngine()
    monkeypatch.setattr(audit_repository, "postgres_engine", lambda: engine)
    user = CurrentUser(user_id="u1", username="alice", role="admin", permissions=["*"], auth_mode="test")
    ok = audit_repository.write_audit_log(
        action="settings.save",
        user=user,
        resource_type="settings",
        metadata={
            "DATABASE_URL": "postgresql://postgres:secret@127.0.0.1/postgres",
            "Authorization": "Bearer abcdefghijklmn",
            "normal": "value",
        },
    )
    assert ok is True
    metadata = json.loads(engine.conn.params["metadata_json"])
    assert "secret" not in metadata["DATABASE_URL"]
    assert "******" in metadata["DATABASE_URL"]
    assert metadata["Authorization"] == "Bearer ******"
    assert metadata["normal"] == "value"
