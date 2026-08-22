from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Sequence
from urllib.parse import quote_plus, unquote, urlparse

try:
    from .rag_r1_runtime_profile_check import (
        RuntimeProfileCheckError,
        merge_runtime_values,
    )
except ImportError:  # pragma: no cover - direct script execution
    from rag_r1_runtime_profile_check import (
        RuntimeProfileCheckError,
        merge_runtime_values,
    )


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"
LOG_DIR = Path(os.environ.get("RUNTIME_LOG_DIR", str(ROOT / "output" / "runtime_logs"))).resolve()


def _configured_port(name: str, default: int) -> int:
    raw_value = os.environ.get(name, str(default)).strip()
    try:
        port = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer port") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError(f"{name} must be between 1 and 65535")
    return port


BACKEND_PORT = _configured_port("WEB_BACKEND_PORT", 8000)
FRONTEND_PORT = _configured_port("WEB_FRONTEND_PORT", 5173)
BACKEND_STARTUP_TIMEOUT = int(os.environ.get("WEB_BACKEND_STARTUP_TIMEOUT", "720"))
FRONTEND_STARTUP_TIMEOUT = int(os.environ.get("WEB_FRONTEND_STARTUP_TIMEOUT", "180"))
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}/api/health"
FRONTEND_URL = f"http://127.0.0.1:{FRONTEND_PORT}"

RAG_RUNTIME_EXPORT_KEYS = frozenset(
    {
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "TOKENIZERS_PARALLELISM",
    }
)


def load_env_file(env_path: Path, *, required: bool = False) -> bool:
    if not env_path.exists():
        if required:
            raise RuntimeError(f"Runtime config does not exist: {env_path}")
        return False
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and (key not in os.environ or os.environ.get(key, "") == ""):
            os.environ[key] = value
    return True


def load_dotenv(runtime_configs: Sequence[Path] | None = None) -> None:
    for runtime_config in runtime_configs or ():
        load_env_file(runtime_config, required=True)
    load_env_file(ROOT / ".env")


def _read_env_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RuntimeError(f"Runtime config does not exist: {path}")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip().strip('"').strip("'")
    return values


def load_enterprise_rag_runtime(qdrant_config: Path, model_config: Path) -> None:
    """Load the API-only RAG profile without exposing the Qdrant admin key."""

    try:
        values = merge_runtime_values(
            _read_env_values(qdrant_config),
            _read_env_values(model_config),
        )
    except RuntimeProfileCheckError as exc:
        raise RuntimeError(f"RAG runtime profile is unavailable: {exc}") from exc
    if "QDRANT_ADMIN_API_KEY" in values:
        raise RuntimeError("RAG runtime profile rejected an admin-key leak")
    exported = {
        key: value
        for key, value in values.items()
        if key.startswith("RAG_") or key in RAG_RUNTIME_EXPORT_KEYS
    }
    if not exported.get("RAG_QDRANT_API_KEY"):
        raise RuntimeError("RAG runtime profile does not contain a read-only API key")
    os.environ.pop("QDRANT_ADMIN_API_KEY", None)
    for key, value in exported.items():
        os.environ[key] = value


def load_rag_reader_env(env_path: Path | None) -> None:
    if env_path is None:
        raise RuntimeError("Approved read-only RAG runtime config was not found")
    values = _read_env_values(env_path)
    if any(key in values for key in ("QDRANT_ADMIN_API_KEY", "QDRANT_ADMIN_KEY")):
        raise RuntimeError("RAG reader config contains an admin credential")
    required = {"QDRANT_API_KEY", "QDRANT_CA_CERT", "QDRANT_URL", "QDRANT_READ_ONLY_API_KEY"}
    if set(values) != required | {
        "RAG_EMBEDDING_DIM", "RAG_EMBEDDING_MODEL", "RAG_QDRANT_COLLECTION",
        "RAG_RELEASE_ID", "RAG_RERANKER_MODEL",
    }:
        raise RuntimeError("RAG reader config key set is invalid")
    if values["QDRANT_API_KEY"] != values["QDRANT_READ_ONLY_API_KEY"]:
        raise RuntimeError("RAG reader key identity mismatch")
    mappings = {
        "RAG_QDRANT_API_KEY": values["QDRANT_API_KEY"],
        "RAG_QDRANT_TLS_CA_PATH": values["QDRANT_CA_CERT"],
        "RAG_QDRANT_URL": values["QDRANT_URL"],
    }
    for key, value in mappings.items():
        os.environ.setdefault(key, value)


