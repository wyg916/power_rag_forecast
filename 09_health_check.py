from __future__ import annotations

import argparse
import importlib
import json
import platform
import sys
from pathlib import Path
from typing import Any

import requests

from automation_common import get_pipeline_paths, load_config, now_compact, now_text
from database_utils import test_database_connection


DEPENDENCIES = [
    "pandas",
    "numpy",
    "matplotlib",
    "sklearn",
    "requests",
    "yaml",
    "sqlalchemy",
    "pymysql",
    "docx",
    "openpyxl",
    "joblib",
    "jsonschema",
]


def _check_dependency(name: str) -> dict[str, Any]:
    try:
        importlib.import_module(name)
        return {"name": name, "ok": True, "message": "ok"}
    except Exception as exc:
        return {"name": name, "ok": False, "message": str(exc)}


def _file_status(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "size": path.stat().st_size if path.exists() and path.is_file() else None,
    }


def _check_local_model() -> dict[str, Any]:
    try:
        response = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
        response.raise_for_status()
        models = response.json().get("models") or []
        names = [str(item.get("name") or item.get("model") or "") for item in models if item.get("name") or item.get("model")]
        selected = next((name for name in names if name == "qwen3:4b"), "")
        if not selected:
            selected = next((name for name in names if name.lower().startswith("qwen3")), "")
        return {"ok": bool(selected), "selected_model": selected, "models": names}
    except Exception as exc:
        return {"ok": False, "selected_model": "", "models": [], "message": str(exc)}


def run_health_check(strict: bool = False) -> tuple[dict[str, Any], int]:
    config = load_config()
    paths = get_pipeline_paths(config)
    db_ok, db_message = test_database_connection(config)
    local_model = _check_local_model()
    dependency_checks = [_check_dependency(name) for name in DEPENDENCIES]
    required_files = [
        paths.engine_script,
        paths.data_dir / "master_table.xlsx",
        paths.data_dir / "forecast_load_selected.xlsx",
        paths.result_table_dir / "18_未来24小时预测结果_正式版.xlsx",
        Path("run_daily_pipeline.bat"),
        Path("run_daily_pipeline_refresh_data.bat"),
        Path("run_daily_pipeline_skip_prediction.bat"),
        Path("启动智能运营分析GUI.bat"),
        Path("create_windows_task.bat"),
    ]
    report = {
        "generated_at": now_text(),
        "python": sys.version,
        "platform": platform.platform(),
        "database": {"ok": db_ok, "message": db_message},
        "local_model": local_model,
        "dependencies": dependency_checks,
        "files": [_file_status(path) for path in required_files],
        "paths": {
            "root_dir": str(paths.root_dir),
            "data_dir": str(paths.data_dir),
            "result_table_dir": str(paths.result_table_dir),
            "log_dir": str(paths.log_dir),
        },
    }
    hard_failures = [item for item in dependency_checks if not item["ok"]]
    hard_failures += [item for item in report["files"] if not item["exists"] and item["path"].endswith((".py", ".bat"))]
    exit_code = 1 if strict and (hard_failures or not db_ok or not local_model["ok"]) else 0
    output_path = paths.log_dir / f"health_check_{now_compact()}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["output_path"] = str(output_path)
    return report, exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description="智能运营分析项目健康检查")
    parser.add_argument("--strict", action="store_true", help="严格模式：数据库或依赖异常时返回非零状态码")
    args = parser.parse_args()
    report, exit_code = run_health_check(strict=args.strict)
    print("健康检查完成")
    print(f"报告路径：{report['output_path']}")
    print(f"数据库：{report['database']['message']}")
    print(f"本地模型：{report['local_model'].get('selected_model') or report['local_model'].get('message') or '未就绪'}")
    missing_deps = [d["name"] for d in report["dependencies"] if not d["ok"]]
    if missing_deps:
        print("缺失依赖：" + "、".join(missing_deps))
    missing_files = [f["path"] for f in report["files"] if not f["exists"]]
    if missing_files:
        print("缺失文件：" + "、".join(missing_files))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
