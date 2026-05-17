"""Price spread versus market depth bubble plot."""

from __future__ import annotations

import numpy as np
import seaborn as sns
from matplotlib.lines import Line2D

from src.analysis.core.data_processor import AnalyticsDataset
from src.analysis.core.plot_engine import PlotEngine
from src.analysis.plotters.base_plotter import BasePlotter
from src.analysis.style_config import StyleConfig


class PriceDispersionPlotter(BasePlotter):
    title = "Price Spread vs. Market Depth"
    filename = "02_price_spread_market_depth.png"
    summary = "Shows whether broader offer depth compresses or amplifies price spread across products."

    def create_plot(self, dataset: AnalyticsDataset, engine: PlotEngine):
        product_metrics = dataset.product_metrics.copy()
        fig, ax = engine.create_figure()

        # Filter out products with no active offers before computing bubble size.
        plot_df = product_metrics.loc[product_metrics["offer_count"] > 0].copy()
        plot_df["bubble_size"] = np.clip(plot_df["avg_price"] / 30, 80, 1400)

        if plot_df.empty:
            ax.text(
                0.5,
                0.5,
                "No active product-level pricing data available.",
                ha="center",
                va="center",
            )
            engine.finalize_axes(ax, self.title)
            return fig

        # Plot each product as one point, with price level represented by area.
        sns.scatterplot(
            data=plot_df,
            x="offer_count",
            y="price_spread_pct",
            hue="product_category",
            size="bubble_size",
            sizes=(120, 1400),
            palette=StyleConfig.CATEGORY_COLORS,
            alpha=0.75,
            edgecolor="white",
            linewidth=0.7,
            ax=ax,
            legend=False,
        )

        visible_categories = [
            category
            for category in StyleConfig.CATEGORY_COLORS
            if category in set(plot_df["product_category"].dropna())
        ]
        # Build a manual legend so unused configured categories stay hidden.
        category_handles = [
            Line2D(
                [0],
                [0],
                marker="o",
                linestyle="",
                label=category,
                markerfacecolor=StyleConfig.CATEGORY_COLORS[category],
                markeredgecolor="white",
                markersize=10,
            )
            for category in visible_categories
        ]
        engine.finalize_axes(
            ax,
            self.title,
            xlabel="Total Number of Offers",
            ylabel="Price Spread (%)",
            subtitle="Bubble size represents average price per product. Each point is a product snapshot.",
            right_margin=0.93,
            top_margin=0.82,
        )
        if category_handles:
            ax.legend(
                handles=category_handles,
                title=None,
                loc="upper right",
                frameon=True,
            )
        return fig