def resolve_rag_reader_config(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    configured = os.environ.get("RAG_READER_CONFIG", "").strip()
    if configured:
        return Path(configured).resolve()
    try:
        common_dir = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "--git-common-dir"],
            text=True,
            encoding="utf-8",
            errors="replace",
        ).strip()
        shared_root = (ROOT / common_dir).resolve().parent
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("Git common worktree could not be resolved") from exc
    matches = sorted(
        candidate
        for sibling in shared_root.parent.glob(f"{shared_root.name}_*")
        if (candidate := sibling / "rag-r1" / "performance" / "r3-qdrant-readonly.env").is_file()
    )
    if len(matches) != 1:
        raise RuntimeError(
            "Approved read-only RAG runtime config discovery must resolve exactly one file"
        )
    return matches[0]


def ensure_database_url() -> None:
    os.environ.setdefault("DATABASE_PRIMARY", "postgresql")
    os.environ.setdefault("DATABASE_ALLOW_LEGACY_FALLBACK", "0")
    if os.environ.get("DATABASE_URL", "").strip():
        return
    pg_user = os.environ.get("POSTGRES_USER", "").strip()
    pg_password = os.environ.get("POSTGRES_PASSWORD", "").strip()
    pg_host = os.environ.get("POSTGRES_HOST", "localhost").strip() or "localhost"
    pg_port = os.environ.get("POSTGRES_PORT", "5432").strip() or "5432"
    pg_db = os.environ.get("POSTGRES_DB", "postgres").strip() or "postgres"
    if pg_user:
        os.environ["DATABASE_URL"] = (
            f"postgresql+psycopg://{quote_plus(pg_user)}:{quote_plus(pg_password)}"
            f"@{pg_host}:{pg_port}/{quote_plus(pg_db)}"
        )


def _database_identity(raw_url: str) -> tuple[str, str, int, str] | None:
    try:
        parsed = urlparse(raw_url)
        return (
            unquote(parsed.username or ""),
            (parsed.hostname or "").lower(),
            int(parsed.port or 5432),
            unquote(parsed.path.lstrip("/")),
        )
    except (TypeError, ValueError):
        return None


def validate_database_target() -> bool:
    raw_url = os.environ.get("DATABASE_URL", "").strip()
    security_url = os.environ.get("SECURITY_DATABASE_URL", "").strip()
    if not raw_url or not security_url:
        log(
            "[ERROR] DATABASE_URL and SECURITY_DATABASE_URL are both required "
            "for the unified RC launcher."
        )
        return False
    runtime_identity = _database_identity(raw_url)
    security_identity = _database_identity(security_url)
    if runtime_identity is None or security_identity is None:
        log("[ERROR] Database identity target cannot be parsed.")
        return False
    approved = (
        ("beta10d_app_login", "localhost", 5432, "postgres"),
        ("beta10d_security_login", "localhost", 5432, "postgres"),
    )
    normalized_runtime = (
        runtime_identity[0],
        "localhost" if runtime_identity[1] == "127.0.0.1" else runtime_identity[1],
        runtime_identity[2],
        runtime_identity[3],
    )
    normalized_security = (
        security_identity[0],
        "localhost" if security_identity[1] == "127.0.0.1" else security_identity[1],
        security_identity[2],
        security_identity[3],
    )
    if (normalized_runtime, normalized_security) != approved:
        log(
            "[ERROR] Database identities rejected; expected local least-privilege "
            "runtime and security identities."
        )
        return False
    if raw_url == security_url:
        log("[ERROR] Runtime and security database identities must remain separated.")
        return False
    log(
        "[OK] Database identities: beta10d_app_login + beta10d_security_login "
        "@localhost:5432/postgres (credentials hidden)."
    )
    return True


def git_identity() -> tuple[str, str]:
    try:
        branch = subprocess.check_output(
            ["git", "-C", str(ROOT), "branch", "--show-current"],
            text=True,
            encoding="utf-8",
            errors="replace",
        ).strip()
        sha = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            text=True,
            encoding="utf-8",
            errors="replace",
        ).strip()
        return branch, sha
    except (OSError, subprocess.SubprocessError):
        return "unknown", "unknown"


