from __future__ import annotations

import os
import sys


def main() -> int:
    smoke_test = "--smoke-test" in sys.argv
    if smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    from PySide6.QtWidgets import QApplication

    from ui.main_window import MainWindow
    from ui.theme import apply_app_theme

    try:
        from qfluentwidgets import Theme, setTheme

        setTheme(Theme.DARK)
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("智能运营分析项目控制台")
    apply_app_theme(app)

    window = MainWindow(auto_refresh=not smoke_test)
    if smoke_test:
        print("ui_smoke_ok")
        return 0

    window.center_on_screen()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
