from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ui.theme import COLORS


class NavigationItem(QFrame):
    clicked = Signal(str)

    def __init__(self, page_id: str, icon: str, title: str, subtitle: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.page_id = page_id
        self.icon = icon
        self.title = title
        self.subtitle = subtitle
        self._active = False
        self._collapsed = False
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(52)

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 7, 10, 7)
        root.setSpacing(10)
        self.bar = QFrame()
        self.bar.setFixedWidth(3)
        root.addWidget(self.bar)
        self.icon_label = QLabel(icon)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setFixedWidth(30)
        root.addWidget(self.icon_label)
        text_box = QVBoxLayout()
        text_box.setSpacing(1)
        self.title_label = QLabel(title)
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setWordWrap(False)
        text_box.addWidget(self.title_label)
        text_box.addWidget(self.subtitle_label)
        root.addLayout(text_box, 1)
        self._apply_style()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._apply_style()

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.setMinimumHeight(46 if collapsed else 52)
        self.title_label.setVisible(not collapsed)
        self.subtitle_label.setVisible(not collapsed)
        self.bar.setVisible(not collapsed)
        self.setToolTip(f"{self.title}\n{self.subtitle}" if collapsed else "")
        self._apply_style()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.page_id)
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hover", True)
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hover", False)
        self._apply_style()
        super().leaveEvent(event)

    def _apply_style(self) -> None:
        hover = bool(self.property("hover"))
        bg = "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2563EB,stop:1 #0EA5E9)" if self._active else "#10233A" if hover else "transparent"
        border = "#38BDF8" if self._active or hover else "transparent"
        self.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 9px; }}"
            f"QLabel {{ background: transparent; border: 0; }}"
        )
        self.bar.setStyleSheet(f"background: {COLORS['primary'] if self._active else 'transparent'}; border-radius: 1px;")
        self.icon_label.setStyleSheet(f"color: {COLORS['text'] if self._active else COLORS['primary']}; font-size: 17px; font-weight: 700;")
        self.title_label.setStyleSheet(f"color: {COLORS['text']}; font-size: 14px; font-weight: {'700' if self._active else '600'};")
        self.subtitle_label.setStyleSheet(f"color: {COLORS['body'] if self._active else COLORS['muted']}; font-size: 11px;")


class NavigationRail(QFrame):
    pageSelected = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self._collapsed = False
        self.setFixedWidth(232)
        self.buttons: dict[str, NavigationItem] = {}
        self.group_labels: list[QLabel] = []

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 14, 12, 14)
        self.layout.setSpacing(7)

        self.title = QLabel("智能运营分析项目控制台")
        self.title.setObjectName("WindowTitle")
        self.title.setWordWrap(True)
        self.title.setStyleSheet("font-size: 15px;")
        self.layout.addWidget(self.title)
        self.layout.addSpacing(8)

        self.menu_scroll = QScrollArea()
        self.menu_scroll.setWidgetResizable(True)
        self.menu_scroll.setFrameShape(QScrollArea.NoFrame)
        self.menu_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.menu_content = QWidget()
        self.menu_layout = QVBoxLayout(self.menu_content)
        self.menu_layout.setContentsMargins(0, 0, 0, 0)
        self.menu_layout.setSpacing(7)
        self.menu_scroll.setWidget(self.menu_content)
        self.layout.addWidget(self.menu_scroll, 1)

        groups = [
            ("运行控制", [
                ("dashboard", "⌂", "控制台", "一体化运行"),
                ("prediction", "◎", "预测任务", "模型运行与报告"),
                ("tasks", "☑", "任务计划", "计划任务管理"),
            ]),
            ("业务分析", [
                ("forecast_results", "⌁", "预测结果中心", "前瞻/风险/解读"),
                ("reports", "AI", "AI报告中心", "历史/审批/可信检查"),
                ("models", "▦", "模型中心", "版本/指标/运维"),
                ("data", "▤", "数据质量中心", "闭环/质量/同步"),
            ]),
            ("系统管理", [
                ("database", "DB", "数据库管理", "表/视图/查询"),
                ("settings", "⚙", "系统设置", "配置与参数"),
                ("logs", "▣", "日志中心", "运行日志查看"),
                ("help", "?", "帮助文档", "使用说明"),
            ]),
        ]
        for group_name, entries in groups:
            self._add_group_label(group_name)
            for page_id, icon, title, subtitle in entries:
                item = NavigationItem(page_id, icon, title, subtitle)
                item.clicked.connect(self.select)
                self.buttons[page_id] = item
                self.menu_layout.addWidget(item)

        self.version = QLabel("应用版本\nv2.6.0\n\n当前环境\n生产环境")
        self.version.setObjectName("MutedText")
        self.layout.addWidget(self.version)
        self.collapse_btn = QPushButton("⇤  折叠导航")
        self.collapse_btn.clicked.connect(self.toggle_collapsed)
        self.layout.addWidget(self.collapse_btn)
        self.select("dashboard", emit=False)

    def _add_group_label(self, text: str) -> None:
        label = QLabel(text.upper())
        label.setStyleSheet(f"color: {COLORS['disabled']}; font-size: 11px; font-weight: 700; padding: 8px 2px 2px;")
        self.group_labels.append(label)
        self.menu_layout.addWidget(label)

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.setFixedWidth(74 if collapsed else 232)
        self.title.setVisible(not collapsed)
        self.version.setVisible(not collapsed)
        self.collapse_btn.setText("⇥" if collapsed else "⇤  折叠导航")
        for label in self.group_labels:
            label.setVisible(not collapsed)
        for item in self.buttons.values():
            item.set_collapsed(collapsed)

    def select(self, page_id: str, emit: bool = True) -> None:
        for key, button in self.buttons.items():
            button.set_active(key == page_id)
        if emit:
            self.pageSelected.emit(page_id)
