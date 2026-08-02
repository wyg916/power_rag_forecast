from __future__ import annotations

import sys
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from automation_common import get_pipeline_paths, load_config  # noqa: E402


APP_VERSION = "v2.11.2"
PLATFORM_NAME = "售电交易 AI 辅助决策平台"


def runtime_asset_root() -> Path:
    """Resolve an explicit read-only asset root for linked worktrees."""

    value = os.environ.get("POWER_TRADING_ASSET_ROOT", "").strip()
    if not value:
        return PROJECT_ROOT
    root = Path(value).resolve(strict=True)
    if not root.is_dir():
        raise RuntimeError("POWER_TRADING_ASSET_ROOT 必须指向现有目录。")
    return root


@lru_cache(maxsize=1)
def project_config() -> dict[str, Any]:
    return load_config()


@lru_cache(maxsize=1)
def project_paths():
    return get_pipeline_paths(project_config())


def reset_config_cache() -> None:
    project_config.cache_clear()
    project_paths.cache_clear()

