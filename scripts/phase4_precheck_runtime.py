from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"
DEFAULT_QUEUE = "phase4_health"
DOCKER_TIMEOUT_SECONDS = 20
WORKER_START_TIMEOUT_SECONDS = 60
HEALTH_TASK_TIMEOUT_SECONDS = 30


def _resolve_project_path(env_name: str, default: str) -> Path:
    raw = os.environ.get(env_name, default).strip() or default
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def runtime_paths() -> dict[str, Path]:
    runtime_dir = _resolve_project_path("PHASE4_RUNTIME_DIR", ".codex_tmp/phase4_runtime")
    log_dir = _resolve_project_path("PHASE4_RUNTIME_LOG_DIR", "output/runtime_logs/phase4")
    return {
        "runtime_dir": runtime_dir,
        "log_dir": log_dir,
        "pid_file": runtime_dir / "celery_health_worker.json",
        "worker_log": log_dir / "celery_health_worker.log",
    }


def runtime_temp_dir() -> Path:
    path = _resolve_project_path("PHASE4_TEMP_DIR", ".codex_tmp/phase4_runtime_tmp")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_project_env() -> None:
    try:
        from config_loader import load_dotenv

        load_dotenv()
    except Exception:
        return


def redis_url() -> str:
    _load_project_env()
    return (
        os.environ.get("REDIS_URL")
        or os.environ.get("CELERY_BROKER_URL")
        or DEFAULT_REDIS_URL
    ).strip()


def celery_queue() -> str:
    return os.environ.get("PHASE4_CELERY_QUEUE", DEFAULT_QUEUE).strip() or DEFAULT_QUEUE


def masked_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        credentials = "***@" if parsed.username or parsed.password else ""
        return urlunsplit((parsed.scheme, f"{credentials}{hostname}{port}", parsed.path, "", ""))
    except Exception:
        return "<configured>"


def _json_result(ok: bool, action: str, **details: Any) -> dict[str, Any]:
    return {
        "ok": ok,
        "action": action,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        **details,
    }


def _emit(result: dict[str, Any]) -> int:
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 1


def _redis_connection_parts(value: str) -> tuple[str, int]:
    parsed = urlsplit(value)
    host = parsed.hostname or "127.0.0.1"
    port = int(parsed.port or 6379)
    return host, port


def _local_redis_target(value: str) -> bool:
    host, _ = _redis_connection_parts(value)
    return host.lower() in {"127.0.0.1", "localhost", "::1"}


def _port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def redis_ping(value: str | None = None) -> dict[str, Any]:
    target = (value or redis_url()).strip()
    try:
        import redis

        client = redis.Redis.from_url(
            target,
            socket_connect_timeout=0.8,
            socket_timeout=0.8,
            health_check_interval=10,
        )
        started = time.perf_counter()
        pong = bool(client.ping())
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return _json_result(
            pong,
            "redis_ping",
            redis_url=masked_url(target),
            latency_ms=latency_ms,
            status="connected" if pong else "unexpected_response",
        )
    except Exception as exc:
        return _json_result(
            False,
            "redis_ping",
            redis_url=masked_url(target),
            status="unavailable",
            error_type=exc.__class__.__name__,
            error=str(exc)[:240],
        )


def _docker_base_command() -> list[str]:
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("Docker CLI is not available.")
    context = os.environ.get("PHASE4_DOCKER_CONTEXT", "desktop-linux").strip()
    command = [docker]
    if context:
        command.extend(["--context", context])
    command.extend(["compose", "-f", str(PROJECT_ROOT / "docker-compose.yml")])
    return command


def _docker_env() -> dict[str, str]:
    env = os.environ.copy()
    temp_dir = str(runtime_temp_dir())
    env.setdefault("JWT_SECRET_KEY", "phase4_precheck_compose_interpolation_only")
    env.setdefault("ADMIN_INITIALIZED", "1")
    env["TEMP"] = temp_dir
    env["TMP"] = temp_dir
    return env


