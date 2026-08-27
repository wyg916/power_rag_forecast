from __future__ import annotations

import argparse
import ctypes
import json
import os
import signal
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote_plus, unquote, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = PROJECT_ROOT / ".codex_tmp" / "rag_release_worker_runtime"
PID_FILE = RUNTIME_ROOT / "worker.json"
TOKEN_FILE = RUNTIME_ROOT / "token.secret"
CLIENT_ENV_FILE = RUNTIME_ROOT / "client.env"
LOG_FILE = PROJECT_ROOT / "output" / "runtime_logs" / "rag_release_worker.log"
HOST = "127.0.0.1"
PORT = 8787
HEALTH_URL = f"http://{HOST}:{PORT}/health"
WORKER_URL = f"http://{HOST}:{PORT}"


def _load_env_file(path: Path, *, required: bool = False) -> None:
    if not path.is_file():
        if required:
            raise RuntimeError(f"Runtime config does not exist: {path}")
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and not os.environ.get(key, ""):
            os.environ[key] = value


def configure_runtime(runtime_configs: Sequence[Path], qdrant_env: Path) -> None:
    for path in runtime_configs:
        _load_env_file(path.resolve(), required=True)
    _load_env_file(PROJECT_ROOT / ".env")
    database_url = (
        os.environ.get("RAG_RELEASE_DATABASE_URL", "").strip()
        or os.environ.get("MIGRATION_DATABASE_URL", "").strip()
    )
    if not database_url and os.environ.get("POSTGRES_USER", "").strip():
        database_url = (
            "postgresql+psycopg://"
            f"{quote_plus(os.environ['POSTGRES_USER'].strip())}:"
            f"{quote_plus(os.environ.get('POSTGRES_PASSWORD', '').strip())}@"
            f"{os.environ.get('POSTGRES_HOST', 'localhost').strip() or 'localhost'}:"
            f"{os.environ.get('POSTGRES_PORT', '5432').strip() or '5432'}/"
            f"{quote_plus(os.environ.get('POSTGRES_DB', 'postgres').strip() or 'postgres')}"
        )
    parsed = urlparse(database_url)
    identity = (
        unquote(parsed.username or ""),
        (parsed.hostname or "").lower(),
        int(parsed.port or 5432),
        unquote(parsed.path.lstrip("/")),
    )
    if identity not in {
        ("postgres", "localhost", 5432, "postgres"),
        ("postgres", "127.0.0.1", 5432, "postgres"),
    }:
        raise RuntimeError("Release worker database target is not the approved local publisher identity")
    qdrant_path = qdrant_env.resolve()
    if not qdrant_path.is_file() or not qdrant_path.is_relative_to(
        Path("E:/智能运营分析项目_运行资产/rag-r1/qdrant/secrets").resolve()
    ):
        raise RuntimeError("Release worker Qdrant config is outside the approved local runtime assets")
    os.environ["RAG_RELEASE_DATABASE_URL"] = database_url
    os.environ["RAG_RELEASE_QDRANT_ENV_FILE"] = str(qdrant_path)


def _pid_active(pid: int) -> bool:
    if pid <= 0 or os.name != "nt":
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel32.GetExitCodeProcess.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    process = kernel32.OpenProcess(0x1000, False, pid)
    if not process:
        return False
    try:
        exit_code = ctypes.c_ulong()
        return bool(
            kernel32.GetExitCodeProcess(process, ctypes.byref(exit_code))
            and exit_code.value == 259
        )
    finally:
        kernel32.CloseHandle(process)


def _read_pid() -> int:
    try:
        return int(json.loads(PID_FILE.read_text(encoding="utf-8")).get("pid") or 0)
    except (OSError, ValueError, json.JSONDecodeError):
        return 0


def _health_ok(timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return response.status == 200 and payload == {"ok": True, "service": "rag_release_worker"}
    except (OSError, TimeoutError, UnicodeError, json.JSONDecodeError, urllib.error.URLError):
        return False


def _port_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.connect((HOST, PORT))
            return True
        except OSError:
            return False


def _token() -> str:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        value = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        value = ""
    if len(value) < 32:
        value = secrets.token_urlsafe(48)
        TOKEN_FILE.write_text(value, encoding="utf-8")
    CLIENT_ENV_FILE.write_text(
        f"RAG_RELEASE_WORKER_URL={WORKER_URL}\nRAG_RELEASE_WORKER_TOKEN={value}\n",
        encoding="utf-8",
    )
    return value


def status() -> dict[str, Any]:
    pid = _read_pid()
    healthy = _health_ok()
    return {
        "ok": bool(pid and _pid_active(pid) and healthy),
        "action": "rag_release_worker_status",
        "pid": pid or None,
        "pid_active": _pid_active(pid),
        "healthy": healthy,
        "url": WORKER_URL,
        "client_env": str(CLIENT_ENV_FILE),
        "log_path": str(LOG_FILE),
    }


def stop() -> dict[str, Any]:
    pid = _read_pid()
    if not pid or not _pid_active(pid):
        return {
            "ok": True,
            "action": "rag_release_worker_stop",
            "pid": pid or None,
            "idempotent": True,
        }
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        return {
            "ok": False,
            "action": "rag_release_worker_stop",
            "pid": pid,
            "error": f"Release worker stop failed: {exc.__class__.__name__}",
        }
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and _pid_active(pid):
        time.sleep(0.25)
    return {
        "ok": not _pid_active(pid),
        "action": "rag_release_worker_stop",
        "pid": pid,
        "idempotent": False,
        "error": "Release worker did not stop" if _pid_active(pid) else "",
    }


def start(python: str) -> dict[str, Any]:
    current = status()
    if current["ok"]:
        _token()
        return {**current, "action": "rag_release_worker_start", "idempotent": True}
    if _port_open():
        return {
            "ok": False,
            "action": "rag_release_worker_start",
            "error": f"Port {PORT} is occupied by an unverified process",
        }
    token = _token()
    env = os.environ.copy()
    env.update(
        {
            "PYTHONUTF8": "1",
            "RAG_RELEASE_WORKER_TOKEN": token,
            "RAG_PROCESS_ROLE": "publisher",
            "RAG_QDRANT_ACCESS_MODE": "admin",
        }
    )
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    creation_flags = (
        getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    with LOG_FILE.open("a", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            [
                python,
                "-X",
                "utf8",
                "-m",
                "uvicorn",
                "backend.app.workers.rag_release_worker_app:app",
                "--host",
                HOST,
                "--port",
                str(PORT),
                "--log-level",
                "info",
            ],
            cwd=PROJECT_ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
            close_fds=True,
        )
    PID_FILE.write_text(
        json.dumps(
            {
                "pid": process.pid,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "url": WORKER_URL,
                "log_path": str(LOG_FILE),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline and _pid_active(process.pid):
        if _health_ok():
            return {**status(), "action": "rag_release_worker_start", "idempotent": False}
        time.sleep(1)
    return {
        "ok": False,
        "action": "rag_release_worker_start",
        "pid": process.pid,
        "error": "Release worker did not become healthy",
        "log_path": str(LOG_FILE),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Local credential-separated RAG release worker controller")
    parser.add_argument("action", choices=("start", "status", "stop"))
    parser.add_argument("--runtime-config", type=Path, action="append", default=[])
    parser.add_argument("--qdrant-env", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == "stop":
            result = stop()
        else:
            configure_runtime(args.runtime_config, args.qdrant_env)
            result = start(sys.executable) if args.action == "start" else status()
    except (OSError, RuntimeError, ValueError) as exc:
        result = {"ok": False, "action": f"rag_release_worker_{args.action}", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
