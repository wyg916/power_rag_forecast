"""阶段二预测引擎模块化入口。

该包先以兼容包装方式复用原 v4_fix1 中已经验证过的核心函数，
后续可逐步把实现从兼容脚本迁移到独立模块中。
"""

from .legacy_engine import DEFAULT_ENGINE_SCRIPT, load_engine_module

__all__ = ["DEFAULT_ENGINE_SCRIPT", "load_engine_module"]
