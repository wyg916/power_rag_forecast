from __future__ import annotations

import getpass
import platform
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from database_utils import get_database_config
from automation_common import load_config
from ui.components.cards import ActionCard, SectionCard
from ui.components.layouts import ResponsiveGrid, make_scroll_page
from ui.navigation import NavigationRail
from ui.pages.dashboard_page import DashboardPage
from ui.pages.database_page import DatabasePage
from ui.pages.forecast_result_page import ForecastResultPage
from ui.pages.ai_report_page import AIReportPage
from ui.pages.logs_page import LogsPage
from ui.pages.models_page import ModelsPage
from ui.pages.settings_page import SettingsPage
from ui.services.db_service import DatabaseService
from ui.services.forecast_result_service import ForecastResultService
from ui.services.legacy_actions import CommandSpec, LegacyActions
from ui.services.model_service import ModelService
from ui.services.report_service import ReportService
from ui.theme import COLORS


class MainWindow(QMainWindow):
    def __init__(self, auto_refresh: bool = True):
        super().__init__()
        self.setWindowTitle("智能运营分析项目控制台")
        self.resize(1600, 900)
        self.setMinimumSize(1280, 720)
        self.actions = LegacyActions()
        self.db_service = DatabaseService()
        self.forecast_service = ForecastResultService()
        self.model_service = ModelService()
        self.report_service = ReportService()
        self.process: QProcess | None = None
        self.active_command: CommandSpec | None = None

        config = load_config()
        db_cfg = get_database_config(config)
        paths = self.actions.project_paths()

        root = QWidget()
        root.setObjectName("RootWidget")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        self.top_bar = self._build_top_bar()
        root_layout.addWidget(self.top_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.nav = NavigationRail()
        self.stack = QStackedWidget()
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        root_layout.addLayout(body, 1)

        self.bottom_bar = self._build_bottom_bar(db_cfg.database)
        root_layout.addWidget(self.bottom_bar)

        self.dashboard = DashboardPage(paths.final_output_root_dir)
        self.database_page = DatabasePage(self.db_service)
        self.forecast_result_page = ForecastResultPage(self.forecast_service, auto_refresh=auto_refresh)
        self.models_page = ModelsPage(self.model_service, auto_refresh=auto_refresh)
        self.ai_report_page = AIReportPage(self.report_service, auto_refresh=auto_refresh)
        self.logs_page = LogsPage(paths.log_dir)
        self.settings_page = SettingsPage(paths.final_output_root_dir, db_cfg.database)

        self.pages = {
            "dashboard": self.dashboard,
            "data": self._build_action_hub(
                "数据管理",
                "围绕数据同步、数据库闭环和结果浏览的常用操作。",
                [
                    ("database_closure", "↺", "数据库闭环同步", "同步核心数据、结果表和预测追踪"),
                    ("health_check", "✓", "健康检查", "检查数据、依赖和数据库状态"),
                ],
            ),
            "prediction": self._build_action_hub(
                "预测任务",
                "执行正式前瞻预测、AI 日报和归档落库流程。",
                [
                    ("fast_forecast", "FAST", "快速预测（Active 模型）", "不重新训练，加载 Active artifact 推理"),
                    ("refresh_fast_forecast", "DATA", "更新数据 + 快速预测", "先刷新数据，再快速推理"),
                    ("skip_prediction", "AI", "仅生成 AI 报告", "复用已有预测结果"),
                    ("retrain_model", "TRAIN", "完整训练候选模型", "重新训练并登记 candidate artifact"),
                    ("model_auto_optimize", "AUTO", "模型自优化", "误差记忆、退化判断与必要重训"),
                    ("compare_promote", "CMP", "候选模型对比上线", "对比 candidate 与 Active"),
                    ("refresh_data", "⇧", "更新数据并全流程", "兼容旧模式：会重新训练"),
                    ("full", "▶", "直接全流程", "兼容旧模式：会重新训练"),
                    ("prediction_report_only", "▣", "预测并生成报告", "兼容旧模式：会重新预测/训练"),
                ],
            ),
            "forecast_results": self.forecast_result_page,
            "models": self.models_page,
            "reports": self.ai_report_page,
            "database": self.database_page,
            "tasks": self._build_action_hub(
                "任务计划",
                "任务计划创建入口位于控制台首页，可直接覆盖同名计划任务。",
                [
                    ("smoke_test", "T", "轻量整体自检", "确认计划任务前的环境状态"),
                    ("health_check", "✓", "健康检查", "确认数据库与依赖状态"),
                ],
            ),
            "settings": self.settings_page,
            "logs": self.logs_page,
            "help": self._build_help_page(),
        }
        for key in self.pages:
            self.stack.addWidget(self.pages[key])

        self.nav.pageSelected.connect(self.select_page)
        self.dashboard.runRequested.connect(self.run_action)
        self.dashboard.stopRequested.connect(self.stop_process)
        self.dashboard.testDatabaseRequested.connect(self.test_database)
        self.dashboard.saveOutputRootRequested.connect(self.save_output_root)
        self.dashboard.openPathRequested.connect(self.open_target)
        self.dashboard.createTaskRequested.connect(self.create_task)
        self.database_page.messageEmitted.connect(self._handle_page_message)
        self.forecast_result_page.messageEmitted.connect(self._handle_page_message)
        self.forecast_result_page.commandRequested.connect(self.start_process)
        self.forecast_result_page.openPathRequested.connect(self.open_target)
        self.models_page.messageEmitted.connect(self._handle_page_message)
        self.models_page.commandRequested.connect(self.start_process)
        self.models_page.openPathRequested.connect(self.open_target)
        self.ai_report_page.messageEmitted.connect(self._handle_page_message)
        self.ai_report_page.commandRequested.connect(self.start_process)
        self.ai_report_page.openPathRequested.connect(self.open_target)
        self.logs_page.messageEmitted.connect(self._handle_page_message)
        self.settings_page.saveOutputRootRequested.connect(self.save_output_root)
        self.settings_page.testDatabaseRequested.connect(self.test_database)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._tick)
        self.clock_timer.start(1000)
        self._tick()
        if auto_refresh:
            QTimer.singleShot(300, self.refresh_status_summary)

    def _build_top_bar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("TopBar")
        frame.setMinimumHeight(50)
        frame.setMaximumHeight(58)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 0, 18, 0)
        title = QLabel("智能运营分析项目控制台")
        title.setObjectName("WindowTitle")
        self.top_status_label = QLabel("系统状态：初始化")
        self.top_time_label = QLabel("-")
        self.top_db_label = QLabel("数据库：检查中")
        user = QLabel(f"当前用户：{getpass.getuser()}")
        for label in [self.top_status_label, self.top_time_label, self.top_db_label, user]:
            label.setObjectName("MutedText")
        layout.addWidget(title)
        layout.addStretch(1)
        layout.addWidget(self.top_status_label)
        layout.addSpacing(18)
        layout.addWidget(self.top_time_label)
        layout.addSpacing(18)
        layout.addWidget(self.top_db_label)
        layout.addSpacing(18)
        layout.addWidget(user)
        return frame

    def _build_bottom_bar(self, database_name: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("BottomBar")
        frame.setMinimumHeight(34)
        frame.setMaximumHeight(40)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 0, 18, 0)
        self.bottom_status_label = QLabel("就绪")
        self.bottom_db_label = QLabel(f"数据库：{database_name or '-'}")
        self.bottom_python_label = QLabel(f"Python {platform.python_version()}")
        self.bottom_env_label = QLabel("环境：生产环境")
        self.bottom_user_label = QLabel(f"当前用户：{getpass.getuser()}")
        for label in [
            self.bottom_status_label,
            self.bottom_db_label,
            self.bottom_python_label,
            self.bottom_env_label,
            self.bottom_user_label,
        ]:
            label.setObjectName("MutedText")
        layout.addWidget(self.bottom_status_label)
        layout.addStretch(1)
        layout.addWidget(self.bottom_db_label)
        layout.addSpacing(18)
        layout.addWidget(self.bottom_python_label)
        layout.addSpacing(18)
        layout.addWidget(self.bottom_env_label)
        layout.addSpacing(18)
        layout.addWidget(self.bottom_user_label)
        return frame

    def _build_action_hub(self, title: str, subtitle: str, actions: list[tuple[str, str, str, str]]) -> QWidget:
        page = QWidget()
        layout, _scroll, _content = make_scroll_page(page)
        title_label = QLabel(title)
        title_label.setObjectName("PageTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("MutedText")
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        section = SectionCard("常用操作")
        grid = ResponsiveGrid(min_item_width=240, max_columns=4)
        for action_id, icon, card_title, card_subtitle in actions:
            card = ActionCard(icon, card_title, card_subtitle)
            card.clicked.connect(lambda checked=False, aid=action_id: self.run_action(aid))
            grid.addWidget(card)
        section.layout.addWidget(grid)
        layout.addWidget(section)
        layout.addStretch(1)
        return page

    def _build_help_page(self) -> QWidget:
        page = QWidget()
        layout, _scroll, _content = make_scroll_page(page)
        title = QLabel("帮助文档")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        section = SectionCard("本地说明")
        for label, target in [
            ("打开使用说明", "README"),
            ("打开总结果目录", "FINAL_OUTPUT_ROOT"),
            ("打开日志目录", "LOG_DIR"),
        ]:
            card = ActionCard("?", label, "在系统默认程序中打开")
            card.clicked.connect(lambda checked=False, t=target: self.open_target(t))
            section.layout.addWidget(card)
        layout.addWidget(section)
        layout.addStretch(1)
        return page

    def center_on_screen(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        available = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

    def select_page(self, page_id: str) -> None:
        widget = self.pages.get(page_id)
        if not widget:
            return
        self.stack.setCurrentWidget(widget)
        self.nav.select(page_id, emit=False)
        if page_id == "database":
            self.database_page.refresh_all()
        if page_id == "forecast_results":
            self.forecast_result_page.refresh_async()
        if page_id == "models":
            self.models_page.refresh_async()
        if page_id == "reports":
            self.ai_report_page.refresh_async()
        if page_id == "logs":
            self.logs_page.refresh_files()

    def run_action(self, action_id: str) -> None:
        try:
            spec = self.actions.command_for_action(action_id)
            self.start_process(spec)
        except Exception as exc:
            self.log(f"启动动作失败：{exc}", "ERROR")
            QMessageBox.critical(self, "动作失败", str(exc))

    def create_task(self, task_name: str, run_time: str, mode: str) -> None:
        try:
            spec = self.actions.create_task_command(task_name or "PowerMarketDailyAutomation", run_time or "06:30", mode)
            self.start_process(spec)
            self.dashboard.update_status({"task": "已创建"})
        except Exception as exc:
            self.log(f"创建任务计划失败：{exc}", "ERROR")
            QMessageBox.critical(self, "任务计划失败", str(exc))

    def start_process(self, spec: CommandSpec) -> None:
        if self.process and self.process.state() != QProcess.NotRunning:
            self.log("已有任务正在运行，请等待完成或停止当前任务。", "WARNING")
            return
        self.active_command = spec
        self.process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUTF8", "1")
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(str(self.actions.root_dir))
        self.process.readyReadStandardOutput.connect(self._read_process_output)
        self.process.readyReadStandardError.connect(self._read_process_output)
        self.process.finished.connect(self._process_finished)
        self.process.errorOccurred.connect(self._process_error)
        self._set_running_state(True)
        self.bottom_status_label.setText(f"运行中：{spec.title}")
        self.top_status_label.setText("系统状态：运行中")
        self.log(f"开始执行：{spec.display}", "INFO")
        self.process.start(spec.command[0], spec.command[1:])

    def stop_process(self) -> None:
        if not self.process or self.process.state() == QProcess.NotRunning:
            self.log("当前没有正在运行的任务。", "WARNING")
            return
        self.process.terminate()
        if not self.process.waitForFinished(3000):
            self.process.kill()
        self.log("已请求停止当前任务。", "WARNING")

    def _read_process_output(self) -> None:
        if not self.process:
            return
        chunks = [self.process.readAllStandardOutput(), self.process.readAllStandardError()]
        for chunk in chunks:
            if chunk:
                text = bytes(chunk).decode("utf-8", errors="replace")
                for line in text.splitlines():
                    if line.strip():
                        self.log(line.rstrip())

    def _process_finished(self, exit_code: int, _status) -> None:
        title = self.active_command.title if self.active_command else "任务"
        if exit_code == 0:
            self.log(f"{title}执行完成。", "SUCCESS")
            self.bottom_status_label.setText("就绪")
            self.top_status_label.setText("系统状态：就绪")
        else:
            self.log(f"{title}执行失败，退出码：{exit_code}", "ERROR")
            self.bottom_status_label.setText(f"失败：{title}")
            self.top_status_label.setText("系统状态：异常")
        self._set_running_state(False)
        self.refresh_status_summary()
        self._refresh_current_center_page()

    def _process_error(self, error) -> None:
        self.log(f"任务启动异常：{error}", "ERROR")
        self._set_running_state(False)

    def test_database(self) -> None:
        ok, message = self.actions.test_database()
        self.log(message, "SUCCESS" if ok else "ERROR")
        self.top_db_label.setText("数据库：已连接" if ok else "数据库：连接失败")
        self.dashboard.update_status({"database": "已连接" if ok else "连接失败"})
        if ok:
            self.refresh_status_summary()
        else:
            QMessageBox.critical(self, "数据库连接失败", message)

    def save_output_root(self, value: str) -> None:
        try:
            path = self.actions.save_output_root(value)
            self.dashboard.set_output_root(path)
            self.settings_page.set_output_root(path)
            self.log(f"已保存总输出目录：{path}", "SUCCESS")
        except Exception as exc:
            self.log(f"保存输出目录失败：{exc}", "ERROR")
            QMessageBox.critical(self, "保存失败", str(exc))

    def open_target(self, target: str) -> None:
        try:
            paths = self.actions.project_paths()
            mapping = {
                "FINAL_OUTPUT_ROOT": paths.final_output_root_dir,
                "RESULT_TABLE_DIR": paths.result_table_dir,
                "LOG_DIR": paths.log_dir,
                "MODEL_ARTIFACTS": self.actions.root_dir / "model_artifacts",
                "README": [
                    self.actions.root_dir / "使用说明_正式前瞻预测_任务计划_GUI.txt",
                    self.actions.root_dir / "README_正式前瞻预测_任务计划_GUI.md",
                    self.actions.root_dir / "README_AI自动化说明.md",
                ],
            }
            value = mapping.get(target, target)
            if isinstance(value, list):
                path = self.actions.open_first_existing(value)
            else:
                path = Path(value)
                self.actions.open_path(path)
            self.log(f"已打开：{path}", "SUCCESS")
        except Exception as exc:
            self.log(f"打开路径失败：{exc}", "ERROR")
            QMessageBox.critical(self, "打开失败", str(exc))

    def refresh_status_summary(self) -> None:
        try:
            ok, message = self.db_service.test()
            self.top_db_label.setText("数据库：已连接" if ok else "数据库：连接失败")
            if ok:
                overview = self.db_service.overview()
                latest_data = self._safe_latest_value("raw_da_price", "datetime")
                latest_prediction = self._safe_latest_value("result_forward_24h_formal", "datetime")
                latest_report = str(overview.get("latest_report_time") or "-")
                self.dashboard.update_status(
                    {
                        "database": "已连接",
                        "latest_data": latest_data,
                        "latest_prediction": latest_prediction,
                        "latest_report": latest_report,
                        "health": "正常",
                    }
                )
                self.bottom_db_label.setText(f"数据库：已连接 ({overview.get('database_name', '-')})")
            else:
                self.dashboard.update_status({"database": "连接失败", "health": "异常"})
                self.bottom_db_label.setText("数据库：连接失败")
                self.log(message, "ERROR")
        except Exception as exc:
            self.dashboard.update_status({"database": "连接失败", "health": "异常"})
            self.top_db_label.setText("数据库：连接失败")
            self.bottom_db_label.setText("数据库：连接失败")
            self.log(f"刷新状态失败：{exc}", "ERROR")

    def _safe_latest_value(self, relation_name: str, column_name: str) -> str:
        try:
            return self.db_service.latest_value(relation_name, column_name) or "-"
        except Exception:
            return "-"

    def _handle_page_message(self, message: str, level: str) -> None:
        if message.startswith("OPEN_PATH::"):
            self.open_target(message.replace("OPEN_PATH::", "", 1))
            return
        self.log(message, level)

    def _set_running_state(self, running: bool) -> None:
        self.dashboard.set_running(running)
        self.forecast_result_page.set_running(running)
        self.models_page.set_running(running)
        self.ai_report_page.set_running(running)

    def _refresh_current_center_page(self) -> None:
        current = self.stack.currentWidget()
        if current is self.forecast_result_page:
            self.forecast_result_page.refresh_async()
        elif current is self.models_page:
            self.models_page.refresh_async()
        elif current is self.ai_report_page:
            self.ai_report_page.refresh_async()

    def _tick(self) -> None:
        self.top_time_label.setText(datetime.now().strftime("当前时间：%Y-%m-%d %H:%M:%S"))

    def log(self, message: str, level: str | None = None) -> None:
        self.dashboard.append_log(message, level)

    def closeEvent(self, event):  # noqa: N802
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            self.process.waitForFinished(1500)
        super().closeEvent(event)
