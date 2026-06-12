from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ui.theme import COLORS


class SectionCard(QFrame):
    def __init__(self, title: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SectionCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 12, 12, 12)
        self.layout.setSpacing(10)
        if title:
            label = QLabel(title)
            label.setObjectName("SectionTitle")
            self.layout.addWidget(label)


class ActionCard(QFrame):
    clicked = Signal()

    def __init__(
        self,
        icon: str,
        title: str,
        subtitle: str,
        badge: str = "",
        badge_color: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("ActionCard")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self._enabled = True
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(12)

        icon_label = QLabel(icon)
        icon_label.setFixedSize(34, 34)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(
            f"color: {COLORS['primary']}; font-size: 22px; background: #071423; "
            f"border: 1px solid {COLORS['border']}; border-radius: 6px;"
        )
        root.addWidget(icon_label)

        text_box = QVBoxLayout()
        text_box.setSpacing(4)
        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {COLORS['text']}; font-weight: 700; font-size: 14px;")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("CardSubtitle")
        subtitle_label.setWordWrap(True)
        text_box.addWidget(title_label)
        text_box.addWidget(subtitle_label)
        root.addLayout(text_box, 1)

        if badge:
            badge_label = QLabel(badge)
            badge_label.setAlignment(Qt.AlignCenter)
            color = badge_color or COLORS["primary"]
            badge_label.setStyleSheet(
                f"color: {color}; background: rgba(0, 212, 255, 0.08); "
                f"border: 1px solid {color}; border-radius: 5px; padding: 3px 7px;"
            )
            root.addWidget(badge_label)

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        self._enabled = enabled
        super().setEnabled(enabled)
        self.setProperty("disabled", not enabled)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):  # noqa: N802
        if self._enabled and event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
