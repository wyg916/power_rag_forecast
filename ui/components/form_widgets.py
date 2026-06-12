from __future__ import annotations

from PySide6.QtWidgets import QPushButton


try:
    from qfluentwidgets import PushButton as FluentPushButton
except Exception:  # pragma: no cover - optional style backend
    FluentPushButton = None


def make_button(text: str, primary: bool = False, danger: bool = False) -> QPushButton:
    button = FluentPushButton(text) if FluentPushButton else QPushButton(text)
    button.setMinimumHeight(34)
    if primary:
        button.setObjectName("PrimaryButton")
    if danger:
        button.setObjectName("DangerButton")
    return button
