from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ui.components.cards import ActionCard, SectionCard
from ui.components.form_widgets import make_button
from ui.components.layouts import ResponsiveGrid
from ui.components.log_panel import LogPanel
from ui.components.status_cards import MetricCard
from ui.services.task_service import TASK_MODE_DESCRIPTIONS
from ui.theme import COLORS


class DashboardPage(QWidget):
    runRequested = Signal(str)
    stopRequested = Signal()
    testDatabaseRequested = Signal()
    saveOutputRootRequested = Signal(str)
    openPathRequested = Signal(str)
    createTaskRequested = Signal(str, str, str)

    def __init__(self, output_root: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.action_cards: dict[str, ActionCard] = {}
        self.output_root = output_root

        root = QHBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 16)
        root.setSpacing(0)
        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(18)
        scroll.setWidget(content)
        splitter.addWidget(scroll)

        self._build_header()
        self._build_actions()
        self._build_output_section()
        self._build_task_section()
        self._build_quick_open()
        self.content_layout.addStretch(1)

        right_widget = QSplitter(Qt.Vertical)
        right_widget.setChildrenCollapsible(False)
        right_widget.addWidget(self._build_quick_status())
        right_widget.addWidget(self._build_mode_help())
        log_section = SectionCard("运行日志")
        self.log_panel = LogPanel()
        self.log_panel.setMinimumHeight(260)
        log_section.layout.addWidget(self.log_panel)
        right_widget.addWidget(log_section)
        right_widget.setSizes([210, 180, 360])
        right_widget.setStretchFactor(0, 2)
        right_widget.setStretchFactor(1, 1)
        right_widget.setStretchFactor(2, 4)
        splitter.addWidget(right_widget)
        splitter.setSizes([930, 430])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

    def _build_header(self) -> None:
        title = QLabel("电价预测 + AI日报 + 数据库落库一体化控制台")
        title.setObjectName("PageTitle")
        subtitle = QLabel("支持一键更新数据、正式前瞻预测、AI 报告生成、数据库同步、归档、任务计划和数据库浏览/查询。")
        subtitle.setObjectName("MutedText")
        subtitle.setWordWrap(True)
        self.content_layout.addWidget(title)
        self.content_layout.addWidget(subtitle)

    def _build_actions(self) -> None:
        section = SectionCard("日常预测与模型维护")
        grid = ResponsiveGrid(min_item_width=245, max_columns=3, spacing=12)
        actions = [
            ("fast_forecast", "FAST", "快速预测（使用 Active 模型）", "加载 Active 模型，不重新训练，速度更快", "日常", COLORS["success"]),
            ("refresh_fast_forecast", "DATA", "更新数据 + 快速预测", "先刷新数据，再快速推理，不重新训练", "推荐", COLORS["primary"]),
            ("skip_prediction", "AI", "仅重新生成 AI 报告", "复用已有预测结果", "", ""),
            ("retrain_model", "TRAIN", "完整训练并登记候选模型", "重新训练模型并保存候选产物，耗时较长", "重训", COLORS["warning"]),
            ("model_auto_optimize", "AUTO", "执行模型自优化", "回填真实值、更新误差记忆、判断是否重训", "", ""),
            ("compare_promote", "CMP", "候选模型对比上线", "对比 candidate 与 Active 模型", "", ""),
            ("refresh_data", "RUN", "更新数据并全流程", "兼容旧模式：会重新训练", "旧全流程", COLORS["warning"]),
            ("full", "FULL", "直接全流程", "兼容旧模式：不刷新数据但会重新训练", "", ""),
            ("prediction_report_only", "RPT", "预测并生成报告", "兼容旧模式：会重新预测/训练", "", ""),
            ("inventory", "M", "模型盘点", "查看本机模型", "", ""),
            ("model_monitor", "◎", "模型诊断检查", "健康/性能检查", "", ""),
            ("health_check", "✓", "健康检查", "系统与依赖检查", "", ""),
            ("test_database", "DB", "测试数据库连接", "连接 MySQL 数据库", "", ""),
        ]
        for index, (action_id, icon, title, subtitle, badge, color) in enumerate(actions):
            card = ActionCard(icon, title, subtitle, badge, color)
            if action_id == "test_database":
                card.clicked.connect(self.testDatabaseRequested.emit)
            else:
                card.clicked.connect(lambda checked=False, aid=action_id: self.runRequested.emit(aid))
            self.action_cards[action_id] = card
            grid.addWidget(card)

        stop_card = ActionCard("×", "停止当前任务", "当前无运行任务")
        stop_card.setEnabled(False)
        stop_card.clicked.connect(self.stopRequested.emit)
        self.action_cards["stop"] = stop_card
        grid.addWidget(stop_card)

        closure_card = ActionCard("↺", "数据库闭环同步", "同步结果表与追踪表")
        closure_card.clicked.connect(lambda: self.runRequested.emit("database_closure"))
        self.action_cards["database_closure"] = closure_card
        grid.addWidget(closure_card)
        section.layout.addWidget(grid)
        self.content_layout.addWidget(section)

    def _build_output_section(self) -> None:
        section = SectionCard("总输出目录")
        row = QHBoxLayout()
        label = QLabel("结果总目录")
        self.output_edit = QLineEdit(str(self.output_root))
        choose_btn = make_button("选择目录")
        save_btn = make_button("保存配置", primary=True)
        open_btn = make_button("打开目录")
        choose_btn.clicked.connect(self._choose_output_dir)
        save_btn.clicked.connect(lambda: self.saveOutputRootRequested.emit(self.output_edit.text()))
        open_btn.clicked.connect(lambda: self.openPathRequested.emit(self.output_edit.text()))
        row.addWidget(label)
        row.addWidget(self.output_edit, 1)
        row.addWidget(choose_btn)
        row.addWidget(save_btn)
        row.addWidget(open_btn)
        section.layout.addLayout(row)
        self.content_layout.addWidget(section)

    def _build_task_section(self) -> None:
        section = SectionCard("任务计划")
        row = QHBoxLayout()
        self.task_name_edit = QLineEdit("PowerMarketDailyAutomation")
        self.task_time_edit = QLineEdit("06:30")
        self.task_mode_combo = QComboBox()
        self.task_mode_combo.addItems(list(TASK_MODE_DESCRIPTIONS.keys()))
        create_btn = make_button("创建/覆盖任务计划", primary=True)
        create_btn.clicked.connect(
            lambda: self.createTaskRequested.emit(
                self.task_name_edit.text().strip(),
                self.task_time_edit.text().strip(),
                self.task_mode_combo.currentText(),
            )
        )
        row.addWidget(QLabel("任务名称"))
        row.addWidget(self.task_name_edit, 2)
        row.addWidget(QLabel("每日时间"))
        row.addWidget(self.task_time_edit, 1)
        row.addWidget(QLabel("执行模式"))
        row.addWidget(self.task_mode_combo, 2)
        row.addWidget(create_btn)
        section.layout.addLayout(row)
        self.task_hint = QLabel()
        self.task_hint.setObjectName("MutedText")
        self.task_hint.setWordWrap(True)
        section.layout.addWidget(self.task_hint)
        self.task_mode_combo.currentTextChanged.connect(self._update_task_hint)
        self._update_task_hint(self.task_mode_combo.currentText())
        self.content_layout.addWidget(section)

    def _build_quick_open(self) -> None:
        section = SectionCard("快捷打开")
        grid = ResponsiveGrid(min_item_width=190, max_columns=4, spacing=12)
        actions = [
            ("打开总结果目录", "FINAL_OUTPUT_ROOT"),
            ("打开内部结果目录", "RESULT_TABLE_DIR"),
            ("打开日志目录", "LOG_DIR"),
            ("打开使用说明", "README"),
        ]
        for index, (title, target) in enumerate(actions):
            button = make_button(title)
            button.clicked.connect(lambda checked=False, t=target: self.openPathRequested.emit(t))
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            grid.addWidget(button)
        section.layout.addWidget(grid)
        self.content_layout.addWidget(section)

    def _build_quick_status(self) -> SectionCard:
        section = SectionCard("快速状态")
        grid = ResponsiveGrid(min_item_width=155, max_columns=2, spacing=10)
        self.status_cards = {
            "database": MetricCard("数据库连接", "检查中"),
            "latest_data": MetricCard("最新数据", "-"),
            "latest_prediction": MetricCard("最新预测", "-"),
            "latest_report": MetricCard("最新 AI 报告", "-"),
            "task": MetricCard("任务计划", "待创建"),
            "health": MetricCard("系统健康", "待检查"),
        }
        for index, card in enumerate(self.status_cards.values()):
            grid.addWidget(card)
        section.layout.addWidget(grid)
        return section

    def _build_mode_help(self) -> SectionCard:
        section = SectionCard("运行模式说明")
        for mode, desc in TASK_MODE_DESCRIPTIONS.items():
            row = QHBoxLayout()
            tag = QLabel(mode)
            tag.setStyleSheet(
                f"color: {COLORS['text']}; background: rgba(37, 99, 235, 0.28); "
                "border-radius: 5px; padding: 3px 7px;"
            )
            text = QLabel(desc)
            text.setObjectName("MutedText")
            text.setWordWrap(True)
            row.addWidget(tag)
            row.addWidget(text, 1)
            section.layout.addLayout(row)
        return section

    def _choose_output_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择总输出目录", self.output_edit.text())
        if selected:
            self.output_edit.setText(selected)

    def _update_task_hint(self, mode: str) -> None:
        self.task_hint.setText(f"模式说明：{TASK_MODE_DESCRIPTIONS.get(mode, '-')}")

    def set_output_root(self, path: Path) -> None:
        self.output_edit.setText(str(path))

    def set_running(self, running: bool) -> None:
        for key, card in self.action_cards.items():
            card.setEnabled(not running)
        self.action_cards["stop"].setEnabled(running)

    def append_log(self, message: str, level: str | None = None) -> None:
        self.log_panel.append(message, level)

    def update_status(self, data: dict[str, str]) -> None:
        if "database" in data:
            color = COLORS["success"] if "已连接" in data["database"] or "成功" in data["database"] else COLORS["danger"]
            self.status_cards["database"].set_value(data["database"], color)
        if "latest_data" in data:
            self.status_cards["latest_data"].set_value(data["latest_data"])
        if "latest_prediction" in data:
            self.status_cards["latest_prediction"].set_value(data["latest_prediction"])
        if "latest_report" in data:
            self.status_cards["latest_report"].set_value(data["latest_report"])
        if "task" in data:
            self.status_cards["task"].set_value(data["task"], COLORS["success"])
        if "health" in data:
            self.status_cards["health"].set_value(data["health"], COLORS["success"])
