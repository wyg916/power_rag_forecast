from __future__ import annotations

import importlib
from typing import Callable


LogFunc = Callable[[str], None] | None


def dispatch_report(log: LogFunc = None) -> None:
    if log:
        log("通过 dispatch_service 执行结果归档派发。")
    importlib.import_module("04_dispatch_report").main()
