from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QPlainTextEdit, QSplitter, QVBoxLayout, QWidget

from ui.components.cards import SectionCard
from ui.components.form_widgets import make_button
from ui.components.layouts import make_scroll_page


class LogsPage(QWidget):
    messageEmitted = Signal(str, str)

    def __init__(self, log_dir: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.log_dir = log_dir
        root, _scroll, _content = make_scroll_page(self)

        title = QLabel("日志中心")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        card = SectionCard("运行日志文件")
        toolbar = QHBoxLayout()
        refresh_btn = make_button("刷新")
        open_btn = make_button("打开日志目录")
        refresh_btn.clicked.connect(self.refresh_files)
        open_btn.clicked.connect(lambda: self.messageEmitted.emit(f"OPEN_PATH::{self.log_dir}", "INFO"))
        toolbar.addWidget(refresh_btn)
        toolbar.addWidget(open_btn)
        toolbar.addStretch(1)
        card.layout.addLayout(toolbar)

        body = QSplitter(Qt.Horizontal)
        self.file_list = QListWidget()
        self.viewer = QPlainTextEdit()
        self.viewer.setReadOnly(True)
        body.addWidget(self.file_list)
        body.addWidget(self.viewer)
        body.setSizes([320, 900])
        body.setStretchFactor(0, 25)
        body.setStretchFactor(1, 75)
        card.layout.addWidget(body, 1)
        root.addWidget(card, 1)
        self.file_list.currentTextChanged.connect(self._load_selected_file)

    def refresh_files(self) -> None:
        self.file_list.clear()
        if not self.log_dir.exists():
            self.messageEmitted.emit(f"日志目录不存在：{self.log_dir}", "WARNING")
            return
        files = sorted(self.log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        self.file_list.addItems([p.name for p in files[:100]])
        self.messageEmitted.emit(f"日志文件已刷新：{len(files)} 个。", "SUCCESS")
        if self.file_list.count():
            self.file_list.setCurrentRow(0)

    def _load_selected_file(self, name: str) -> None:
        if not name:
            return
        path = self.log_dir / name
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            self.viewer.setPlainText(text[-120000:])
        except Exception as exc:
            self.messageEmitted.emit(f"读取日志失败：{exc}", "ERROR")
