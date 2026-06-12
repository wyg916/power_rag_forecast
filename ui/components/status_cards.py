from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ui.theme import COLORS


class MetricCard(QFrame):
    def __init__(self, title: str, value: str = "-", accent: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("StatusCard")
        self._accent = accent or COLORS["primary"]
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("MutedText")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("MetricValue")
        self.value_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str, accent: str | None = None) -> None:
        self.value_label.setText(value or "-")
        if accent:
            self.value_label.setStyleSheet(f"color: {accent}; font-weight: 700;")


class StatusPill(QFrame):
    def __init__(self, text: str, color: str = COLORS["success"], parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color: {color};")
        self.label = QLabel(text)
        self.label.setStyleSheet(f"color: {COLORS['body']};")
        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        layout.addStretch(1)

    def set_status(self, text: str, color: str) -> None:
        self.dot.setStyleSheet(f"color: {color};")
        self.label.setText(text)


class KeyValueRow(QFrame):
    def __init__(self, key: str, value: str = "-", parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.key_label = QLabel(key)
        self.key_label.setObjectName("MutedText")
        self.value_label = QLabel(value)
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.value_label.setStyleSheet(f"color: {COLORS['text']};")
        layout.addWidget(self.key_label)
        layout.addStretch(1)
        layout.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value or "-")
