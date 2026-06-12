from __future__ import annotations

from typing import Any


def _money(value: Any) -> str:
    try:
        return f"{float(value):.2f} USD/MWh"
    except Exception:
        return "-"


def answer_current_date(result: dict[str, Any]) -> str:
    weekday = result.get("weekday_cn") or ""
    date_text = f"{result.get('system_date')}，{weekday}" if weekday else str(result.get("system_date"))
    return f"现在是 {result.get('system_datetime') or date_text}。"


def answer_prediction_window(result: dict[str, Any]) -> str:
    window = result.get("prediction_window") or {}
    data_window = result.get("data_window") or {}
    return (
        f"结论：当前最新预测窗口为 {window.get('start') or '-'} 至 {window.get('end') or '-'}。\n\n"
        f"数据窗口参考：{data_window.get('start') or '-'} 至 {data_window.get('end') or '-'}。\n\n"
        f"数据依据：最新运行 ID {result.get('latest_run_id') or '-'}。"
    )


def answer_data_freshness(result: dict[str, Any], label: str) -> str:
    if result.get("multi_table"):
        items = result.get("items") or []
        available = [item for item in items if item.get("available")]
        missing = [item for item in items if not item.get("available")]
        lines = []
        for item in items:
            if item.get("available"):
                lines.append(
                    f"- {item.get('table')}：最新时间 {item.get('max_datetime') or '-'}；"
                    f"数据范围 {item.get('min_datetime') or '-'} 至 {item.get('max_datetime') or '-'}；"
                    f"记录数 {item.get('row_count') or 0}；时间字段 {item.get('datetime_field') or '-'}。"
                )
            else:
                lines.append(f"- {item.get('table')}：未找到或不可查询；原因：{item.get('message') or '未知'}")
        conclusion = "已查到部分数据库表。" if missing and available else ("已查到这些数据库表的最新数据。" if available else "这些数据库表当前未查到可用数据。")
        return (
            f"结论：{conclusion}\n\n"
            "表数据新鲜度：\n"
            + "\n".join(lines)
            + "\n\n建议：如果某张表显示未找到，请先确认表名是否存在、迁移是否执行到最新版本，以及数据导入任务是否完成。"
        )
    if not result.get("available"):
        return f"结论：当前系统未查询到{label}数据范围。\n\n数据依据：{result.get('message') or '数据源不可用'}。"
    return (
        f"结论：当前{label}最新时间为 {result.get('max_datetime')}。\n\n"
        "数据依据：\n"
        f"1. 数据表：{result.get('table')}\n"
        f"2. 时间字段：{result.get('datetime_field')}\n"
        f"3. 数据范围：{result.get('min_datetime')} 至 {result.get('max_datetime')}\n"
        f"4. 记录数：{result.get('row_count')} 条\n"
        f"5. 缺失计数：{result.get('missing_count')}。"
    )


def answer_data_sql_query(result: dict[str, Any]) -> str:
    table = result.get("table_name") or "-"
    fields = result.get("fields") or result.get("columns") or []
    field_text = "、".join(str(field) for field in fields[:10]) if fields else "-"
    time_range = result.get("time_range") or {}
    range_start = time_range.get("start") or time_range.get("requested_start") or "-"
    range_end = time_range.get("end") or time_range.get("requested_end") or "-"
    time_field = time_range.get("field") or "-"
    query_summary = result.get("query_summary") or "执行只读查数。"
    if not result.get("available"):
        return (
            "结论：本次没有查到可用数据。\n\n"
            "查数口径：\n"
            f"1. 表名：{table}\n"
            f"2. 字段：{field_text}\n"
            f"3. 时间范围：{range_start} 至 {range_end}，时间字段 {time_field}\n"
            f"4. 查询摘要：{query_summary}\n"
            f"5. 查不到原因：{result.get('not_found_reason') or '未返回匹配记录'}。"
        )
    records = result.get("records") or []
    preview_lines: list[str] = []
    for idx, row in enumerate(records[:3], 1):
        pieces = []
        for key in (result.get("columns") or fields)[:5]:
            if key in row:
                pieces.append(f"{key}={row.get(key)}")
        preview_lines.append(f"{idx}. " + "；".join(pieces))
    preview = "\n".join(preview_lines) if preview_lines else "已返回记录，但无可展示字段。"
    return (
        f"结论：已按只读 SQL 查到 {result.get('row_count') or len(records)} 条结果预览。\n\n"
        "查数口径：\n"
        f"1. 表名：{table}\n"
        f"2. 字段：{field_text}\n"
        f"3. 时间范围：{range_start} 至 {range_end}，时间字段 {time_field}\n"
        f"4. 查询摘要：{query_summary}\n\n"
        "结果预览：\n"
        f"{preview}"
    )


def answer_forecast_metric(result: dict[str, Any], intent: str) -> str:
    if not result.get("available"):
        return "结论：当前系统未查询到可用预测数据。\n\n建议：先运行今日分析或快速预测后再提问。"
    if intent == "forecast_max_price":
        return (
            f"结论：当前预测最高电价出现在 {result.get('max_time')}，约 {_money(result.get('max_price'))}。\n\n"
            f"数据依据：未来 24 小时均价约 {_money(result.get('avg_price'))}，P75 约 {_money(result.get('p75'))}，峰谷价差约 {_money(result.get('spread'))}。"
        )
    if intent == "forecast_min_price":
        return (
            f"结论：当前预测最低电价出现在 {result.get('min_time')}，约 {_money(result.get('min_price'))}。\n\n"
            f"数据依据：未来 24 小时均价约 {_money(result.get('avg_price'))}，P25 约 {_money(result.get('p25'))}，峰谷价差约 {_money(result.get('spread'))}。"
        )
    if intent == "forecast_avg_price":
        return f"结论：当前未来 24 小时预测均价约 {_money(result.get('avg_price'))}。\n\n数据依据：result_forward_24h_formal 最新预测结果。"
    return f"结论：当前预测峰谷价差约 {_money(result.get('spread'))}。\n\n数据依据：最高价 {_money(result.get('max_price'))}，最低价 {_money(result.get('min_price'))}。"
