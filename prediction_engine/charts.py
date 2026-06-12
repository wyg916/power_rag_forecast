from __future__ import annotations

from .legacy_engine import load_engine_module


def save_fig(fig, filepath: str):
    return load_engine_module().save_fig(fig, filepath)
