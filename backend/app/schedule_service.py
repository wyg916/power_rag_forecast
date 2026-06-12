from __future__ import annotations

import csv
import json
import os
import re
import subprocess
from io import StringIO
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT
from .data_access import jsonable
from .observability import log_suppressed_exception


MODE_TO_BAT = {
    "fast_forecast": "run_daily_pipeline_fast_forecast.bat",
    "refresh_fast_forecast": "run_daily_pipeline_refresh_fast_forecast.bat",
    "retrain_model": "run_daily_pipeline_retrain_model.bat",
    "model_auto_optimize": "run_model_auto_optimize.bat",
    "full": "run_daily_pipeline.bat",
    "refresh_data": "run_daily_pipeline_refresh_data.bat",
    "skip_prediction": "run_daily_pipeline_skip_prediction.bat",
    "prediction_report_only": "run_daily_pipeline_prediction_report_only.bat",
    "model_ops_daily": "run_model_ops_daily.bat",
    "health_check": "run_health_check.bat",
    "smoke_test": "run_smoke_test.bat",
    "web_smoke_test": "run_web_smoke_test.bat",
}

MANAGED_PREFIXES = ("PowerMarket", "PowerTrading", "售电交易", "智能运营", "AI电价")


def _no_window_creationflags() -> int:
    if os.name != "nt":
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run_schtasks(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["schtasks.exe", *arguments],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="mbcs",
        errors="replace",
        timeout=30,
        stdin=subprocess.DEVNULL,
        creationflags=_no_window_creationflags(),
    )


def _run_powershell(script: str) -> subprocess.CompletedProcess[str]:
    wrapped = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; " + script
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", wrapped],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        stdin=subprocess.DEVNULL,
        creationflags=_no_window_creationflags(),
    )


def _list_tasks_powershell() -> list[dict[str, Any]] | None:
    bat_names = ",".join(f"'{name}'" for name in MODE_TO_BAT.values())
    project = str(PROJECT_ROOT).replace("'", "''")
    script = f"""
$project = '{project}'
$batNames = @({bat_names})
$items = @()
Get-ScheduledTask | ForEach-Object {{
    $task = $_
    $actions = @($task.Actions | ForEach-Object {{ ($_.Execute + ' ' + $_.Arguments).Trim() }}) -join ' '
    $batHit = $false
    foreach ($bat in $batNames) {{ if ($actions -like ('*' + $bat + '*')) {{ $batHit = $true }} }}
    $nameHit = $task.TaskName -like 'PowerMarket*' -or $task.TaskName -like 'PowerTrading*' -or $task.TaskName -like '售电交易*' -or $task.TaskName -like '智能运营*' -or $task.TaskName -like 'AI电价*'
    $projectHit = $actions -like ('*' + $project + '*')
    if ($nameHit -or $projectHit -or $batHit) {{
        $info = Get-ScheduledTaskInfo -TaskName $task.TaskName -TaskPath $task.TaskPath -ErrorAction SilentlyContinue
        $items += [pscustomobject]@{{
            task_name = $task.TaskName
            status = [string]$task.State
            next_run_time = if ($info -and $info.NextRunTime) {{ $info.NextRunTime.ToString('yyyy-MM-dd HH:mm:ss') }} else {{ '' }}
            last_run_time = if ($info -and $info.LastRunTime) {{ $info.LastRunTime.ToString('yyyy-MM-dd HH:mm:ss') }} else {{ '' }}
            last_result = if ($info) {{ [string]$info.LastTaskResult }} else {{ '' }}
            schedule = @($task.Triggers | ForEach-Object {{ $_.ToString() }}) -join '; '
            mode = ''
            command = $actions
        }}
    }}
}}
@($items) | ConvertTo-Json -Depth 5 -Compress
"""
    result = _run_powershell(script)
    if result.returncode != 0:
        return None
    text_value = (result.stdout or "").strip()
    if not text_value:
        return []
    try:
        payload = json.loads(text_value)
    except Exception as exc:
        log_suppressed_exception("schedule.list_tasks.parse_json", exc, stdout=text_value[:500])
        return None
    if isinstance(payload, dict):
        payload = [payload]
    rows: list[dict[str, Any]] = []
    for item in payload or []:
        command = str(item.get("command") or "")
        rows.append(
            {
                "task_name": str(item.get("task_name") or "").lstrip("\\"),
                "status": item.get("status") or "",
                "next_run_time": item.get("next_run_time") or "",
                "last_run_time": item.get("last_run_time") or "",
                "last_result": item.get("last_result") or "",
                "schedule": item.get("schedule") or "",
                "mode": _mode_from_command(command),
                "command": command,
            }
        )
    rows.sort(key=lambda item: item.get("task_name", ""))
    return rows


