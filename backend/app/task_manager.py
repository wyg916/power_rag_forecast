from __future__ import annotations

import os
import json
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from .config import PROJECT_ROOT, project_config, project_paths
from .data_access import database_engine, jsonable
from .observability import log_suppressed_exception
from .workers.task_commands import command_for_kind


@dataclass
class TaskRecord:
    task_id: str
    run_id: str
    kind: str
    status: str
    command: list[str]
    log_path: str
    started_at: str
    ended_at: str | None = None
    duration_seconds: float | None = None
    returncode: int | None = None
    error_message: str = ""
    execution_mode: str = "local_thread"
    progress: float = 0
    message: str = ""


class TaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

    def _command_for_kind(self, kind: str) -> list[str]:
        return command_for_kind(kind)
        py = sys.executable
        mapping = {
            "today_analysis": [py, "-X", "utf8", str(PROJECT_ROOT / "main_daily_run.py"), "--refresh-data", "--fast-forecast"],
            "refresh_data": [py, "-X", "utf8", str(PROJECT_ROOT / "fetch_power_market_data.py")],
            "fast_forecast": [py, "-X", "utf8", str(PROJECT_ROOT / "main_daily_run.py"), "--fast-forecast"],
            "report_only": [py, "-X", "utf8", str(PROJECT_ROOT / "main_daily_run.py"), "--skip-prediction"],
            "health_check": [py, "-X", "utf8", str(PROJECT_ROOT / "09_health_check.py")],
            "retrain_model": [py, "-X", "utf8", str(PROJECT_ROOT / "main_daily_run.py"), "--retrain-model"],
            "model_auto_optimize": [py, "-X", "utf8", str(PROJECT_ROOT / "main_daily_run.py"), "--model-auto-optimize"],
        }
        if kind not in mapping:
            raise ValueError(f"不支持的任务类型：{kind}")
        return mapping[kind]

    @staticmethod
    def _creationflags() -> int:
        if os.name != "nt":
            return 0
        return getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    def start(self, kind: str) -> dict[str, Any]:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_id = "task_" + uuid.uuid4().hex[:12]
        paths = project_paths()
        paths.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = paths.log_dir / f"web_task_{kind}_{run_id}.log"
        command = self._command_for_kind(kind)
        record = TaskRecord(
            task_id=task_id,
            run_id=run_id,
            kind=kind,
            status="running",
            command=command,
            log_path=str(log_path),
            started_at=datetime.now().isoformat(sep=" ", timespec="seconds"),
            progress=10,
            message="running",
        )
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["NO_PAUSE"] = "1"
        with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
            log_file.write(f"[{record.started_at}] Web 任务启动：{kind}\n")
            log_file.write("命令：" + " ".join(command) + "\n")
            process = subprocess.Popen(
                command,
                cwd=str(PROJECT_ROOT),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
                stdin=subprocess.DEVNULL,
                creationflags=self._creationflags(),
            )
        with self._lock:
            self._tasks[task_id] = record
            self._processes[task_id] = process
        self._save_analysis_run(record, "running")
        threading.Thread(target=self._wait_for_task, args=(task_id,), daemon=True).start()
        return self.get(task_id)

    def _wait_for_task(self, task_id: str) -> None:
        with self._lock:
            process = self._processes.get(task_id)
            record = self._tasks.get(task_id)
        if process is None or record is None:
            return
        start = time.perf_counter()
        returncode = process.wait()
        ended = datetime.now().isoformat(sep=" ", timespec="seconds")
        with self._lock:
            record.returncode = returncode
            record.ended_at = ended
            record.duration_seconds = round(time.perf_counter() - start, 3)
            record.status = "success" if returncode == 0 else "failed"
            record.progress = 100
            record.message = record.status
            if returncode != 0:
                record.error_message = f"任务退出码：{returncode}"
            self._processes.pop(task_id, None)
        try:
            with open(record.log_path, "a", encoding="utf-8", errors="replace") as log_file:
                log_file.write(f"\n[{ended}] Web 任务结束：{record.status}，退出码：{returncode}\n")
        except Exception as exc:
            log_suppressed_exception("task_manager.append_finish_log", exc, task_id=task_id, log_path=record.log_path)
        self._save_analysis_run(record, record.status)

    def _save_analysis_run(self, record: TaskRecord, status: str) -> None:
        try:
            from .repositories.task_repository import save_task_record

            if save_task_record(asdict(record), status=status):
                return
        except Exception as exc:
            log_suppressed_exception("task_manager.save_task_record.repository", exc, task_id=record.task_id, status=status)

        engine = database_engine()
        if engine is None:
            return
        if engine.dialect.name == "postgresql":
            return
        try:
            from database_utils import apply_database_migrations

            apply_database_migrations(project_config())
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO analysis_runs (
                            run_id, run_type, status, started_at, ended_at,
                            duration_seconds, error_message, created_by
                        )
                        VALUES (
                            :run_id, :run_type, :status, :started_at, :ended_at,
                            :duration_seconds, :error_message, 'web'
                        )
                        ON DUPLICATE KEY UPDATE
                            status = VALUES(status),
                            ended_at = VALUES(ended_at),
                            duration_seconds = VALUES(duration_seconds),
                            error_message = VALUES(error_message)
                        """
                    ),
                    {
                        "run_id": record.run_id,
                        "run_type": record.kind,
                        "status": status,
                        "started_at": record.started_at,
                        "ended_at": record.ended_at,
                        "duration_seconds": record.duration_seconds,
                        "error_message": record.error_message,
                    },
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO task_logs (
                            task_id, run_id, task_name, task_kind, status,
                            command_json, log_path, started_at, ended_at,
                            duration_seconds, returncode, error_message
                        )
                        VALUES (
                            :task_id, :run_id, :task_name, :task_kind, :status,
                            :command_json, :log_path, :started_at, :ended_at,
                            :duration_seconds, :returncode, :error_message
                        )
                        ON DUPLICATE KEY UPDATE
                            run_id = VALUES(run_id),
                            task_name = VALUES(task_name),
                            task_kind = VALUES(task_kind),
                            status = VALUES(status),
                            command_json = VALUES(command_json),
                            log_path = VALUES(log_path),
                            ended_at = VALUES(ended_at),
                            duration_seconds = VALUES(duration_seconds),
                            returncode = VALUES(returncode),
                            error_message = VALUES(error_message)
                        """
                    ),
                    {
                        "task_id": record.task_id,
                        "run_id": record.run_id,
                        "task_name": record.kind,
                        "task_kind": record.kind,
                        "status": status,
                        "command_json": json.dumps(record.command, ensure_ascii=False),
                        "log_path": record.log_path,
                        "started_at": record.started_at,
                        "ended_at": record.ended_at,
                        "duration_seconds": record.duration_seconds,
                        "returncode": record.returncode,
                        "error_message": record.error_message,
                    },
                )
        except Exception as exc:
            log_suppressed_exception("task_manager.save_task_record.legacy_database", exc, task_id=record.task_id, status=status)
            return

    def get(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._tasks.get(task_id)
        if record is None:
            raise KeyError(task_id)
        return jsonable(asdict(record))

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = [asdict(record) for record in self._tasks.values()]
        rows.sort(key=lambda row: row["started_at"], reverse=True)
        return jsonable(rows)

    def logs(self, task_id: str, tail: int = 4000) -> str:
        record = self._tasks.get(task_id)
        if record is None:
            raise KeyError(task_id)
        path = Path(record.log_path)
        if not path.exists():
            return ""
        text_value = path.read_text(encoding="utf-8", errors="replace")
        return text_value[-tail:]

    def cancel(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            process = self._processes.get(task_id)
            record = self._tasks.get(task_id)
        if record is None:
            raise KeyError(task_id)
        if process is not None and process.poll() is None:
            process.terminate()
            record.status = "cancelled"
            record.progress = 100
            record.message = "cancelled"
            record.ended_at = datetime.now().isoformat(sep=" ", timespec="seconds")
            record.error_message = "用户通过 Web 任务接口取消。"
            self._save_analysis_run(record, "cancelled")
        return self.get(task_id)


task_manager = TaskManager()
