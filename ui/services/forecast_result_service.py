from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

from automation_common import get_pipeline_paths, load_config, now_compact
from database_utils import create_database_engine, get_database_config, test_database_connection
from ui.services.legacy_actions import CommandSpec, ROOT_DIR


PROJECT_ROOT = ROOT_DIR


@dataclass(frozen=True)
class ForecastBatch:
    label: str
    kind: str
    value: str


class ForecastResultService:
    def detect_project_root(self) -> Path:
        return PROJECT_ROOT

    def load_center_data(self, selection: dict[str, str] | None = None) -> dict[str, Any]:
        config = load_config()
        paths = get_pipeline_paths(config)
        ai_summary = self._read_json(paths.current_dir / "ai_input_summary.json")
        batches = self.list_batches()

        selected = selection or {"kind": "latest", "value": ""}
        df = pd.DataFrame()
        source = ""
        source_path: Path | None = None
        result_dir: Path | None = None

        if selected.get("kind") == "db_run":
            df = self.load_forecast_by_run_id(selected.get("value", ""))
            source = f"数据库：result_forward_24h_formal / {selected.get('value', '')}"
        elif selected.get("kind") == "local_file":
            source_path = Path(selected.get("value", ""))
            df = self._read_forecast_excel(source_path)
            result_dir = self._infer_result_dir(source_path, paths)
            source = f"本地文件：{source_path.name}"
        elif selected.get("kind") == "local_package":
            result_dir = Path(selected.get("value", ""))
            source_path = self._find_forecast_file_in_package(result_dir)
            df = self._read_forecast_excel(source_path) if source_path else pd.DataFrame()
            source = f"本地归档：{result_dir.name}"
        else:
            try:
                df = self.load_latest_forecast_from_database()
                source = "数据库：vw_latest_forward_24h_formal"
            except Exception:
                df, source_path, result_dir = self.load_latest_forecast_from_files(return_meta=True)
                source = "本地文件降级数据源"

        if df.empty:
            try:
                df, source_path, result_dir = self.load_latest_forecast_from_files(return_meta=True)
                source = "本地文件降级数据源"
            except Exception:
                df = pd.DataFrame()

        normalized = self.normalize_forecast_columns(df)
        summary = self.build_forecast_summary(normalized, ai_summary=ai_summary)
        run_id = summary.get("run_id") or self._infer_run_id(normalized, ai_summary, selected)
        summary["run_id"] = run_id
        summary["data_source"] = source
        risks = self.detect_risk_periods(normalized)
        interpretation = self.build_rule_based_business_interpretation(normalized, summary, ai_summary, risks)
        if not source_path:
            source_path = self._find_source_path_for_latest(paths)
        if not result_dir:
            result_dir = self.find_latest_result_package() or paths.result_table_dir
        chart_path = self._find_chart_path(result_dir, paths)
        source_type = "database" if source.startswith("数据库") else "local"
        return {
            "dataframe": normalized,
            "summary": summary,
            "risks": risks,
            "interpretation": interpretation,
            "batches": batches,
            "source_type": source_type,
            "source_path": str(source_path) if source_path else "",
            "result_dir": str(result_dir) if result_dir else "",
            "latest_package": str(self.find_latest_result_package() or ""),
            "chart_path": str(chart_path) if chart_path else "",
            "empty_message": "" if not normalized.empty else "当前未发现未来24小时正式前瞻预测结果。",
        }

    def list_batches(self) -> list[dict[str, str]]:
        batches: list[ForecastBatch] = [ForecastBatch("最新批次", "latest", "")]
        batches.extend(self._database_batches()[:20])
        latest_package = self.find_latest_result_package()
        if latest_package:
            batches.append(ForecastBatch(f"最新本地归档：{latest_package.name}", "local_package", str(latest_package)))
        for package in self._local_packages()[:5]:
            batches.append(ForecastBatch(f"本地归档：{package.name}", "local_package", str(package)))
        for file_path in self.find_forecast_excel_files()[:10]:
            batches.append(ForecastBatch(f"本地文件：{file_path.name}", "local_file", str(file_path)))
        seen: set[tuple[str, str]] = set()
        output: list[dict[str, str]] = []
        for item in batches:
            key = (item.kind, item.value)
            if key in seen:
                continue
            seen.add(key)
            output.append({"label": item.label, "kind": item.kind, "value": item.value})
        return output

    def load_latest_forecast_from_database(self) -> pd.DataFrame:
        config = load_config()
        ok, message = test_database_connection(config)
        if not ok or not get_database_config(config).enabled:
            raise RuntimeError(message)
        engine = create_database_engine(config)
        with engine.connect() as conn:
            return pd.read_sql(
                text("SELECT * FROM `vw_latest_forward_24h_formal` ORDER BY `datetime` ASC"),
                conn,
            )

    def load_forecast_by_run_id(self, run_id: str) -> pd.DataFrame:
        if not run_id:
            return self.load_latest_forecast_from_database()
        config = load_config()
        ok, message = test_database_connection(config)
        if not ok or not get_database_config(config).enabled:
            raise RuntimeError(message)
        engine = create_database_engine(config)
        with engine.connect() as conn:
            return pd.read_sql(
                text(
                    """
                    SELECT *
                    FROM `result_forward_24h_formal`
                    WHERE `run_id` = :run_id
                    ORDER BY `datetime` ASC
                    """
                ),
                conn,
                params={"run_id": run_id},
            )

    def load_latest_forecast_from_files(self, return_meta: bool = False):
        candidates = self.find_forecast_excel_files()
        if not candidates:
            if return_meta:
                return pd.DataFrame(), None, None
            return pd.DataFrame()
        path = candidates[0]
        df = self._read_forecast_excel(path)
        result_dir = self._infer_result_dir(path, get_pipeline_paths(load_config()))
        if return_meta:
            return df, path, result_dir
        return df

    def find_latest_result_package(self) -> Path | None:
        paths = get_pipeline_paths(load_config())
        packages = self._local_packages(paths)
        return packages[0] if packages else None

    def find_forecast_excel_files(self) -> list[Path]:
        paths = get_pipeline_paths(load_config())
        candidates: list[Path] = []
        direct = [
            paths.result_table_dir / "18_未来24小时预测结果_正式版.xlsx",
            paths.result_dir / "18_未来24小时预测结果_正式版.xlsx",
        ]
        latest_package = self.find_latest_result_package()
        if latest_package:
            direct.extend(
                [
                    latest_package / "01_正式预测结果" / "未来24小时正式前瞻预测结果.xlsx",
                    latest_package / "02_AI报告" / "智能分析输入摘要.json",
                ]
            )
        for path in direct:
            if path.suffix.lower() == ".xlsx" and path.exists():
                candidates.append(path)

        search_roots = [
            paths.result_table_dir,
            paths.result_dir,
            paths.final_output_root_dir,
            paths.current_dir,
            paths.data_dir,
        ]
        for root in search_roots:
            if not root.exists():
                continue
            for path in root.rglob("*.xlsx"):
                name = path.name
                if self._looks_like_forecast_file(name):
                    candidates.append(path)
        return self._dedupe_sorted(candidates)

    def get_forecast_chart_data(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        normalized = df.copy()
        if "datetime" not in normalized.columns or "predicted_price" not in normalized.columns:
            normalized = self.normalize_forecast_columns(normalized)
        if normalized.empty or "datetime" not in normalized.columns or "predicted_price" not in normalized.columns:
            return pd.DataFrame()
        output = normalized.copy()
        output["datetime"] = pd.to_datetime(output["datetime"], errors="coerce")
        output["predicted_price"] = pd.to_numeric(output["predicted_price"], errors="coerce")
        for col in ["p10", "p90", "spike_risk_prob", "forecast_load", "temperature"]:
            if col in output.columns:
                output[col] = pd.to_numeric(output[col], errors="coerce")
        return output.dropna(subset=["datetime", "predicted_price"]).sort_values("datetime")

    def build_chart_annotations(self, df: pd.DataFrame, summary: dict[str, Any]) -> dict[str, Any]:
        work = self.get_forecast_chart_data(df)
        if work.empty:
            return {"top_risk": [], "peak_hours": [], "max_point": {}, "min_point": {}, "note": "暂无预测数据。"}
        max_row = work.loc[work["predicted_price"].idxmax()]
        min_row = work.loc[work["predicted_price"].idxmin()]
        risk_rows = work.iloc[0:0]
        if "risk_level" in work.columns:
            risk_rows = work[work["risk_level"].astype(str).isin(["高", "HIGH", "high"])]
        if "spike_risk_prob" in work.columns:
            spike_rows = work[pd.to_numeric(work["spike_risk_prob"], errors="coerce").fillna(0) >= 0.15]
            risk_rows = pd.concat([risk_rows, spike_rows]).drop_duplicates()
        risk_rows = risk_rows.sort_values(["spike_risk_prob", "predicted_price"], ascending=False, na_position="last").head(3)
        peak_rows = work.iloc[0:0]
        if "is_peak_hour" in work.columns:
            peak_rows = work[pd.to_numeric(work["is_peak_hour"], errors="coerce").fillna(0).astype(int) == 1].sort_values("predicted_price", ascending=False).head(3)
        return {
            "max_point": self._chart_row(max_row),
            "min_point": self._chart_row(min_row),
            "top_risk": [self._chart_row(row) for _, row in risk_rows.iterrows()],
            "peak_hours": [self._chart_row(row) for _, row in peak_rows.iterrows()],
            "note": (
                f"红点表示高风险时段，橙点表示高峰时段；当前整体风险等级为 {summary.get('risk_level', '-')}。"
            ),
        }

    def get_price_column(self, df: pd.DataFrame) -> str | None:
        return self._find_column(
            df,
            [
                "predicted_price",
                "da_price_pred",
                "forecast_price",
                "预测电价",
                "预测价格",
                "预测的未来24小时日前电价",
                "日前电价预测值",
            ],
        )

    def get_datetime_column(self, df: pd.DataFrame) -> str | None:
        return self._find_column(df, ["datetime", "forecast_datetime", "时间", "预测时间", "目标时间"])

    def get_interval_columns(self, df: pd.DataFrame) -> tuple[str | None, str | None]:
        p10 = self._find_column(df, ["p10", "lower_bound", "p10_pred", "P10", "预测下界", "下界"])
        p90 = self._find_column(df, ["p90", "upper_bound", "p90_pred", "P90", "预测上界", "上界"])
        return p10, p90

    def get_risk_columns(self, df: pd.DataFrame) -> dict[str, str | None]:
        return {
            "risk_level": self._find_column(df, ["risk_level", "风险等级"]),
            "spike_risk_prob": self._find_column(df, ["spike_risk_prob", "spike_probability", "尖峰风险概率"]),
            "is_peak_hour": self._find_column(df, ["is_peak_hour", "是否高峰小时", "高峰时段"]),
        }

    def normalize_forecast_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        output = df.copy()
        mapping = {
            "datetime": ["datetime", "forecast_datetime", "时间", "预测时间", "目标时间"],
            "predicted_price": [
                "predicted_price",
                "da_price_pred",
                "forecast_price",
                "预测电价",
                "预测价格",
                "预测的未来24小时日前电价",
                "日前电价预测值",
            ],
            "p10": ["p10", "lower_bound", "p10_pred", "P10", "预测下界", "下界"],
            "p90": ["p90", "upper_bound", "p90_pred", "P90", "预测上界", "上界"],
            "risk_level": ["risk_level", "风险等级"],
            "is_peak_hour": ["is_peak_hour", "是否高峰小时", "高峰时段"],
            "spike_risk_prob": ["spike_risk_prob", "spike_probability", "尖峰风险概率"],
            "forecast_load": ["forecast_load", "预测负荷", "负荷预测"],
            "temperature": ["temperature", "temp", "温度", "temperature_lag_1"],
            "model_version": ["model_version", "模型版本", "final_model"],
            "run_id": ["run_id"],
        }
        selected: dict[str, pd.Series] = {}
        for target, aliases in mapping.items():
            source = self._find_column(output, aliases)
            if source:
                selected[target] = output[source]
        if "datetime" not in selected:
            return pd.DataFrame()
        result = pd.DataFrame(selected)
        result["datetime"] = pd.to_datetime(result["datetime"], errors="coerce")
        result = result.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
        for column in ["predicted_price", "p10", "p90", "spike_risk_prob", "forecast_load", "temperature"]:
            if column in result.columns:
                result[column] = pd.to_numeric(result[column], errors="coerce")
        if "predicted_price" not in result.columns:
            result["predicted_price"] = pd.NA
        if "is_peak_hour" not in result.columns:
            result["is_peak_hour"] = result["datetime"].dt.hour.isin([6, 7, 8, 9, 10, 11, 18, 19, 20, 21]).astype(int)
        else:
            result["is_peak_hour"] = pd.to_numeric(result["is_peak_hour"], errors="coerce").fillna(0).astype(int)
        if "spike_risk_prob" not in result.columns:
            result["spike_risk_prob"] = pd.NA
        if "risk_level" not in result.columns:
            result["risk_level"] = self._derive_risk_level(result)
        if "model_version" not in result.columns:
            result["model_version"] = ""
        return result

    def build_forecast_summary(self, df: pd.DataFrame, ai_summary: dict[str, Any] | None = None) -> dict[str, Any]:
        ai_summary = ai_summary or {}
        forecast_summary = ai_summary.get("forecast_summary") or {}
        report_facts = ai_summary.get("report_facts") or {}
        summary = {
            "forecast_start": forecast_summary.get("forecast_start") or report_facts.get("forecast_start") or "-",
            "forecast_end": forecast_summary.get("forecast_end") or report_facts.get("forecast_end") or "-",
            "avg_price": forecast_summary.get("next_24h_avg_price") or report_facts.get("avg_price"),
            "max_price": forecast_summary.get("next_24h_max_price") or report_facts.get("max_price"),
            "max_hour": forecast_summary.get("next_24h_max_hour") or report_facts.get("max_hour") or "-",
            "min_price": forecast_summary.get("next_24h_min_price") or report_facts.get("min_price"),
            "min_hour": forecast_summary.get("next_24h_min_hour") or report_facts.get("min_hour") or "-",
            "peak_valley_spread": forecast_summary.get("peak_valley_spread") or report_facts.get("peak_valley_spread"),
            "risk_level": "中",
            "run_id": ai_summary.get("run_id", ""),
        }
        if df is not None and not df.empty and "predicted_price" in df.columns:
            prices = pd.to_numeric(df["predicted_price"], errors="coerce")
            valid = df.loc[prices.notna()].copy()
            if not valid.empty:
                valid["_price"] = pd.to_numeric(valid["predicted_price"], errors="coerce")
                max_row = valid.loc[valid["_price"].idxmax()]
                min_row = valid.loc[valid["_price"].idxmin()]
                summary.update(
                    {
                        "forecast_start": str(valid["datetime"].min()),
                        "forecast_end": str(valid["datetime"].max()),
                        "avg_price": float(valid["_price"].mean()),
                        "max_price": float(max_row["_price"]),
                        "max_hour": pd.to_datetime(max_row["datetime"]).strftime("%H:%M"),
                        "min_price": float(min_row["_price"]),
                        "min_hour": pd.to_datetime(min_row["datetime"]).strftime("%H:%M"),
                        "peak_valley_spread": float(max_row["_price"] - min_row["_price"]),
                    }
                )
                if "run_id" in valid.columns and str(valid["run_id"].dropna().iloc[0] if valid["run_id"].dropna().size else "").strip():
                    summary["run_id"] = str(valid["run_id"].dropna().iloc[0])
        summary["risk_level"] = self._overall_risk(summary, df)
        return summary

    def detect_risk_periods(self, df: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
        if df is None or df.empty:
            return {
                "top_high": [],
                "top_low": [],
                "peak_risk": [],
                "spike_risk": [],
                "volatile": [],
                "focus": [],
            }
        work = df.copy()
        work["_price"] = pd.to_numeric(work.get("predicted_price"), errors="coerce")
        work["_spike"] = pd.to_numeric(work.get("spike_risk_prob"), errors="coerce").fillna(0)
        work["_diff"] = work["_price"].diff().abs()
        high = work.sort_values("_price", ascending=False).head(3)
        low = work.sort_values("_price", ascending=True).head(3)
        if "is_peak_hour" in work.columns:
            peak_mask = pd.to_numeric(work["is_peak_hour"], errors="coerce").fillna(0).astype(int) == 1
        else:
            peak_mask = pd.Series(False, index=work.index)
        if "risk_level" in work.columns:
            elevated_risk = work["risk_level"].isin(["中", "高"])
            high_risk = work["risk_level"].eq("高")
        else:
            elevated_risk = pd.Series(False, index=work.index)
            high_risk = pd.Series(False, index=work.index)
        peak = work[peak_mask & elevated_risk].sort_values("_price", ascending=False).head(5)
        spike = work[(work["_spike"] >= 0.15) | high_risk].sort_values("_spike", ascending=False).head(5)
        volatile = work.sort_values("_diff", ascending=False).head(5)
        focus = pd.concat([high.head(2), spike.head(2), peak.head(2)]).drop_duplicates(subset=["datetime"]).head(6)
        return {
            "top_high": self._rows_for_cards(high),
            "top_low": self._rows_for_cards(low),
            "peak_risk": self._rows_for_cards(peak),
            "spike_risk": self._rows_for_cards(spike),
            "volatile": self._rows_for_cards(volatile),
            "focus": self._rows_for_cards(focus),
        }

    def build_rule_based_business_interpretation(
        self,
        df: pd.DataFrame,
        summary: dict[str, Any],
        ai_summary: dict[str, Any] | None = None,
        risks: dict[str, list[dict[str, Any]]] | None = None,
    ) -> str:
        ai_summary = ai_summary or {}
        risks = risks or {}
        lines: list[str] = []
        avg_price = self._format_number(summary.get("avg_price"))
        spread = self._safe_float(summary.get("peak_valley_spread"))
        risk_level = summary.get("risk_level", "-")
        lines.append(f"未来24小时预测均价约为 {avg_price} USD/MWh，整体风险等级为 {risk_level}。")
        if spread is not None:
            if spread >= 50:
                lines.append(f"峰谷价差约 {spread:.2f} USD/MWh，价格分化明显，建议重点监控峰段。")
            elif spread >= 25:
                lines.append(f"峰谷价差约 {spread:.2f} USD/MWh，存在一定日内波动。")
            else:
                lines.append(f"峰谷价差约 {spread:.2f} USD/MWh，日内波动相对温和。")
        focus = risks.get("focus") or []
        if focus:
            hours = "、".join(item.get("hour", "-") for item in focus[:5])
            lines.append(f"建议重点关注时段：{hours}。")
        summary_risk_hours = ((ai_summary.get("forecast_summary") or {}).get("top_risk_hours") or (ai_summary.get("report_facts") or {}).get("risk_hours") or [])
        if summary_risk_hours:
            lines.append("已读取 AI 输入摘要中的风险时段，可在 AI 报告中心重新生成更完整解释。")
        forecast_end = pd.to_datetime(summary.get("forecast_end"), errors="coerce")
        if pd.notna(forecast_end):
            age_days = (pd.Timestamp.now() - forecast_end).days
            if age_days > 2:
                lines.append(f"预测窗口结束时间距当前已超过 {age_days} 天，建议先执行数据刷新或重新运行预测。")
        if risk_level in {"高", "中"}:
            lines.append("如需对外汇报，建议点击“仅重新生成 AI 报告”同步最新业务解读。")
        return "\n".join(lines)

    def export_forecast_table(self, df: pd.DataFrame, output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".csv":
            df.to_csv(path, index=False, encoding="utf-8-sig")
        else:
            df.to_excel(path, index=False)
        return path

    def open_file(self, path: str | Path) -> None:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在：{path}")
        os.startfile(str(path))

    def open_directory(self, path: str | Path) -> None:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"目录不存在：{path}")
        os.startfile(str(path))

    def prediction_report_command(self) -> CommandSpec:
        return CommandSpec(
            "重新运行预测并生成报告",
            [sys.executable, "-X", "utf8", str(PROJECT_ROOT / "main_daily_run.py"), "--prediction-report-only"],
        )

    def regenerate_report_command(self) -> CommandSpec:
        return CommandSpec(
            "仅重新生成 AI 报告",
            [sys.executable, "-X", "utf8", str(PROJECT_ROOT / "main_daily_run.py"), "--skip-prediction"],
        )

    def default_export_path(self) -> Path:
        paths = get_pipeline_paths(load_config())
        return paths.final_output_root_dir / f"forecast_table_export_{now_compact()}.xlsx"

    def _database_batches(self) -> list[ForecastBatch]:
        config = load_config()
        ok, _message = test_database_connection(config)
        if not ok or not get_database_config(config).enabled:
            return []
        try:
            engine = create_database_engine(config)
            with engine.connect() as conn:
                df = pd.read_sql(
                    text(
                        """
                        SELECT run_id, MAX(run_started_at) AS run_started_at, MAX(db_imported_at) AS imported_at
                        FROM result_forward_24h_formal
                        GROUP BY run_id
                        ORDER BY MAX(id) DESC
                        LIMIT 20
                        """
                    ),
                    conn,
                )
            return [
                ForecastBatch(f"数据库批次：{row.run_id}", "db_run", str(row.run_id))
                for row in df.itertuples(index=False)
                if str(row.run_id).strip()
            ]
        except Exception:
            return []

    def _local_packages(self, paths=None) -> list[Path]:
        paths = paths or get_pipeline_paths(load_config())
        root = paths.final_output_root_dir
        if not root.exists():
            return []
        packages = [p for p in root.iterdir() if p.is_dir()]
        return sorted(packages, key=lambda p: p.stat().st_mtime, reverse=True)

    def _read_forecast_excel(self, path: Path | None) -> pd.DataFrame:
        if not path or not path.exists() or path.suffix.lower() != ".xlsx":
            return pd.DataFrame()
        try:
            return pd.read_excel(path)
        except Exception:
            return pd.DataFrame()

    def _find_forecast_file_in_package(self, package: Path) -> Path | None:
        if not package or not package.exists():
            return None
        direct = package / "01_正式预测结果" / "未来24小时正式前瞻预测结果.xlsx"
        if direct.exists():
            return direct
        matches = [p for p in package.rglob("*.xlsx") if self._looks_like_forecast_file(p.name)]
        return sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True)[0] if matches else None

    def _find_chart_path(self, result_dir: Path | None, paths) -> Path | None:
        if result_dir and result_dir.exists():
            chart = self._latest_chart_in(result_dir)
            if chart:
                return chart
        latest_package = self.find_latest_result_package()
        if latest_package and latest_package != result_dir:
            chart = self._latest_chart_in(latest_package)
            if chart:
                return chart
        candidates: list[Path] = []
        for root in [paths.result_dir / "图表", paths.final_output_root_dir]:
            if root.exists():
                candidates.extend(root.rglob("*正式前瞻预测图*.png"))
        return self._dedupe_sorted(candidates)[0] if candidates else None

    @staticmethod
    def _latest_chart_in(root: Path) -> Path | None:
        matches = [p for p in root.rglob("*正式前瞻预测图*.png") if p.is_file()]
        return sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True)[0] if matches else None

    def _find_source_path_for_latest(self, paths) -> Path | None:
        files = self.find_forecast_excel_files()
        return files[0] if files else None

    @staticmethod
    def _infer_result_dir(source_path: Path | None, paths) -> Path | None:
        if not source_path:
            return None
        parts = list(source_path.parents)
        for parent in parts:
            if parent.name.endswith("电价预测运行结果"):
                return parent
        if source_path.is_relative_to(paths.result_table_dir):
            return paths.result_dir
        return source_path.parent

    @staticmethod
    def _looks_like_forecast_file(name: str) -> bool:
        return (
            name.endswith(".xlsx")
            and ("24" in name)
            and ("预测" in name)
            and ("结果" in name)
            and ("演示" not in name)
            and ("输入" not in name)
        ) or name == "未来24小时正式前瞻预测结果.xlsx"

    @staticmethod
    def _dedupe_sorted(paths: list[Path]) -> list[Path]:
        seen: set[str] = set()
        unique: list[Path] = []
        for path in paths:
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            unique.append(path)
        return sorted(unique, key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)

    @staticmethod
    def _find_column(df: pd.DataFrame, aliases: list[str]) -> str | None:
        lower_map = {str(col).strip().lower(): str(col) for col in df.columns}
        for alias in aliases:
            if alias in df.columns:
                return alias
            found = lower_map.get(alias.lower())
            if found:
                return found
        return None

    @staticmethod
    def _derive_risk_level(df: pd.DataFrame) -> pd.Series:
        if "predicted_price" in df.columns:
            prices = pd.to_numeric(df["predicted_price"], errors="coerce")
        else:
            prices = pd.Series(float("nan"), index=df.index)
        if "spike_risk_prob" in df.columns:
            spike = pd.to_numeric(df["spike_risk_prob"], errors="coerce").fillna(0)
        else:
            spike = pd.Series(0, index=df.index)
        high_threshold = prices.quantile(0.9) if prices.notna().any() else float("inf")
        medium_threshold = prices.quantile(0.75) if prices.notna().any() else float("inf")
        levels = []
        for price, prob in zip(prices, spike):
            if (pd.notna(price) and price >= high_threshold) or prob >= 0.4:
                levels.append("高")
            elif (pd.notna(price) and price >= medium_threshold) or prob >= 0.15:
                levels.append("中")
            else:
                levels.append("低")
        return pd.Series(levels, index=df.index)

    @staticmethod
    def _overall_risk(summary: dict[str, Any], df: pd.DataFrame) -> str:
        spread = ForecastResultService._safe_float(summary.get("peak_valley_spread"))
        high_rows = 0
        if df is not None and not df.empty and "risk_level" in df.columns:
            high_rows = int((df["risk_level"] == "高").sum())
        if high_rows >= 2 or (spread is not None and spread >= 50):
            return "高"
        if high_rows >= 1 or (spread is not None and spread >= 25):
            return "中"
        return "低"

    @staticmethod
    def _rows_for_cards(df: pd.DataFrame) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if df is None or df.empty:
            return rows
        for _, row in df.iterrows():
            dt = pd.to_datetime(row.get("datetime"), errors="coerce")
            rows.append(
                {
                    "time": str(dt) if pd.notna(dt) else "",
                    "hour": dt.strftime("%H:%M") if pd.notna(dt) else "",
                    "predicted_price": ForecastResultService._safe_float(row.get("predicted_price")),
                    "risk_level": str(row.get("risk_level", "")),
                    "spike_risk_prob": ForecastResultService._safe_float(row.get("spike_risk_prob")),
                }
            )
        return rows

    @staticmethod
    def _chart_row(row: pd.Series) -> dict[str, Any]:
        dt = pd.to_datetime(row.get("datetime"), errors="coerce")
        return {
            "time": str(dt) if pd.notna(dt) else "",
            "hour": dt.strftime("%H:%M") if pd.notna(dt) else "",
            "predicted_price": ForecastResultService._safe_float(row.get("predicted_price")),
            "risk_level": str(row.get("risk_level", "")),
            "spike_risk_prob": ForecastResultService._safe_float(row.get("spike_risk_prob")),
        }

    @staticmethod
    def _infer_run_id(df: pd.DataFrame, ai_summary: dict[str, Any], selected: dict[str, str]) -> str:
        if selected.get("kind") == "db_run":
            return selected.get("value", "")
        if ai_summary.get("run_id"):
            return str(ai_summary["run_id"])
        if df is not None and not df.empty and "run_id" in df.columns:
            values = df["run_id"].dropna().astype(str)
            if not values.empty:
                return values.iloc[0]
        return "-"

    @staticmethod
    def _format_number(value: Any) -> str:
        number = ForecastResultService._safe_float(value)
        return "-" if number is None else f"{number:.2f}"

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value is None or pd.isna(value):
                return None
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
