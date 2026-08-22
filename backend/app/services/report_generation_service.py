from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app.config import PROJECT_ROOT
from backend.app.repositories.base import dumps_json, loads_json, mapping_dict
from backend.app.source_contract import resolve_forecast_source


REPORT_SCHEMA_VERSION = "phase5.c.operation-report.v1"
REPORT_TYPES = frozenset({"daily", "weekly", "operation_decision"})


class ReportGenerationError(RuntimeError):
    """Raised when a report cannot be grounded in a complete forecast fact."""


def _iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _number(value: Any, *, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ReportGenerationError(f"{field} 缺失或不是数值") from exc
    if not math.isfinite(result):
        raise ReportGenerationError(f"{field} 包含 NaN 或 Inf")
    return result


def _canonical_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_report_type(value: str) -> str:
    report_type = str(value or "daily").strip().lower()
    if report_type not in REPORT_TYPES:
        raise ReportGenerationError(f"不支持的报告类型：{report_type}")
    return report_type


def _safe_report_id(run_id: str, report_type: str) -> str:
    safe_run = re.sub(r"[^A-Za-z0-9_-]", "_", run_id)[:80]
    return f"p5c_{report_type}_{safe_run}"


def _public_hour(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "forecast_time": _iso(row.get("datetime") or row.get("forecast_time")),
        "predicted_price": round(_number(row.get("predicted_price"), field="predicted_price"), 6),
        "spike_risk_prob": round(_number(row.get("spike_risk_prob") or row.get("spike_probability") or 0, field="spike_risk_prob"), 6),
    }


def build_operational_report(
    run: dict[str, Any],
    rows: list[dict[str, Any]],
    source_meta: dict[str, Any],
    *,
    report_id: str,
    report_type: str,
    region: str,
    report_date: str | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic decision-support report from one forecast run."""

    if str(run.get("status") or "").lower() != "success":
        raise ReportGenerationError("报告只能绑定 success 预测批次")
    if len(rows) != 24 or int(run.get("record_count") or 0) != 24:
        raise ReportGenerationError("报告要求 forecast run 与结果均恰好为 24 行")
    run_id = str(run.get("run_id") or "").strip()
    required_identity = ("model_version", "feature_version", "schema_hash", "result_hash")
    missing = [field for field in required_identity if not str(run.get(field) or "").strip()]
    if not run_id or missing:
        raise ReportGenerationError("预测身份不完整：" + ",".join(missing or ["run_id"]))

    public_rows = [_public_hour(row) for row in rows]
    if len({row["forecast_time"] for row in public_rows}) != 24:
        raise ReportGenerationError("预测时间轴缺失或重复")
    prices = [row["predicted_price"] for row in public_rows]
    sorted_high = sorted(public_rows, key=lambda item: item["predicted_price"], reverse=True)
    sorted_low = sorted(public_rows, key=lambda item: item["predicted_price"])
    spike_hours = [row for row in public_rows if row["spike_risk_prob"] >= 0.5]
    negative_hours = [row for row in public_rows if row["predicted_price"] < 0]
    peak_valley_spread = max(prices) - min(prices)
    stale = bool(source_meta.get("is_stale"))

    recommendations: list[dict[str, Any]] = []
    if stale:
        recommendations.append(
            {
                "priority": "critical",
                "action": "刷新预测后再形成实时运营或交易判断",
                "reason": "当前预测窗口已过期，本报告只能用于流程验证和历史审计",
                "evidence": {"stale_reason": source_meta.get("stale_reason"), "forecast_end_at": _iso(run.get("forecast_end_at"))},
            }
        )
    if spike_hours:
        recommendations.append(
            {
                "priority": "high",
                "action": "对尖峰风险时段增加人工复核并核对负荷、天气和市场事件",
                "reason": f"检测到 {len(spike_hours)} 个 spike_risk_prob≥0.5 的时段",
                "evidence": {"hours": [row["forecast_time"] for row in spike_hours[:6]]},
            }
        )
    if peak_valley_spread > 0:
        recommendations.append(
            {
                "priority": "medium",
                "action": "结合合同、偏差考核和设备约束评估移峰填谷空间",
                "reason": f"预测峰谷价差为 {peak_valley_spread:.2f}",
                "evidence": {"peak_hours": sorted_high[:3], "valley_hours": sorted_low[:3]},
            }
        )
    if negative_hours:
        recommendations.append(
            {
                "priority": "high",
                "action": "复核负电价时段的数据质量和市场约束，禁止仅凭单一模型自动交易",
                "reason": f"预测包含 {len(negative_hours)} 个负电价时段",
                "evidence": {"hours": negative_hours[:6]},
            }
        )
    recommendations.append(
        {
            "priority": "guardrail",
            "action": "所有建议须经人工审核，系统不得自动下单或宣称已实现收益",
            "reason": "PHASE5-C 为运营决策支持报告，不是交易执行或 PHASE5-D 策略状态机",
            "evidence": {"report_schema_version": REPORT_SCHEMA_VERSION},
        }
    )

    generated = generated_at or datetime.now(timezone.utc)
    forecast_day = str(public_rows[0]["forecast_time"] or "")[:10]
    effective_report_date = str(report_date or forecast_day or date.today().isoformat())
    payload: dict[str, Any] = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "report_id": report_id,
        "report_type": _safe_report_type(report_type),
        "title": f"电力运营决策支持报告（{effective_report_date}）",
        "report_date": effective_report_date,
        "region": str(region or "模型覆盖市场").strip() or "模型覆盖市场",
        "status": "ready",
        "generated_at": _iso(generated),
        "source": {
            "source_type": source_meta.get("source_type"),
            "domain": source_meta.get("domain"),
            "run_id": run_id,
            "input_batch_id": run.get("input_batch_id"),
            "model_version": run.get("model_version"),
            "feature_version": run.get("feature_version"),
            "schema_hash": run.get("schema_hash"),
            "artifact_id": run.get("artifact_id"),
            "artifact_hash": run.get("artifact_hash"),
            "result_hash": run.get("result_hash"),
            "forecast_start_at": _iso(run.get("forecast_start_at")),
            "forecast_end_at": _iso(run.get("forecast_end_at")),
            "is_stale": stale,
            "stale_reason": source_meta.get("stale_reason"),
        },
        "executive_summary": {
            "record_count": 24,
            "average_price": round(sum(prices) / len(prices), 6),
            "maximum_price": round(max(prices), 6),
            "minimum_price": round(min(prices), 6),
            "peak_valley_spread": round(peak_valley_spread, 6),
            "spike_risk_hour_count": len(spike_hours),
            "negative_price_hour_count": len(negative_hours),
            "current_use_allowed": not stale,
        },
        "key_windows": {
            "highest_price_hours": sorted_high[:3],
            "lowest_price_hours": sorted_low[:3],
            "spike_risk_hours": spike_hours,
            "negative_price_hours": negative_hours,
        },
        "decision_support": recommendations,
        "evidence": [
            {"table": "forecast_runs", "run_id": run_id, "result_hash": run.get("result_hash")},
            {"table": "forecast_results", "run_id": run_id, "record_count": 24},
            {"table": "model_registry", "model_version": run.get("model_version"), "artifact_hash": run.get("artifact_hash")},
        ],
        "limitations": [
            "报告数值为模型预测，不是成交价或自动交易指令。",
            "报告未使用未来实际值验证本批次误差。",
            "过期预测只可用于历史审计和流程验证。" if stale else "报告使用当前 latest_success 批次，仍需人工复核外部市场事件。",
        ],
    }
    payload["report_hash"] = _canonical_hash(payload)
    return payload


def render_report_markdown(report: dict[str, Any]) -> str:
    summary = report["executive_summary"]
    source = report["source"]
    lines = [
        f"# {report['title']}",
        "",
        f"- 报告 ID：`{report['report_id']}`",
        f"- 预测 run_id：`{source['run_id']}`",
        f"- 模型/特征版本：`{source['model_version']}` / `{source['feature_version']}`",
        f"- source_type：`{source['source_type']}`",
        f"- stale：`{str(source['is_stale']).lower()}`（{source.get('stale_reason') or '-'}）",
        f"- 报告 SHA-256：`{report['report_hash']}`",
        "",
        "## 执行摘要",
        "",
        f"24 小时均价 {summary['average_price']:.2f}，最高 {summary['maximum_price']:.2f}，最低 {summary['minimum_price']:.2f}，峰谷价差 {summary['peak_valley_spread']:.2f}。",
        f"尖峰风险时段 {summary['spike_risk_hour_count']} 个，负电价时段 {summary['negative_price_hour_count']} 个。",
        "",
        "## 运营决策支持",
        "",
    ]
    for item in report["decision_support"]:
        lines.append(f"- [{item['priority']}] {item['action']}；依据：{item['reason']}。")
    lines += ["", "## 证据", ""]
    for item in report["evidence"]:
        lines.append("- " + json.dumps(item, ensure_ascii=False, sort_keys=True, default=str))
    lines += ["", "## 限制", ""]
    lines.extend(f"- {item}" for item in report["limitations"])
    return "\n".join(lines) + "\n"


def _existing_report(engine: Engine, report_id: str) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT report_id, run_id, title, status, report_type, file_path,
                       metadata_json, content_json, generated_at, created_at, updated_at
                FROM report_runs WHERE report_id = :report_id
                """
            ),
            {"report_id": report_id},
        ).mappings().first()
    return mapping_dict(row) if row else None


