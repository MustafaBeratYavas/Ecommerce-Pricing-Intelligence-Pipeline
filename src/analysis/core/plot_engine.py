"""Chart canvas creation, cleanup, and export operations."""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib.pyplot as plt

from src.analysis.style_config import StyleConfig
from src.core.config import Config
from src.definitions import ROOT_DIR


class PlotEngine:
    def __init__(self, output_dir: str | None = None) -> None:
        self.config = Config()
        StyleConfig.refresh_from_config(self.config)
        default_output = self.config.get(
            "paths", "charts_dir", default="reports/charts"
        )
        self.output_dir = output_dir or os.path.join(ROOT_DIR, default_output)
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    def create_figure(self, large: bool = False):
        figure_size = (
            StyleConfig.LARGE_FIGURE_SIZE if large else StyleConfig.FIGURE_SIZE
        )
        return plt.subplots(figsize=figure_size, dpi=StyleConfig.DPI)

    def clear_output(self) -> None:
        # Remove stale chart artifacts before regenerating the active portfolio.
        for filename in os.listdir(self.output_dir):
            if filename.lower().endswith(".png"):
                os.remove(os.path.join(self.output_dir, filename))

    def finalize_axes(
        self,
        ax,
        title: str,
        xlabel: str = "",
        ylabel: str = "",
        subtitle: str = "",
        left_margin: float = 0.08,
        right_margin: float = 0.97,
        top_margin: float = 0.82,
        bottom_margin: float = 0.13,
    ) -> None:
        fig = ax.figure
        ax.set_xlabel(
            xlabel, fontsize=StyleConfig.LABEL_SIZE, labelpad=StyleConfig.AXIS_LABEL_PAD
        )
        ax.set_ylabel(
            ylabel, fontsize=StyleConfig.LABEL_SIZE, labelpad=StyleConfig.AXIS_LABEL_PAD
        )
        ax.tick_params(axis="both", which="major", pad=StyleConfig.TICK_LABEL_PAD)
        for spine in ax.spines.values():
            spine.set_color(StyleConfig.BORDER)

        title_y = 0.965 if subtitle else 0.955
        fig.suptitle(
            title,
            x=0.5,
            y=title_y,
            ha="center",
            fontsize=StyleConfig.TITLE_SIZE,
            fontweight="bold",
            color=StyleConfig.TEXT,
        )
        if subtitle:
            fig.text(
                0.5,
                0.915,
                subtitle,
                ha="center",
                va="center",
                fontsize=StyleConfig.SUBTITLE_SIZE,
                color=StyleConfig.MUTED_TEXT,
            )
        fig.subplots_adjust(
            left=left_margin,
            right=right_margin,
            top=top_margin,
            bottom=bottom_margin,
        )
        ax.set_position(StyleConfig.PLOT_RECT)

    def save_figure(self, fig, filename: str) -> str:
        path = os.path.join(self.output_dir, filename)
        fig.set_size_inches(*StyleConfig.FIGURE_SIZE)
        fig.savefig(path, dpi=StyleConfig.DPI, bbox_inches=None)
        plt.close(fig)
        return path
