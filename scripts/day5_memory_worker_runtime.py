from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.phase4_precheck_runtime import _pid_active, _terminate_pid, configure_runtime


def paths() -> dict[str, Path]:
    runtime = ROOT / ".codex_tmp" / "day5_memory_worker"
    return {
        "runtime": runtime,
        "pid": runtime / "worker.json",
        "heartbeat": runtime / "heartbeat.json",
        "log": ROOT / "output" / "runtime_logs" / "day5_memory_outbox_worker.log",
    }


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def status() -> dict:
    value = paths()
    record = read_json(value["pid"])
    heartbeat = read_json(value["heartbeat"])
    pid = int(record.get("pid") or 0)
    checked = heartbeat.get("checked_at")
    age = 10**9
    if checked:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(checked)).total_seconds()
    ok = bool(pid and _pid_active(pid) and age <= 15 and heartbeat.get("ok"))
    return {
        "ok": ok, "action": "memory_outbox_worker_status", "pid": pid or None,
        "pid_active": _pid_active(pid), "heartbeat_age_seconds": round(age, 3),
        "alembic_head": heartbeat.get("alembic_head"), "last_batch": heartbeat.get("last_batch", []),
        "log_path": str(value["log"]),
    }


def run() -> int:
    from sqlalchemy import text
    from backend.app.ai_assistant.memory.enterprise_memory import _engine
    from backend.app.ai_assistant.memory.lifecycle import process_outbox_batch

    value = paths()
    value["runtime"].mkdir(parents=True, exist_ok=True)
    while True:
        report = {"ok": False, "checked_at": datetime.now(timezone.utc).isoformat(), "last_batch": []}
        try:
            with _engine().connect() as connection:
                report["schema_contract_ready"] = bool(connection.execute(
                    text(
                        "SELECT to_regclass('ai_memory_deletion_jobs') IS NOT NULL "
                        "AND to_regprocedure('ai_memory_purge(character varying,character varying)') IS NOT NULL"
                    )
                ).scalar_one())
            report["alembic_head"] = "not_readable_by_runtime_identity"
            if not report["schema_contract_ready"]:
                raise RuntimeError("day5_schema_contract_unavailable")
            report["last_batch"] = process_outbox_batch(limit=20)
            report["ok"] = True
            report["error"] = ""
        except Exception as exc:
            report["error"] = f"{exc.__class__.__name__}:{str(exc)[:160]}"
        value["heartbeat"].write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(2)


def start(configs: list[Path]) -> dict:
    value = paths()
    value["runtime"].mkdir(parents=True, exist_ok=True)
    value["log"].parent.mkdir(parents=True, exist_ok=True)
    existing = status()
    if existing["ok"]:
        return {**existing, "action": "memory_outbox_worker_start", "idempotent": True}
    stale_pid = int(read_json(value["pid"]).get("pid") or 0)
    if stale_pid and _pid_active(stale_pid):
        _terminate_pid(stale_pid)
    command = [sys.executable, "-X", "utf8", str(Path(__file__).resolve())]
    for config in configs:
        command += ["--runtime-config", str(config)]
    command += ["run"]
    flags = (
        getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    with value["log"].open("a", encoding="utf-8") as handle:
        process = subprocess.Popen(
            command, cwd=ROOT, env=os.environ.copy(), stdin=subprocess.DEVNULL,
            stdout=handle, stderr=subprocess.STDOUT, creationflags=flags, close_fds=True,
        )
    value["pid"].write_text(json.dumps({"pid": process.pid, "started_at": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")
    deadline = time.monotonic() + 30
    current = status()
    while time.monotonic() < deadline and not current["ok"] and _pid_active(process.pid):
        time.sleep(1)
        current = status()
    return {**current, "action": "memory_outbox_worker_start", "idempotent": False}


def stop() -> dict:
    pid = int(read_json(paths()["pid"]).get("pid") or 0)
    stopped = not pid or _terminate_pid(pid)
    return {
        "ok": stopped, "action": "memory_outbox_worker_stop", "pid": pid or None,
        "pid_active": _pid_active(pid), "runtime_files_preserved": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-config", action="append", type=Path, default=[])
    parser.add_argument("command", choices=("start", "status", "stop", "run"))
    args = parser.parse_args()
    configure_runtime(args.runtime_config)
    if args.command == "run":
        return run()
    report = start(args.runtime_config) if args.command == "start" else stop() if args.command == "stop" else status()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
