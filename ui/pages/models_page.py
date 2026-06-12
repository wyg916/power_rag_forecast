from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.components.cards import ActionCard, SectionCard
from ui.components.form_widgets import make_button
from ui.components.layouts import ResponsiveGrid, make_scroll_page
from ui.components.status_cards import KeyValueRow, MetricCard
from ui.components.worker import Worker
from ui.services.model_service import ModelService
from ui.theme import COLORS


class ModelsPage(QWidget):
    messageEmitted = Signal(str, str)
    commandRequested = Signal(object)
    openPathRequested = Signal(str)

    def __init__(self, model_service: ModelService, parent: QWidget | None = None, auto_refresh: bool = True):
        super().__init__(parent)
        self.model_service = model_service
        self.thread_pool = QThreadPool.globalInstance()
        self._loading = False

        root, _scroll, _content = make_scroll_page(self)

        title = QLabel("模型中心")
        title.setObjectName("PageTitle")
        subtitle = QLabel("集中查看 Active 模型、版本 registry、误差指标、artifact 和候选模型对比。")
        subtitle.setObjectName("MutedText")
        root.addWidget(title)
        root.addWidget(subtitle)

        toolbar = ResponsiveGrid(min_item_width=185, max_columns=5, spacing=8)
        self.refresh_btn = make_button("刷新模型数据", primary=True)
        self.update_memory_btn = make_button("更新误差记忆")
        self.ops_btn = make_button("执行每日模型运维", primary=True)
        self.compare_btn = make_button("候选模型对比")
        self.auto_optimize_btn = make_button("执行模型自优化")
        self.promote_btn = make_button("最新候选设为 Active")
        self.toggle_bias_btn = make_button("切换偏差校正")
        self.open_artifacts_btn = make_button("打开 model_artifacts")
        self.refresh_btn.clicked.connect(self.refresh_async)
        self.update_memory_btn.clicked.connect(lambda: self.commandRequested.emit(self.model_service.error_memory_command()))
        self.ops_btn.clicked.connect(lambda: self.commandRequested.emit(self.model_service.model_ops_command()))
        self.compare_btn.clicked.connect(lambda: self.commandRequested.emit(self.model_service.compare_command()))
        self.auto_optimize_btn.clicked.connect(lambda: self.commandRequested.emit(self.model_service.auto_optimize_command()))
        self.promote_btn.clicked.connect(lambda: self.commandRequested.emit(self.model_service.promote_latest_candidate_command()))
        self.toggle_bias_btn.clicked.connect(self._toggle_bias_async)
        self.open_artifacts_btn.clicked.connect(lambda: self.openPathRequested.emit(str(self.model_service.artifacts_dir())))
        for button in [
            self.refresh_btn,
            self.update_memory_btn,
            self.ops_btn,
            self.compare_btn,
            self.auto_optimize_btn,
            self.promote_btn,
            self.toggle_bias_btn,
            self.open_artifacts_btn,
        ]:
            toolbar.addWidget(button)
        root.addWidget(toolbar)

        body = QSplitter(Qt.Horizontal)
        body.setChildrenCollapsible(False)
        body.setMinimumHeight(560)
        root.addWidget(body, 1)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QScrollArea.NoFrame)
        left_content = QWidget()
        left_layout = QVBoxLayout(left_content)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(14)
        left_scroll.setWidget(left_content)
        body.addWidget(left_scroll)

        self.active_card = SectionCard("当前 Active 模型总览")
        self.active_rows = {
            "model_version": KeyValueRow("模型版本", "-"),
            "model_role": KeyValueRow("模型角色", "-"),
            "status": KeyValueRow("状态", "-"),
            "source": KeyValueRow("数据来源", "-"),
            "created_at": KeyValueRow("创建时间", "-"),
            "activated_at": KeyValueRow("激活时间", "-"),
            "artifact_complete": KeyValueRow("Artifact 完整性", "-"),
            "can_fast_forecast": KeyValueRow("快速预测可用", "-"),
            "latest_fast_forecast_time": KeyValueRow("最近快速预测", "-"),
            "latest_retrain_time": KeyValueRow("最近完整重训", "-"),
            "latest_auto_optimize_time": KeyValueRow("最近自动优化", "-"),
            "missing_files": KeyValueRow("缺失文件/提示", "-"),
            "artifact_path": KeyValueRow("Artifact 路径", "-"),
        }
        for row in self.active_rows.values():
            self.active_card.layout.addWidget(row)
        left_layout.addWidget(self.active_card)

        metrics_card = SectionCard("模型指标")
        grid = ResponsiveGrid(min_item_width=150, max_columns=3, spacing=10)
        self.metric_cards = {
            "mae": MetricCard("MAE", "-"),
            "rmse": MetricCard("RMSE", "-"),
            "mape": MetricCard("MAPE", "-"),
            "r2": MetricCard("R2", "-"),
            "peak_rmse": MetricCard("高峰 RMSE", "-"),
            "spike_rmse": MetricCard("尖峰 RMSE", "-"),
        }
        for card in self.metric_cards.values():
            grid.addWidget(card)
        metrics_card.layout.addWidget(grid)
        left_layout.addWidget(metrics_card)

        learning_card = SectionCard("误差记忆与校正效果")
        learning_grid = ResponsiveGrid(min_item_width=150, max_columns=3, spacing=10)
        self.memory_cards = {
            "sample_count": MetricCard("记忆样本数", "-"),
            "avg_bias": MetricCard("平均偏差", "-"),
            "peak_avg_bias": MetricCard("高峰平均偏差", "-"),
            "spike_avg_bias": MetricCard("尖峰平均偏差", "-"),
            "corrected_mae": MetricCard("校正后 MAE", "-"),
            "improvement_pct": MetricCard("校正提升", "-"),
        }
        for card in self.memory_cards.values():
            learning_grid.addWidget(card)
        learning_card.layout.addWidget(learning_grid)
        left_layout.addWidget(learning_card)

        self_learning_card = SectionCard("自学习状态")
        self.learning_rows = {
            "bias_correction_status": KeyValueRow("偏差校正", "-"),
            "should_retrain": KeyValueRow("重训建议", "-"),
            "retrain_reason": KeyValueRow("判断原因", "-"),
            "strategy_memory_status": KeyValueRow("策略记忆", "-"),
            "error_memory_status": KeyValueRow("误差记忆", "-"),
            "model_version": KeyValueRow("关联模型", "-"),
        }
        for row in self.learning_rows.values():
            self_learning_card.layout.addWidget(row)
        left_layout.addWidget(self_learning_card)

        action_card = SectionCard("模型动作")
        action_grid = ResponsiveGrid(min_item_width=210, max_columns=2, spacing=12)
        trend_card = ActionCard("↗", "最近误差趋势", "查看 prediction_tracking 聚合误差")
        trend_card.clicked.connect(lambda: self.tabs_hint.setPlainText("最近误差趋势位于右侧下方表格。"))
        compare_card = ActionCard("⇄", "候选模型与 Active 对比", "执行 07_compare_and_promote_model.py")
        compare_card.clicked.connect(lambda: self.commandRequested.emit(self.model_service.compare_command()))
        memory_card = ActionCard("MEM", "更新误差记忆", "用真实值回填后的 prediction_tracking 生成分层误差记忆")
        memory_card.clicked.connect(lambda: self.commandRequested.emit(self.model_service.error_memory_command()))
        retrain_card = ActionCard("TRAIN", "完整训练候选模型", "重新训练并保存 candidate artifact")
        retrain_card.clicked.connect(lambda: self.commandRequested.emit(self.model_service.retrain_command()))
        auto_card = ActionCard("AUTO", "一键执行自动优化", "回填、误差记忆、退化判断、必要时候选重训")
        auto_card.clicked.connect(lambda: self.commandRequested.emit(self.model_service.auto_optimize_command()))
        promote_card = ActionCard("ACTIVE", "一键设为 Active", "将最新 candidate 模型设为 Active")
        promote_card.clicked.connect(lambda: self.commandRequested.emit(self.model_service.promote_latest_candidate_command()))
        toggle_card = ActionCard("BIAS", "启用/关闭偏差校正", "修改 model_learning.bias_correction_enabled")
        toggle_card.clicked.connect(self._toggle_bias_async)
        ops_card = ActionCard("◎", "每日模型运维", "闭环同步、真实值回填、健康监控")
        ops_card.clicked.connect(lambda: self.commandRequested.emit(self.model_service.model_ops_command()))
        artifact_card = ActionCard("DIR", "打开 artifact 目录", "查看本地模型产物")
        artifact_card.clicked.connect(lambda: self.openPathRequested.emit(str(self.model_service.artifacts_dir())))
        for card in [trend_card, compare_card, memory_card, retrain_card, auto_card, promote_card, toggle_card, ops_card, artifact_card]:
            action_grid.addWidget(card)
        action_card.layout.addWidget(action_grid)
        left_layout.addWidget(action_card)
        left_layout.addStretch(1)

        right_widget = QWidget()
        right = QVBoxLayout(right_widget)
        right.setSpacing(14)
        right.setContentsMargins(0, 0, 0, 0)
        body.addWidget(right_widget)

        version_card = SectionCard("模型版本列表")
        self.versions_table = QTableWidget()
        self.versions_table.setAlternatingRowColors(True)
        self.versions_table.setWordWrap(False)
        self.versions_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        version_card.layout.addWidget(self.versions_table)
        right.addWidget(version_card, 2)

        tabs = QTabWidget()
        error_card = SectionCard("最近误差趋势")
        self.error_table = QTableWidget()
        self.error_table.setAlternatingRowColors(True)
        self.error_table.setWordWrap(False)
        self.error_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        error_card.layout.addWidget(self.error_table)
        artifact_card = SectionCard("Artifact 与对比记录")
        self.artifact_table = QTableWidget()
        self.artifact_table.setAlternatingRowColors(True)
        self.artifact_table.setWordWrap(False)
        self.artifact_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tabs_hint = QPlainTextEdit()
        self.tabs_hint.setReadOnly(True)
        self.tabs_hint.setMinimumHeight(72)
        self.tabs_hint.setMaximumHeight(110)
        artifact_card.layout.addWidget(self.artifact_table)
        artifact_card.layout.addWidget(self.tabs_hint)
        comparison_card = SectionCard("候选模型对比")
        self.comparison_table = QTableWidget()
        self.comparison_table.setAlternatingRowColors(True)
        self.comparison_table.setWordWrap(False)
        self.comparison_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        comparison_card.layout.addWidget(self.comparison_table)
        tabs.addTab(error_card, "最近误差趋势")
        tabs.addTab(artifact_card, "Artifact 对比记录")
        tabs.addTab(comparison_card, "候选模型对比")
        right.addWidget(tabs, 2)
        body.setSizes([520, 940])
        body.setStretchFactor(0, 35)
        body.setStretchFactor(1, 65)

        self.empty_label = QLabel("")
        self.empty_label.setObjectName("MutedText")
        root.addWidget(self.empty_label)
        if auto_refresh:
            self.refresh_async()

    def refresh_async(self) -> None:
        if self._loading:
            return
        self._set_loading(True)
        worker = Worker(self.model_service.load_summary)
        worker.signals.success.connect(self._apply_summary)
        worker.signals.error.connect(self._refresh_error)
        self.thread_pool.start(worker)

    def set_running(self, running: bool) -> None:
        self.update_memory_btn.setEnabled(not running)
        self.ops_btn.setEnabled(not running)
        self.compare_btn.setEnabled(not running)
        self.auto_optimize_btn.setEnabled(not running)
        self.promote_btn.setEnabled(not running)
        self.toggle_bias_btn.setEnabled(not running)

    def _toggle_bias_async(self) -> None:
        if self._loading:
            return
        self._set_loading(True)
        worker = Worker(self.model_service.toggle_bias_correction)
        worker.signals.success.connect(self._toggle_bias_done)
        worker.signals.error.connect(self._refresh_error)
        self.thread_pool.start(worker)

    def _toggle_bias_done(self, payload: dict[str, Any]) -> None:
        self._set_loading(False)
        self.messageEmitted.emit(str(payload.get("message", "偏差校正配置已更新。")), "SUCCESS")
        self.refresh_async()

    def _set_loading(self, loading: bool) -> None:
        self._loading = loading
        self.refresh_btn.setEnabled(not loading)
        self.refresh_btn.setText("刷新中..." if loading else "刷新模型数据")

    def _refresh_error(self, message: str) -> None:
        self._set_loading(False)
        self.messageEmitted.emit(f"模型中心刷新失败：{message}", "ERROR")
        self.empty_label.setText("模型中心数据加载失败，已保留页面空状态。")

    def _apply_summary(self, payload: dict[str, Any]) -> None:
        self._set_loading(False)
        active = payload.get("active") or {}
        for key, row in self.active_rows.items():
            row.set_value(self._format_value(active.get(key)))
        metrics = payload.get("metrics") or {}
        for key, card in self.metric_cards.items():
            card.set_value(self._format_metric(metrics.get(key)))
        error_memory = payload.get("error_memory") or {}
        correction = payload.get("correction_effect") or {}
        self.memory_cards["sample_count"].set_value(self._format_value(error_memory.get("sample_count")))
        self.memory_cards["avg_bias"].set_value(self._format_metric(error_memory.get("avg_bias")))
        self.memory_cards["peak_avg_bias"].set_value(self._format_metric(error_memory.get("peak_avg_bias")))
        self.memory_cards["spike_avg_bias"].set_value(self._format_metric(error_memory.get("spike_avg_bias")))
        self.memory_cards["corrected_mae"].set_value(self._format_metric(correction.get("corrected_mae")))
        self.memory_cards["improvement_pct"].set_value(self._format_percent(correction.get("improvement_pct")))
        learning = payload.get("self_learning") or {}
        for key, row in self.learning_rows.items():
            row.set_value(self._format_learning_value(learning.get(key)))
        self.toggle_bias_btn.setText("关闭偏差校正" if learning.get("bias_correction_enabled", True) else "启用偏差校正")
        self._render_dataframe(self.versions_table, payload.get("versions", pd.DataFrame()))
        self._render_dataframe(self.error_table, payload.get("error_trend", pd.DataFrame()))
        artifacts = payload.get("artifacts", pd.DataFrame())
        comparison = payload.get("comparison", pd.DataFrame())
        self._render_dataframe(self.artifact_table, artifacts)
        self._render_dataframe(self.comparison_table, comparison)
        if artifacts.empty:
            self.tabs_hint.setPlainText("当前暂无本地模型产物，完整训练后将自动展示 artifact。\n\n" f"数据来源：{payload.get('source', '-')}")
        else:
            self.tabs_hint.setPlainText(f"数据来源：{payload.get('source', '-')}")
        self.empty_label.setText(payload.get("empty_message", ""))
        self.messageEmitted.emit("模型中心数据已刷新。", "SUCCESS")

    @staticmethod
    def _format_value(value: Any) -> str:
        if value is None:
            return "-"
        if isinstance(value, float) and pd.isna(value):
            return "-"
        return str(value) if str(value).strip() else "-"

    @staticmethod
    def _format_metric(value: Any) -> str:
        try:
            if value is None or pd.isna(value):
                return "-"
            number = float(value)
            return f"{number:.4f}"
        except Exception:
            return ModelsPage._format_value(value)

    @staticmethod
    def _format_percent(value: Any) -> str:
        try:
            if value is None or pd.isna(value):
                return "-"
            return f"{float(value):.2f}%"
        except Exception:
            return ModelsPage._format_value(value)

    @staticmethod
    def _format_learning_value(value: Any) -> str:
        if isinstance(value, dict):
            if not value:
                return "-"
            for key in ["strategy_id", "model_version", "rmse"]:
                if key in value and value.get(key) not in {None, ""}:
                    return str(value.get(key))
            return str(value)
        return ModelsPage._format_value(value)

    @staticmethod
    def _render_dataframe(table: QTableWidget, df: pd.DataFrame) -> None:
        table.setSortingEnabled(False)
        table.clear()
        if df is None or df.empty:
            table.setRowCount(1)
            table.setColumnCount(1)
            table.setHorizontalHeaderLabels(["状态"])
            table.setItem(0, 0, QTableWidgetItem("暂无数据"))
            table.setSortingEnabled(False)
            return
        output = df.copy()
        output = output[[col for col in output.columns if not str(col).startswith("_")]]
        table.setRowCount(len(output))
        table.setColumnCount(len(output.columns))
        table.setHorizontalHeaderLabels([str(col) for col in output.columns])
        brush = QBrush(QColor(COLORS["body"]))
        for row_index, (_, row) in enumerate(output.iterrows()):
            for col_index, value in enumerate(row.tolist()):
                text = ModelsPage._cell_text(value)
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