def generate_operational_report(
    engine: Engine,
    *,
    run_id: str = "latest",
    report_type: str = "daily",
    region: str = "模型覆盖市场",
    report_date: str | None = None,
    output_root: Path | None = None,
    failure_inject: str | None = None,
) -> dict[str, Any]:
    safe_type = _safe_report_type(report_type)
    run, rows, source_meta = resolve_forecast_source(run_id, engine=engine)
    if not rows:
        raise ReportGenerationError(str(source_meta.get("unavailable_reason") or "没有可用于报告的完整预测批次"))
    resolved_run_id = str(run.get("run_id") or "")
    report_id = _safe_report_id(resolved_run_id, safe_type)
    existing = _existing_report(engine, report_id)
    if existing:
        metadata = loads_json(existing.get("metadata_json"), default={})
        content = loads_json(existing.get("content_json"), default={})
        if str(metadata.get("result_hash") or "") != str(run.get("result_hash") or ""):
            raise ReportGenerationError("报告 ID 已存在但预测 result_hash 不一致，拒绝覆盖")
        return {
            "available": True,
            "idempotent": True,
            "report_id": report_id,
            "run_id": resolved_run_id,
            "status": existing.get("status"),
            "title": existing.get("title"),
            "report_path": existing.get("file_path"),
            "json_path": metadata.get("json_path"),
            "report_hash": metadata.get("report_hash"),
            "summary": content,
            "source_type": metadata.get("source_type") or source_meta.get("source_type"),
            "is_stale": bool(metadata.get("is_stale", source_meta.get("is_stale"))),
            "stale_reason": metadata.get("stale_reason") or source_meta.get("stale_reason"),
        }

    report = build_operational_report(
        run,
        rows,
        source_meta,
        report_id=report_id,
        report_type=safe_type,
        region=region,
        report_date=report_date,
    )
    root = (output_root or (PROJECT_ROOT / "output" / "reports" / "phase5_c")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / f"{report_id}.json"
    markdown_path = root / f"{report_id}.md"
    if json_path.exists() or markdown_path.exists():
        raise ReportGenerationError("报告文件已存在但数据库无对应记录，拒绝覆盖")

    created_files: list[Path] = []
    try:
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        created_files.append(json_path)
        markdown_path.write_text(render_report_markdown(report), encoding="utf-8")
        created_files.append(markdown_path)
        if failure_inject == "before_persist":
            raise ReportGenerationError("INJECTED_BEFORE_PERSIST")
        metadata = {
            "report_schema_version": REPORT_SCHEMA_VERSION,
            "region": report["region"],
            "source_type": source_meta.get("source_type"),
            "is_stale": bool(source_meta.get("is_stale")),
            "stale_reason": source_meta.get("stale_reason"),
            "input_batch_id": run.get("input_batch_id"),
            "model_version": run.get("model_version"),
            "feature_version": run.get("feature_version"),
            "schema_hash": run.get("schema_hash"),
            "artifact_hash": run.get("artifact_hash"),
            "result_hash": run.get("result_hash"),
            "report_hash": report["report_hash"],
            "json_path": str(json_path),
        }
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    INSERT INTO report_runs (
                        report_id, run_id, title, status, report_type, file_path,
                        metadata_json, content_json, generated_at
                    ) VALUES (
                        :report_id, :run_id, :title, 'ready', :report_type, :file_path,
                        CAST(:metadata_json AS jsonb), CAST(:content_json AS jsonb), :generated_at
                    )
                    """
                ),
                {
                    "report_id": report_id,
                    "run_id": resolved_run_id,
                    "title": report["title"],
                    "report_type": safe_type,
                    "file_path": str(markdown_path),
                    "metadata_json": dumps_json(metadata),
                    "content_json": dumps_json(report),
                    "generated_at": datetime.fromisoformat(str(report["generated_at"]).replace("Z", "+00:00")),
                },
            )
            if result.rowcount != 1:
                raise ReportGenerationError("报告记录写入失败")
    except Exception:
        for path in reversed(created_files):
            path.unlink(missing_ok=True)
        raise

    return {
        "available": True,
        "idempotent": False,
        "report_id": report_id,
        "run_id": resolved_run_id,
        "status": "ready",
        "title": report["title"],
        "report_path": str(markdown_path),
        "json_path": str(json_path),
        "report_hash": report["report_hash"],
        "summary": report,
        "source_type": source_meta.get("source_type"),
        "is_stale": bool(source_meta.get("is_stale")),
        "stale_reason": source_meta.get("stale_reason"),
    }
