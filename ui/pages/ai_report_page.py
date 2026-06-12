from __future__ import annotations

import json
from typing import Any

import pandas as pd
from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.components.cards import SectionCard
from ui.components.form_widgets import make_button
from ui.components.layouts import ResponsiveGrid, make_scroll_page
from ui.components.status_cards import KeyValueRow, MetricCard
from ui.components.worker import Worker
from ui.services.report_service import ReportService
from ui.theme import COLORS


class AIReportPage(QWidget):
    messageEmitted = Signal(str, str)
    commandRequested = Signal(object)
    openPathRequested = Signal(str)

    def __init__(self, report_service: ReportService, parent: QWidget | None = None, auto_refresh: bool = True):
        super().__init__(parent)
        self.report_service = report_service
        self.thread_pool = QThreadPool.globalInstance()
        self._loading = False
        self._paths: dict[str, str] = {}
        self._current_run_id = ""

        root, _scroll, _content = make_scroll_page(self)

        title = QLabel("AI 报告中心")
        title.setObjectName("PageTitle")
        subtitle = QLabel("查看最新 AI 日报、历史报告、报告文件和可信检查结果。")
        subtitle.setObjectName("MutedText")
        root.addWidget(title)
        root.addWidget(subtitle)

        toolbar = ResponsiveGrid(min_item_width=180, max_columns=5, spacing=8)
        self.refresh_btn = make_button("刷新报告数据", primary=True)
        self.open_word_btn = make_button("打开 Word 报告")
        self.open_report_json_btn = make_button("打开 ai_report_structured.json")
        self.open_summary_btn = make_button("打开 ai_input_summary.json")
        self.regenerate_btn = make_button("重新生成 AI 报告", primary=True)
        self.refresh_btn.clicked.connect(self.refresh_async)
        self.open_word_btn.clicked.connect(lambda: self._open_path("word_report"))
        self.open_report_json_btn.clicked.connect(lambda: self._open_path("report_json"))
        self.open_summary_btn.clicked.connect(lambda: self._open_path("input_summary"))
        self.regenerate_btn.clicked.connect(lambda: self.commandRequested.emit(self.report_service.regenerate_command()))
        for button in [self.refresh_btn, self.open_word_btn, self.open_report_json_btn, self.open_summary_btn, self.regenerate_btn]:
            toolbar.addWidget(button)
        root.addWidget(toolbar)

        status_card = SectionCard("最新 AI 报告状态")
        status_grid = ResponsiveGrid(min_item_width=220, max_columns=4, spacing=10)
        self.status_cards = {
            "run_id": MetricCard("运行批次", "-"),
            "generated_at": MetricCard("生成时间", "-"),
            "risk_level": MetricCard("风险等级", "-"),
            "generator_mode": MetricCard("生成模式", "-"),
        }
        for card in self.status_cards.values():
            status_grid.addWidget(card)
        status_card.layout.addWidget(status_grid)
        self.path_rows = {
            "word_report": KeyValueRow("Word 报告", "-"),
            "report_json": KeyValueRow("结构化报告 JSON", "-"),
            "input_summary": KeyValueRow("AI 输入摘要 JSON", "-"),
            "source": KeyValueRow("数据来源", "-"),
        }
        for row in self.path_rows.values():
            status_card.layout.addWidget(row)
        root.addWidget(status_card)

        review_card = SectionCard("报告审批流")
        review_grid = ResponsiveGrid(min_item_width=220, max_columns=4, spacing=10)
        self.review_cards = {
            "status": MetricCard("当前报告状态", "待审核"),
            "reviewer": MetricCard("审核人", "-"),
            "reviewed_at": MetricCard("审核时间", "-"),
            "dispatch_allowed": MetricCard("是否允许派发", "否"),
        }
        for card in self.review_cards.values():
            card.setMinimumHeight(62)
            card.setMaximumHeight(76)
            review_grid.addWidget(card)
        review_card.layout.addWidget(review_grid)

        reviewer_row = QHBoxLayout()
        reviewer_row.addWidget(QLabel("审核人"))
        self.reviewer_input = QLineEdit()
        self.reviewer_input.setPlaceholderText("默认使用当前系统用户")
        reviewer_row.addWidget(self.reviewer_input)
        reviewer_row.addWidget(QLabel("审核意见"))
        self.review_comment = QPlainTextEdit()
        self.review_comment.setMinimumHeight(60)
        self.review_comment.setMaximumHeight(82)
        self.review_comment.setPlaceholderText("填写审批意见、驳回原因或派发说明")
        reviewer_row.addWidget(self.review_comment, 1)
        review_card.layout.addLayout(reviewer_row)

        review_buttons = ResponsiveGrid(min_item_width=160, max_columns=4, spacing=8)
        self.approve_btn = make_button("通过报告", primary=True)
        self.reject_btn = make_button("驳回报告", danger=True)
        self.pending_btn = make_button("标记待审核")
        self.dispatch_btn = make_button("检查并标记已派发")
        self.dispatch_message = QLabel("")
        self.dispatch_message.setObjectName("MutedText")
        self.approve_btn.clicked.connect(lambda: self._review_action("approved"))
        self.reject_btn.clicked.connect(lambda: self._review_action("rejected"))
        self.pending_btn.clicked.connect(lambda: self._review_action("pending"))
        self.dispatch_btn.clicked.connect(lambda: self._review_action("dispatched"))
        self.review_action_buttons = [self.approve_btn, self.reject_btn, self.pending_btn, self.dispatch_btn]
        for button in self.review_action_buttons:
            review_buttons.addWidget(button)
        review_card.layout.addWidget(review_buttons)
        review_card.layout.addWidget(self.dispatch_message)
        root.addWidget(review_card)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setMinimumHeight(430)
        history_card = SectionCard("历史报告列表")
        self.history_table = QTableWidget()
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setWordWrap(False)
        self.history_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.history_table.itemSelectionChanged.connect(self._history_selection_changed)
        history_card.layout.addWidget(self.history_table)

        preview_card = SectionCard("报告预览")
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        preview_card.layout.addWidget(self.preview)

        quality_card = SectionCard("报告可信检查结果")
        self.quality_overall = QLabel("-")
        self.quality_overall.setObjectName("SectionTitle")
        self.quality_table = QTableWidget()
        self.quality_table.setAlternatingRowColors(True)
        self.quality_table.setWordWrap(False)
        self.quality_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        quality_card.layout.addWidget(self.quality_overall)
        quality_card.layout.addWidget(self.quality_table)

        splitter.addWidget(history_card)
        splitter.addWidget(preview_card)
        splitter.addWidget(quality_card)
        splitter.setSizes([520, 640, 360])
        splitter.setStretchFactor(0, 35)
        splitter.setStretchFactor(1, 40)
        splitter.setStretchFactor(2, 25)
        root.addWidget(splitter, 1)

        self.empty_label = QLabel("")
        self.empty_label.setObjectName("MutedText")
        root.addWidget(self.empty_label)
        if auto_refresh:
            self.refresh_async()

    def refresh_async(self) -> None:
        if self._loading:
            return
        self._set_loading(True)
        worker = Worker(self.report_service.load_summary)
        worker.signals.success.connect(self._apply_summary)
        worker.signals.error.connect(self._refresh_error)
        self.thread_pool.start(worker)

    def set_running(self, running: bool) -> None:
        self.regenerate_btn.setEnabled(not running)
        for button in getattr(self, "review_action_buttons", []):
            button.setEnabled(not running and not self._loading)

    def _set_loading(self, loading: bool) -> None:
        self._loading = loading
        self.refresh_btn.setEnabled(not loading)
        self.refresh_btn.setText("刷新中..." if loading else "刷新报告数据")
        for button in getattr(self, "review_action_buttons", []):
            button.setEnabled(not loading)

    def _refresh_error(self, message: str) -> None:
        self._set_loading(False)
        self.messageEmitted.emit(f"AI 报告中心刷新失败：{message}", "ERROR")
        self.empty_label.setText("AI 报告数据加载失败，已保留页面空状态。")

    def _apply_summary(self, payload: dict[str, Any]) -> None:
        self._set_loading(False)
        latest = payload.get("latest") or {}
        self._current_run_id = str(latest.get("run_id") or "")
        self._paths = payload.get("paths") or {}
        self.status_cards["run_id"].set_value(str(latest.get("run_id") or "-"))
        self.status_cards["generated_at"].set_value(str(latest.get("generated_at") or "-"))
        self.status_cards["risk_level"].set_value(str(latest.get("risk_level") or "-"))
        self.status_cards["generator_mode"].set_value(str(latest.get("generator_mode") or (latest.get("generator") or {}).get("mode") or "-"))
        for key, row in self.path_rows.items():
            row.set_value(payload.get("source") if key == "source" else self._paths.get(key, "-"))
        self._render_dataframe(self.history_table, payload.get("history", pd.DataFrame()))
        self.preview.setPlainText(self._format_report(latest))
        self._render_quality(payload.get("quality") or {})
        self._render_review(payload.get("review") or {}, payload.get("dispatch_check") or {})
        self.empty_label.setText(payload.get("empty_message", ""))
        self.messageEmitted.emit("AI 报告中心数据已刷新。", "SUCCESS")

    def _open_path(self, key: str) -> None:
        path = self._paths.get(key, "")
        if not path:
            self.messageEmitted.emit("当前没有可打开的报告文件路径。", "WARNING")
            return
        self.openPathRequested.emit(path)

    def _history_selection_changed(self) -> None:
        items = self.history_table.selectedItems()
        if not items:
            return
        row = items[0].row()
        headers = [self.history_table.horizontalHeaderItem(i).text() for i in range(self.history_table.columnCount())]
        values = {
            headers[col]: self.history_table.item(row, col).text() if self.history_table.item(row, col) else ""
            for col in range(self.history_table.columnCount())
        }
        path = values.get("word_report_path", "")
        if path:
            self.path_rows["word_report"].set_value(path)
            self._paths["word_report"] = path
        if values.get("run_id"):
            self._current_run_id = values.get("run_id", "")

    def _render_review(self, review: dict[str, Any], dispatch_check: dict[str, Any]) -> None:
        status = str(review.get("review_status") or "pending")
        status_label = str(review.get("status_label") or {"pending": "待审核", "approved": "已通过", "rejected": "已驳回", "dispatched": "已派发"}.get(status, status))
        status_color = {
            "pending": COLORS["warning"],
            "approved": COLORS["success"],
            "rejected": COLORS["danger"],
            "dispatched": COLORS["primary"],
        }.get(status, COLORS["muted"])
        allowed = bool(dispatch_check.get("allowed"))
        self.review_cards["status"].set_value(status_label, status_color)
        self.review_cards["reviewer"].set_value(str(review.get("reviewer") or "-"))
        self.review_cards["reviewed_at"].set_value(str(review.get("reviewed_at") or "-"))
        self.review_cards["dispatch_allowed"].set_value("允许" if allowed else "不允许", COLORS["success"] if allowed else COLORS["warning"])
        if review.get("reviewer") and not self.reviewer_input.text().strip():
            self.reviewer_input.setText(str(review.get("reviewer")))
        self.review_comment.setPlainText(str(review.get("review_comment") or ""))
        reasons = dispatch_check.get("reasons") or []
        self.dispatch_message.setText("派发检查通过。" if allowed else "派发限制：" + "；".join(reasons[:2]) if reasons else "派发前需通过审批与可信检查。")

    def _review_action(self, action: str) -> None:
        run_id = self._current_run_id or "local_current"
        reviewer = self.reviewer_input.text().strip()
        comment = self.review_comment.toPlainText().strip()
        if action == "approved":
            fn = lambda: self.report_service.approve_report(run_id, reviewer, comment)
        elif action == "rejected":
            fn = lambda: self.report_service.reject_report(run_id, reviewer, comment)
        elif action == "dispatched":
            fn = lambda: self.report_service.mark_report_dispatched(run_id, reviewer, comment)
        else:
            fn = lambda: self.report_service.mark_report_pending(run_id, reviewer, comment)
        self._set_loading(True)
        worker = Worker(fn)
        worker.signals.success.connect(self._review_action_finished)
        worker.signals.error.connect(self._review_action_error)
        self.thread_pool.start(worker)

    def _review_action_finished(self, result: dict[str, Any]) -> None:
        self._set_loading(False)
        if result.get("success") is False:
            self.messageEmitted.emit(str(result.get("message") or "审批操作未通过。"), "WARNING")
        else:
            status = result.get("review") or result
            label = status.get("status_label") or "审批状态已更新"
            storage = status.get("storage") or ""
            self.messageEmitted.emit(f"AI 报告审批状态已更新：{label}" + (f"（{storage}）" if storage else ""), "SUCCESS")
        self.refresh_async()

    def _review_action_error(self, message: str) -> None:
        self._set_loading(False)
        self.messageEmitted.emit(f"AI 报告审批操作失败：{message}", "ERROR")

    def _render_quality(self, quality: dict[str, Any]) -> None:
        overall = quality.get("overall", "-")
        color = COLORS["success"] if overall == "通过" else COLORS["warning"] if overall == "警告" else COLORS["danger"]
        self.quality_overall.setText(f"总体结果：{overall}")
        self.quality_overall.setStyleSheet(f"color: {color}; font-weight: 700;")
        df = pd.DataFrame(quality.get("checks", []))
        self._render_dataframe(self.quality_table, df)

    @staticmethod
    def _format_report(report: dict[str, Any]) -> str:
        if not report:
            return "暂无 AI 报告数据。"
        advice = report.get("operation_advice")
        if isinstance(advice, str):
            try:
                advice = json.loads(advice)
            except Exception:
                pass
        if isinstance(advice, list):
            advice_text = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(advice))
        else:
            advice_text = str(advice or "")
        sections = [
            ("管理摘要", report.get("management_summary")),
            ("市场概览", report.get("market_overview")),
            ("未来24小时趋势", report.get("next_24h_trend")),
            ("高峰风险", report.get("peak_risk")),
            ("操作建议", advice_text),
            ("风险提示", report.get("alert_message")),
        ]
        lines = [
            f"run_id：{report.get('run_id', '-')}",
            f"生成时间：{report.get('generated_at', '-')}",
            f"风险等级：{report.get('risk_level', '-')}",
            "",
        ]
        for title, content in sections:
            text = "" if content is None else str(content).strip()
            if text:
                lines.append(f"【{title}】\n{text}\n")
        return "\n".join(lines)

    @staticmethod
    def _render_dataframe(table: QTableWidget, df: pd.DataFrame) -> None:
        table.setSortingEnabled(False)
        table.clear()
        if df is None or df.empty:
            table.setRowCount(1)
            table.setColumnCount(1)
            table.setHorizontalHeaderLabels(["状态"])
            table.setItem(0, 0, QTableWidgetItem("暂无数据"))
            return
        output = df.copy()
        table.setRowCount(len(output))
        table.setColumnCount(len(output.columns))
        table.setHorizontalHeaderLabels([str(col) for col in output.columns])
        brush = QBrush(QColor(COLORS["body"]))
        for row_index, (_, row) in enumerate(output.iterrows()):
            for col_index, value in enumerate(row.tolist()):
                text = AIReportPage._cell_text(value)
                item = QTableWidgetItem(text)
                item.setForeground(brush)
                table.setItem(row_index, col_index, item)
        table.resizeColumnsToContents()
        table.setSortingEnabled(True)

    @staticmethod
    def _cell_text(value: Any) -> str:
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass
        return str(value)
