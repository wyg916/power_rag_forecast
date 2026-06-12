from __future__ import annotations

import platform
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QLineEdit, QWidget

from ui.components.cards import SectionCard
from ui.components.form_widgets import make_button
from ui.components.layouts import make_scroll_page
from ui.components.status_cards import KeyValueRow


class SettingsPage(QWidget):
    saveOutputRootRequested = Signal(str)
    testDatabaseRequested = Signal()

    def __init__(self, output_root: Path, database_name: str, parent: QWidget | None = None):
        super().__init__(parent)
        root, _scroll, _content = make_scroll_page(self)

        title = QLabel("系统设置")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        output_card = SectionCard("输出配置")
        row = QGridLayout()
        self.output_edit = QLineEdit(str(output_root))
        save_btn = make_button("保存配置", primary=True)
        save_btn.clicked.connect(lambda: self.saveOutputRootRequested.emit(self.output_edit.text()))
        row.addWidget(QLabel("总输出目录"), 0, 0)
        row.addWidget(self.output_edit, 0, 1)
        row.addWidget(save_btn, 0, 2)
        output_card.layout.addLayout(row)
        root.addWidget(output_card)

        env_card = SectionCard("运行环境")
        env_card.layout.addWidget(KeyValueRow("数据库名称", database_name or "-"))
        env_card.layout.addWidget(KeyValueRow("Python 版本", platform.python_version()))
        env_card.layout.addWidget(KeyValueRow("当前系统", platform.platform()))
        env_card.layout.addWidget(KeyValueRow("桌面 UI", "PySide6 + qfluentwidgets"))
        test_btn = make_button("测试数据库连接", primary=True)
        test_btn.clicked.connect(self.testDatabaseRequested.emit)
        env_card.layout.addWidget(test_btn)
        root.addWidget(env_card)
        root.addStretch(1)

    def set_output_root(self, path: Path) -> None:
        self.output_edit.setText(str(path))
