from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

from automation_common import get_pipeline_paths, load_config, save_config
from database_utils import create_database_engine, get_database_config, test_database_connection
from model_ops.active_model_loader import get_active_model_record, validate_artifact_files
from model_ops.auto_retrain_policy import check_model_degradation
from model_ops.error_memory import summarize_error_memory
from model_ops.strategy_memory import summarize_strategy_memory
from ui.services.legacy_actions import CommandSpec, ROOT_DIR


class ModelService:
    def __init__(self):
        self.root_dir = ROOT_DIR

    def load_summary(self) -> dict[str, Any]:
        config = load_config()
        paths = get_pipeline_paths(config)
        ok, db_message = test_database_connection(config)
        db_enabled = get_database_config(config).enabled
        local_summary = self._load_local_ai_summary(paths)
        if ok and db_enabled:
            try:
                payload = self._load_from_database(config, paths, local_summary, db_message)
                return self._attach_learning_summary(config, paths, payload)
            except Exception as exc:
                fallback = self._load_from_local(paths, local_summary)
                fallback["source"] = f"本地文件降级（数据库读取失败：{exc}）"
                return self._attach_learning_summary(config, paths, fallback)
        fallback = self._load_from_local(paths, local_summary)
        fallback["source"] = f"本地文件降级（{db_message}）"
        return self._attach_learning_summary(config, paths, fallback)

    def model_ops_command(self) -> CommandSpec:
        return CommandSpec(
            "每日模型运维",
            ["cmd.exe", "/c", f'set NO_PAUSE=1&& call "{self.root_dir / "run_model_ops_daily.bat"}"'],
        )

    def compare_command(self) -> CommandSpec:
        return CommandSpec(
            "候选模型与 Active 模型对比",
            [sys.executable, "-X", "utf8", str(self.root_dir / "07_compare_and_promote_model.py")],
        )

    def error_memory_command(self) -> CommandSpec:
        return CommandSpec(
            "更新模型误差记忆",
            [sys.executable, "-X", "utf8", str(self.root_dir / "12_update_error_memory.py")],
        )

    def retrain_command(self) -> CommandSpec:
        return CommandSpec(
            "完整训练并登记候选模型",
            [sys.executable, "-X", "utf8", str(self.root_dir / "main_daily_run.py"), "--retrain-model"],
        )

    def auto_optimize_command(self) -> CommandSpec:
        return CommandSpec(
            "执行模型自优化",
            [sys.executable, "-X", "utf8", str(self.root_dir / "main_daily_run.py"), "--model-auto-optimize"],
        )

    def promote_latest_candidate_command(self) -> CommandSpec:
        return CommandSpec(
            "最新候选模型设为 Active",
            [
                sys.executable,
                "-X",
                "utf8",
                str(self.root_dir / "07_compare_and_promote_model.py"),
                "--promote-latest-candidate",
                "--approved-by",
                "gui",
            ],
        )

    def toggle_bias_correction(self) -> dict[str, Any]:
        config = load_config()
        learning = config.setdefault("model_learning", {})
        enabled = bool(learning.get("bias_correction_enabled", True))
        learning["bias_correction_enabled"] = not enabled
        save_config(config)
        return {
            "bias_correction_enabled": not enabled,
            "message": "偏差校正已启用" if not enabled else "偏差校正已关闭",
        }

    def artifacts_dir(self) -> Path:
        return self.root_dir / "model_artifacts"

    def _attach_learning_summary(self, config: dict[str, Any], paths, payload: dict[str, Any]) -> dict[str, Any]:
        active = dict(payload.get("active") or {})
        availability = self._active_availability(config, paths, active)
        active.update(availability)
        payload["active"] = active

        model_version = str(active.get("model_version") or "").strip() or None
        payload["error_memory"] = self._safe_error_memory(config, model_version)
        payload["strategy_memory"] = self._safe_strategy_memory(config)
        payload["correction_effect"] = self._load_correction_effect(config, model_version)
        payload["self_learning"] = self._self_learning_summary(
            config,
            model_version,
            payload["error_memory"],
            payload["strategy_memory"],
        )
        payload["operation_times"] = self._load_operation_times(config)
        for key, value in payload["operation_times"].items():
            active[key] = value
        return payload

    def _active_availability(self, config: dict[str, Any], paths, active: dict[str, Any]) -> dict[str, Any]:
        record: dict[str, Any] = {}
        active_error = ""
        try:
            record = get_active_model_record(config)
        except Exception as exc:
            active_error = str(exc)

        source = record or active
        artifact_path = Path(str(source.get("artifact_path") or ""))
        if artifact_path and not artifact_path.is_absolute():
            artifact_path = paths.root_dir / artifact_path
        has_path = bool(str(source.get("artifact_path") or "").strip())
        missing = validate_artifact_files(artifact_path) if has_path else []
        artifact_complete = has_path and artifact_path.exists() and not missing
        is_active = str(source.get("is_active", "")).strip() in {"1", "True", "true"} or source.get("status") == "active"
        can_fast_forecast = bool(is_active and artifact_complete)
        return {
            "model_version": source.get("model_version") or active.get("model_version", ""),
            "artifact_path": str(artifact_path) if has_path else active.get("artifact_path", ""),
            "artifact_complete": "完整" if artifact_complete else ("未配置 artifact" if not has_path else "不完整"),
            "missing_files": "、".join(missing) if missing else ("-" if artifact_complete else active_error or "-"),
            "can_fast_forecast": "可用" if can_fast_forecast else "不可用",
            "active_load_error": active_error,
        }

    @staticmethod
    def _safe_error_memory(config: dict[str, Any], model_version: str | None) -> dict[str, Any]:
        try:
            return summarize_error_memory(config, model_version=model_version)
        except Exception as exc:
            return {"status": "unavailable", "sample_count": 0, "error": str(exc)}

    @staticmethod
    def _safe_strategy_memory(config: dict[str, Any]) -> dict[str, Any]:
        try:
            return summarize_strategy_memory(config)
        except Exception as exc:
            return {"status": "unavailable", "strategy_count": 0, "recommended_strategy": {}, "error": str(exc)}

    def _self_learning_summary(
        self,
        config: dict[str, Any],
        model_version: str | None,
        error_memory: dict[str, Any],
        strategy_memory: dict[str, Any],
    ) -> dict[str, Any]:
        learning = config.get("model_learning", {}) or {}
        enabled = bool(learning.get("bias_correction_enabled", True))
        policy = {"should_retrain": False, "retrain_reason": "数据库不可用或样本不足，暂未执行重训判断。", "recommended_strategy": {}}
        try:
            decision = check_model_degradation(config)
            policy = {
                "should_retrain": decision.should_retrain,
                "retrain_reason": decision.retrain_reason,
                "recommended_strategy": decision.recommended_strategy,
                "degradation_metrics": decision.degradation_metrics,
            }
        except Exception as exc:
            policy["retrain_reason"] = f"自动重训判断不可用：{exc}"
        return {
            "model_version": model_version or "-",
            "bias_correction_enabled": enabled,
            "bias_correction_status": "已启用" if enabled else "已关闭",
            "error_memory_status": error_memory.get("status", "empty"),
            "strategy_memory_status": strategy_memory.get("status", "empty"),
            "should_retrain": "建议重训" if policy.get("should_retrain") else "暂不需要",
            "retrain_reason": policy.get("retrain_reason", "-"),
            "recommended_strategy": policy.get("recommended_strategy") or {},
            "degradation_metrics": policy.get("degradation_metrics") or {},
        }

    def _load_operation_times(self, config: dict[str, Any]) -> dict[str, str]:
        defaults = {
            "latest_fast_forecast_time": "-",
            "latest_retrain_time": "-",
            "latest_auto_optimize_time": "-",
        }
        if not get_database_config(config).enabled:
            return defaults
        try:
            engine = create_database_engine(config)
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT run_mode, MAX(event_time) AS latest_time
                        FROM pipeline_run_events
                        WHERE run_mode IN (
                            'fast_forecast', 'refresh_fast_forecast',
                            'retrain_model', 'full', 'refresh_data', 'prediction_report_only',
                            'model_auto_optimize'
                        )
                        GROUP BY run_mode
                        """
                    )
                ).mappings().all()
            grouped = {str(row["run_mode"]): str(row["latest_time"]) for row in rows}
            defaults["latest_fast_forecast_time"] = grouped.get("refresh_fast_forecast") or grouped.get("fast_forecast") or "-"
            defaults["latest_retrain_time"] = (
                grouped.get("retrain_model")
                or grouped.get("refresh_data")
                or grouped.get("full")
                or grouped.get("prediction_report_only")
                or "-"
            )
            defaults["latest_auto_optimize_time"] = grouped.get("model_auto_optimize") or "-"
        except Exception:
            pass
        return defaults

    @staticmethod
    def _load_correction_effect(config: dict[str, Any], model_version: str | None) -> dict[str, Any]:
        if not model_version or not get_database_config(config).enabled:
            return {"status": "empty", "sample_count": 0}
        try:
            engine = create_database_engine(config)
            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT
                            COUNT(*) AS sample_count,
                            AVG(ABS(actual_price - predicted_price)) AS corrected_mae
                        FROM prediction_tracking
                        WHERE model_version = :model_version
                          AND actual_price IS NOT NULL
                        """
                    ),
                    {"model_version": model_version},
                ).mappings().fetchone()
            sample_count = int(row["sample_count"] or 0) if row else 0
            return {
                "status": "available" if sample_count else "empty",
                "sample_count": sample_count,
                "raw_mae": None,
                "corrected_mae": row["corrected_mae"] if row else None,
                "improvement_pct": None,
            }
        except Exception as exc:
            return {"status": "unavailable", "sample_count": 0, "error": str(exc)}

    def _load_from_database(
        self,
        config: dict[str, Any],
        paths,
        local_summary: dict[str, Any],
        db_message: str,
    ) -> dict[str, Any]:
        engine = create_database_engine(config)
        with engine.connect() as conn:
            registry = self._read_sql(
                conn,
                """
                SELECT *
                FROM model_registry
                ORDER BY is_active DESC, activated_at DESC, created_at DESC
                LIMIT 200
                """,
            )
            active = self._read_sql(conn, "SELECT * FROM vw_latest_active_model LIMIT 1")
            performance = self._read_sql(
                conn,
                """
                SELECT *
                FROM model_performance_daily
                ORDER BY metric_date DESC, updated_at DESC
                LIMIT 30
                """,
            )
            error_trend = self._read_sql(
                conn,
                """
                SELECT *
                FROM vw_recent_model_errors
                ORDER BY forecast_date DESC
                LIMIT 30
                """,
            )
            comparison = self._read_sql(
                conn,
                """
                SELECT comparison_id, candidate_model_version, active_model_version, decision, reason, created_at
                FROM model_comparison_runs
                ORDER BY created_at DESC
                LIMIT 30
                """,
            )
            if comparison.empty:
                comparison = self._read_sql(
                    conn,
                    """
                    SELECT run_id, model_version, decision, mae, rmse, peak_rmse, spike_rmse, created_at
                    FROM model_evaluation_runs
                    ORDER BY created_at DESC
                    LIMIT 30
                    """,
                )

        summary_metrics = self._metrics_from_summary(local_summary)
        active_model = self._normalize_active(active, performance, registry, summary_metrics, paths)
        metrics = self._merge_metrics(active_model, performance, summary_metrics)
        versions = registry if not registry.empty else self._versions_from_performance(performance, paths)
        if versions.empty:
            versions = self._versions_from_artifacts(paths)
        artifacts = self._artifact_rows(paths, registry)
        return {
            "source": f"数据库优先（{db_message}）",
            "active": active_model,
            "metrics": metrics,
            "versions": versions,
            "error_trend": error_trend,
            "comparison": comparison,
            "artifacts": artifacts,
            "empty_message": "" if not versions.empty or active_model else "当前未发现模型版本数据。",
        }

    def _load_from_local(self, paths, local_summary: dict[str, Any]) -> dict[str, Any]:
        metrics = self._metrics_from_summary(local_summary)
        versions = self._versions_from_artifacts(paths)
        active = {
            "model_version": metrics.get("final_model") or "本地摘要模型",
            "model_role": "forecast",
            "status": "local_summary",
            "is_active": "",
            "artifact_path": str(paths.root_dir / "model_artifacts"),
            "created_at": local_summary.get("generated_at", ""),
            "activated_at": "",
            "source": "ai_input_summary.json",
        } if metrics else {}
        return {
            "source": "本地文件",
            "active": active,
            "metrics": metrics,
            "versions": versions,
            "error_trend": pd.DataFrame(),
            "comparison": pd.DataFrame(),
            "artifacts": self._artifact_rows(paths, pd.DataFrame()),
            "empty_message": "" if metrics or not versions.empty else "当前未发现模型 registry 或 artifact 数据。",
        }

    @staticmethod
    def _read_sql(conn, query: str) -> pd.DataFrame:
        try:
            return pd.read_sql(text(query), conn)
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def _load_local_ai_summary(paths) -> dict[str, Any]:
        path = paths.current_dir / "ai_input_summary.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    @staticmethod
    def _metrics_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
        model = summary.get("model_summary") or {}
        peak = summary.get("peak_special_summary") or {}
        if not model and not peak:
            return {}
        return {
            "final_model": model.get("final_model") or peak.get("model"),
            "mae": model.get("mae") or peak.get("overall_mae"),
            "rmse": model.get("rmse") or peak.get("overall_rmse"),
            "mape": model.get("mape_pct"),
            "r2": model.get("r2"),
            "peak_rmse": peak.get("peak_rmse"),
            "spike_rmse": peak.get("spike_rmse"),
        }

    def _normalize_active(
        self,
        active: pd.DataFrame,
        performance: pd.DataFrame,
        registry: pd.DataFrame,
        summary_metrics: dict[str, Any],
        paths,
    ) -> dict[str, Any]:
        if not active.empty:
            row = active.iloc[0].to_dict()
            row["source"] = "model_registry"
            return row
        if not registry.empty:
            row = registry.iloc[0].to_dict()
            row["source"] = "model_registry_candidate"
            return row
        if not performance.empty:
            row = performance.iloc[0].to_dict()
            row.update(
                {
                    "model_role": "forecast",
                    "status": "derived_from_prediction_tracking",
                    "is_active": "",
                    "artifact_path": str(paths.root_dir / "model_artifacts"),
                    "activated_at": "",
                    "source": "model_performance_daily",
                }
            )
            return row
        if summary_metrics:
            return {
                "model_version": summary_metrics.get("final_model") or "本地摘要模型",
                "model_role": "forecast",
                "status": "local_summary",
                "artifact_path": str(paths.root_dir / "model_artifacts"),
                "source": "ai_input_summary.json",
            }
        return {}

    @staticmethod
    def _merge_metrics(active: dict[str, Any], performance: pd.DataFrame, summary_metrics: dict[str, Any]) -> dict[str, Any]:
        metrics = dict(summary_metrics)
        if active:
            for key, column in [
                ("mae", "test_mae"),
                ("rmse", "test_rmse"),
                ("peak_rmse", "peak_rmse"),
                ("spike_rmse", "spike_rmse"),
            ]:
                value = active.get(column)
                if value not in {None, ""}:
                    metrics[key] = value
        if not performance.empty:
            row = performance.iloc[0].to_dict()
            for key in ["mae", "rmse", "mape", "peak_rmse", "spike_rmse"]:
                if row.get(key) not in {None, ""}:
                    metrics[key] = row.get(key)
        return metrics

    @staticmethod
    def _versions_from_performance(performance: pd.DataFrame, paths) -> pd.DataFrame:
        if performance.empty:
            return pd.DataFrame()
        df = performance.copy()
        df["status"] = "performance_only"
        df["artifact_path"] = str(paths.root_dir / "model_artifacts")
        return df

    @staticmethod
    def _versions_from_artifacts(paths) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        root = paths.root_dir / "model_artifacts"
        if not root.exists():
            return pd.DataFrame()
        for child in sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True):
            manifest_path = child / "manifest.json"
            manifest: dict[str, Any] = {}
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    manifest = {}
            rows.append(
                {
                    "model_version": manifest.get("model_version") or child.name,
                    "model_role": manifest.get("model_role", "forecast"),
                    "status": "local_artifact",
                    "artifact_path": str(child),
                    "created_at": pd.to_datetime(child.stat().st_mtime, unit="s"),
                }
            )
        return pd.DataFrame(rows)

    def _artifact_rows(self, paths, registry: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        if not registry.empty and "artifact_path" in registry.columns:
            for _, row in registry.iterrows():
                artifact_path = Path(str(row.get("artifact_path") or ""))
                rows.append(
                    {
                        "model_version": row.get("model_version", ""),
                        "artifact_path": str(artifact_path),
                        "exists": artifact_path.exists(),
                    }
                )
        local = self._versions_from_artifacts(paths)
        if not local.empty:
            for _, row in local.iterrows():
                rows.append(
                    {
                        "model_version": row.get("model_version", ""),
                        "artifact_path": row.get("artifact_path", ""),
                        "exists": Path(str(row.get("artifact_path", ""))).exists(),
                    }
                )
        return pd.DataFrame(rows)
