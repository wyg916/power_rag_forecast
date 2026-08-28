from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".codex_tmp" / "runtime_control"
STATE_FILE = STATE_DIR / "state.json"
LOG_ROOT = ROOT / "logs" / "runtime"


def _run(args: list[str], *, check: bool = True, env: dict[str, str] | None = None, stdout=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=ROOT, env=env, check=check, text=True, encoding="utf-8", errors="replace",
        stdout=stdout if stdout is not None else subprocess.PIPE,
        stderr=subprocess.STDOUT if stdout is not None else subprocess.PIPE,
    )


def _git(*args: str, allow_failure: bool = False) -> str:
    result = _run(["git", "-C", str(ROOT), *args], check=not allow_failure)
    return (result.stdout or "").strip()


def _identity() -> dict[str, str]:
    return {
        "branch": _git("branch", "--show-current"),
        "sha": _git("rev-parse", "HEAD"),
        "tag": _git("describe", "--tags", "--exact-match", allow_failure=True) or "none",
        "working_directory": str(ROOT),
    }


def _shared_root() -> Path:
    common = Path(_git("rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = (ROOT / common).resolve()
    return common.parent.resolve()


def _runtime_files() -> list[Path]:
    shared = _shared_root()
    return [
        ROOT / "deploy" / "rag-r1" / "preproduction-profile.env",
        Path(f"{shared}_本地配置") / "beta10d_day4_runtime.env",
        ROOT / ".env" if (ROOT / ".env").is_file() else shared / ".env",
    ]


def _web_launcher_command(
    configs: list[Path], *, suppress_browser: bool
) -> list[str]:
    common = [
        item for path in configs for item in ("--runtime-config", str(path))
    ]
    command = [
        sys.executable,
        "-X",
        "utf8",
        str(ROOT / "scripts" / "web_platform_launcher.py"),
        *common,
        "--skip-sync",
    ]
    if suppress_browser:
        command.append("--no-browser")
    return command


def _port_info(port: int) -> dict[str, Any]:
    if os.name != "nt":
        return {"port": port, "pid": None, "health": "unsupported_platform"}
    script = (
        f"$c=Get-NetTCPConnection -State Listen -LocalPort {port} -ErrorAction SilentlyContinue | Select-Object -First 1;"
        "if($c){$p=Get-CimInstance Win32_Process -Filter \"ProcessId=$($c.OwningProcess)\";"
        "[pscustomobject]@{pid=$c.OwningProcess;name=$p.Name;path=$p.ExecutablePath;command_line=$p.CommandLine;created=$p.CreationDate}|ConvertTo-Json -Compress}"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script], capture_output=True,
        text=True, encoding="utf-8", errors="replace", check=False,
    )
    if not result.stdout.strip():
        return {"port": port, "pid": None, "health": "stopped", "source_owned": False}
    payload = json.loads(result.stdout)
    command = str(payload.get("command_line") or "")
    return {
        "port": port, "pid": int(payload.get("pid") or 0) or None,
        "process": payload.get("name"), "path": payload.get("path"),
        "command_line": command, "created": str(payload.get("created") or ""),
        "source_owned": str(ROOT).lower() in command.lower(), "health": "listening",
    }


def _pid_info(pid: int) -> dict[str, Any]:
    if os.name != "nt" or pid <= 0:
        return {"pid": pid or None, "health": "stopped", "source_owned": False}
    script = (
        f"$p=Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\" -ErrorAction SilentlyContinue;"
        "if($p){[pscustomobject]@{pid=$p.ProcessId;name=$p.Name;path=$p.ExecutablePath;command_line=$p.CommandLine;created=$p.CreationDate}|ConvertTo-Json -Compress}"
    )
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not result.stdout.strip():
        return {"pid": None, "health": "stopped", "source_owned": False}
    payload = json.loads(result.stdout)
    command = str(payload.get("command_line") or "")
    return {
        "pid": pid, "process": payload.get("name"), "path": payload.get("path"),
        "command_line": command, "created": str(payload.get("created") or ""),
        "source_owned": str(ROOT).lower() in command.lower(), "health": "running",
    }


def _http_health(port: int, path: str) -> str:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as response:
            return "healthy" if 200 <= response.status < 500 else f"http_{response.status}"
    except Exception:
        return "unavailable"


def _read_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_state(payload: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(STATE_FILE)


def _state_belongs_to_this_worktree(state: dict[str, Any]) -> bool:
    try:
        return Path(str(state.get("working_directory") or "")).resolve() == ROOT
    except OSError:
        return False


def _same_recorded_process(recorded: dict[str, Any], current: dict[str, Any]) -> bool:
    return bool(
        recorded.get("pid")
        and recorded.get("pid") == current.get("pid")
        and recorded.get("created")
        and recorded.get("created") == current.get("created")
    )


def status(*, as_json: bool = False) -> dict[str, Any]:
    backend_port = int(os.environ.get("WEB_BACKEND_PORT", "8000"))
    frontend_port = int(os.environ.get("WEB_FRONTEND_PORT", "5173"))
    state = _read_state()
    services = {
        "backend": {**_port_info(backend_port), "health": _http_health(backend_port, "/api/health")},
        "frontend": {**_port_info(frontend_port), "health": _http_health(frontend_port, "/")},
    }
    try:
        celery_pid = int(json.loads((STATE_DIR.parent / "phase4_runtime" / "celery_health_worker.json").read_text(encoding="utf-8")).get("pid") or 0)
    except (OSError, ValueError):
        celery_pid = 0
    services["celery"] = _pid_info(celery_pid)
    payload = {
        **_identity(), "action": "status", "services": services,
        "log_path": state.get("log_path") or "none",
        "visible_consoles": state.get("visible_consoles", 1),
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for key in ("branch", "sha", "tag", "working_directory", "log_path"):
            print(f"{key}={payload[key]}")
        for name, item in services.items():
            print(f"{name}: PID={item.get('pid')} port={item.get('port')} health={item['health']} source_owned={item.get('source_owned')}")
    return payload


def doctor(*, as_json: bool = False) -> int:
    files = _runtime_files()
    checks = {
        "git_root_exact": Path(_git("rev-parse", "--show-toplevel")).resolve() == ROOT,
        "python_exists": Path(sys.executable).is_file(),
        "runtime_configs_exist": all(path.is_file() for path in files),
        "frontend_dependencies_exist": (ROOT / "frontend" / "node_modules").is_dir(),
        "alembic_single_head": len([line for line in _run([sys.executable, "-m", "alembic", "heads"], check=False).stdout.splitlines() if "(head)" in line]) == 1,
    }
    occupied = [_port_info(int(os.environ.get("WEB_BACKEND_PORT", "8000"))), _port_info(int(os.environ.get("WEB_FRONTEND_PORT", "5173")))]
    warnings = [f"port_{item['port']}_owned_by_other_source" for item in occupied if item.get("pid") and not item.get("source_owned")]
    payload = {**_identity(), "action": "doctor", "ok": all(checks.values()), "checks": checks, "warnings": warnings}
    print(json.dumps(payload, ensure_ascii=False, indent=2) if as_json else "\n".join(
        [*(f"{key}={'PASS' if value else 'FAIL'}" for key, value in checks.items()), *(f"WARN={item}" for item in warnings)]
    ))
    return 0 if payload["ok"] else 2


def start(*, debug: bool, silent: bool, as_json: bool = False) -> int:
    previous_state = _read_state()
    before = status(as_json=False)
    foreign = [item for item in before["services"].values() if item.get("port") and item.get("pid") and not item.get("source_owned")]
    if foreign:
        print("START_BLOCKED_UNKNOWN_PORT_OWNER=" + ",".join(str(item["port"]) for item in foreign))
        return 3
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    log_dir = LOG_ROOT / stamp
    log_dir.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.update({
        "PYTHONUTF8": "1", "RUNTIME_LOG_DIR": str(log_dir),
        "PHASE4_RUNTIME_LOG_DIR": str(log_dir / "celery"),
        "WEB_BACKEND_LOG_LEVEL": "debug" if debug else "info",
        # Fast default startup must not inherit the preproduction profile's
        # multi-GB embedding/reranker warmup. Operators can opt in explicitly.
        "RAG_PREWARM_ON_STARTUP": os.environ.get("RAG_PREWARM_ON_STARTUP", "0"),
        "WEB_BACKEND_STARTUP_TIMEOUT": os.environ.get("WEB_BACKEND_STARTUP_TIMEOUT", "120"),
        "WEB_FRONTEND_STARTUP_TIMEOUT": os.environ.get("WEB_FRONTEND_STARTUP_TIMEOUT", "60"),
    })
    configs = _runtime_files()
    common = [item for path in configs for item in ("--runtime-config", str(path))]
    control_log = log_dir / "controller.log"
    with control_log.open("a", encoding="utf-8") as output:
        web = _run(
            _web_launcher_command(configs, suppress_browser=silent),
            check=False, env=env, stdout=output,
        )
        celery = _run([
            sys.executable, "-X", "utf8", str(ROOT / "scripts" / "phase4_precheck_runtime.py"),
            *common, "celery", "start",
        ], check=False, env=env, stdout=output) if web.returncode == 0 else None
    current = status(as_json=False)
    for name, item in current["services"].items():
        before_item = before["services"].get(name) or {}
        before_pid = before_item.get("pid") if before_item.get("health") in {"healthy", "running", "listening"} else None
        previous_item = (previous_state.get("services") or {}).get(name) or {}
        still_managed = (
            _state_belongs_to_this_worktree(previous_state)
            and bool(previous_item.get("managed"))
            and _same_recorded_process(previous_item, item)
        )
        item["managed"] = bool(item.get("pid")) and (
            item.get("pid") != before_pid or still_managed
        )
    state = {
        **_identity(), "started_at": datetime.now(timezone.utc).isoformat(), "log_path": str(log_dir),
        "visible_consoles": 0 if silent else 1, "debug": debug, "services": current["services"],
    }
    _write_state(state)
    ok = web.returncode == 0 and celery is not None and celery.returncode == 0
    payload = {**state, "action": "start-debug" if debug else "start", "ok": ok}
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"log_path={log_dir}")
    return 0 if ok else 2


def stop(*, as_json: bool = False) -> int:
    state = _read_state()
    failures, stopped = [], []
    state_owned = _state_belongs_to_this_worktree(state)
    for name, recorded in (state.get("services") or {}).items():
        if name == "celery":
            continue
        if not recorded.get("managed"):
            continue
        pid = int(recorded.get("pid") or 0)
        if not pid:
            continue
        current = _port_info(int(recorded["port"]))
        if not current.get("pid"):
            stopped.append(name)
            continue
        controller_proven = state_owned and bool(recorded.get("managed"))
        if (
            current.get("pid") != pid
            or current.get("created") != recorded.get("created")
            or not (current.get("source_owned") or controller_proven)
        ):
            failures.append(f"{name}:ownership_not_proven")
            continue
        try:
            os.kill(pid, signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM)
        except (OSError, SystemError):
            try:
                os.kill(pid, signal.SIGTERM)
            except (OSError, SystemError):
                pass
        for _ in range(20):
            if not _port_info(int(recorded["port"])).get("pid"):
                stopped.append(name)
                break
            time.sleep(0.25)
        else:
            failures.append(f"{name}:stop_timeout")
    log_path = Path(str(state.get("log_path") or ""))
    celery_record = (state.get("services") or {}).get("celery") or {}
    if celery_record.get("managed") and log_path.is_dir() and ROOT in log_path.parents:
        env = os.environ.copy()
        env["PHASE4_RUNTIME_LOG_DIR"] = str(log_path / "celery")
        configs = _runtime_files()
        common = [item for path in configs for item in ("--runtime-config", str(path))]
        celery = _run([
            sys.executable, "-X", "utf8", str(ROOT / "scripts" / "phase4_precheck_runtime.py"),
            *common, "celery", "stop",
        ], check=False, env=env)
        if celery.returncode == 0:
            stopped.append("celery")
        else:
            failures.append("celery:graceful_stop_failed")
    if not failures and state:
        for name in stopped:
            if name in (state.get("services") or {}):
                state["services"][name].update(pid=None, health="stopped", managed=False)
        state["stopped_at"] = datetime.now(timezone.utc).isoformat()
        _write_state(state)
    payload = {**_identity(), "action": "stop", "ok": not failures, "stopped": stopped, "failures": failures, "log_path": state.get("log_path")}
    print(json.dumps(payload, ensure_ascii=False, indent=2) if as_json else f"stopped={','.join(stopped) or 'none'} failures={','.join(failures) or 'none'}")
    return 0 if not failures else 2


def logs(*, lines: int = 40) -> int:
    log_path = Path(str(_read_state().get("log_path") or ""))
    if not log_path.is_dir() or ROOT not in log_path.parents:
        print("log_path=none")
        return 0
    print(f"log_path={log_path}")
    secret = re.compile(r"(Bearer\s+)[^\s]+|sk-[A-Za-z0-9_-]{12,}|(postgres(?:ql)?://)[^\s]+", re.I)
    for path in sorted(log_path.rglob("*.log")):
        print(f"[{path.name}]")
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-max(1, min(lines, 200)):]:
            print(secret.sub(r"\1<REDACTED>", line))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", nargs="?", choices=["start", "start-debug", "status", "logs", "stop", "restart", "doctor"], default="start")
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--lines", type=int, default=40)
    args = parser.parse_args()
    if args.action == "status":
        status(as_json=args.json); return 0
    if args.action == "doctor":
        return doctor(as_json=args.json)
    if args.action == "logs":
        return logs(lines=args.lines)
    if args.action == "stop":
        return stop(as_json=args.json)
    if args.action == "restart":
        stopped = stop(as_json=args.json)
        return stopped or start(debug=False, silent=args.silent, as_json=args.json)
    return start(debug=args.action == "start-debug", silent=args.silent, as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
