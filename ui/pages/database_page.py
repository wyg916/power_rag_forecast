from __future__ import annotations

import json
from typing import Any

import pandas as pd
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.components.cards import SectionCard
from ui.components.form_widgets import make_button
from ui.components.layouts import make_scroll_page
from ui.services.db_service import DatabaseService
from ui.theme import COLORS


class DatabasePage(QWidget):
    messageEmitted = Signal(str, str)

    def __init__(self, db_service: DatabaseService, parent: QWidget | None = None):
        super().__init__(parent)
        self.db_service = db_service
        self.source_display_to_name: dict[str, str] = {}

        root, _scroll, _content = make_scroll_page(self)

        title = QLabel("数据库浏览 / 查询")
        title.setObjectName("PageTitle")
        subtitle = QLabel("支持结果表、视图、运行批次、最新 AI 报告和预测结果的快速浏览。")
        subtitle.setObjectName("MutedText")
        root.addWidget(title)
        root.addWidget(subtitle)

        control_card = SectionCard("查询控制")
        controls = QHBoxLayout()
        self.source_combo = QComboBox()
        self.run_combo = QComboBox()
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 1000)
        self.limit_spin.setValue(200)
        self.only_run_check = QCheckBox("仅当前批次")
        self.only_run_check.setChecked(True)
        refresh_btn = make_button("刷新", primary=True)
        query_btn = make_button("查询")
        report_btn = make_button("加载 AI 报告")
        refresh_btn.clicked.connect(self.refresh_all)
        query_btn.clicked.connect(self.query_selected)
        report_btn.clicked.connect(self.load_report)
        controls.addWidget(QLabel("表/视图"))
        controls.addWidget(self.source_combo, 3)
        controls.addWidget(QLabel("运行批次"))
        controls.addWidget(self.run_combo, 2)
        controls.addWidget(QLabel("行数"))
        controls.addWidget(self.limit_spin)
        controls.addWidget(self.only_run_check)
        controls.addWidget(refresh_btn)
        controls.addWidget(query_btn)
        controls.addWidget(report_btn)
        control_card.layout.addLayout(controls)
        self.meta_label = QLabel("-")
        self.meta_label.setObjectName("MutedText")
        control_card.layout.addWidget(self.meta_label)
        root.addWidget(control_card)

        splitter = QSplitter(Qt.Vertical)
        splitter.setMinimumHeight(520)
        splitter.setChildrenCollapsible(False)
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(False)
        self.report_text = QPlainTextEdit()
        self.report_text.setReadOnly(True)
        self.report_text.setPlaceholderText("选择运行批次后点击“加载 AI 报告”。")
        splitter.addWidget(self.table)
        splitter.addWidget(self.report_text)
        splitter.setSizes([560, 210])
        root.addWidget(splitter, 1)

    def refresh_all(self) -> None:
        try:
            self.db_service.ensure()
            overview = self.db_service.overview()
            runs = self.db_service.run_catalog(limit=100)
            sources = self.db_service.sources()
            self._set_sources(sources)
            self._set_runs(runs)
            self.meta_label.setText(
                f"数据库：{overview.get('database_name', '-')} | 表：{overview.get('table_count', 0)} | "
                f"视图：{overview.get('view_count', 0)} | 最新批次：{overview.get('latest_run_id', '-')}"
            )
            self.messageEmitted.emit("数据库浏览数据已刷新。", "SUCCESS")
            self.query_selected()
        except Exception as exc:
            self.messageEmitted.emit(f"刷新数据库浏览失败：{exc}", "ERROR")

    def query_selected(self) -> None:
        display = self.source_combo.currentText()
        relation = self.source_display_to_name.get(display, "")
        if not relation:
            self.messageEmitted.emit("未选择表或视图。", "WARNING")
            return
        run_id = self.run_combo.currentText().strip() if self.only_run_check.isChecked() else None
        if run_id == "全部":
            run_id = None
        try:
            df = self.db_service.preview(relation, limit=self.limit_spin.value(), run_id=run_id)
            self._render_dataframe(df)
            run_text = f" | run_id={run_id}" if run_id and not relation.startswith("vw_latest_") else ""
            self.meta_label.setText(f"来源：{relation}{run_text} | 预览行数：{len(df)}")
            self.messageEmitted.emit(f"已加载 {relation}，行数：{len(df)}。", "SUCCESS")
        except Exception as exc:
            self.messageEmitted.emit(f"查询失败：{exc}", "ERROR")

    def load_report(self) -> None:
        run_id = self.run_combo.currentText().strip()
        if run_id == "全部":
            run_id = None
        try:
            row = self.db_service.ai_report(run_id=run_id or None)
            if not row:
                self.report_text.setPlainText("当前项目中未找到对应 AI 报告记录。")
                self.messageEmitted.emit("未找到对应 AI 报告记录。", "WARNING")
                return
            self.report_text.setPlainText(self._format_report(row))
            self.messageEmitted.emit(f"已加载 AI 报告：{row.get('run_id', '-')}", "SUCCESS")
        except Exception as exc:
            self.messageEmitted.emit(f"加载 AI 报告失败：{exc}", "ERROR")

    def _set_sources(self, sources: list[dict[str, str]]) -> None:
        current = self.source_combo.currentText()
        self.source_display_to_name = {f"{item['label']} [{item['name']}]": item["name"] for item in sources}
        values = list(self.source_display_to_name.keys())
        self.source_combo.clear()
        self.source_combo.addItems(values)
        preferred = next((v for v in values if "最新前瞻预测" in v), "")
        if current in values:
            self.source_combo.setCurrentText(current)
        elif preferred:
            self.source_combo.setCurrentText(preferred)

    def _set_runs(self, runs: pd.DataFrame) -> None:
        current = self.run_combo.currentText()
        self.run_combo.clear()
        self.run_combo.addItem("全部")
        if not runs.empty and "run_id" in runs.columns:
            for value in runs["run_id"].dropna().astype(str).tolist():
                self.run_combo.addItem(value)
        if current:
            index = self.run_combo.findText(current)
            if index >= 0:
                self.run_combo.setCurrentIndex(index)
        elif self.run_combo.count() > 1:
            self.run_combo.setCurrentIndex(1)

    def _render_dataframe(self, df: pd.DataFrame) -> None:
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setRowCount(len(df))
        self.table.setColumnCount(len(df.columns))
        self.table.setHorizontalHeaderLabels([str(col) for col in df.columns])
        for row_index, (_, row) in enumerate(df.iterrows()):
            for col_index, value in enumerate(row.tolist()):
                text = "" if pd.isna(value) else str(value)
                item = QTableWidgetItem(text)
                item.setForeground(COLORS_QBRUSH)
                self.table.setItem(row_index, col_index, item)
        self.table.resizeColumnsToContents()
        self.table.setSortingEnabled(True)

    @staticmethod
    def _format_report(row: dict[str, Any]) -> str:
        parts = [
            f"run_id：{row.get('run_id', '-')}",
            f"生成时间：{row.get('generated_at', '-')}",
            f"风险等级：{row.get('risk_level', '-')}",
            f"模型：{row.get('generator_model', '-')}",
            f"模式：{row.get('generator_mode', '-')}",
            "",
        ]
        sections = [
            ("执行摘要", row.get("executive_summary")),
            ("市场概览", row.get("market_overview")),
            ("未来 24 小时趋势", row.get("next_24h_trend")),
            ("高峰风险", row.get("peak_risk")),
            ("运营建议", row.get("operation_advice_json")),
            ("管理层摘要", row.get("management_summary")),
            ("告警摘要", row.get("alert_message")),
            ("局限性说明", row.get("limitations")),
        ]
        for title, content in sections:
            text = "" if content is None else str(content).strip()
            if title == "运营建议" and text.startswith("["):
                try:
                    values = json.loads(text)
                    text = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(values))
                except Exception:
                    pass
            if text:
                parts.append(f"【{title}】\n{text}\n")
        if len(parts) <= 6 and row.get("full_report_text"):
            parts.append(str(row["full_report_text"]))
        return "\n".join(parts)


from PySide6.QtGui import QBrush, QColor  # noqa: E402

COLORS_QBRUSH = QBrush(QColor(COLORS["body"]))
