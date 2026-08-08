from __future__ import annotations

import importlib.util
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "phase4_precheck_runtime.py"
SPEC = importlib.util.spec_from_file_location("phase4_precheck_runtime", MODULE_PATH)
assert SPEC and SPEC.loader
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


def test_masked_url_never_exposes_credentials():
    masked = runtime.masked_url("redis://user:very-secret@127.0.0.1:6379/3")
    assert "very-secret" not in masked
    assert "user" not in masked
    assert masked == "redis://***@127.0.0.1:6379/3"


def test_health_worker_is_isolated_to_safe_queue(monkeypatch):
    monkeypatch.setenv("PHASE4_CELERY_QUEUE", "phase4_health")
    command = runtime._celery_worker_command()
    joined = " ".join(command)
    assert "--pool=solo" in command
    assert "--concurrency=1" in command
    assert "--queues=phase4_health" in command
    assert "forecast" not in joined
    assert "report" not in joined
    assert "data_sync" not in joined
    assert "embedding" not in joined


def test_runtime_paths_stay_inside_project(monkeypatch):
    monkeypatch.delenv("PHASE4_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("PHASE4_RUNTIME_LOG_DIR", raising=False)
    paths = runtime.runtime_paths()
    for path in paths.values():
        assert path.is_relative_to(ROOT)
        assert path.drive.upper() == "E:"


def test_runtime_helper_adds_project_root_to_import_path():
    assert str(ROOT) in runtime.sys.path


def test_pid_active_recognizes_current_windows_process():
    assert runtime._pid_active(os.getpid()) is True


def test_non_local_redis_target_is_fail_closed():
    assert runtime._local_redis_target("redis://127.0.0.1:6379/0") is True
    assert runtime._local_redis_target("redis://localhost:6379/0") is True
    assert runtime._local_redis_target("redis://redis.example.com:6379/0") is False


def test_docker_command_is_scoped_to_project_compose(monkeypatch):
    monkeypatch.setattr(runtime.shutil, "which", lambda _: "docker")
    monkeypatch.setenv("PHASE4_DOCKER_CONTEXT", "desktop-linux")
    command = runtime._docker_base_command()
    assert command[:3] == ["docker", "--context", "desktop-linux"]
    assert command[3:] == ["compose", "-f", str(ROOT / "docker-compose.yml")]


def test_compose_redis_port_is_loopback_only():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert '127.0.0.1:${REDIS_PORT:-6379}:6379' in compose


def test_explicit_runtime_config_populates_compose_environment(
    monkeypatch, tmp_path
):
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    config = tmp_path / "runtime.env"
    config.write_text("DB_PASSWORD=not-logged\n", encoding="utf-8")

    runtime.configure_runtime([config])

    docker_env = runtime._docker_env()
    assert docker_env["POSTGRES_PASSWORD"] == "not-logged"
    assert docker_env["APP_DB_PASSWORD"] == "not-logged"
    assert docker_env["SECURITY_DB_PASSWORD"] == "not-logged"


def test_missing_explicit_runtime_config_fails_closed(tmp_path):
    missing = tmp_path / "missing.env"

    try:
        runtime.configure_runtime([missing])
    except RuntimeError as exc:
        assert "Runtime config does not exist" in str(exc)
    else:
        raise AssertionError("missing explicit runtime config must fail")