def _run_docker(arguments: list[str], timeout: int = DOCKER_TIMEOUT_SECONDS) -> dict[str, Any]:
    command = [*_docker_base_command(), *arguments]
    try:
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            env=_docker_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=5,
                check=False,
            )
            return {
                "ok": False,
                "returncode": 124,
                "stdout": "",
                "stderr": f"Docker command timed out after {timeout}s and its CLI process tree was terminated.",
                "command_scope": "docker compose redis service only",
            }
        return {
            "ok": process.returncode == 0,
            "returncode": process.returncode,
            "stdout": stdout.strip()[-2000:],
            "stderr": stderr.strip()[-2000:],
            "command_scope": "docker compose redis service only",
        }
    except Exception as exc:
        return {
            "ok": False,
            "returncode": 1,
            "stdout": "",
            "stderr": str(exc)[:500],
            "command_scope": "docker compose redis service only",
        }


def redis_start() -> dict[str, Any]:
    target = redis_url()
    if not _local_redis_target(target):
        return _json_result(
            False,
            "redis_start",
            redis_url=masked_url(target),
            error="Refusing to start a local container for a non-local Redis URL.",
        )
    initial = redis_ping(target)
    if initial["ok"]:
        return _json_result(
            True,
            "redis_start",
            idempotent=True,
            redis_url=masked_url(target),
            ping=initial,
        )
    host, port = _redis_connection_parts(target)
    if _port_open(host, port):
        return _json_result(
            False,
            "redis_start",
            redis_url=masked_url(target),
            error=f"Port {host}:{port} is occupied but does not answer Redis PING.",
        )
    docker_result = _run_docker(["up", "-d", "redis"])
    if not docker_result["ok"]:
        return _json_result(
            False,
            "redis_start",
            redis_url=masked_url(target),
            docker=docker_result,
            error="Docker Redis could not be started.",
        )
    deadline = time.monotonic() + 35
    latest = redis_ping(target)
    while not latest["ok"] and time.monotonic() < deadline:
        time.sleep(1)
        latest = redis_ping(target)
    return _json_result(
        bool(latest["ok"]),
        "redis_start",
        idempotent=False,
        redis_url=masked_url(target),
        docker=docker_result,
        ping=latest,
    )


def redis_stop() -> dict[str, Any]:
    target = redis_url()
    if not _local_redis_target(target):
        return _json_result(
            False,
            "redis_stop",
            redis_url=masked_url(target),
            error="Refusing to stop infrastructure for a non-local Redis URL.",
        )
    docker_result = _run_docker(["stop", "redis"])
    if not docker_result["ok"]:
        return _json_result(
            False,
            "redis_stop",
            redis_url=masked_url(target),
            docker=docker_result,
        )
    deadline = time.monotonic() + 15
    latest = redis_ping(target)
    while latest["ok"] and time.monotonic() < deadline:
        time.sleep(0.5)
        latest = redis_ping(target)
    return _json_result(
        not latest["ok"],
        "redis_stop",
        redis_url=masked_url(target),
        docker=docker_result,
        ping_after_stop=latest,
        volume_preserved=True,
    )


def redis_status() -> dict[str, Any]:
    target = redis_url()
    docker_result = _run_docker(["ps", "--all", "redis"], timeout=8)
    ping = redis_ping(target)
    return _json_result(
        bool(ping["ok"]),
        "redis_status",
        redis_url=masked_url(target),
        ping=ping,
        docker=docker_result,
    )


def _celery_worker_command() -> list[str]:
    return [
        sys.executable,
        "-X",
        "utf8",
        "-m",
        "celery",
        "-A",
        "backend.app.workers.celery_app:celery_app",
        "worker",
        "--pool=solo",
        "--concurrency=1",
        "--loglevel=INFO",
        f"--queues={celery_queue()}",
        "--hostname=phase4-health@%h",
        "--without-gossip",
        "--without-mingle",
    ]