def alembic_heads(py: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [py, "-X", "utf8", "-m", "alembic", "heads"],
            cwd=str(ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, exc.__class__.__name__
    heads = [line.strip() for line in result.stdout.splitlines() if "(head)" in line]
    if result.returncode != 0 or len(heads) != 1:
        return False, "; ".join(heads) or "unavailable"
    return True, heads[0].removesuffix(" (head)").strip()


def log(message: str) -> None:
    print(message, flush=True)


def python_executable() -> str:
    configured = os.environ.get("PYTHON_EXE", "").strip()
    if configured:
        if Path(configured).exists():
            return configured
        resolved = shutil.which(configured)
        if resolved:
            return resolved
    return sys.executable or shutil.which("python") or "python"


def npm_executable() -> str | None:
    configured = os.environ.get("NPM_EXE", "").strip()
    if configured and Path(configured).exists():
        return configured
    for candidate in [
        shutil.which("npm.cmd"),
        shutil.which("npm"),
        os.environ.get("APPDATA", "") and str(Path(os.environ["APPDATA"]) / "npm" / "npm.cmd"),
        os.environ.get("ProgramFiles", "") and str(Path(os.environ["ProgramFiles"]) / "nodejs" / "npm.cmd"),
        os.environ.get("ProgramFiles(x86)", "") and str(Path(os.environ["ProgramFiles(x86)"]) / "nodejs" / "npm.cmd"),
    ]:
        if candidate and Path(candidate).exists():
            return str(candidate)
    node_home = os.environ.get("NODE_HOME", "").strip()
    if node_home:
        candidate = Path(node_home) / "npm.cmd"
        if candidate.exists():
            return str(candidate)
    return None


def port_open(port: int, timeout: float = 0.8) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect(("127.0.0.1", port))
            return True
        except OSError:
            return False


def http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= int(response.status) < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def backend_http_ok(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(BACKEND_URL, timeout=timeout) as response:
            if not 200 <= int(response.status) < 500:
                return False
            payload = json.loads(response.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, urllib.error.URLError, TimeoutError, OSError):
        return False
    if not bool(payload.get("ok")):
        return False
    prewarm_required = os.environ.get("RAG_PREWARM_ON_STARTUP", "0").strip().lower() in {
        "1", "true", "yes", "on",
    }
    if not prewarm_required:
        return True
    warmup = payload.get("rag_runtime_warmup") or {}
    return bool(warmup.get("required")) and warmup.get("status") == "ready"


def wait_http(url: str, name: str, seconds: int) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if http_ok(url):
            log(f"[OK] {name} is ready: {url}")
            return True
        time.sleep(2)
    log(f"[WARN] {name} is not ready after {seconds}s: {url}")
    return False


def wait_backend_ready(seconds: int) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if backend_http_ok():
            log(f"[OK] Backend is ready with required RAG warmup: {BACKEND_URL}")
            return True
        time.sleep(2)
    log(f"[WARN] Backend is not ready after {seconds}s: {BACKEND_URL}")
    return False


def popen_detached(args: list[str], cwd: Path, log_name: str) -> subprocess.Popen:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / log_name
    stdout = open(log_path, "a", encoding="utf-8", errors="replace")
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env.setdefault("AUTH_REQUIRED", "0")
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    log(f"[INFO] Start process: {' '.join(args)}")
    log(f"[INFO] Log file: {log_path}")
    return subprocess.Popen(args, cwd=str(cwd), env=env, stdout=stdout, stderr=subprocess.STDOUT, creationflags=flags)


def sync_core_data(py: str) -> bool:
    if os.environ.get("SKIP_CORE_SYNC", "0") == "1":
        log("[INFO] SKIP_CORE_SYNC=1, skip core data sync.")
        return True
    log("[INFO] Sync core facts, tariff rules and policy summaries.")
    result = subprocess.run([py, "-X", "utf8", str(ROOT / "13_sync_core_data_to_db.py")], cwd=str(ROOT), text=True)
    if result.returncode != 0:
        log(f"[ERROR] Core data sync failed, exit code: {result.returncode}")
        return False
    return True


def start_backend(py: str, sync: bool) -> bool:
    if backend_http_ok():
        log(f"[INFO] Backend is already healthy on port {BACKEND_PORT}.")
        return True
    if port_open(BACKEND_PORT):
        log(
            f"[WARN] Port {BACKEND_PORT} is open but health check failed. "
            "Check output/runtime_logs/web_backend.log."
        )
        return False
    if sync and not sync_core_data(py):
        return False
    popen_detached(
        [
            py,
            "-X",
            "utf8",
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--app-dir",
            str(ROOT),
            "--host",
            "127.0.0.1",
            "--port",
            str(BACKEND_PORT),
            "--log-level",
            os.environ.get("WEB_BACKEND_LOG_LEVEL", "info"),
        ],
        ROOT,
        "web_backend.log",
    )
    return wait_backend_ready(BACKEND_STARTUP_TIMEOUT)


def ensure_frontend_deps() -> bool:
    if (FRONTEND_DIR / "node_modules").exists():
        return True
    log("[ERROR] frontend/node_modules was not found.")
    log(
        "[TIP] Provision or reuse approved dependencies explicitly; "
        "automatic network installation is disabled."
    )
    return False


def start_static_frontend(py: str) -> bool:
    index_file = FRONTEND_DIST_DIR / "index.html"
    if not index_file.exists():
        log("[ERROR] npm was not found and frontend/dist/index.html does not exist.")
        log("[TIP] Install Node.js 20+ and make npm available in PATH, or run npm build once to create frontend/dist.")
        return False
    log("[WARN] npm was not found. Falling back to built frontend/dist static server.")
    popen_detached(
        [
            py,
            "-X",
            "utf8",
            str(ROOT / "scripts" / "spa_static_server.py"),
            "--host",
            "127.0.0.1",
            "--port",
            str(FRONTEND_PORT),
            "--directory",
            str(FRONTEND_DIST_DIR),
        ],
        ROOT,
        "web_frontend.log",
    )
    return wait_http(FRONTEND_URL, "Frontend static server", 30)


def start_frontend(py: str) -> bool:
    if http_ok(FRONTEND_URL):
        log(f"[INFO] Frontend is already healthy on port {FRONTEND_PORT}.")
        return True
    if port_open(FRONTEND_PORT):
        log(
            f"[WARN] Port {FRONTEND_PORT} is open but frontend HTTP check failed. "
            "Check output/runtime_logs/web_frontend.log."
        )
        return False
    npm = npm_executable()
    if not npm:
        return start_static_frontend(py)
    if not ensure_frontend_deps():
        return False
    os.environ.setdefault(
        "VITE_API_PROXY_TARGET", f"http://127.0.0.1:{BACKEND_PORT}"
    )
    popen_detached(
        [
            npm,
            "run",
            "dev",
            "--",
            "--force",
            "--host",
            "127.0.0.1",
            "--port",
            str(FRONTEND_PORT),
        ],
        FRONTEND_DIR,
        "web_frontend.log",
    )
    return wait_http(FRONTEND_URL, "Frontend", FRONTEND_STARTUP_TIMEOUT)


def maybe_check_ollama() -> None:
    if os.environ.get("START_OLLAMA", "0") != "1":
        log("[INFO] START_OLLAMA is not 1; skip Ollama startup/warmup to keep low-memory startup stable.")
        return
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as response:
            log(f"[OK] Ollama API reachable, status={response.status}.")
    except Exception as exc:
        log(f"[WARN] Ollama API is not reachable: {exc}. Continue without local model warmup.")


def open_browser() -> None:
    try:
        if os.name == "nt":
            os.startfile(FRONTEND_URL)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["python", "-m", "webbrowser", FRONTEND_URL])
    except Exception as exc:
        log(f"[WARN] Failed to open browser automatically: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-only", action="store_true")
    parser.add_argument("--frontend-only", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--skip-sync", action="store_true")
    parser.add_argument("--runtime-config", type=Path, action="append")
    parser.add_argument("--rag-qdrant-config", type=Path)
    parser.add_argument("--rag-model-config", type=Path)
    parser.add_argument("--rag-reader-config", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    try:
        load_dotenv(
            [path.resolve() for path in args.runtime_config]
            if args.runtime_config
            else None
        )
        if bool(args.rag_qdrant_config) != bool(args.rag_model_config):
            raise RuntimeError(
                "--rag-qdrant-config and --rag-model-config must be provided together"
            )
        if args.rag_qdrant_config and args.rag_model_config:
            load_enterprise_rag_runtime(
                args.rag_qdrant_config.resolve(),
                args.rag_model_config.resolve(),
            )
        else:
            load_rag_reader_env(resolve_rag_reader_config(args.rag_reader_config))
    except (OSError, RuntimeError) as exc:
        log(f"[ERROR] Runtime configuration failed: {exc}")
        return 2
    ensure_database_url()
    py = python_executable()
    branch, sha = git_identity()
    log("[INFO] Power Trading AI unified RC launcher v2.11.2")
    log(f"[INFO] RC branch: {branch}")
    log(f"[INFO] RC SHA: {sha}")
    log(f"[INFO] Python: {py}")
    if not validate_database_target():
        return 2
    heads_ok, head = alembic_heads(py)
    if not heads_ok:
        log(f"[ERROR] Alembic head preflight failed: {head}")
        return 2
    log(f"[OK] Alembic head: {head}")
    if args.preflight_only:
        log("[DONE] Unified RC launcher preflight passed; no service was started.")
        return 0
    maybe_check_ollama()

    ok = True
    if not args.frontend_only:
        ok = start_backend(py, sync=not args.skip_sync) and ok
    if not args.backend_only:
        ok = start_frontend(py) and ok

    if ok:
        log(f"[DONE] Web platform ready: {FRONTEND_URL}")
        if not args.no_browser and not args.backend_only:
            open_browser()
        return 0
    log("[ERROR] Web platform startup did not complete. See output/runtime_logs.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