def _field(row: dict[str, str], *candidates: str) -> str:
    lower = {str(k).lower(): str(v or "") for k, v in row.items() if k is not None}
    for candidate in candidates:
        if candidate in row:
            return str(row.get(candidate) or "")
        value = lower.get(candidate.lower())
        if value:
            return value
    return ""


def _task_name_from_row(row: dict[str, str]) -> str:
    value = _field(row, "TaskName", "任务名", "任务名称")
    if value:
        return value
    for value in row.values():
        if isinstance(value, str) and value.startswith("\\"):
            return value
    return next((str(v) for v in row.values() if isinstance(v, str) and v), "")


def _command_from_row(row: dict[str, str]) -> str:
    value = _field(row, "Task To Run", "要运行的任务", "操作", "Actions")
    if value:
        return value
    return next((str(v) for v in row.values() if isinstance(v, str) and (".bat" in v.lower() or "cmd.exe" in v.lower())), "")


def _mode_from_command(command: str) -> str:
    command_lower = command.lower()
    for mode, bat_name in MODE_TO_BAT.items():
        if bat_name.lower() in command_lower:
            return mode
    return ""


def _is_project_task(task_name: str, command: str) -> bool:
    plain_name = task_name.lstrip("\\")
    if plain_name.startswith(MANAGED_PREFIXES):
        return True
    project_text = str(PROJECT_ROOT).lower()
    return project_text in command.lower() or any(bat.lower() in command.lower() for bat in MODE_TO_BAT.values())


def _normalize_task_name(name: str) -> str:
    clean = re.sub(r'[\\/:*?"<>|]+', "_", name.strip())
    if not clean:
        clean = "PowerMarket_WebTask"
    if not clean.startswith(MANAGED_PREFIXES):
        clean = "PowerMarket_" + clean
    return clean[:238]


def list_scheduled_tasks() -> dict[str, Any]:
    ps_rows = _list_tasks_powershell()
    if ps_rows is not None:
        return {"available": True, "tasks": jsonable(ps_rows)}

    result = _run_schtasks(["/Query", "/FO", "CSV", "/V"])
    if result.returncode != 0:
        return {"available": False, "tasks": [], "message": result.stderr or result.stdout}
    reader = csv.DictReader(StringIO(result.stdout))
    rows: list[dict[str, Any]] = []
    for row in reader:
        task_name = _task_name_from_row(row)
        command = _command_from_row(row)
        if not task_name or not _is_project_task(task_name, command):
            continue
        rows.append(
            {
                "task_name": task_name.lstrip("\\"),
                "status": _field(row, "Status", "状态"),
                "next_run_time": _field(row, "Next Run Time", "下次运行时间"),
                "last_run_time": _field(row, "Last Run Time", "上次运行时间"),
                "last_result": _field(row, "Last Result", "上次结果"),
                "schedule": _field(row, "Schedule Type", "计划类型"),
                "mode": _mode_from_command(command),
                "command": command,
            }
        )
    rows.sort(key=lambda item: item.get("task_name", ""))
    return {"available": True, "tasks": jsonable(rows)}


def create_scheduled_task(name: str, mode: str, run_time: str, highest: bool = False) -> dict[str, Any]:
    if mode not in MODE_TO_BAT:
        raise ValueError(f"不支持的定时任务模式：{mode}")
    if not re.match(r"^\d{2}:\d{2}$", run_time):
        raise ValueError("运行时间必须使用 HH:mm 格式，例如 06:30")
    task_name = _normalize_task_name(name)
    batch_path = PROJECT_ROOT / MODE_TO_BAT[mode]
    if not batch_path.exists():
        raise FileNotFoundError(f"未找到启动文件：{batch_path.name}")
    task_command = f'cmd.exe /c "set NO_PAUSE=1&& call ""{batch_path}"""'
    args = ["/Create", "/F", "/SC", "DAILY", "/TN", task_name, "/TR", task_command, "/ST", run_time]
    if highest:
        args += ["/RL", "HIGHEST"]
    result = _run_schtasks(args)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "创建 Windows 定时任务失败")
    payload = list_scheduled_tasks()
    payload["created"] = {"task_name": task_name, "mode": mode, "run_time": run_time}
    return payload


def delete_scheduled_task(task_name: str) -> dict[str, Any]:
    current = list_scheduled_tasks()
    managed = {row["task_name"]: row for row in current.get("tasks", [])}
    resolved = task_name.lstrip("\\")
    if resolved not in managed:
        raise ValueError("只能删除当前项目创建或引用当前项目启动脚本的定时任务")
    result = _run_schtasks(["/Delete", "/TN", resolved, "/F"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "删除 Windows 定时任务失败")
    payload = list_scheduled_tasks()
    payload["deleted"] = resolved
    return payload
