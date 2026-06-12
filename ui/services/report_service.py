from __future__ import annotations

import json
import getpass
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

from automation_common import get_pipeline_paths, load_config
from database_utils import create_database_engine, get_database_config, test_database_connection
from ui.services.legacy_actions import CommandSpec, ROOT_DIR


REQUIRED_REPORT_KEYS = [
    "executive_summary",
    "market_overview",
    "next_24h_trend",
    "peak_risk",
    "operation_advice",
    "management_summary",
    "alert_message",
    "limitations",
]

REVIEW_TABLE = "ai_report_review_runs"
LEGACY_REVIEW_TABLE = "report_approval_runs"
REVIEW_STATUSES = {"pending", "approved", "rejected", "dispatched"}
STATUS_LABELS = {
    "pending": "待审核",
    "approved": "已通过",
    "rejected": "已驳回",
    "dispatched": "已派发",
}


class ReportService:
    def __init__(self):
        self.root_dir = ROOT_DIR

    def load_summary(self) -> dict[str, Any]:
        config = load_config()
        paths = get_pipeline_paths(config)
        ok, db_message = test_database_connection(config)
        db_enabled = get_database_config(config).enabled
        if ok and db_enabled:
            try:
                payload = self._load_from_database(config, paths)
                payload["source"] = f"数据库优先（{db_message}）"
                return self._attach_review_payload(payload)
            except Exception as exc:
                payload = self._load_from_local(paths)
                payload["source"] = f"本地文件降级（数据库读取失败：{exc}）"
                return self._attach_review_payload(payload)
        payload = self._load_from_local(paths)
        payload["source"] = f"本地文件降级（{db_message}）"
        return self._attach_review_payload(payload)

    def regenerate_command(self) -> CommandSpec:
        return CommandSpec(
            "重新生成 AI 报告",
            [sys.executable, "-X", "utf8", str(self.root_dir / "main_daily_run.py"), "--skip-prediction"],
        )

    def get_report_review_status(self, run_id: str) -> dict[str, Any]:
        run_id = str(run_id or "local_current")
        config = load_config()
        ok, _message = test_database_connection(config)
        if ok and get_database_config(config).enabled:
            try:
                engine = create_database_engine(config)
                with engine.begin() as conn:
                    self._ensure_review_table(conn)
                    row = conn.execute(
                        text(
                            f"""
                            SELECT run_id, report_path, review_status, reviewer, review_comment,
                                   reviewed_at, dispatch_allowed, created_at, updated_at
                            FROM {REVIEW_TABLE}
                            WHERE run_id = :run_id
                            ORDER BY id DESC
                            LIMIT 1
                            """
                        ),
                        {"run_id": run_id},
                    ).mappings().fetchone()
                    if row:
                        return self._normalize_review_status(dict(row))
            except Exception:
                pass
        return self._load_local_review_status(run_id)

    def save_report_review_status(self, run_id: str, status: str, reviewer: str = "", comment: str = "") -> dict[str, Any]:
        status = self._normalize_status(status)
        run_id = str(run_id or "local_current")
        reviewer = reviewer or getpass.getuser()
        paths = get_pipeline_paths(load_config())
        report_path = str(self._resolve_paths(paths, {"run_id": run_id}).get("word_report", ""))
        record = {
            "run_id": run_id,
            "report_path": report_path,
            "review_status": status,
            "reviewer": reviewer,
            "review_comment": comment,
            "reviewed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "dispatch_allowed": status in {"approved", "dispatched"},
        }
        config = load_config()
        ok, _message = test_database_connection(config)
        if ok and get_database_config(config).enabled:
            try:
                engine = create_database_engine(config)
                with engine.begin() as conn:
                    self._ensure_review_table(conn)
                    conn.execute(
                        text(
                            f"""
                            INSERT INTO {REVIEW_TABLE}
                                (run_id, report_path, review_status, reviewer, review_comment,
                                 reviewed_at, dispatch_allowed, created_at, updated_at)
                            VALUES
                                (:run_id, :report_path, :review_status, :reviewer, :review_comment,
                                 :reviewed_at, :dispatch_allowed, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                            ON DUPLICATE KEY UPDATE
                                report_path = VALUES(report_path),
                                review_status = VALUES(review_status),
                                reviewer = VALUES(reviewer),
                                review_comment = VALUES(review_comment),
                                reviewed_at = VALUES(reviewed_at),
                                dispatch_allowed = VALUES(dispatch_allowed),
                                updated_at = CURRENT_TIMESTAMP
                            """
                        ),
                        record,
                    )
                record["storage"] = "database"
                return self._normalize_review_status(record)
            except Exception as exc:
                record["storage_error"] = str(exc)
        saved = self._save_local_review_status(record)
        saved["storage"] = "local_json"
        return saved

    def approve_report(self, run_id: str, reviewer: str = "", comment: str = "") -> dict[str, Any]:
        return self.save_report_review_status(run_id, "approved", reviewer, comment)

    def reject_report(self, run_id: str, reviewer: str = "", comment: str = "") -> dict[str, Any]:
        return self.save_report_review_status(run_id, "rejected", reviewer, comment)

    def mark_report_pending(self, run_id: str, reviewer: str = "", comment: str = "") -> dict[str, Any]:
        return self.save_report_review_status(run_id, "pending", reviewer, comment)

    def mark_report_dispatched(self, run_id: str, reviewer: str = "", comment: str = "") -> dict[str, Any]:
        check = self.can_dispatch_report(run_id)
        if not check.get("allowed"):
            return {"success": False, "message": "派发条件未通过：" + "；".join(check.get("reasons", [])), "dispatch_check": check}
        status = self.save_report_review_status(run_id, "dispatched", reviewer, comment)
        return {"success": True, "message": "报告已标记为已派发。", "review": status, "dispatch_check": check}

    def can_dispatch_report(self, run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or self._load_report_payload_for_run(run_id)
        review = payload.get("review") or self.get_report_review_status(run_id)
        quality = payload.get("quality") or self.run_report_trust_check(run_id)
        paths_map = payload.get("paths") or {}
        word_path = Path(str(paths_map.get("word_report") or ""))
        reasons: list[str] = []
        status = str(review.get("review_status") or "pending")
        if status not in {"approved", "dispatched"}:
            reasons.append(f"当前审批状态为“{STATUS_LABELS.get(status, status)}”，不是已通过。")
        if quality.get("overall") == "失败" or any(item.get("status") == "FAIL" for item in quality.get("checks", [])):
            reasons.append("报告可信检查存在失败项。")
        if not word_path.exists():
            reasons.append("Word 报告文件不存在。")
        return {
            "allowed": not reasons,
            "reasons": reasons,
            "review_status": status,
            "quality_overall": quality.get("overall", "-"),
            "word_report": str(word_path),
        }

    def run_report_trust_check(self, run_id: str) -> dict[str, Any]:
        payload = self._load_report_payload_for_run(run_id)
        return payload.get("quality") or {"overall": "失败", "checks": [{"status": "FAIL", "item": "报告读取", "message": "无法读取报告数据。"}]}

    def _load_from_database(self, config: dict[str, Any], paths) -> dict[str, Any]:
        engine = create_database_engine(config)
        with engine.connect() as conn:
            history = pd.read_sql(
                text(
                    """
                    SELECT id, run_id, run_mode, generated_at, risk_level,
                           generator_provider, generator_model, generator_mode,
                           word_report_path, word_report_size_bytes
                    FROM ai_report_runs
                    ORDER BY id DESC
                    LIMIT 100
                    """
                ),
                conn,
            )
            latest_row = {}
            if not history.empty:
                latest_id = int(history.iloc[0]["id"])
                row = conn.execute(
                    text("SELECT * FROM ai_report_runs WHERE id = :id"),
                    {"id": latest_id},
                ).mappings().fetchone()
                latest_row = dict(row) if row else {}

            summary_row = None
            if latest_row.get("run_id"):
                summary_row = conn.execute(
                    text(
                        """
                        SELECT *
                        FROM ai_input_summary_runs
                        WHERE run_id = :run_id
                        ORDER BY id DESC
                        LIMIT 1
                        """
                    ),
                    {"run_id": latest_row["run_id"]},
                ).mappings().fetchone()
            if not summary_row:
                summary_row = conn.execute(
                    text("SELECT * FROM ai_input_summary_runs ORDER BY id DESC LIMIT 1")
                ).mappings().fetchone()
            history = self._attach_database_review_history(history, conn)
        latest = self._normalize_report(latest_row)
        input_summary = self._parse_summary_row(dict(summary_row) if summary_row else {})
        paths_map = self._resolve_paths(paths, latest)
        quality = self.quality_check(latest, input_summary, paths_map)
        return {
            "latest": latest,
            "history": history,
            "input_summary": input_summary,
            "paths": paths_map,
            "quality": quality,
            "empty_message": "" if latest else "当前未发现 AI 报告记录。",
        }

    def _load_from_local(self, paths) -> dict[str, Any]:
        report_path = paths.current_dir / "ai_report_structured.json"
        summary_path = paths.current_dir / "ai_input_summary.json"
        report = self._read_json(report_path)
        summary = self._read_json(summary_path)
        latest = self._normalize_report(report)
        latest.setdefault("run_id", summary.get("run_id", "local_current"))
        latest.setdefault("generated_at", report_path.stat().st_mtime if report_path.exists() else "")
        latest["word_report_path"] = str(paths.current_dir / "电价智能分析综合报告.docx")
        latest["generator_mode"] = (report.get("generator") or {}).get("mode", "")
        latest["generator_model"] = (report.get("generator") or {}).get("model", "")
        latest["generator_provider"] = (report.get("generator") or {}).get("provider", "")
        history = self._attach_local_review_history(self._local_history(paths))
        paths_map = self._resolve_paths(paths, latest)
        return {
            "latest": latest,
            "history": history,
            "input_summary": summary,
            "paths": paths_map,
            "quality": self.quality_check(latest, summary, paths_map),
            "empty_message": "" if latest else "当前未发现本地 AI 报告文件。",
        }

    def _attach_review_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        latest = payload.get("latest") or {}
        run_id = str(latest.get("run_id") or "local_current")
        review = self.get_report_review_status(run_id)
        payload["review"] = review
        payload["dispatch_check"] = self.can_dispatch_report(run_id, payload={**payload, "review": review})
        return payload

    def _load_report_payload_for_run(self, run_id: str) -> dict[str, Any]:
        config = load_config()
        paths = get_pipeline_paths(config)
        ok, _message = test_database_connection(config)
        if ok and get_database_config(config).enabled and run_id:
            try:
                engine = create_database_engine(config)
                with engine.connect() as conn:
                    report_row = conn.execute(
                        text("SELECT * FROM ai_report_runs WHERE run_id = :run_id ORDER BY id DESC LIMIT 1"),
                        {"run_id": run_id},
                    ).mappings().fetchone()
                    summary_row = conn.execute(
                        text("SELECT * FROM ai_input_summary_runs WHERE run_id = :run_id ORDER BY id DESC LIMIT 1"),
                        {"run_id": run_id},
                    ).mappings().fetchone()
                latest = self._normalize_report(dict(report_row) if report_row else {})
                summary = self._parse_summary_row(dict(summary_row) if summary_row else {})
                if latest or summary:
                    paths_map = self._resolve_paths(paths, latest)
                    return {
                        "latest": latest,
                        "input_summary": summary,
                        "paths": paths_map,
                        "quality": self.quality_check(latest, summary, paths_map),
                    }
            except Exception:
                pass
        local = self._load_from_local(paths)
        local["review"] = self.get_report_review_status(str((local.get("latest") or {}).get("run_id") or run_id or "local_current"))
        return local

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _normalize_report(row: dict[str, Any]) -> dict[str, Any]:
        if not row:
            return {}
        report = dict(row)
        if "report_json" in report and isinstance(report["report_json"], str) and report["report_json"].strip():
            try:
                merged = json.loads(report["report_json"])
                merged.update({k: v for k, v in report.items() if k not in merged or v not in {None, ""}})
                report = merged
            except Exception:
                pass
        if isinstance(report.get("operation_advice_json"), str):
            try:
                report["operation_advice"] = json.loads(report["operation_advice_json"])
            except Exception:
                report["operation_advice"] = report["operation_advice_json"]
        return report

    @staticmethod
    def _parse_summary_row(row: dict[str, Any]) -> dict[str, Any]:
        if not row:
            return {}
        if isinstance(row.get("summary_json"), str) and row["summary_json"].strip():
            try:
                return json.loads(row["summary_json"])
            except Exception:
                pass
        return row

    def _local_history(self, paths) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        current_summary = self._read_json(paths.current_dir / "ai_input_summary.json")
        current_run_id = str(current_summary.get("run_id") or "current")
        if paths.current_dir.exists():
            doc = paths.current_dir / "电价智能分析综合报告.docx"
            if doc.exists():
                rows.append(
                    {
                        "run_id": current_run_id,
                        "generated_at": pd.to_datetime(doc.stat().st_mtime, unit="s"),
                        "risk_level": "",
                        "generator_mode": "local_current",
                        "word_report_path": str(doc),
                    }
                )
        if paths.final_output_root_dir.exists():
            for folder in sorted(paths.final_output_root_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:50]:
                report_dir = folder / "02_AI报告"
                doc = report_dir / "电价智能分析综合报告.docx"
                if doc.exists():
                    rows.append(
                        {
                            "run_id": folder.name.split("_电价预测运行结果")[0],
                            "generated_at": pd.to_datetime(doc.stat().st_mtime, unit="s"),
                            "risk_level": "",
                            "generator_mode": "archive",
                            "word_report_path": str(doc),
                        }
                    )
        return pd.DataFrame(rows)

    @staticmethod
    def _resolve_paths(paths, latest: dict[str, Any]) -> dict[str, str]:
        current_json = paths.current_dir / "ai_report_structured.json"
        current_summary = paths.current_dir / "ai_input_summary.json"
        raw_word_path = str(latest.get("word_report_path") or "").strip()
        word_path = Path(raw_word_path) if raw_word_path else paths.current_dir / "电价智能分析综合报告.docx"
        if not word_path.exists() or word_path.is_dir():
            word_path = paths.current_dir / "电价智能分析综合报告.docx"
        return {
            "word_report": str(word_path),
            "report_json": str(current_json),
            "input_summary": str(current_summary),
        }

    def _attach_database_review_history(self, history: pd.DataFrame, conn) -> pd.DataFrame:
        if history is None or history.empty or "run_id" not in history.columns:
            return history
        try:
            self._ensure_review_table(conn)
            review_df = pd.read_sql(
                text(
                    f"""
                    SELECT run_id, review_status, reviewer, review_comment, reviewed_at, dispatch_allowed
                    FROM {REVIEW_TABLE}
                    """
                ),
                conn,
            )
            if review_df.empty:
                return self._attach_local_review_history(history)
            merged = history.merge(review_df.drop_duplicates(subset=["run_id"], keep="last"), on="run_id", how="left")
            return self._fill_review_columns(merged)
        except Exception:
            return self._attach_local_review_history(history)

    def _attach_local_review_history(self, history: pd.DataFrame) -> pd.DataFrame:
        if history is None or history.empty or "run_id" not in history.columns:
            return history
        output = history.copy()
        records = [self.get_report_review_status(str(run_id)) for run_id in output["run_id"].tolist()]
        output["review_status"] = [item.get("review_status", "pending") for item in records]
        output["审批状态"] = [item.get("status_label", "待审核") for item in records]
        output["reviewer"] = [item.get("reviewer", "") for item in records]
        output["reviewed_at"] = [item.get("reviewed_at", "") for item in records]
        output["dispatch_allowed"] = [item.get("dispatch_allowed", False) for item in records]
        return output

    @staticmethod
    def _fill_review_columns(history: pd.DataFrame) -> pd.DataFrame:
        output = history.copy()
        if "review_status" not in output.columns:
            output["review_status"] = "pending"
        output["review_status"] = output["review_status"].fillna("pending")
        output["审批状态"] = output["review_status"].map(lambda value: STATUS_LABELS.get(str(value), "待审核"))
        if "reviewer" not in output.columns:
            output["reviewer"] = ""
        if "reviewed_at" not in output.columns:
            output["reviewed_at"] = ""
        if "dispatch_allowed" not in output.columns:
            output["dispatch_allowed"] = False
        return output

    @staticmethod
    def _ensure_review_table(conn) -> None:
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {REVIEW_TABLE} (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    run_id VARCHAR(64) NOT NULL,
                    report_path VARCHAR(500) NULL,
                    review_status VARCHAR(32) DEFAULT 'pending',
                    reviewer VARCHAR(128) NULL,
                    review_comment TEXT NULL,
                    reviewed_at DATETIME NULL,
                    dispatch_allowed TINYINT(1) DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_ai_report_review_run_id (run_id),
                    INDEX idx_ai_report_review_status (review_status),
                    INDEX idx_ai_report_review_reviewed_at (reviewed_at)
                )
                """
            )
        )

    def _load_local_review_status(self, run_id: str) -> dict[str, Any]:
        paths = get_pipeline_paths(load_config())
        for path in self._local_review_paths(run_id):
            data = self._read_json(path)
            if data and (str(data.get("run_id") or "") == run_id or path.name != "ai_report_review_status.json"):
                return self._normalize_review_status(data)
        return self._normalize_review_status({"run_id": run_id, "review_status": "pending", "dispatch_allowed": False})

    def _save_local_review_status(self, record: dict[str, Any]) -> dict[str, Any]:
        run_id = str(record.get("run_id") or "local_current")
        paths = get_pipeline_paths(load_config())
        review_root = paths.current_dir.parent / "review_status"
        paths.current_dir.mkdir(parents=True, exist_ok=True)
        review_root.mkdir(parents=True, exist_ok=True)
        record = self._normalize_review_status(record)
        for path in [paths.current_dir / "ai_report_review_status.json", review_root / f"{self._safe_filename(run_id)}.json"]:
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return record

    @staticmethod
    def _safe_filename(value: str) -> str:
        return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)[:120] or "local_current"

    def _local_review_paths(self, run_id: str) -> list[Path]:
        paths = get_pipeline_paths(load_config())
        return [
            paths.current_dir.parent / "review_status" / f"{self._safe_filename(run_id)}.json",
            paths.current_dir / "ai_report_review_status.json",
        ]

    @staticmethod
    def _normalize_status(status: str) -> str:
        value = str(status or "pending").strip().lower()
        return value if value in REVIEW_STATUSES else "pending"

    @staticmethod
    def _normalize_review_status(record: dict[str, Any]) -> dict[str, Any]:
        status = ReportService._normalize_status(str(record.get("review_status") or record.get("approval_status") or "pending"))
        dispatch_allowed = record.get("dispatch_allowed")
        if isinstance(dispatch_allowed, str):
            dispatch_allowed = dispatch_allowed.strip().lower() in {"1", "true", "yes", "y", "已允许"}
        return {
            "run_id": str(record.get("run_id") or "local_current"),
            "report_path": str(record.get("report_path") or ""),
            "review_status": status,
            "status_label": STATUS_LABELS.get(status, "待审核"),
            "reviewer": str(record.get("reviewer") or ""),
            "review_comment": str(record.get("review_comment") or ""),
            "reviewed_at": str(record.get("reviewed_at") or ""),
            "dispatch_allowed": bool(dispatch_allowed) or status in {"approved", "dispatched"},
            "created_at": str(record.get("created_at") or ""),
            "updated_at": str(record.get("updated_at") or ""),
            "storage": str(record.get("storage") or ""),
        }

    def quality_check(self, report: dict[str, Any], summary: dict[str, Any], paths_map: dict[str, str] | None = None) -> dict[str, Any]:
        checks: list[dict[str, str]] = []
        paths_map = paths_map or {}
        forecast = summary.get("forecast_summary") or {}
        facts = summary.get("report_facts") or {}
        max_hour = forecast.get("next_24h_max_hour") or facts.get("max_hour")
        min_hour = forecast.get("next_24h_min_hour") or facts.get("min_hour")
        risk_hours = forecast.get("top_risk_hours") or facts.get("risk_hours") or report.get("key_hours")
        generator = report.get("generator") or {}
        generator_mode = str(report.get("generator_mode") or generator.get("mode") or "")
        report_text = json.dumps(report, ensure_ascii=False, default=str)

        self._append_check(checks, self._path_exists(paths_map.get("report_json")), "结构化报告 JSON", "ai_report_structured.json 已存在。", "缺少 ai_report_structured.json。")
        self._append_check(checks, self._path_exists(paths_map.get("input_summary")), "AI 输入摘要 JSON", "ai_input_summary.json 已存在。", "缺少 ai_input_summary.json。")
        self._append_check(checks, self._path_exists(paths_map.get("word_report")), "Word 报告", "Word 报告已存在。", "缺少 Word 报告文件。")

        self._append_check(checks, bool(max_hour and min_hour), "最高价/最低价时段", "最高价和最低价时段已存在。", "缺少最高价或最低价时段。")
        self._append_check(checks, bool(risk_hours), "风险时段", "风险时段已存在。", "缺少风险时段。")
        self._append_check(checks, "最高" in report_text and (str(max_hour) in report_text if max_hour else True), "报告最高价内容", "报告正文包含最高价信息。", "报告正文缺少最高价信息。")
        self._append_check(checks, "最低" in report_text and (str(min_hour) in report_text if min_hour else True), "报告最低价内容", "报告正文包含最低价信息。", "报告正文缺少最低价信息。")
        self._append_check(checks, bool(report.get("next_24h_trend")) or "未来24" in report_text, "未来24小时趋势", "报告包含未来24小时趋势。", "报告缺少未来24小时趋势。")
        self._append_check(checks, bool(report.get("operation_advice")) or "建议" in report_text, "操作建议", "报告包含操作建议。", "报告缺少操作建议。")
        if "fallback" in generator_mode.lower():
            checks.append({"status": "WARNING", "item": "fallback 生成", "message": f"报告包含 fallback 生成段：{generator_mode}"})
        else:
            checks.append({"status": "PASS", "item": "fallback 生成", "message": f"当前生成模式：{generator_mode or '-'}"})

        missing = [key for key in REQUIRED_REPORT_KEYS if not report.get(key)]
        if missing:
            checks.append({"status": "FAIL", "item": "关键字段", "message": "缺失字段：" + ", ".join(missing)})
        else:
            checks.append({"status": "PASS", "item": "关键字段", "message": "关键报告字段完整。"})

        numeric_warnings = self._numeric_consistency_warnings(report_text, forecast, facts)
        if numeric_warnings:
            checks.append({"status": "WARNING", "item": "关键数值一致性", "message": "；".join(numeric_warnings)})
        else:
            checks.append({"status": "PASS", "item": "关键数值一致性", "message": "关键价格数值与预测摘要基本一致。"})

        if any(item["status"] == "FAIL" for item in checks):
            overall = "失败"
        elif any(item["status"] == "WARNING" for item in checks):
            overall = "警告"
        else:
            overall = "通过"
        return {"overall": overall, "checks": checks}

    @staticmethod
    def _append_check(checks: list[dict[str, str]], passed: bool, item: str, ok_message: str, bad_message: str) -> None:
        checks.append({"status": "PASS" if passed else "FAIL", "item": item, "message": ok_message if passed else bad_message})

    @staticmethod
    def _numeric_consistency_warnings(report_text: str, forecast: dict[str, Any], facts: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        candidates = {
            "最高价": forecast.get("next_24h_max_price") or facts.get("max_price"),
            "最低价": forecast.get("next_24h_min_price") or facts.get("min_price"),
            "均价": forecast.get("next_24h_avg_price") or facts.get("avg_price"),
        }
        for label, value in candidates.items():
            number = ReportService._safe_float(value)
            if number is None:
                continue
            compact = f"{number:.2f}"
            rounded = f"{number:.1f}"
            if compact not in report_text and rounded not in report_text:
                warnings.append(f"{label} {compact} 未在报告正文中明确出现")
        return warnings

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value is None or pd.isna(value):
                return None
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _path_exists(value: Any) -> bool:
        text_value = str(value or "").strip()
        return bool(text_value) and Path(text_value).exists()
