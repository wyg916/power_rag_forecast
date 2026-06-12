from __future__ import annotations

from pathlib import Path
import importlib

from automation_common import get_pipeline_paths, load_config
from main_daily_run import validate_skip_prediction_inputs
from prediction_engine.legacy_engine import load_engine_module
from services.config_service import disable_database_if_unavailable
run_health_check = importlib.import_module("09_health_check").run_health_check


def _assert_bat_crlf() -> None:
    for path in Path(".").glob("*.bat"):
        data = path.read_bytes()
        if b"\r\n" not in data:
            raise AssertionError(f"批处理文件不是 CRLF 换行：{path}")


def main() -> None:
    config = load_config()
    paths = get_pipeline_paths(config)
    disable_database_if_unavailable(config, log=print)
    validate_skip_prediction_inputs(paths, print)
    module = load_engine_module()
    if not hasattr(module, "main") or not hasattr(module, "run_peak_enhanced_pipeline"):
        raise AssertionError("预测引擎兼容入口缺少关键函数。")
    _assert_bat_crlf()
    report, exit_code = run_health_check(strict=False)
    print(f"健康检查报告：{report['output_path']}")
    print("Smoke test passed.")
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
