"""Render marketplace lowest-price win rates by category.

This plotter measures where marketplaces win the minimum-price position across
verified active offers. It splits tied wins and normalizes by category size so
the heatmap compares categories fairly.
"""

from __future__ import annotations

import seaborn as sns

from src.analysis.core.data_processor import AnalyticsDataset
from src.analysis.core.plot_engine import PlotEngine
from src.analysis.plotters.base_plotter import BasePlotter
from src.analysis.style_config import StyleConfig
from src.core.config import Config


class MarketplaceAggressivenessPlotter(BasePlotter):
    title = "Marketplace Lowest-Price Win Rate"
    filename = "01_marketplace_lowest_price_win_rate.png"
    summary = "Measures how often each marketplace matches the lowest visible price within each product category."

    def create_plot(self, dataset: AnalyticsDataset, engine: PlotEngine):
        df = dataset.latest_active_offers.copy()
        fig, ax = engine.create_figure()
        config = Config()

        # Render a clear empty state when no verified offers are available.
        if df.empty:
            ax.text(
                0.5,
                0.5,
                "No active offers available for heatmap generation.",
                ha="center",
                va="center",
            )
            engine.finalize_axes(ax, self.title)
            return fig

        # Split credit across marketplaces tied for one product's lowest price.
        df["lowest_price"] = df.groupby("product_code")["price"].transform("min")
        winners = df.loc[df["price"] == df["lowest_price"]].copy()
        winners["tie_count"] = winners.groupby("product_code")["marketplace"].transform(
            "size"
        )
        winners["win_credit"] = 1 / winners["tie_count"]

        top_n = int(config.get("analysis", "marketplace_top_n", default=10))
        top_marketplaces = df["marketplace"].value_counts().head(top_n).index.tolist()
        winners = winners.loc[winners["marketplace"].isin(top_marketplaces)]

        # Normalize wins by category size so categories remain comparable.
        heatmap_source = (
            winners.groupby(["marketplace", "product_category"])["win_credit"]
            .sum()
            .reset_index(name="buybox_wins")
            .merge(dataset.category_offer_totals, on="product_category", how="left")
        )
        heatmap_source["win_rate_pct"] = (
            heatmap_source["buybox_wins"]
            / heatmap_source["category_product_count"]
            * 100
        )

        pivot = (
            heatmap_source.pivot(
                index="marketplace", columns="product_category", values="win_rate_pct"
            )
            .reindex(top_marketplaces)
            .fillna(0.0)
        )

        ax.set_position(StyleConfig.PLOT_RECT)
        cax = fig.add_axes(StyleConfig.COLORBAR_RECT)

        sns.heatmap(
            pivot,
            ax=ax,
            cmap="mako",
            linewidths=0.8,
            annot=True,
            fmt=".1f",
            cbar_ax=cax,
            cbar_kws={"label": ""},
        )
        cax.set_ylabel("")
        cax.tick_params(
            colors=ax.xaxis.label.get_color(), pad=StyleConfig.TICK_LABEL_PAD
        )
        engine.finalize_axes(
            ax,
            self.title,
            xlabel="Category",
            ylabel="Marketplace",
            subtitle=(
                f"Top {top_n} marketplaces by active offer volume; "
                "tied lowest prices split win credit evenly."
            ),
            right_margin=0.93,
            top_margin=0.82,
        )
        return fig
