from __future__ import annotations

from scripts import runtime_control


def test_same_recorded_process_requires_pid_and_creation_identity() -> None:
    recorded = {"pid": 101, "created": "created-1", "managed": True}

    assert runtime_control._same_recorded_process(
        recorded, {"pid": 101, "created": "created-1"}
    )
    assert not runtime_control._same_recorded_process(
        recorded, {"pid": 101, "created": "created-2"}
    )
    assert not runtime_control._same_recorded_process(
        recorded, {"pid": 202, "created": "created-1"}
    )


def test_second_start_preserves_controller_ownership(
    monkeypatch, tmp_path
) -> None:
    previous_state = {
        "working_directory": str(runtime_control.ROOT),
        "log_path": str(tmp_path / "first"),
        "services": {
            "backend": {
                "pid": 101,
                "created": "created-backend",
                "managed": True,
            },
            "frontend": {
                "pid": 202,
                "created": "created-frontend",
                "managed": True,
            },
            "celery": {
                "pid": 303,
                "created": "created-celery",
                "managed": True,
            },
        },
    }
    services = {
        "backend": {
            "pid": 101,
            "created": "created-backend",
            "health": "healthy",
            "port": 18084,
            "source_owned": True,
        },
        "frontend": {
            "pid": 202,
            "created": "created-frontend",
            "health": "healthy",
            "port": 15184,
            "source_owned": True,
        },
        "celery": {
            "pid": 303,
            "created": "created-celery",
            "health": "running",
            "source_owned": False,
        },
    }
    statuses = [
        {"services": services, "log_path": str(tmp_path / "first")},
        {"services": services, "log_path": str(tmp_path / "first")},
    ]
    written: list[dict[str, object]] = []

    monkeypatch.setattr(runtime_control, "LOG_ROOT", tmp_path)
    monkeypatch.setattr(runtime_control, "_read_state", lambda: previous_state)
    monkeypatch.setattr(runtime_control, "status", lambda **_: statuses.pop(0))
    monkeypatch.setattr(
        runtime_control,
        "_runtime_files",
        lambda: [tmp_path / "profile.env"],
    )
    monkeypatch.setattr(
        runtime_control,
        "_run",
        lambda *_, **__: type("Result", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(runtime_control, "_write_state", written.append)
    monkeypatch.setattr(
        runtime_control,
        "_identity",
        lambda: {
            "branch": "codex/test",
            "sha": "a" * 40,
            "tag": "none",
            "working_directory": str(runtime_control.ROOT),
        },
    )

    assert runtime_control.start(debug=False, silent=True) == 0
    assert written
    assert all(
        item["managed"]
        for item in written[0]["services"].values()  # type: ignore[index,union-attr]
    )


def test_process_from_other_worktree_is_not_adopted(monkeypatch) -> None:
    monkeypatch.setattr(runtime_control, "ROOT", runtime_control.ROOT)
    state = {
        "working_directory": str(runtime_control.ROOT.parent / "other"),
        "services": {},
    }

    assert not runtime_control._state_belongs_to_this_worktree(state)
