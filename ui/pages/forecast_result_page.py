from __future__ import annotations

from typing import Any

import pandas as pd
from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.components.cards import SectionCard
from ui.components.forecast_chart import ForecastChartWidget
from ui.components.form_widgets import make_button
from ui.components.layouts import ResponsiveGrid, make_scroll_page
from ui.components.status_cards import MetricCard
from ui.components.worker import Worker
from ui.services.forecast_result_service import ForecastResultService
from ui.theme import COLORS


class ForecastResultPage(QWidget):
    messageEmitted = Signal(str, str)
    commandRequested = Signal(object)
    openPathRequested = Signal(str)

    def __init__(self, forecast_service: ForecastResultService, parent: QWidget | None = None, auto_refresh: bool = True):
        super().__init__(parent)
        self.forecast_service = forecast_service
        self.thread_pool = QThreadPool.globalInstance()
        self._loading = False
        self._full_df = pd.DataFrame()
        self._filtered_df = pd.DataFrame()
        self._paths: dict[str, str] = {}
        self._business_text = ""
        self._summary: dict[str, Any] = {}

        root, _scroll, _content = make_scroll_page(self)

        title = QLabel("预测结果中心")
        title.setObjectName("PageTitle")
        subtitle = QLabel("未来24小时正式前瞻预测、峰谷风险、预测区间与业务解读")
        subtitle.setObjectName("MutedText")
        root.addWidget(title)
        root.addWidget(subtitle)

        toolbar = QWidget()
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(8)
        selector_row = QHBoxLayout()
        self.batch_combo = QComboBox()
        self.batch_combo.setMinimumWidth(260)
        self.refresh_btn = make_button("刷新预测结果", primary=True)
        self.open_excel_btn = make_button("打开预测结果 Excel")
        self.open_result_dir_btn = make_button("打开结果目录")
        self.open_latest_btn = make_button("打开最新归档目录")
        self.run_prediction_btn = make_button("重新运行预测并生成报告", primary=True)
        self.report_only_btn = make_button("仅重新生成 AI 报告")
        self.export_btn = make_button("导出当前预测表")
        self.copy_summary_btn = make_button("复制业务摘要")
        selector_row.addWidget(self.batch_combo, 1)
        selector_row.addWidget(self.refresh_btn)
        selector_row.addStretch(1)
        toolbar_layout.addLayout(selector_row)
        action_grid = ResponsiveGrid(min_item_width=158, max_columns=6, spacing=8)
        for button in [
            self.open_excel_btn,
            self.open_result_dir_btn,
            self.open_latest_btn,
            self.run_prediction_btn,
            self.report_only_btn,
            self.export_btn,
            self.copy_summary_btn,
        ]:
            action_grid.addWidget(button)
        toolbar_layout.addWidget(action_grid)
        root.addWidget(toolbar)

        self.refresh_btn.clicked.connect(self.refresh_async)
        self.batch_combo.currentIndexChanged.connect(lambda _index: self.refresh_async())
        self.open_excel_btn.clicked.connect(lambda: self._open_path("source_path"))
        self.open_result_dir_btn.clicked.connect(lambda: self._open_path("result_dir"))
        self.open_latest_btn.clicked.connect(lambda: self._open_path("latest_package"))
        self.run_prediction_btn.clicked.connect(lambda: self.commandRequested.emit(self.forecast_service.prediction_report_command()))
        self.report_only_btn.clicked.connect(lambda: self.commandRequested.emit(self.forecast_service.regenerate_report_command()))
        self.export_btn.clicked.connect(self._export_current_table)
        self.copy_summary_btn.clicked.connect(self._copy_business_summary)

        summary_card = SectionCard("顶部业务摘要")
        summary_card.layout.setContentsMargins(16, 10, 16, 12)
        summary_card.layout.setSpacing(8)
        summary_grid = ResponsiveGrid(min_item_width=190, max_columns=5, spacing=10)
        self.summary_cards = {
            "forecast_window": MetricCard("预测窗口", "-"),
            "avg_price": MetricCard("24小时均价", "-"),
            "max_price": MetricCard("最高价", "-"),
            "min_price": MetricCard("最低价", "-"),
            "peak_valley_spread": MetricCard("峰谷价差", "-"),
            "risk_level": MetricCard("风险等级", "-"),
        }
        for card in self.summary_cards.values():
            card.setMinimumHeight(64)
            card.setMaximumHeight(76)
            summary_grid.addWidget(card)
        summary_card.layout.addWidget(summary_grid)
        self.source_info = QLabel("-")
        self.source_info.setObjectName("MutedText")
        self.source_info.setWordWrap(True)
        summary_card.layout.addWidget(self.source_info)
        root.addWidget(summary_card)

        body = QSplitter(Qt.Vertical)
        body.setChildrenCollapsible(False)
        body.setMinimumHeight(800)
        upper = QSplitter(Qt.Horizontal)
        upper.setChildrenCollapsible(False)
        upper.setMinimumHeight(520)
        table_card = SectionCard("未来24小时预测表")
        table_card.setMinimumHeight(420)
        table_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        filter_row = QHBoxLayout()
        self.risk_filter = QComboBox()
        self.risk_filter.addItems(["全部风险", "高", "中", "低"])
        self.only_peak = QCheckBox("只看高峰时段")
        self.only_spike = QCheckBox("只看尖峰风险")
        filter_row.addWidget(QLabel("风险筛选"))
        filter_row.addWidget(self.risk_filter)
        filter_row.addWidget(self.only_peak)
        filter_row.addWidget(self.only_spike)
        filter_row.addStretch(1)
        table_card.layout.addLayout(filter_row)
        self.forecast_table = QTableWidget()
        self.forecast_table.setAlternatingRowColors(True)
        self.forecast_table.setSortingEnabled(True)
        self.forecast_table.setWordWrap(False)
        self.forecast_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table_card.layout.addWidget(self.forecast_table)
        self.risk_filter.currentTextChanged.connect(self._apply_filters)
        self.only_peak.stateChanged.connect(self._apply_filters)
        self.only_spike.stateChanged.connect(self._apply_filters)

        chart_card = SectionCard("预测趋势图")
        chart_card.setMinimumHeight(480)
        chart_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        chart_toolbar = QHBoxLayout()
        self.open_chart_btn = make_button("打开已有预测图")
        self.open_chart_btn.clicked.connect(lambda: self._open_path("chart_path"))
        chart_toolbar.addStretch(1)
        chart_toolbar.addWidget(self.open_chart_btn)
        chart_card.layout.addLayout(chart_toolbar)
        self.chart = ForecastChartWidget(minimum_height=420)
        chart_card.layout.addWidget(self.chart, 1)
        upper.addWidget(table_card)
        upper.addWidget(chart_card)
        upper.setSizes([680, 840])
        upper.setStretchFactor(0, 45)
        upper.setStretchFactor(1, 55)
        body.addWidget(upper)

        lower = QSplitter(Qt.Horizontal)
        lower.setChildrenCollapsible(False)
        lower.setMinimumHeight(260)
        risk_card = SectionCard("风险时段分析")
        self.risk_grid = ResponsiveGrid(min_item_width=190, max_columns=3, spacing=10)
        self.risk_cards = {
            "top_high": MetricCard("Top 3 高价时段", "-"),
            "top_low": MetricCard("Top 3 低价时段", "-"),
            "peak_risk": MetricCard("高峰风险时段", "-"),
            "spike_risk": MetricCard("尖峰风险时段", "-"),
            "volatile": MetricCard("波动较大时段", "-"),
            "focus": MetricCard("建议重点关注", "-"),
        }
        for index, card in enumerate(self.risk_cards.values()):
            self.risk_grid.addWidget(card)
        risk_card.layout.addWidget(self.risk_grid)

        interpretation_card = SectionCard("业务解读")
        self.interpretation = QPlainTextEdit()
        self.interpretation.setReadOnly(True)
        interpretation_card.layout.addWidget(self.interpretation)
        lower.addWidget(risk_card)
        lower.addWidget(interpretation_card)
        lower.setSizes([620, 700])
        body.addWidget(lower)
        body.setSizes([680, 270])
        root.addWidget(body, 1)

        self.empty_label = QLabel("")
        self.empty_label.setObjectName("MutedText")
        root.addWidget(self.empty_label)
        if auto_refresh:
            self.refresh_async()

    def refresh_async(self) -> None:
        if self._loading:
            return
        self._set_loading(True)
        selection = self.batch_combo.currentData()
        worker = Worker(lambda: self.forecast_service.load_center_data(selection))
        worker.signals.success.connect(self._apply_payload)
        worker.signals.error.connect(self._refresh_error)
        self.thread_pool.start(worker)

    def set_running(self, running: bool) -> None:
        self.run_prediction_btn.setEnabled(not running)
        self.report_only_btn.setEnabled(not running)

    def _set_loading(self, loading: bool) -> None:
        self._loading = loading
        self.refresh_btn.setEnabled(not loading)
        self.batch_combo.setEnabled(not loading)
        self.refresh_btn.setText("刷新中..." if loading else "刷新预测结果")

    def _refresh_error(self, message: str) -> None:
        self._set_loading(False)
        self.messageEmitted.emit(f"预测结果中心刷新失败：{message}", "ERROR")
        self.empty_label.setText("预测结果加载失败，已保留页面空状态。")

    def _apply_payload(self, payload: dict[str, Any]) -> None:
        self._set_loading(False)
        self._paths = {
            "source_path": payload.get("source_path", ""),
            "result_dir": payload.get("result_dir", ""),
            "latest_package": payload.get("latest_package", ""),
            "chart_path": payload.get("chart_path", ""),
        }
        self._update_batches(payload.get("batches", []))
        summary = payload.get("summary") or {}
        self._full_df = payload.get("dataframe", pd.DataFrame())
        self._business_text = payload.get("interpretation", "")
        self._summary = summary
        self._update_summary(summary)
        self._update_risks(payload.get("risks", {}))
        self.interpretation.setPlainText(self._business_text or "暂无业务解读。")
        self.empty_label.setText(payload.get("empty_message", ""))
        self._apply_filters()
        if "本地文件降级" in str(summary.get("data_source", "")):
            self.messageEmitted.emit("预测结果中心当前使用本地文件降级数据源。", "WARNING")
        else:
            self.messageEmitted.emit("预测结果中心数据已刷新。", "SUCCESS")

    def _update_batches(self, batches: list[dict[str, str]]) -> None:
        current = self.batch_combo.currentData() or {"kind": "latest", "value": ""}
        self.batch_combo.blockSignals(True)
        self.batch_combo.clear()
        for item in batches:
            self.batch_combo.addItem(item.get("label", "-"), {"kind": item.get("kind", ""), "value": item.get("value", "")})
        selected_index = 0
        for index in range(self.batch_combo.count()):
            data = self.batch_combo.itemData(index)
            if data == current:
                selected_index = index
                break
        self.batch_combo.setCurrentIndex(selected_index)
        self.batch_combo.blockSignals(False)

    def _update_summary(self, summary: dict[str, Any]) -> None:
        for key, card in self.summary_cards.items():
            if key == "forecast_window":
                value = f"{summary.get('forecast_start', '-')}\n至 {summary.get('forecast_end', '-')}"
            else:
                value = summary.get(key, "-")
            if key in {"avg_price", "max_price", "min_price", "peak_valley_spread"}:
                value = self._format_number(value)
                if key == "max_price" and summary.get("max_hour"):
                    value = f"{value} / {summary.get('max_hour')}"
                if key == "min_price" and summary.get("min_hour"):
                    value = f"{value} / {summary.get('min_hour')}"
            color = None
            if key == "risk_level":
                color = {"高": COLORS["danger"], "中": COLORS["warning"], "低": COLORS["success"]}.get(str(value), COLORS["muted"])
            card.set_value(str(value or "-"), color)
        self.source_info.setText(f"数据来源：{summary.get('data_source', '-')}    |    run_id：{summary.get('run_id', '-')}")

    def _update_risks(self, risks: dict[str, list[dict[str, Any]]]) -> None:
        for key, card in self.risk_cards.items():
            rows = risks.get(key, [])
            text = self._format_risk_rows(rows)
            accent = COLORS["danger"] if key in {"top_high", "spike_risk", "focus"} else COLORS["warning"]
            card.set_value(text or "-", accent)

    def _apply_filters(self) -> None:
        df = self._full_df.copy()
        if df.empty:
            self._filtered_df = df
            self._render_table(df)
            self.chart.render_empty("暂无预测数据，请先运行预测流程。")
            return
        risk = self.risk_filter.currentText()
        if risk != "全部风险" and "risk_level" in df.columns:
            df = df[df["risk_level"].astype(str) == risk]
        if self.only_peak.isChecked() and "is_peak_hour" in df.columns:
            df = df[pd.to_numeric(df["is_peak_hour"], errors="coerce").fillna(0).astype(int) == 1]
        if self.only_spike.isChecked():
            if "spike_risk_prob" in df.columns:
                spike = pd.to_numeric(df["spike_risk_prob"], errors="coerce").fillna(0)
            else:
                spike = pd.Series(0, index=df.index)
            if "risk_level" in df.columns:
                high_risk = df["risk_level"].astype(str) == "高"
            else:
                high_risk = pd.Series(False, index=df.index)
            df = df[(spike >= 0.15) | high_risk]
        self._filtered_df = df
        self._render_table(df)
        chart_df = self.forecast_service.get_forecast_chart_data(df)
        annotations = self.forecast_service.build_chart_annotations(chart_df, self._summary)
        self.chart.render_forecast(chart_df, self._summary, annotations)

    def _render_table(self, df: pd.DataFrame) -> None:
        self.forecast_table.setSortingEnabled(False)
        self.forecast_table.clear()
        display_columns = [
            "datetime",
            "predicted_price",
            "p10",
            "p90",
            "risk_level",
            "is_peak_hour",
            "spike_risk_prob",
            "forecast_load",
            "temperature",
            "model_version",
        ]
        available = []
        for col in display_columns:
            if col not in df.columns:
                continue
            if col in {"p10", "p90", "temperature"} and df[col].isna().all():
                continue
            available.append(col)
        headers = {
            "datetime": "datetime",
            "predicted_price": "predicted_price",
            "p10": "p10",
            "p90": "p90",
            "risk_level": "risk_level",
            "is_peak_hour": "is_peak_hour",
            "spike_risk_prob": "spike_risk_prob",
            "forecast_load": "forecast_load",
            "temperature": "temperature",
            "model_version": "model_version",
        }
        if df.empty or not available:
            self.forecast_table.setRowCount(1)
            self.forecast_table.setColumnCount(1)
            self.forecast_table.setHorizontalHeaderLabels(["状态"])
            self.forecast_table.setItem(0, 0, QTableWidgetItem("暂无数据"))
            return
        self.forecast_table.setRowCount(len(df))
        self.forecast_table.setColumnCount(len(available))
        self.forecast_table.setHorizontalHeaderLabels([headers[col] for col in available])
        brush = QBrush(QColor(COLORS["body"]))
        for row_index, (_, row) in enumerate(df[available].iterrows()):
            for col_index, value in enumerate(row.tolist()):
                item = QTableWidgetItem(self._cell_text(value))
                item.setForeground(brush)
                self.forecast_table.setItem(row_index, col_index, item)
        self.forecast_table.resizeColumnsToContents()
        self.forecast_table.setSortingEnabled(True)

    def _open_path(self, key: str) -> None:
        path = self._paths.get(key, "")
        if not path:
            self.messageEmitted.emit("当前没有可打开的路径。", "WARNING")
            return
        self.openPathRequested.emit(path)

    def _export_current_table(self) -> None:
        df = self._filtered_df if not self._filtered_df.empty else self._full_df
        if df.empty:
            self.messageEmitted.emit("当前没有可导出的预测表。", "WARNING")
            return
        default_path = str(self.forecast_service.default_export_path())
        output, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出当前预测表",
            default_path,
            "Excel 文件 (*.xlsx);;CSV 文件 (*.csv)",
        )
        if not output:
            return
        try:
            path = self.forecast_service.export_forecast_table(df, output)
            self.messageEmitted.emit(f"预测表已导出：{path}", "SUCCESS")
        except Exception as exc:
            self.messageEmitted.emit(f"导出预测表失败：{exc}", "ERROR")

    def _copy_business_summary(self) -> None:
        text = self._business_text.strip()
        if not text:
            self.messageEmitted.emit("当前没有可复制的业务摘要。", "WARNING")
            return
        QApplication.clipboard().setText(text)
        self.messageEmitted.emit("业务摘要已复制到剪贴板。", "SUCCESS")

    @staticmethod
    def _format_risk_rows(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "-"
        parts = []
        for item in rows[:3]:
            price = ForecastResultPage._format_number(item.get("predicted_price"))
            prob = item.get("spike_risk_prob")
            prob_text = "" if prob is None else f" / 风险{float(prob):.1%}"
            parts.append(f"{item.get('hour', '-')} {price}{prob_text}")
        return "\n".join(parts)

    @staticmethod
    def _format_number(value: Any) -> str:
        try:
            if value is None or pd.isna(value):
                return "-"
            return f"{float(value):.2f}"
        except Exception:
            return str(value) if value is not None else "-"

    @staticmethod
    def _cell_text(value: Any) -> str:
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass
        if isinstance(value, pd.Timestamp):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return str(value)