def _worker_env() -> dict[str, str]:
    target = redis_url()
    temp_dir = str(runtime_temp_dir())
    env = os.environ.copy()
    env.update(
        {
            "PYTHONUTF8": "1",
            "TEMP": temp_dir,
            "TMP": temp_dir,
            "REDIS_URL": target,
            "CELERY_BROKER_URL": os.environ.get("CELERY_BROKER_URL", target),
            "CELERY_RESULT_BACKEND": os.environ.get("CELERY_RESULT_BACKEND", target),
            "TASK_EXECUTION_MODE": "celery",
        }
    )
    return env


def _read_pid_record() -> dict[str, Any]:
    path = runtime_paths()["pid_file"]
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _pid_active(pid: int) -> bool:
    if pid <= 0:
        return False
    process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not process:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetExitCodeProcess(process, ctypes.byref(exit_code)):
            return False
        return exit_code.value == 259
    finally:
        ctypes.windll.kernel32.CloseHandle(process)


def _inspect_health_workers(timeout: float = 5.0) -> list[str]:
    try:
        from backend.app.workers.celery_app import celery_app

        if celery_app is None:
            return []
        expected = f"phase4-health@{socket.gethostname()}"
        responses = celery_app.control.ping(destination=[expected], timeout=timeout) or []
        names = {
            name
            for response in responses
            for name in response
            if name.startswith("phase4-health@")
        }
        return sorted(names)
    except Exception:
        return []


def celery_status() -> dict[str, Any]:
    record = _read_pid_record()
    pid = int(record.get("pid") or 0)
    workers = _inspect_health_workers()
    redis_result = redis_ping()
    ok = bool(pid and _pid_active(pid) and workers and redis_result["ok"])
    return _json_result(
        ok,
        "celery_status",
        pid=pid or None,
        pid_active=_pid_active(pid),
        workers=workers,
        queue=celery_queue(),
        redis=redis_result,
        log_path=str(runtime_paths()["worker_log"]),
    )


def celery_start() -> dict[str, Any]:
    paths = runtime_paths()
    paths["runtime_dir"].mkdir(parents=True, exist_ok=True)
    paths["log_dir"].mkdir(parents=True, exist_ok=True)
    redis_result = redis_ping()
    if not redis_result["ok"]:
        return _json_result(
            False,
            "celery_start",
            redis=redis_result,
            error="Redis is unavailable; worker start is fail-closed.",
        )
    existing = celery_status()
    if existing["ok"]:
        return _json_result(True, "celery_start", idempotent=True, status=existing)

    command = _celery_worker_command()
    creation_flags = (
        getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    with paths["worker_log"].open("a", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            env=_worker_env(),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
            close_fds=True,
        )
    record = {
        "pid": process.pid,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "queue": celery_queue(),
        "log_path": str(paths["worker_log"]),
        "python": sys.executable,
    }
    paths["pid_file"].write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    deadline = time.monotonic() + WORKER_START_TIMEOUT_SECONDS
    workers: list[str] = []
    while time.monotonic() < deadline and _pid_active(process.pid):
        workers = _inspect_health_workers()
        if workers:
            break
        time.sleep(1)
    return _json_result(
        bool(workers and _pid_active(process.pid)),
        "celery_start",
        idempotent=False,
        pid=process.pid,
        pid_active=_pid_active(process.pid),
        workers=workers,
        queue=celery_queue(),
        pool="solo",
        concurrency=1,
        log_path=str(paths["worker_log"]),
        consumes_business_queues=False,
    )


def celery_health_task() -> dict[str, Any]:
    status = celery_status()
    if not status["ok"]:
        return _json_result(False, "celery_health_task", status=status, error="Health worker is unavailable.")
    try:
        from backend.app.workers.tasks import health_check_task

        async_result = health_check_task.apply_async(queue=celery_queue())
        payload = async_result.get(timeout=HEALTH_TASK_TIMEOUT_SECONDS)
        return _json_result(
            async_result.state == "SUCCESS",
            "celery_health_task",
            task_id=async_result.id,
            state=async_result.state,
            result=payload,
            result_backend_queryable=True,
            queue=celery_queue(),
        )
    except Exception as exc:
        return _json_result(
            False,
            "celery_health_task",
            error_type=exc.__class__.__name__,
            error=str(exc)[:500],
            queue=celery_queue(),
        )


def _terminate_pid(pid: int) -> bool:
    if not _pid_active(pid):
        return True
    try:
        os.kill(pid, signal.CTRL_BREAK_EVENT)
    except Exception:
        pass
    deadline = time.monotonic() + 8
    while _pid_active(pid) and time.monotonic() < deadline:
        time.sleep(0.25)
    if not _pid_active(pid):
        return True
    handle = ctypes.windll.kernel32.OpenProcess(0x0001 | 0x00100000, False, pid)
    if not handle:
        return False
    try:
        ctypes.windll.kernel32.TerminateProcess(handle, 0)
        ctypes.windll.kernel32.WaitForSingleObject(handle, 5000)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)
    return not _pid_active(pid)


