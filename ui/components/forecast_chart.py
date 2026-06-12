from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from ui.components.matplotlib_canvas import FigureCanvas, MATPLOTLIB_AVAILABLE, create_dark_figure, mdates
from ui.theme import COLORS


class ForecastChartWidget(QWidget):
    """Reusable dark forecast chart widget for dashboard-style pages."""

    def __init__(self, parent: QWidget | None = None, minimum_height: int = 380):
        super().__init__(parent)
        self.figure = create_dark_figure()
        self.canvas = FigureCanvas(self.figure) if MATPLOTLIB_AVAILABLE and self.figure is not None and FigureCanvas else None
        self.placeholder = QLabel("")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setMinimumHeight(minimum_height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        if self.canvas is not None:
            self.canvas.setMinimumHeight(minimum_height)
            self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(self.canvas)
        else:
            self.placeholder.setObjectName("MutedText")
            self.placeholder.setAlignment(Qt.AlignCenter)
            self.placeholder.setWordWrap(True)
            layout.addWidget(self.placeholder)
            self.render_empty("当前环境无法加载 matplotlib 图表组件，可使用“打开已有预测图”查看图表文件。")

    def render_empty(self, message: str = "暂无预测数据，请先运行预测流程。") -> None:
        if self.canvas is None or self.figure is None:
            self.placeholder.setText(message)
            return
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        self._style_axes(ax)
        ax.text(0.5, 0.5, message, color=COLORS["muted"], ha="center", va="center", transform=ax.transAxes, fontsize=12)
        ax.set_xticks([])
        ax.set_yticks([])
        self.figure.subplots_adjust(left=0.08, right=0.97, top=0.88, bottom=0.14)
        self.canvas.draw_idle()

    def render_forecast(self, df: pd.DataFrame, summary: dict[str, Any] | None = None, annotations: dict[str, Any] | None = None) -> None:
        summary = summary or {}
        annotations = annotations or {}
        if self.canvas is None or self.figure is None:
            return
        work = self._prepare_dataframe(df)
        if work.empty:
            self.render_empty()
            return

        self.figure.clear()
        ax = self.figure.add_subplot(111)
        self._style_axes(ax)

        x_values = self._date_numbers(work["datetime"]) if mdates else work["datetime"]
        prices = work["predicted_price"]
        ax.plot(
            x_values,
            prices,
            color=COLORS["primary"],
            linewidth=2.4,
            marker="o",
            markersize=4.5,
            markerfacecolor=COLORS["primary"],
            markeredgewidth=0,
            label="预测电价",
            zorder=3,
        )

        if {"p10", "p90"}.issubset(work.columns):
            p10 = pd.to_numeric(work["p10"], errors="coerce")
            p90 = pd.to_numeric(work["p90"], errors="coerce")
            if p10.notna().any() and p90.notna().any():
                ax.fill_between(x_values, p10, p90, color=COLORS["button"], alpha=0.18, label="P10-P90预测区间", zorder=1)

        peak_rows = self._peak_rows(work)
        if not peak_rows.empty:
            peak_x = self._date_numbers(peak_rows["datetime"]) if mdates else peak_rows["datetime"]
            ax.scatter(peak_x, peak_rows["predicted_price"], color=COLORS["warning"], s=58, label="高峰时段", zorder=5)

        risk_rows = self._risk_rows(work)
        if not risk_rows.empty:
            risk_x = self._date_numbers(risk_rows["datetime"]) if mdates else risk_rows["datetime"]
            ax.scatter(risk_x, risk_rows["predicted_price"], color=COLORS["danger"], s=68, label="高风险时段", zorder=6)

        self._annotate_extreme(ax, work, x_values, highest=True)
        self._annotate_extreme(ax, work, x_values, highest=False)
        top_risk_rows = risk_rows.head(3)
        self._annotate_risk_points(ax, top_risk_rows)
        risk_times = set(pd.to_datetime(top_risk_rows["datetime"], errors="coerce").dropna())
        peak_label_rows = peak_rows[~pd.to_datetime(peak_rows["datetime"], errors="coerce").isin(risk_times)]
        self._annotate_peak_points(ax, peak_label_rows.sort_values("predicted_price", ascending=False).head(3))

        spread = self._number(summary.get("peak_valley_spread"))
        if spread is not None:
            ax.text(
                0.015,
                0.08,
                f"峰谷价差：{spread:.2f} USD/MWh",
                transform=ax.transAxes,
                color=COLORS["text"],
                fontsize=9,
                bbox={"boxstyle": "round,pad=0.35", "facecolor": "#071423", "edgecolor": COLORS["border"], "alpha": 0.88},
            )

        ax.set_title("未来24小时正式前瞻预测趋势", color=COLORS["text"], fontsize=13, fontweight="bold", pad=22)
        subtitle = self._subtitle(summary, work)
        ax.text(0.0, 1.025, subtitle, transform=ax.transAxes, color=COLORS["body"], fontsize=9, va="bottom")
        ax.set_xlabel("预测时段", color=COLORS["body"], labelpad=8)
        ax.set_ylabel("预测电价（USD/MWh）", color=COLORS["body"], labelpad=8)
        self._format_x_axis(ax, len(work))
        ax.legend(
            loc="upper right",
            facecolor="#071423",
            edgecolor=COLORS["border"],
            labelcolor=COLORS["body"],
            fontsize=8,
            framealpha=0.9,
        )
        self.figure.text(
            0.5,
            0.025,
            "红点表示高风险时段，橙点表示高峰时段，蓝线为预测电价，阴影为预测区间。",
            ha="center",
            color=COLORS["muted"],
            fontsize=8.5,
        )
        self.figure.subplots_adjust(left=0.08, right=0.96, top=0.86, bottom=0.18)
        self.canvas.draw_idle()

    def save_png(self, path: str | Path) -> Path:
        if self.figure is None:
            raise RuntimeError("当前环境未加载 matplotlib，无法保存图表。")
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        self.figure.savefig(output, facecolor=self.figure.get_facecolor(), dpi=150)
        return output

    def open_existing(self, path: str | Path) -> None:
        target = Path(path)
        if not target.exists():
            raise FileNotFoundError(f"图表文件不存在：{target}")
        os.startfile(str(target))

    def _style_axes(self, ax) -> None:
        ax.set_facecolor(COLORS["card"])
        ax.tick_params(colors=COLORS["muted"], labelsize=9)
        for spine in ax.spines.values():
            spine.set_color(COLORS["border"])
        ax.grid(True, color=COLORS["border"], alpha=0.55, linewidth=0.75)

    @staticmethod
    def _prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty or "datetime" not in df.columns or "predicted_price" not in df.columns:
            return pd.DataFrame()
        work = df.copy()
        work["datetime"] = pd.to_datetime(work["datetime"], errors="coerce")
        work["predicted_price"] = pd.to_numeric(work["predicted_price"], errors="coerce")
        for col in ["p10", "p90", "spike_risk_prob"]:
            if col in work.columns:
                work[col] = pd.to_numeric(work[col], errors="coerce")
        return work.dropna(subset=["datetime", "predicted_price"]).sort_values("datetime")

    @staticmethod
    def _peak_rows(work: pd.DataFrame) -> pd.DataFrame:
        if "is_peak_hour" not in work.columns:
            return work.iloc[0:0]
        mask = pd.to_numeric(work["is_peak_hour"], errors="coerce").fillna(0).astype(int) == 1
        return work[mask]

    @staticmethod
    def _risk_rows(work: pd.DataFrame) -> pd.DataFrame:
        risk_mask = pd.Series(False, index=work.index)
        if "risk_level" in work.columns:
            risk_mask = risk_mask | work["risk_level"].astype(str).isin(["高", "HIGH", "high"])
        if "spike_risk_prob" in work.columns:
            risk_mask = risk_mask | (pd.to_numeric(work["spike_risk_prob"], errors="coerce").fillna(0) >= 0.15)
        return work[risk_mask].sort_values(["spike_risk_prob", "predicted_price"], ascending=False, na_position="last") if risk_mask.any() else work.iloc[0:0]

    def _annotate_extreme(self, ax, work: pd.DataFrame, x_values, highest: bool) -> None:
        idx = work["predicted_price"].idxmax() if highest else work["predicted_price"].idxmin()
        pos = list(work.index).index(idx)
        row = work.loc[idx]
        price = self._number(row["predicted_price"]) or 0.0
        hour = pd.to_datetime(row["datetime"]).strftime("%H:%M")
        label = f"{'最高价' if highest else '最低价'} {price:.2f}，{hour}"
        color = COLORS["danger"] if highest else COLORS["success"]
        offset = (28, 28) if highest else (28, -34)
        ax.annotate(
            label,
            xy=(x_values[pos], price),
            xytext=offset,
            textcoords="offset points",
            color=color,
            fontsize=9,
            arrowprops={"arrowstyle": "->", "color": color, "lw": 1.1},
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "#071423", "edgecolor": color, "alpha": 0.88},
        )

    def _annotate_risk_points(self, ax, rows: pd.DataFrame) -> None:
        for offset_index, (_, row) in enumerate(rows.iterrows()):
            x = self._date_numbers(pd.Series([row["datetime"]]))[0] if mdates else row["datetime"]
            y = self._number(row.get("predicted_price"))
            if y is None:
                continue
            ax.annotate(
                "高风险",
                xy=(x, y),
                xytext=(0, 14 + offset_index * 3),
                textcoords="offset points",
                ha="center",
                color=COLORS["danger"],
                fontsize=8,
                bbox={"boxstyle": "round,pad=0.18", "facecolor": "#24111A", "edgecolor": COLORS["danger"], "alpha": 0.82},
            )

    def _annotate_peak_points(self, ax, rows: pd.DataFrame) -> None:
        for _, row in rows.iterrows():
            x = self._date_numbers(pd.Series([row["datetime"]]))[0] if mdates else row["datetime"]
            y = self._number(row.get("predicted_price"))
            if y is None:
                continue
            ax.annotate("高峰", xy=(x, y), xytext=(0, -18), textcoords="offset points", ha="center", color=COLORS["warning"], fontsize=8)

    @staticmethod
    def _format_x_axis(ax, count: int) -> None:
        if not mdates:
            return
        interval = 3 if count > 18 else 2
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=interval))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        for label in ax.get_xticklabels():
            label.set_rotation(30)
            label.set_ha("right")

    @staticmethod
    def _date_numbers(series: pd.Series):
        values = pd.to_datetime(series, errors="coerce")
        return mdates.date2num([value.to_pydatetime() for value in values])

    def _subtitle(self, summary: dict[str, Any], work: pd.DataFrame) -> str:
        avg = self._number(summary.get("avg_price")) or self._number(work["predicted_price"].mean())
        max_price = self._number(summary.get("max_price")) or self._number(work["predicted_price"].max())
        min_price = self._number(summary.get("min_price")) or self._number(work["predicted_price"].min())
        spread = self._number(summary.get("peak_valley_spread"))
        risk = str(summary.get("risk_level") or "-")
        max_hour = str(summary.get("max_hour") or pd.to_datetime(work.loc[work["predicted_price"].idxmax(), "datetime"]).strftime("%H:%M"))
        min_hour = str(summary.get("min_hour") or pd.to_datetime(work.loc[work["predicted_price"].idxmin(), "datetime"]).strftime("%H:%M"))
        return (
            f"均价 {self._fmt(avg)} | 最高 {self._fmt(max_price)}（{max_hour}） | "
            f"最低 {self._fmt(min_price)}（{min_hour}） | 峰谷价差 {self._fmt(spread)} | 风险等级 {risk}"
        )

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            if value is None or pd.isna(value):
                return None
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _fmt(value: float | None) -> str:
        return "-" if value is None else f"{value:.2f}"
