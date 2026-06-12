from __future__ import annotations

import json
import os
import copy
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ROOT_DIR / "llm_service_config.yaml"


@dataclass
class PipelinePaths:
    root_dir: Path
    engine_script: Path
    data_dir: Path
    result_dir: Path
    result_table_dir: Path
    automation_dir: Path
    current_dir: Path
    archive_dir: Path
    dispatch_dir: Path
    log_dir: Path
    final_output_root_dir: Path


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    from config_loader import load_config as load_runtime_config

    return load_runtime_config(config_path or CONFIG_PATH)


def save_config(config: dict[str, Any], config_path: Path | None = None) -> None:
    import yaml

    config_file = config_path or CONFIG_PATH
    output_config = copy.deepcopy(config)
    output_config.get("database", {})["password"] = ""
    output_config.get("llm", {})["api_key"] = ""
    output_config.get("market", {})["pjm_subscription_key"] = ""
    with config_file.open("w", encoding="utf-8") as f:
        yaml.safe_dump(output_config, f, allow_unicode=True, sort_keys=False)


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else ROOT_DIR / path


def get_pipeline_paths(config: dict[str, Any]) -> PipelinePaths:
    paths_cfg = config["paths"]
    paths = PipelinePaths(
        root_dir=ROOT_DIR,
        engine_script=resolve_path(paths_cfg["engine_script"]),
        data_dir=resolve_path(paths_cfg["data_dir"]),
        result_dir=resolve_path(paths_cfg["result_dir"]),
        result_table_dir=resolve_path(paths_cfg["result_table_dir"]),
        automation_dir=resolve_path(paths_cfg["automation_dir"]),
        current_dir=resolve_path(paths_cfg["current_dir"]),
        archive_dir=resolve_path(paths_cfg["archive_dir"]),
        dispatch_dir=resolve_path(paths_cfg["dispatch_dir"]),
        log_dir=resolve_path(paths_cfg["log_dir"]),
        final_output_root_dir=resolve_path(paths_cfg["final_output_root_dir"]),
    )
    for folder in [
        paths.automation_dir,
        paths.current_dir,
        paths.archive_dir,
        paths.dispatch_dir,
        paths.log_dir,
        paths.final_output_root_dir,
    ]:
        folder.mkdir(parents=True, exist_ok=True)
    return paths


def now_text(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return datetime.now().strftime(fmt)


def now_compact() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def setup_run_logger(log_dir: Path, prefix: str):
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{prefix}_{now_compact()}.log"

    def _log(message: str) -> None:
        text = f"[{now_text()}] {message}"
        print(text)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(text + "\n")

    return _log, log_path


def timed_block(log, label: str):
    start = time.perf_counter()
    log(f"开始：{label}")

    def _finish(extra_message: str = "") -> None:
        elapsed = format_duration(time.perf_counter() - start)
        if extra_message:
            log(f"完成：{label}，耗时：{elapsed}，{extra_message}")
        else:
            log(f"完成：{label}，耗时：{elapsed}")

    return _finish


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        return float(value)
    except Exception:
        return None


def safe_int(value: Any) -> int | None:
    number = safe_float(value)
    return None if number is None else int(number)


def read_excel(path: Path) -> pd.DataFrame:
    return pd.read_excel(path)


def normalize_timestamp(value: Any) -> str:
    if value is None:
        return ""
    try:
        ts = pd.to_datetime(value)
        if pd.isna(ts):
            return ""
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)


def find_first_column(columns: list[str], keywords: list[str]) -> str | None:
    for keyword in keywords:
        for col in columns:
            if keyword in str(col):
                return str(col)
    return None


def env_or_default(name: str, default: str) -> str:
    return os.environ.get(name, default)


def get_run_context() -> dict[str, str]:
    run_id = os.environ.get("PIPELINE_RUN_ID", now_compact())
    run_started_at = os.environ.get("PIPELINE_RUN_STARTED_AT", now_text())
    run_mode = os.environ.get("PIPELINE_RUN_MODE", "manual")
    return {
        "run_id": run_id,
        "run_started_at": run_started_at,
        "run_mode": run_mode,
    }
