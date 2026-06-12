from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


COLORS = {
    "bg": "#07111F",
    "sidebar": "#081525",
    "card": "#0B1727",
    "card_hover": "#132238",
    "border": "#1E3A5F",
    "primary": "#00D4FF",
    "button": "#2563EB",
    "success": "#22C55E",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "ai": "#A855F7",
    "text": "#FFFFFF",
    "body": "#D1D5DB",
    "muted": "#94A3B8",
    "disabled": "#64748B",
    "terminal": "#050B14",
}


def apply_app_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(COLORS["bg"]))
    palette.setColor(QPalette.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Base, QColor(COLORS["terminal"]))
    palette.setColor(QPalette.AlternateBase, QColor(COLORS["card"]))
    palette.setColor(QPalette.ToolTipBase, QColor(COLORS["card"]))
    palette.setColor(QPalette.ToolTipText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Text, QColor(COLORS["body"]))
    palette.setColor(QPalette.Button, QColor(COLORS["card"]))
    palette.setColor(QPalette.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.Highlight, QColor(COLORS["button"]))
    palette.setColor(QPalette.HighlightedText, QColor(COLORS["text"]))
    app.setPalette(palette)
    app.setStyleSheet(APP_QSS)


APP_QSS = f"""
QWidget {{
    background: {COLORS["bg"]};
    color: {COLORS["body"]};
    font-family: "Microsoft YaHei UI", "Segoe UI", Arial;
    letter-spacing: 0px;
}}
QMainWindow, #RootWidget {{
    background: {COLORS["bg"]};
}}
QFrame#TopBar, QFrame#BottomBar {{
    background: #06101C;
    border: 1px solid rgba(30, 58, 95, 0.75);
}}
QFrame#Sidebar {{
    background: {COLORS["sidebar"]};
    border-right: 1px solid {COLORS["border"]};
}}
QFrame#SectionCard, QFrame#StatusCard, QFrame#ActionCard {{
    background: {COLORS["card"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 10px;
}}
QFrame#ActionCard:hover {{
    background: {COLORS["card_hover"]};
    border: 1px solid {COLORS["primary"]};
}}
QFrame#ActionCard[disabled="true"] {{
    color: {COLORS["disabled"]};
    border-color: #16263D;
}}
QLabel#WindowTitle, QLabel#PageTitle {{
    color: {COLORS["text"]};
    font-weight: 700;
}}
QLabel#PageTitle {{
    font-size: 24px;
}}
QLabel#SectionTitle {{
    color: {COLORS["text"]};
    font-size: 15px;
    font-weight: 700;
}}
QLabel#MutedText, QLabel#CardSubtitle {{
    color: {COLORS["muted"]};
}}
QLabel#MetricValue {{
    color: {COLORS["text"]};
    font-weight: 700;
    font-size: 14px;
}}
QPushButton {{
    background: #10233A;
    border: 1px solid {COLORS["border"]};
    border-radius: 7px;
    color: {COLORS["body"]};
    min-height: 34px;
    padding: 6px 12px;
}}
QPushButton:hover {{
    background: {COLORS["card_hover"]};
    border-color: {COLORS["primary"]};
    color: {COLORS["text"]};
}}
QPushButton:pressed {{
    background: #0B3A66;
}}
QPushButton:disabled {{
    color: {COLORS["disabled"]};
    background: #0A1422;
    border-color: #14253C;
}}
QPushButton#PrimaryButton {{
    background: {COLORS["button"]};
    border: 1px solid #3B82F6;
    color: {COLORS["text"]};
}}
QPushButton#DangerButton {{
    background: #3A1420;
    border: 1px solid {COLORS["danger"]};
    color: #FCA5A5;
}}
QLineEdit, QComboBox, QSpinBox, QTimeEdit {{
    background: #071423;
    border: 1px solid {COLORS["border"]};
    border-radius: 7px;
    color: {COLORS["text"]};
    min-height: 34px;
    padding: 4px 8px;
}}
QComboBox QAbstractItemView {{
    background: #081525;
    color: {COLORS["body"]};
    selection-background-color: {COLORS["button"]};
    border: 1px solid {COLORS["border"]};
}}
QTextEdit, QPlainTextEdit {{
    background: {COLORS["terminal"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    color: {COLORS["body"]};
    selection-background-color: #1D4ED8;
}}
QTableWidget {{
    background: #071423;
    alternate-background-color: #0A1728;
    gridline-color: #163252;
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    color: {COLORS["body"]};
}}
QHeaderView::section {{
    background: #0D2035;
    color: {COLORS["text"]};
    border: 0px;
    border-right: 1px solid {COLORS["border"]};
    padding: 6px;
    font-weight: 700;
}}
QSplitter::handle {{
    background: #0A1A2C;
}}
QSplitter::handle:hover {{
    background: {COLORS["border"]};
}}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: #071423;
    border: 0px;
    width: 10px;
    height: 10px;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: #1E3A5F;
    border-radius: 5px;
}}
QListWidget {{
    background: #071423;
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    color: {COLORS["body"]};
}}
QListWidget::item {{
    padding: 8px;
}}
QListWidget::item:selected {{
    background: #1D4ED8;
    color: {COLORS["text"]};
}}
"""
