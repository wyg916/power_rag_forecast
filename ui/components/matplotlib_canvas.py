from __future__ import annotations

from typing import Iterable

from ui.theme import COLORS


MATPLOTLIB_AVAILABLE = False
Figure = None
FigureCanvas = None
mdates = None


try:  # pragma: no cover - optional GUI backend availability is environment-specific
    from matplotlib import font_manager, rcParams
    import matplotlib.dates as _mdates
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as _FigureCanvas
    from matplotlib.figure import Figure as _Figure

    Figure = _Figure
    FigureCanvas = _FigureCanvas
    mdates = _mdates
    MATPLOTLIB_AVAILABLE = True
except Exception:  # pragma: no cover
    font_manager = None
    rcParams = None


FONT_CANDIDATES = [
    "Microsoft YaHei",
    "Microsoft YaHei UI",
    "SimHei",
    "Microsoft JhengHei",
    "Arial Unicode MS",
    "Noto Sans CJK SC",
    "DejaVu Sans",
]


def configure_matplotlib_chinese_font(candidates: Iterable[str] | None = None) -> str:
    """Configure matplotlib for Chinese labels without failing on minimal hosts."""
    if not MATPLOTLIB_AVAILABLE or rcParams is None:
        return ""
    selected = ""
    try:
        available = {font.name for font in font_manager.fontManager.ttflist}
        for name in candidates or FONT_CANDIDATES:
            if name in available:
                selected = name
                break
        family = [selected] if selected else []
        family.extend([name for name in FONT_CANDIDATES if name not in family])
        rcParams["font.sans-serif"] = family
        rcParams["axes.unicode_minus"] = False
    except Exception:
        rcParams["axes.unicode_minus"] = False
    return selected


def create_dark_figure(figsize: tuple[float, float] = (9.5, 4.8), dpi: int = 100):
    configure_matplotlib_chinese_font()
    if not MATPLOTLIB_AVAILABLE or Figure is None:
        return None
    return Figure(figsize=figsize, dpi=dpi, facecolor=COLORS["card"])
