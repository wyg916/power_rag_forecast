from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from automation_common import get_pipeline_paths, load_config, save_config
from database_utils import apply_database_migrations, test_database_connection


ROOT_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CommandSpec:
    title: str
    command: list[str]

    @property
    def display(self) -> str:
        return subprocess.list2cmdline(self.command)


class LegacyActions:
    """Bridge the Qt UI to existing project scripts without rewriting business logic."""

    def __init__(self):
        self.root_dir = ROOT_DIR

    def python_command(self, script_name: str, *args: str) -> list[str]:
        return [sys.executable, "-X", "utf8", str(self.root_dir / script_name), *args]

    def command_for_action(self, action_id: str) -> CommandSpec:
        mapping = {
            "fast_forecast": ("快速预测（Active模型）", self.python_command("main_daily_run.py", "--fast-forecast")),
            "refresh_fast_forecast": (
                "更新数据 + 快速预测",
                self.python_command("main_daily_run.py", "--refresh-data", "--fast-forecast"),
            ),
            "retrain_model": ("完整训练并登记候选模型", self.python_command("main_daily_run.py", "--retrain-model")),
            "model_auto_optimize": ("执行模型自优化", self.python_command("main_daily_run.py", "--model-auto-optimize")),
            "refresh_data": ("更新数据并全流程", self.python_command("main_daily_run.py", "--refresh-data")),
            "full": ("直接全流程", self.python_command("main_daily_run.py")),
            "skip_prediction": ("仅生成 AI 报告", self.python_command("main_daily_run.py", "--skip-prediction")),
            "prediction_report_only": ("预测并生成报告", self.python_command("main_daily_run.py", "--prediction-report-only")),
            "inventory": ("模型盘点", self.python_command("00_local_model_inventory.py")),
            "model_monitor": ("模型诊断检查", self.python_command("06_model_monitor.py")),
            "model_ops_daily": (
                "每日模型运维",
                ["cmd.exe", "/c", f'set NO_PAUSE=1&& call "{self.root_dir / "run_model_ops_daily.bat"}"'],
            ),
            "health_check": ("健康检查", self.python_command("09_health_check.py")),
            "database_closure": ("数据库闭环同步", self.python_command("08_sync_database_closure.py")),
            "update_actuals": ("真实值与误差回填", self.python_command("05_update_actuals_and_errors.py")),
            "compare_promote": ("候选模型对比", self.python_command("07_compare_and_promote_model.py")),
            "promote_latest_candidate": (
                "最新候选模型设为 Active",
                self.python_command("07_compare_and_promote_model.py", "--promote-latest-candidate", "--approved-by", "gui"),
            ),
            "smoke_test": ("轻量整体自检", self.python_command("10_smoke_test.py")),
        }
        if action_id not in mapping:
            raise ValueError(f"未知动作：{action_id}")
        title, command = mapping[action_id]
        return CommandSpec(title=title, command=command)

    def create_task_command(self, task_name: str, run_time: str, mode: str) -> CommandSpec:
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.root_dir / "create_windows_task.ps1"),
            "-TaskName",
            task_name,
            "-RunTime",
            run_time,
            "-Mode",
            mode,
        ]
        return CommandSpec(title="创建/覆盖 Windows 任务计划", command=command)

    def test_database(self) -> tuple[bool, str]:
        return test_database_connection(load_config())

    def initialize_database_structures(self) -> None:
        apply_database_migrations(load_config())

    def output_root(self) -> Path:
        return get_pipeline_paths(load_config()).final_output_root_dir

    def project_paths(self):
        return get_pipeline_paths(load_config())

    def save_output_root(self, selected: str) -> Path:
        if not selected.strip():
            raise ValueError("输出目录不能为空")
        config = load_config()
        config["paths"]["final_output_root_dir"] = selected.replace("\\", "/")
        save_config(config)
        return get_pipeline_paths(config).final_output_root_dir

    def open_path(self, path: str | Path) -> None:
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = self.root_dir / resolved
        if not resolved.exists():
            raise FileNotFoundError(f"路径不存在：{resolved}")
        os.startfile(str(resolved))

    def open_first_existing(self, candidates: Iterable[str | Path]) -> Path:
        for candidate in candidates:
            path = Path(candidate)
            if not path.is_absolute():
                path = self.root_dir / path
            if path.exists():
                self.open_path(path)
                return path
        raise FileNotFoundError("未找到可打开的路径")
