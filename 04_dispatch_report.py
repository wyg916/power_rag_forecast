from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import requests

from automation_common import format_duration, get_pipeline_paths, get_run_context, load_config, now_compact, read_json, setup_run_logger, write_json
from database_utils import save_dispatch_manifest, save_pipeline_event


def copy_outputs(current_dir: Path, target_dir: Path) -> list[str]:
    target_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for path in current_dir.iterdir():
        if path.is_file():
            shutil.copy2(path, target_dir / path.name)
            copied.append(path.name)
    return copied


def update_latest_archive_pointer(paths, run_timestamp: str, archive_target: Path) -> list[str]:
    latest_dir = paths.dispatch_dir / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    copied_files = copy_outputs(archive_target, latest_dir)
    pointer_path = paths.dispatch_dir / "latest_pointer.txt"
    pointer_path.write_text(run_timestamp, encoding="utf-8")
    return copied_files


def copy_file_if_exists(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def try_send_webhook(url: str, text: str) -> tuple[bool, str]:
    try:
        response = requests.post(url, json={"msgtype": "text", "text": {"content": text}}, timeout=20)
        return response.ok, response.text
    except Exception as exc:
        return False, str(exc)


def copy_latest_log(log_dir: Path, pattern: str, target: Path, copied: list[dict[str, str]]) -> None:
    matches = sorted(log_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        return
    source = matches[0]
    if copy_file_if_exists(source, target):
        copied.append({"source": str(source), "target": str(target)})


def build_user_facing_package(paths, run_timestamp: str) -> tuple[Path, list[dict[str, str]]]:
    run_folder = paths.final_output_root_dir / f"{run_timestamp}_电价预测运行结果"
    formal_dir = run_folder / "01_正式预测结果"
    ai_dir = run_folder / "02_AI报告"
    model_dir = run_folder / "03_关键模型结果"
    log_dir = run_folder / "04_运行日志"

    table_dir = paths.result_table_dir
    fig_dir = paths.result_dir / "图表"
    copied: list[dict[str, str]] = []

    def _copy(source: Path, target: Path) -> None:
        if copy_file_if_exists(source, target):
            copied.append({"source": str(source), "target": str(target)})

    _copy(table_dir / "18_未来24小时预测结果_正式版.xlsx", formal_dir / "未来24小时正式前瞻预测结果.xlsx")
    _copy(table_dir / "18_未来24小时预测输入特征_正式版.xlsx", formal_dir / "未来24小时正式前瞻预测输入特征.xlsx")
    _copy(fig_dir / "21_未来24小时日前电价预测图_正式版.png", formal_dir / "未来24小时正式前瞻预测图.png")
    _copy(table_dir / "19_业务统计摘要.xlsx", formal_dir / "业务统计摘要.xlsx")

    _copy(table_dir / "10_模型评估结果.xlsx", model_dir / "模型评估结果.xlsx")
    _copy(table_dir / "11_高峰尖刺专项评估.xlsx", model_dir / "高峰尖刺专项评估.xlsx")
    _copy(table_dir / "14_异常波动明细.xlsx", model_dir / "异常波动明细.xlsx")
    _copy(table_dir / "15_按小时误差统计.xlsx", model_dir / "按小时误差统计.xlsx")
    _copy(table_dir / "16_滚动回测结果.xlsx", model_dir / "滚动回测结果.xlsx")

    _copy(paths.current_dir / "电价智能分析综合报告.docx", ai_dir / "电价智能分析综合报告.docx")
    _copy(paths.current_dir / "ai_input_summary.json", ai_dir / "智能分析输入摘要.json")
    _copy(paths.current_dir / "ai_report_structured.json", ai_dir / "智能分析结构化报告.json")

    copy_latest_log(paths.log_dir, "main_daily_run_*.log", log_dir / "总控运行日志.log", copied)
    copy_latest_log(paths.log_dir, "01_run_prediction_*.log", log_dir / "预测引擎调度日志.log", copied)
    copy_latest_log(paths.log_dir, "02_build_ai_summary_*.log", log_dir / "AI输入摘要日志.log", copied)
    copy_latest_log(paths.log_dir, "03_llm_generate_report_*.log", log_dir / "AI报告生成日志.log", copied)
    copy_latest_log(paths.log_dir, "04_dispatch_report_*.log", log_dir / "结果归档派发日志.log", copied)
    _copy(paths.result_dir / "日志" / "运行日志.txt", log_dir / "预测引擎运行日志.txt")

    summary_text = "\n".join(
        [
            "本次运行结果已完成归档。",
            f"执行时间戳：{run_timestamp}",
            f"总输出目录：{run_folder}",
            f"正式预测结果：{formal_dir}",
            f"AI 报告目录：{ai_dir}",
            f"关键模型结果：{model_dir}",
            f"运行日志目录：{log_dir}",
            "",
            "说明：",
            "1. 未来24小时正式前瞻预测结果.xlsx 为主要预测结果文件。",
            "2. 电价智能分析综合报告.docx 为合并后的 Word 报告。",
            "3. 智能分析输入摘要.json 和 智能分析结构化报告.json 用于程序联调与复核。",
        ]
    )
    info_path = run_folder / "运行结果说明.txt"
    info_path.parent.mkdir(parents=True, exist_ok=True)
    info_path.write_text(summary_text, encoding="utf-8")
    copied.append({"source": "generated", "target": str(info_path)})

    return run_folder, copied


def main() -> None:
    start = time.perf_counter()
    config = load_config()
    paths = get_pipeline_paths(config)
    run_context = get_run_context()
    dispatch_cfg = config["dispatch"]
    log, _ = setup_run_logger(paths.log_dir, "04_dispatch_report")

    run_timestamp = now_compact()
    internal_archive_target = paths.dispatch_dir / run_timestamp
    copied_files = copy_outputs(paths.current_dir, internal_archive_target)
    latest_dir = paths.dispatch_dir / "latest"
    latest_pointer_path = paths.dispatch_dir / "latest_pointer.txt"

    report_structured = read_json(paths.current_dir / "ai_report_structured.json")
    alert_text = str(report_structured.get("alert_message", "")).strip()
    webhook_results = []

    if dispatch_cfg.get("enable_wecom_webhook"):
        url = os.environ.get(dispatch_cfg["wecom_webhook_env"], "")
        if url:
            ok, detail = try_send_webhook(url, alert_text)
            webhook_results.append({"channel": "企业微信", "ok": ok, "detail": detail})

    if dispatch_cfg.get("enable_dingtalk_webhook"):
        url = os.environ.get(dispatch_cfg["dingtalk_webhook_env"], "")
        if url:
            ok, detail = try_send_webhook(url, alert_text)
            webhook_results.append({"channel": "钉钉", "ok": ok, "detail": detail})

    if dispatch_cfg.get("enable_feishu_webhook"):
        url = os.environ.get(dispatch_cfg["feishu_webhook_env"], "")
        if url:
            ok, detail = try_send_webhook(url, alert_text)
            webhook_results.append({"channel": "飞书", "ok": ok, "detail": detail})

    user_facing_folder, user_copies = build_user_facing_package(paths, run_timestamp)
    manifest = {
        "internal_archive_path": str(internal_archive_target),
        "latest_archive_path": str(latest_dir),
        "latest_pointer_path": str(latest_pointer_path),
        "user_facing_output_path": str(user_facing_folder),
        "internal_current_files": copied_files,
        "user_facing_files": user_copies,
        "webhook_results": webhook_results,
    }

    write_json(internal_archive_target / "dispatch_manifest.json", manifest)
    latest_files = update_latest_archive_pointer(paths, run_timestamp, internal_archive_target)
    manifest["latest_files"] = latest_files
    write_json(internal_archive_target / "dispatch_manifest.json", manifest)
    write_json(latest_dir / "dispatch_manifest.json", manifest)
    write_json(user_facing_folder / "归档清单.json", manifest)
    save_dispatch_manifest(config, manifest, user_facing_folder, run_context=run_context, log=log)

    elapsed = format_duration(time.perf_counter() - start)
    log(f"已完成本地归档派发：{internal_archive_target}")
    log(f"已生成用户结果总文件夹：{user_facing_folder}，耗时：{elapsed}")
    save_pipeline_event(config, "dispatch_report", "completed", f"结果归档完成，耗时：{elapsed}", run_context)


if __name__ == "__main__":
    main()
