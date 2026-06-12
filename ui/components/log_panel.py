from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QTextEdit, QVBoxLayout, QWidget

from ui.theme import COLORS


class LogPanel(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.addStretch(1)
        self.clear_button = QPushButton("清空日志")
        self.clear_button.setFixedWidth(92)
        toolbar.addWidget(self.clear_button)
        layout.addLayout(toolbar)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(210)
        self.text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.text.setStyleSheet(f"font-family: Consolas, 'Microsoft YaHei UI'; background: {COLORS['terminal']};")
        layout.addWidget(self.text, 1)
        self.clear_button.clicked.connect(self.text.clear)

    def append(self, message: str, level: str | None = None) -> None:
        level_name = (level or self._infer_level(message)).upper()
        color = {
            "SUCCESS": COLORS["success"],
            "ERROR": COLORS["danger"],
            "WARNING": COLORS["warning"],
            "INFO": COLORS["primary"],
        }.get(level_name, COLORS["body"])
        timestamp = datetime.now().strftime("%H:%M:%S")
        safe = (
            message.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        self.text.append(f'<span style="color:{COLORS["muted"]}">[{timestamp}]</span> '
                         f'<span style="color:{color}">{safe}</span>')
        self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().maximum())

    @staticmethod
    def _infer_level(message: str) -> str:
        text = message.upper()
        if "ERROR" in text or "失败" in message or "异常" in message:
            return "ERROR"
        if "WARN" in text or "警告" in message or "跳过" in message:
            return "WARNING"
        if "SUCCESS" in text or "完成" in message or "成功" in message:
            return "SUCCESS"
        return "INFO"
