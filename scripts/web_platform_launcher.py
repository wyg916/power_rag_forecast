from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote_plus


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"
LOG_DIR = ROOT / "output" / "runtime_logs"
BACKEND_URL = "http://127.0.0.1:8000/api/health"
FRONTEND_URL = "http://127.0.0.1:5173"


def load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and (key not in os.environ or os.environ.get(key, "") == ""):
            os.environ[key] = value


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


def wait_http(url: str, name: str, seconds: int) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if http_ok(url):
            log(f"[OK] {name} is ready: {url}")
            return True
        time.sleep(2)
    log(f"[WARN] {name} is not ready after {seconds}s: {url}")
    return False


def port_pids(port: int) -> list[int]:
    if os.name != "nt":
        return []
    try:
        output = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], text=True, encoding="utf-8", errors="ignore")
    except Exception:
        return []
    pids: set[int] = set()
    suffix = f":{port}"
    for raw_line in output.splitlines():
        columns = raw_line.split()
        if len(columns) < 5:
            continue
        local_address = columns[1]
        state = columns[3].upper()
        pid_text = columns[4]
        if not local_address.endswith(suffix) or state != "LISTENING":
            continue
        try:
            pids.add(int(pid_text))
        except ValueError:
            continue
    return sorted(pids)


def stop_port(port: int, name: str) -> None:
    pids = port_pids(port)
    if not pids:
        return
    current_pid = os.getpid()
    for pid in pids:
        if pid == current_pid:
            continue
        log(f"[INFO] Stop existing {name} process on port {port}, pid={pid}.")
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            log(f"[WARN] Failed to stop pid={pid}: {exc}")
    deadline = time.time() + 12
    while time.time() < deadline and port_open(port, timeout=0.2):
        time.sleep(0.5)


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


def start_backend(py: str, sync: bool, restart: bool = False) -> bool:
    if restart:
        stop_port(8000, "backend")
    if http_ok(BACKEND_URL):
        log("[INFO] Backend is already healthy on port 8000.")
        return True
    if port_open(8000):
        log("[WARN] Port 8000 is open but health check failed. Check output/runtime_logs/web_backend.log.")
        return False
    if sync and not sync_core_data(py):
        return False
    popen_detached([py, "-X", "utf8", "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000"], ROOT, "web_backend.log")
    return wait_http(BACKEND_URL, "Backend", 90)


def ensure_frontend_deps() -> bool:
    if (FRONTEND_DIR / "node_modules").exists():
        return True
    npm = npm_executable()
    if not npm:
        log("[ERROR] npm was not found in PATH.")
        return False
    log("[INFO] node_modules not found. Installing frontend dependencies.")
    result = subprocess.run([npm, "install"], cwd=str(FRONTEND_DIR), text=True)
    if result.returncode != 0:
        log(f"[ERROR] npm install failed, exit code: {result.returncode}")
        return False
    return True

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
            "5173",
            "--directory",
            str(FRONTEND_DIST_DIR),
        ],
        ROOT,
        "web_frontend.log",
    )
    return wait_http(FRONTEND_URL, "Frontend static server", 30)


def start_frontend(py: str, restart: bool = False) -> bool:
    if restart:
        stop_port(5173, "frontend")
    if http_ok(FRONTEND_URL):
        log("[INFO] Frontend is already healthy on port 5173.")
        return True
    if port_open(5173):
        log("[WARN] Port 5173 is open but frontend HTTP check failed. Check output/runtime_logs/web_frontend.log.")
        return False
    npm = npm_executable()
    if not npm:
        return start_static_frontend(py)
    if not ensure_frontend_deps():
        return False
    popen_detached([npm, "run", "dev", "--", "--force"], FRONTEND_DIR, "web_frontend.log")
    return wait_http(FRONTEND_URL, "Frontend", 90)


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
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    ensure_database_url()
    py = python_executable()
    log("[INFO] Power Trading AI Web platform launcher v2.11.2 DB-STATE-V1")
    log(f"[INFO] Python: {py}")
    maybe_check_ollama()

    ok = True
    if not args.frontend_only:
        ok = start_backend(py, sync=not args.skip_sync, restart=args.restart) and ok
    if not args.backend_only:
        ok = start_frontend(py, restart=args.restart) and ok

    if ok:
        log(f"[DONE] Web platform ready: {FRONTEND_URL}")
        if not args.no_browser and not args.backend_only:
            open_browser()
        return 0
    log("[ERROR] Web platform startup did not complete. See output/runtime_logs.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