def celery_stop() -> dict[str, Any]:
    paths = runtime_paths()
    record = _read_pid_record()
    pid = int(record.get("pid") or 0)
    workers = _inspect_health_workers()
    if workers:
        try:
            from backend.app.workers.celery_app import celery_app

            celery_app.control.broadcast("shutdown", destination=workers)
        except Exception:
            pass
    deadline = time.monotonic() + 12
    while pid and _pid_active(pid) and time.monotonic() < deadline:
        time.sleep(0.25)
    stopped = True if not pid else _terminate_pid(pid)
    remaining = _inspect_health_workers()
    return _json_result(
        bool(stopped and not remaining),
        "celery_stop",
        pid=pid or None,
        pid_active=_pid_active(pid),
        remaining_workers=remaining,
        orphan_process=False if stopped and not remaining else "unknown",
        pid_file_preserved=str(paths["pid_file"]),
    )


def combined_health() -> dict[str, Any]:
    redis_result = redis_ping()
    if not redis_result["ok"]:
        return _json_result(False, "combined_health", redis=redis_result, celery=None)
    celery_result = celery_health_task()
    return _json_result(
        bool(redis_result["ok"] and celery_result["ok"]),
        "combined_health",
        redis=redis_result,
        celery=celery_result,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="PHASE4-PRECHECK Redis/Celery local runtime helper")
    parser.add_argument("component", choices=["redis", "celery", "combined"])
    parser.add_argument("action", choices=["start", "stop", "status", "ping", "health"])
    parser.add_argument("--url", default="", help="Optional Redis URL for ping/fail-closed verification.")
    args = parser.parse_args()

    if args.component == "redis":
        actions = {
            "start": redis_start,
            "stop": redis_stop,
            "status": redis_status,
            "ping": lambda: redis_ping(args.url or None),
            "health": lambda: redis_ping(args.url or None),
        }
    elif args.component == "celery":
        actions = {
            "start": celery_start,
            "stop": celery_stop,
            "status": celery_status,
            "ping": celery_status,
            "health": celery_health_task,
        }
    else:
        actions = {
            "start": lambda: _json_result(False, "combined_start", error="Start Redis and Celery explicitly."),
            "stop": lambda: _json_result(False, "combined_stop", error="Stop Celery and Redis explicitly."),
            "status": lambda: _json_result(
                redis_ping()["ok"] and celery_status()["ok"],
                "combined_status",
                redis=redis_ping(),
                celery=celery_status(),
            ),
            "ping": combined_health,
            "health": combined_health,
        }
    return _emit(actions[args.action]())


if __name__ == "__main__":
    raise SystemExit(main())
