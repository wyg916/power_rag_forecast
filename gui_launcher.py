from __future__ import annotations

import os
import json
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from automation_common import get_pipeline_paths, load_config, save_config
from database_utils import (
    ensure_database_structures,
    fetch_ai_report_record,
    fetch_database_overview,
    fetch_recent_run_catalog,
    list_database_browse_sources,
    preview_relation,
    test_database_connection,
)


ROOT_DIR = Path(__file__).resolve().parent
PYTHON_EXE = Path(sys.executable)

STEP_PATTERNS = [
    ("开始执行：00_local_model_inventory.py", "盘点本地模型环境"),
    ("开始执行：fetch_power_market_data.py", "更新公开数据并准备入库"),
    ("目标维护时间范围", "更新公开数据并准备入库"),
    ("日前电价增量抓取起点", "抓取日前电价增量"),
    ("实时电价增量抓取起点", "抓取实时电价增量"),
    ("实际负荷增量抓取起点", "抓取实际负荷增量"),
    ("负荷预测增量抓取起点", "抓取负荷预测增量"),
    ("天气增量抓取起点", "抓取天气增量"),
    ("数据库已就绪", "同步数据到数据库"),
    ("已写入数据表：raw_", "同步原始数据到数据库"),
    ("已写入数据表：model_master_table", "同步主表到数据库"),
    ("已为数据表添加主键", "初始化数据库主键"),
    ("已为数据表添加自增主键", "初始化数据库主键"),
    ("已为数据表添加索引", "初始化数据库索引"),
    ("已创建或更新视图", "初始化数据库视图"),
    ("开始执行：01_run_prediction.py", "准备预测引擎输入"),
    ("开始从数据库导出预测输入数据", "从数据库导出预测输入"),
    ("已从数据库导出预测输入文件", "从数据库导出预测输入"),
    ("开始执行预测引擎", "启动预测引擎"),
    ("开始运行：高峰尖刺增强版", "预测引擎启动"),
    ("开始读取主表数据", "读取主表数据"),
    ("开始数据质量检查", "进行数据质量检查"),
    ("开始数据泄漏检查", "进行数据泄漏检查"),
    ("开始输出EDA图表", "生成探索图表"),
    ("开始特征工程", "执行特征工程"),
    ("开始时间序列切分", "切分训练/验证/测试集"),
    ("开始执行高峰尖刺增强建模管线", "训练高峰尖刺增强模型"),
    ("开始异常波动识别", "识别异常波动"),
    ("开始生成未来24小时预测结果", "生成未来24小时正式前瞻预测"),
    ("开始输出业务统计结果", "输出业务统计结果"),
    ("开始同步预测结果数据表到数据库", "同步预测结果到数据库"),
    ("已写入数据表：result_", "同步预测结果到数据库"),
    ("开始执行：02_build_ai_summary.py", "生成 AI 输入摘要"),
    ("已生成 AI 输入摘要", "AI 输入摘要已生成"),
    ("开始执行：03_llm_generate_report.py", "生成 AI 报告"),
    ("开始调用本地模型生成报告", "本地大模型生成报告"),
    ("已生成 Word 综合报告与结构化报告", "AI 报告已生成"),
    ("开始执行：04_dispatch_report.py", "整理并归档结果"),
    ("已生成用户结果总文件夹", "结果归档完成"),
    ("本次自动化任务全部完成", "全部完成"),
]


def _safe_text(value) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.lower() == "nan":
        return ""
    return text


class PipelineGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("智能运营分析项目控制台")
        self.root.geometry("1360x900")
        self.root.minsize(1180, 760)

        self.config = load_config()
        self.paths = get_pipeline_paths(self.config)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.current_process: subprocess.Popen[str] | None = None
        self.is_running = False
        self.run_start_time: float | None = None
        self.current_step_text = "待命"

        self.task_name_var = tk.StringVar(value="PowerMarketDailyAutomation")
        self.task_time_var = tk.StringVar(value="06:30")
        self.task_mode_var = tk.StringVar(value="refresh_data")
        self.status_var = tk.StringVar(value="就绪")
        self.output_root_var = tk.StringVar(value=str(self.paths.final_output_root_dir))

        self.db_name_var = tk.StringVar(value="-")
        self.db_table_count_var = tk.StringVar(value="-")
        self.db_view_count_var = tk.StringVar(value="-")
        self.db_index_count_var = tk.StringVar(value="-")
        self.db_latest_run_var = tk.StringVar(value="-")
        self.db_latest_report_mode_var = tk.StringVar(value="-")
        self.db_latest_report_time_var = tk.StringVar(value="-")
        self.db_latest_risk_var = tk.StringVar(value="-")

        self.run_id_var = tk.StringVar(value="")
        self.report_meta_var = tk.StringVar(value="未加载 AI 报告")
        self.preview_limit_var = tk.IntVar(value=200)
        self.preview_only_run_var = tk.BooleanVar(value=True)
        self.preview_source_display_var = tk.StringVar(value="")
        self.preview_meta_var = tk.StringVar(value="未加载数据表")
        self.source_display_to_name: dict[str, str] = {}

        self.run_buttons: list[ttk.Button] = []

        self._build_ui()
        self.root.after(200, self._drain_log_queue)
        self.root.after(500, self._refresh_status_timer)
        self.root.after(900, lambda: self.refresh_database_browser(silent=True))

    def _build_ui(self) -> None:
        main_frame = ttk.Frame(self.root, padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        header = ttk.Label(
            main_frame,
            text="电价预测 + AI 日报 + 数据库落库 一体化控制台",
            font=("Microsoft YaHei", 16, "bold"),
        )
        header.pack(anchor=tk.W)

        desc = ttk.Label(
            main_frame,
            text="支持一键更新数据、运行正式前瞻预测、生成 AI 报告、落库、归档、任务计划，以及数据库浏览/查询。",
            font=("Microsoft YaHei", 10),
        )
        desc.pack(anchor=tk.W, pady=(6, 10))

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.control_tab = ttk.Frame(self.notebook, padding=12)
        self.database_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.control_tab, text="流程控制")
        self.notebook.add(self.database_tab, text="数据库浏览/查询")

        self._build_control_tab()
        self._build_database_tab()

    def _build_control_tab(self) -> None:
        action_frame = ttk.LabelFrame(self.control_tab, text="一键运行", padding=12)
        action_frame.pack(fill=tk.X)

        self.run_buttons.append(self._add_button(action_frame, "更新数据并全流程", lambda: self.run_command(self._python_command("main_daily_run.py", "--refresh-data")), 0, 0))
        self.run_buttons.append(self._add_button(action_frame, "直接全流程", lambda: self.run_command(self._python_command("main_daily_run.py")), 0, 1))
        self.run_buttons.append(self._add_button(action_frame, "仅生成 AI 报告", lambda: self.run_command(self._python_command("main_daily_run.py", "--skip-prediction")), 0, 2))
        self.run_buttons.append(self._add_button(action_frame, "预测并生成报告", lambda: self.run_command(self._python_command("main_daily_run.py", "--prediction-report-only")), 1, 0))
        self.run_buttons.append(self._add_button(action_frame, "模型盘点", lambda: self.run_command(self._python_command("00_local_model_inventory.py")), 1, 1))
        self.run_buttons.append(self._add_button(action_frame, "模型运维检查", lambda: self.run_command(self._python_command("06_model_monitor.py")), 1, 2))
        self.run_buttons.append(self._add_button(action_frame, "健康检查", lambda: self.run_command(self._python_command("09_health_check.py")), 1, 3))
        self.run_buttons.append(self._add_button(action_frame, "测试数据库连接", self.show_database_status, 2, 0))
        self.run_buttons.append(self._add_button(action_frame, "停止当前任务", self.stop_current_process, 2, 1))

        output_frame = ttk.LabelFrame(self.control_tab, text="总输出目录", padding=12)
        output_frame.pack(fill=tk.X, pady=(12, 0))
        ttk.Label(output_frame, text="结果总目录").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Entry(output_frame, textvariable=self.output_root_var, width=84).grid(row=0, column=1, sticky=tk.W, pady=4)
        self.run_buttons.append(self._add_button(output_frame, "选择目录", self.choose_output_directory, 0, 2))
        self.run_buttons.append(self._add_button(output_frame, "保存配置", self.save_output_directory, 0, 3))

        task_frame = ttk.LabelFrame(self.control_tab, text="任务计划", padding=12)
        task_frame.pack(fill=tk.X, pady=(12, 0))

        ttk.Label(task_frame, text="任务名称").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Entry(task_frame, textvariable=self.task_name_var, width=30).grid(row=0, column=1, sticky=tk.W, pady=4)

        ttk.Label(task_frame, text="每日时间").grid(row=0, column=2, sticky=tk.W, padx=(20, 8), pady=4)
        ttk.Entry(task_frame, textvariable=self.task_time_var, width=10).grid(row=0, column=3, sticky=tk.W, pady=4)

        ttk.Label(task_frame, text="执行模式").grid(row=0, column=4, sticky=tk.W, padx=(20, 8), pady=4)
        mode_box = ttk.Combobox(
            task_frame,
            textvariable=self.task_mode_var,
            values=["refresh_data", "full", "skip_prediction", "model_ops_daily", "health_check"],
            state="readonly",
            width=18,
        )
        mode_box.grid(row=0, column=5, sticky=tk.W, pady=4)

        task_hint = ttk.Label(
            task_frame,
            text="推荐模式：refresh_data，表示每天先更新数据，再做正式前瞻预测、AI 报告和数据库同步。",
            font=("Microsoft YaHei", 9),
        )
        task_hint.grid(row=1, column=0, columnspan=6, sticky=tk.W, pady=(6, 8))
        self.run_buttons.append(self._add_button(task_frame, "创建/覆盖任务计划", self.create_windows_task, 2, 0))

        open_frame = ttk.LabelFrame(self.control_tab, text="打开目录与文件", padding=12)
        open_frame.pack(fill=tk.X, pady=(12, 0))
        self.run_buttons.append(self._add_button(open_frame, "打开总结果目录", self.open_output_root, 0, 0))
        self.run_buttons.append(self._add_button(open_frame, "打开内部结果目录", lambda: self.open_path(ROOT_DIR / "结果-3"), 0, 1))
        self.run_buttons.append(self._add_button(open_frame, "打开日志目录", lambda: self.open_path(ROOT_DIR / "自动化输出" / "logs"), 0, 2))
        self.run_buttons.append(self._add_button(open_frame, "打开使用说明", lambda: self.open_path(ROOT_DIR / "使用说明_正式前瞻预测_任务计划_GUI.txt"), 0, 3))

        status_frame = ttk.Frame(self.control_tab)
        status_frame.pack(fill=tk.X, pady=(12, 0))
        ttk.Label(status_frame, text="状态：").pack(side=tk.LEFT)
        ttk.Label(status_frame, textvariable=self.status_var, foreground="#0b5cab").pack(side=tk.LEFT)

        log_frame = ttk.LabelFrame(self.control_tab, text="运行日志", padding=12)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=("Consolas", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.insert(tk.END, "控制台已启动。\n")
        self.log_text.see(tk.END)

    def _build_database_tab(self) -> None:
        overview_frame = ttk.LabelFrame(self.database_tab, text="数据库概览", padding=12)
        overview_frame.pack(fill=tk.X)

        overview_items = [
            ("数据库", self.db_name_var),
            ("数据表数", self.db_table_count_var),
            ("视图数", self.db_view_count_var),
            ("索引数", self.db_index_count_var),
            ("最新 run_id", self.db_latest_run_var),
            ("最新报告模式", self.db_latest_report_mode_var),
            ("最新报告时间", self.db_latest_report_time_var),
            ("最新风险等级", self.db_latest_risk_var),
        ]
        for idx, (label_text, variable) in enumerate(overview_items):
            row = idx // 4
            col = (idx % 4) * 2
            ttk.Label(overview_frame, text=label_text).grid(row=row, column=col, sticky=tk.W, padx=(0, 8), pady=4)
            ttk.Label(overview_frame, textvariable=variable, foreground="#0b5cab").grid(row=row, column=col + 1, sticky=tk.W, padx=(0, 20), pady=4)

        action_frame = ttk.LabelFrame(self.database_tab, text="数据库操作", padding=12)
        action_frame.pack(fill=tk.X, pady=(12, 0))
        self._add_button(action_frame, "刷新数据库概览", lambda: self.refresh_database_browser(silent=False), 0, 0)
        self._add_button(action_frame, "初始化主键/索引/视图", self.apply_database_migration, 0, 1)
        self._add_button(action_frame, "查看数据库说明", lambda: self.open_path(ROOT_DIR / "output" / "数据库表说明文档_调用版.txt"), 0, 2)
        self._add_button(action_frame, "重新生成数据库说明", lambda: self.run_command(self._python_command("generate_database_documentation.py")), 0, 3)

        report_frame = ttk.LabelFrame(self.database_tab, text="AI 报告浏览", padding=12)
        report_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        ttk.Label(report_frame, text="选择 run_id").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        self.run_id_box = ttk.Combobox(report_frame, textvariable=self.run_id_var, state="readonly", width=28)
        self.run_id_box.grid(row=0, column=1, sticky=tk.W, pady=4)
        self._add_button(report_frame, "加载所选 run_id 报告", self.load_selected_run_report, 0, 2)
        self._add_button(report_frame, "加载最新 run_id 报告", self.load_latest_run_report, 0, 3)

        ttk.Label(report_frame, textvariable=self.report_meta_var, foreground="#444444").grid(
            row=1, column=0, columnspan=4, sticky=tk.W, pady=(6, 10)
        )

        self.report_text = scrolledtext.ScrolledText(report_frame, wrap=tk.WORD, font=("Microsoft YaHei", 10), height=12)
        self.report_text.grid(row=2, column=0, columnspan=4, sticky="nsew")
        report_frame.rowconfigure(2, weight=1)
        report_frame.columnconfigure(1, weight=1)

        preview_frame = ttk.LabelFrame(self.database_tab, text="结果表预览", padding=12)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        ttk.Label(preview_frame, text="表 / 视图").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        self.preview_source_box = ttk.Combobox(preview_frame, textvariable=self.preview_source_display_var, state="readonly", width=44)
        self.preview_source_box.grid(row=0, column=1, sticky=tk.W, pady=4)

        ttk.Label(preview_frame, text="行数上限").grid(row=0, column=2, sticky=tk.W, padx=(20, 8), pady=4)
        ttk.Spinbox(preview_frame, from_=20, to=1000, increment=20, textvariable=self.preview_limit_var, width=8).grid(
            row=0, column=3, sticky=tk.W, pady=4
        )

        ttk.Checkbutton(preview_frame, text="仅查看当前 run_id", variable=self.preview_only_run_var).grid(
            row=0, column=4, sticky=tk.W, padx=(20, 8), pady=4
        )
        self._add_button(preview_frame, "刷新当前预览", self.load_selected_preview, 0, 5)

        ttk.Label(preview_frame, textvariable=self.preview_meta_var, foreground="#444444").grid(
            row=1, column=0, columnspan=6, sticky=tk.W, pady=(6, 8)
        )

        table_container = ttk.Frame(preview_frame)
        table_container.grid(row=2, column=0, columnspan=6, sticky="nsew")
        preview_frame.rowconfigure(2, weight=1)
        preview_frame.columnconfigure(1, weight=1)

        self.preview_tree = ttk.Treeview(table_container, show="headings")
        y_scroll = ttk.Scrollbar(table_container, orient=tk.VERTICAL, command=self.preview_tree.yview)
        x_scroll = ttk.Scrollbar(table_container, orient=tk.HORIZONTAL, command=self.preview_tree.xview)
        self.preview_tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.preview_tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_container.rowconfigure(0, weight=1)
        table_container.columnconfigure(0, weight=1)

    def _add_button(self, parent: ttk.Widget, text: str, command, row: int, column: int) -> ttk.Button:
        button = ttk.Button(parent, text=text, command=command)
        button.grid(row=row, column=column, sticky=tk.W, padx=6, pady=6)
        return button

    def _python_command(self, script_name: str, *args: str) -> list[str]:
        return [str(PYTHON_EXE), str(ROOT_DIR / script_name), *args]

    def _infer_step_from_log(self, line: str) -> str | None:
        for pattern, label in STEP_PATTERNS:
            if pattern in line:
                return label
        match = re.search(r"开始执行：(.+?\.py)", line)
        if match:
            return f"执行脚本 {match.group(1)}"
        return None

    def run_command(self, command: list[str]) -> None:
        if self.is_running:
            self.append_log("已有任务在运行，请先等待完成或点击“停止当前任务”。")
            return

        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        self.append_log(f"开始执行：{' '.join(command)}")
        self.current_step_text = "启动任务"
        self.status_var.set(f"运行中 | 当前步骤：{self.current_step_text}")
        self.is_running = True
        self.run_start_time = time.perf_counter()
        self._set_buttons_state()

        def _worker() -> None:
            try:
                self.current_process = subprocess.Popen(
                    command,
                    cwd=str(ROOT_DIR),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env,
                )
                assert self.current_process.stdout is not None
                for line in self.current_process.stdout:
                    self.log_queue.put(line.rstrip("\n"))
                code = self.current_process.wait()
                if code == 0:
                    self.log_queue.put("任务执行完成。")
                    self.log_queue.put("__PROCESS_OK__")
                else:
                    self.log_queue.put(f"任务执行失败，返回码：{code}")
                    self.log_queue.put("__PROCESS_FAIL__")
            except Exception as exc:
                self.log_queue.put(f"启动任务失败：{exc}")
                self.log_queue.put("__PROCESS_FAIL__")

        threading.Thread(target=_worker, daemon=True).start()

    def stop_current_process(self) -> None:
        if not self.current_process or self.current_process.poll() is not None:
            self.append_log("当前没有正在运行的任务。")
            return
        try:
            self.current_process.terminate()
            self.append_log("已请求停止当前任务。")
        except Exception as exc:
            self.append_log(f"停止任务失败：{exc}")

    def create_windows_task(self) -> None:
        task_name = self.task_name_var.get().strip() or "PowerMarketDailyAutomation"
        run_time = self.task_time_var.get().strip() or "06:30"
        mode = self.task_mode_var.get().strip() or "refresh_data"
        command = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT_DIR / "create_windows_task.ps1"),
            "-TaskName",
            task_name,
            "-RunTime",
            run_time,
            "-Mode",
            mode,
        ]
        self.run_command(command)

    def choose_output_directory(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_root_var.get() or str(ROOT_DIR))
        if selected:
            self.output_root_var.set(selected)

    def save_output_directory(self) -> None:
        selected = self.output_root_var.get().strip()
        if not selected:
            messagebox.showerror("保存失败", "输出目录不能为空。")
            return
        self.config = load_config()
        self.config["paths"]["final_output_root_dir"] = selected.replace("\\", "/")
        save_config(self.config)
        self.paths = get_pipeline_paths(self.config)
        self.append_log(f"已保存总输出目录：{self.paths.final_output_root_dir}")

    def show_database_status(self) -> None:
        self.config = load_config()
        ok, message = test_database_connection(self.config)
        self.append_log(message)
        if ok:
            messagebox.showinfo("数据库状态", message)
            self.refresh_database_browser(silent=True)
        else:
            messagebox.showerror("数据库状态", message)

    def open_output_root(self) -> None:
        self.config = load_config()
        self.paths = get_pipeline_paths(self.config)
        self.output_root_var.set(str(self.paths.final_output_root_dir))
        self.open_path(self.paths.final_output_root_dir)

    def open_path(self, path: Path) -> None:
        if not path.exists():
            messagebox.showerror("路径不存在", f"未找到路径：{path}")
            return
        os.startfile(str(path))

    def append_log(self, text: str) -> None:
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)

    def apply_database_migration(self) -> None:
        try:
            self.config = load_config()
            ensure_database_structures(self.config, log=self.append_log)
            self.append_log("数据库主键、索引和视图初始化完成。")
            self.refresh_database_browser(silent=True)
            messagebox.showinfo("数据库结构", "数据库主键、索引和视图已完成初始化。")
        except Exception as exc:
            self.append_log(f"数据库结构初始化失败：{exc}")
            messagebox.showerror("数据库结构", f"数据库结构初始化失败：{exc}")

    def refresh_database_browser(self, silent: bool = False) -> None:
        try:
            self.config = load_config()
            ensure_database_structures(self.config, log=None)
            overview = fetch_database_overview(self.config)
            self.db_name_var.set(_safe_text(overview.get("database_name")) or "-")
            self.db_table_count_var.set(_safe_text(overview.get("table_count")) or "0")
            self.db_view_count_var.set(_safe_text(overview.get("view_count")) or "0")
            self.db_index_count_var.set(_safe_text(overview.get("index_count")) or "0")
            self.db_latest_run_var.set(_safe_text(overview.get("latest_run_id")) or "-")
            self.db_latest_report_mode_var.set(_safe_text(overview.get("latest_report_mode")) or "-")
            self.db_latest_report_time_var.set(_safe_text(overview.get("latest_report_time")) or "-")
            self.db_latest_risk_var.set(_safe_text(overview.get("latest_risk_level")) or "-")

            run_catalog = fetch_recent_run_catalog(self.config, limit=100)
            run_ids = [_safe_text(value) for value in run_catalog.get("run_id", pd.Series(dtype=str)).tolist() if _safe_text(value)]
            self.run_id_box["values"] = run_ids
            preferred_run_id = ""
            if not run_catalog.empty and "ai_report_generated_at" in run_catalog.columns:
                report_ready_rows = run_catalog[
                    run_catalog["ai_report_generated_at"].notna()
                    & (run_catalog["ai_report_generated_at"].astype(str).str.strip() != "")
                ]
                if not report_ready_rows.empty:
                    preferred_run_id = _safe_text(report_ready_rows.iloc[0].get("run_id"))
            if run_ids and self.run_id_var.get() not in run_ids:
                self.run_id_var.set(preferred_run_id or run_ids[0])
            elif not run_ids:
                self.run_id_var.set("")

            sources = list_database_browse_sources(self.config)
            self.source_display_to_name = {
                f"{item['label']} [{item['name']}]": item["name"]
                for item in sources
            }
            display_values = list(self.source_display_to_name.keys())
            self.preview_source_box["values"] = display_values
            if display_values and self.preview_source_display_var.get() not in display_values:
                self.preview_source_display_var.set(display_values[0])

            if self.run_id_var.get():
                self.load_selected_run_report(silent=True)
            if self.preview_source_display_var.get():
                self.load_selected_preview(silent=True)

            if not silent:
                self.append_log("数据库浏览页已刷新。")
        except Exception as exc:
            if not silent:
                self.append_log(f"刷新数据库浏览页失败：{exc}")
                messagebox.showerror("数据库浏览", f"刷新数据库浏览页失败：{exc}")

    def load_latest_run_report(self) -> None:
        self.refresh_database_browser(silent=True)
        self.load_selected_run_report(silent=False)

    def load_selected_run_report(self, silent: bool = False) -> None:
        try:
            self.config = load_config()
            run_id = self.run_id_var.get().strip() or None
            row = fetch_ai_report_record(self.config, run_id=run_id)
            self.report_text.delete("1.0", tk.END)
            if not row:
                self.report_meta_var.set("未找到对应的 AI 报告记录")
                if not silent:
                    self.append_log("未找到对应的 AI 报告记录。")
                return

            metadata_line = (
                f"run_id：{_safe_text(row.get('run_id'))} | "
                f"生成时间：{_safe_text(row.get('generated_at'))} | "
                f"风险等级：{_safe_text(row.get('risk_level'))} | "
                f"模型：{_safe_text(row.get('generator_model'))} | "
                f"模式：{_safe_text(row.get('generator_mode'))}"
            )
            self.report_meta_var.set(metadata_line)

            sections = [
                ("执行摘要", row.get("executive_summary")),
                ("市场概览", row.get("market_overview")),
                ("未来24小时趋势", row.get("next_24h_trend")),
                ("高峰风险", row.get("peak_risk")),
                ("运营建议", row.get("operation_advice_json")),
                ("管理层摘要", row.get("management_summary")),
                ("告警摘要", row.get("alert_message")),
                ("局限性说明", row.get("limitations")),
            ]
            report_lines: list[str] = []
            for title, content in sections:
                text = _safe_text(content)
                if title == "运营建议" and text.startswith("[") and text.endswith("]"):
                    try:
                        advice_list = json.loads(text)
                        text = "\n".join(f"{idx + 1}. {_safe_text(item)}" for idx, item in enumerate(advice_list))
                    except Exception:
                        pass
                if not text:
                    continue
                report_lines.append(f"【{title}】\n{text}")
            self.report_text.insert(tk.END, "\n\n".join(report_lines) if report_lines else _safe_text(row.get("full_report_text")))
            self.report_text.see("1.0")
            if not silent:
                self.append_log(f"已加载 AI 报告：{_safe_text(row.get('run_id'))}")
        except Exception as exc:
            if not silent:
                self.append_log(f"加载 AI 报告失败：{exc}")
                messagebox.showerror("AI 报告浏览", f"加载 AI 报告失败：{exc}")

    def load_selected_preview(self, silent: bool = False) -> None:
        try:
            relation_name = self.source_display_to_name.get(self.preview_source_display_var.get(), "")
            if not relation_name:
                self.preview_meta_var.set("未选择结果表或视图")
                return
            limit = int(self.preview_limit_var.get() or 200)
            run_id = self.run_id_var.get().strip() if self.preview_only_run_var.get() else None
            self.config = load_config()
            df = preview_relation(self.config, relation_name=relation_name, limit=limit, run_id=run_id)
            self._render_dataframe(df)
            run_filter_text = f" | run_id：{run_id}" if run_id and "vw_latest_" not in relation_name else ""
            self.preview_meta_var.set(
                f"来源：{relation_name}{run_filter_text} | 预览行数：{len(df)}"
            )
            if not silent:
                self.append_log(f"已加载结果预览：{relation_name}，行数：{len(df)}")
        except Exception as exc:
            if not silent:
                self.append_log(f"加载结果预览失败：{exc}")
                messagebox.showerror("结果表预览", f"加载结果预览失败：{exc}")

    def _render_dataframe(self, df: pd.DataFrame) -> None:
        columns = [str(col) for col in df.columns]
        self.preview_tree.delete(*self.preview_tree.get_children())
        self.preview_tree["columns"] = columns

        for column in columns:
            self.preview_tree.heading(column, text=column)
            self.preview_tree.column(column, width=130, anchor=tk.W, stretch=True)

        for _, row in df.iterrows():
            values = []
            for column in columns:
                value = row[column]
                text = _safe_text(value).replace("\r", " ").replace("\n", " ")
                if len(text) > 180:
                    text = text[:177] + "..."
                values.append(text)
            self.preview_tree.insert("", tk.END, values=values)

    def _drain_log_queue(self) -> None:
        while True:
            try:
                item = self.log_queue.get_nowait()
            except queue.Empty:
                break

            if item == "__PROCESS_OK__":
                self.is_running = False
                self.current_process = None
                self.status_var.set("已完成")
                self.run_start_time = None
                self.current_step_text = "待命"
                self._set_buttons_state()
                self.refresh_database_browser(silent=True)
                continue
            if item == "__PROCESS_FAIL__":
                self.is_running = False
                self.current_process = None
                self.status_var.set("失败")
                self.run_start_time = None
                self.current_step_text = "待命"
                self._set_buttons_state()
                self.refresh_database_browser(silent=True)
                continue

            inferred = self._infer_step_from_log(item)
            if inferred:
                self.current_step_text = inferred
            self.append_log(item)

        self.root.after(200, self._drain_log_queue)

    def _refresh_status_timer(self) -> None:
        if self.is_running and self.run_start_time is not None:
            elapsed = int(time.perf_counter() - self.run_start_time)
            hours, remainder = divmod(elapsed, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.status_var.set(
                f"运行中 | 当前步骤：{self.current_step_text} | 已耗时：{hours:02d}:{minutes:02d}:{seconds:02d}"
            )
        self.root.after(500, self._refresh_status_timer)

    def _set_buttons_state(self) -> None:
        for button in self.run_buttons:
            if button.cget("text") == "停止当前任务":
                button.config(state=tk.NORMAL if self.is_running else tk.DISABLED)
            else:
                button.config(state=tk.DISABLED if self.is_running else tk.NORMAL)


def main() -> None:
    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    app = PipelineGUI(root)
    app._set_buttons_state()
    root.mainloop()


if __name__ == "__main__":
    main()
