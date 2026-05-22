"""Render portfolio mix across categories and configured price tiers.

The plotter summarizes product-grain metrics into stacked category bars. It
relies on DataProcessor for tier assignment and avoids any direct warehouse or
scraper dependencies.
"""

from __future__ import annotations

import pandas as pd
from matplotlib.patches import Patch

from src.analysis.core.data_processor import AnalyticsDataset
from src.analysis.core.plot_engine import PlotEngine
from src.analysis.plotters.base_plotter import BasePlotter
from src.analysis.style_config import StyleConfig


class PortfolioSegmentationPlotter(BasePlotter):
    title = "Portfolio Mix by Category and Price Tier"
    filename = "05_portfolio_price_tier_mix.png"
    summary = "Shows the product portfolio split by category and price tier using minimum visible price per product."

    def create_plot(self, dataset: AnalyticsDataset, engine: PlotEngine):
        products = dataset.product_metrics.copy()
        fig, ax = engine.create_figure()

        plot_df = products.loc[products["price_tier"].notna()].copy()
        # Render a visible empty state when no product can be assigned a tier.
        if plot_df.empty:
            ax.text(
                0.5,
                0.5,
                "No active product pricing is available for portfolio segmentation.",
                ha="center",
                va="center",
            )
            engine.finalize_axes(ax, self.title)
            return fig

        tier_order = StyleConfig.PRICE_TIER_ORDER
        # Sort categories by portfolio size so the longest bars anchor the chart.
        category_order = (
            plot_df.groupby("product_category")["product_code"]
            .nunique()
            .sort_values(ascending=True)
            .index.tolist()
        )

        summary = (
            plot_df.groupby(["product_category", "price_tier"])["product_code"]
            .nunique()
            .reset_index(name="product_count")
        )
        pivot = (
            summary.pivot(
                index="product_category", columns="price_tier", values="product_count"
            )
            .reindex(index=category_order, columns=tier_order, fill_value=0)
            .fillna(0)
        )

        left = pd.Series(0.0, index=pivot.index)
        y_positions = list(range(len(pivot.index)))
        # Draw price tiers as stacked horizontal bars with in-segment labels.
        for tier in tier_order:
            values = pivot[tier]
            bars = ax.barh(
                y_positions,
                values,
                left=left,
                height=0.58,
                color=StyleConfig.TIER_COLORS.get(tier, StyleConfig.ACCENT),
                edgecolor="white",
                linewidth=0.9,
                label=tier,
            )
            for bar, value in zip(bars, values):
                if value <= 0:
                    continue
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_y() + bar.get_height() / 2,
                    f"{int(value)}",
                    ha="center",
                    va="center",
                    fontsize=StyleConfig.TICK_SIZE,
                    fontweight="bold",
                )
            left = left + values

        totals = pivot.sum(axis=1)
        # Add product totals just outside each stacked bar for quick comparison.
        for y_pos, total in zip(y_positions, totals):
            ax.text(
                total + max(totals.max() * 0.015, 0.25),
                y_pos,
                f"{int(total)} products",
                va="center",
                fontsize=StyleConfig.TICK_SIZE,
                color=StyleConfig.MUTED_TEXT,
            )

        ax.set_yticks(list(y_positions))
        ax.set_yticklabels(pivot.index)
        ax.set_xlim(0, totals.max() * 1.16)
        vertical_padding = 0.65 if len(y_positions) <= 2 else 0.45
        ax.set_ylim(-vertical_padding, len(y_positions) - 1 + vertical_padding)

        engine.finalize_axes(
            ax,
            self.title,
            xlabel="Number of Products",
            ylabel="Category",
            subtitle="Stacked bars show entry, mid-range, and premium portfolio weight within each category.",
            right_margin=0.94,
            top_margin=0.82,
            bottom_margin=0.2,
        )

        legend_handles = [
            Patch(
                facecolor=StyleConfig.TIER_COLORS[tier],
                edgecolor="white",
                label=tier,
            )
            for tier in tier_order
        ]
        ax.legend(
            handles=legend_handles,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.15),
            ncol=3,
            frameon=True,
            title=None,
        )
        return fig
