from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENGINE_SCRIPT = PROJECT_ROOT / "高峰尖刺增强版_电力市场电价预测与智能分析系统_v4_fix1.py"
LEGACY_MODULE_NAME = "_legacy_power_prediction_engine_v4_fix1"


@lru_cache(maxsize=4)
def _load_engine_module_cached(script_path: str) -> ModuleType:
    path = Path(script_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"未找到预测引擎脚本：{path}")

    module_key = f"{LEGACY_MODULE_NAME}_{abs(hash(str(path)))}"
    if module_key in sys.modules:
        return sys.modules[module_key]

    spec = importlib.util.spec_from_file_location(module_key, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载预测引擎模块：{path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_key] = module
    spec.loader.exec_module(module)
    return module


def load_engine_module(script_path: str | Path | None = None) -> ModuleType:
    """加载原 v4_fix1 脚本为模块。

    v4_fix1 已保留脚本直接运行入口，同时增加 main guard，因此这里导入
    不会触发完整训练流程，便于新模块复用其中的稳定函数。
    """

    path = Path(script_path).resolve() if script_path else DEFAULT_ENGINE_SCRIPT
    return _load_engine_module_cached(str(path))
