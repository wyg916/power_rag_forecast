from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QScrollArea, QSizePolicy, QVBoxLayout, QWidget


class ResponsiveGrid(QWidget):
    def __init__(
        self,
        min_item_width: int = 230,
        max_columns: int = 5,
        spacing: int = 10,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.min_item_width = min_item_width
        self.max_columns = max_columns
        self._items: list[QWidget] = []
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(spacing)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

    def addWidget(self, widget: QWidget) -> None:  # noqa: N802
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._items.append(widget)
        self._reflow()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reflow()

    def _reflow(self) -> None:
        if not self._items:
            return
        available = max(self.width(), self.min_item_width)
        columns = max(1, min(self.max_columns, available // self.min_item_width))
        for item in self._items:
            self.grid.removeWidget(item)
        for index, item in enumerate(self._items):
            self.grid.addWidget(item, index // columns, index % columns)


def make_scroll_page(parent: QWidget, margins: tuple[int, int, int, int] = (22, 20, 22, 16), spacing: int = 14):
    outer = QVBoxLayout(parent)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    content = QWidget()
    content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
    layout = QVBoxLayout(content)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    scroll.setWidget(content)
    outer.addWidget(scroll, 1)
    return layout, scroll, content
