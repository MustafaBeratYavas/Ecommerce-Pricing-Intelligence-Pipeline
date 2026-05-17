"""Category price distribution and outlier risk chart."""

from __future__ import annotations

import pandas as pd
import seaborn as sns

from src.analysis.core.data_processor import AnalyticsDataset
from src.analysis.core.plot_engine import PlotEngine
from src.analysis.plotters.base_plotter import BasePlotter
from src.analysis.style_config import StyleConfig
from src.core.config import Config


class GhostListingPlotter(BasePlotter):
    title = "Category Price Distribution & Outlier Risk"
    filename = "03_category_price_outlier_risk.png"
    summary = "Highlights category-level price distributions and isolates upper-tail price outlier candidates."

    def create_plot(self, dataset: AnalyticsDataset, engine: PlotEngine):
        df = dataset.latest_active_offers.copy()
        fig, ax = engine.create_figure()
        # Load outlier sensitivity and sampling controls from analysis config.
        settings = Config().get("analysis", "outlier_detection", default={}) or {}
        iqr_multiplier = float(settings.get("iqr_multiplier", 1.5))
        sample_size = int(settings.get("sample_size_per_category", 120))
        random_state = int(settings.get("sample_random_state", 42))

        if df.empty:
            ax.text(
                0.5,
                0.5,
                "No active offers available for outlier detection.",
                ha="center",
                va="center",
            )
            engine.finalize_axes(ax, self.title)
            return fig

        # Order categories by median price so the distribution is easy to scan.
        order = (
            df.groupby("product_category")["price"]
            .median()
            .sort_values()
            .index.tolist()
        )

        sns.boxplot(
            data=df,
            y="product_category",
            x="price",
            hue="product_category",
            order=order,
            whis=iqr_multiplier,
            showfliers=False,
            dodge=False,
            palette=StyleConfig.CATEGORY_COLORS,
            ax=ax,
            legend=False,
        )
        if ax.legend_ is not None:
            ax.legend_.remove()

        sample = pd.concat(
            [
                group.sample(min(len(group), sample_size), random_state=random_state)
                for _, group in df.groupby("product_category")
            ],
            ignore_index=True,
        )
        # Overlay a bounded sample of offers to show density without overcrowding.
        sns.swarmplot(
            data=sample,
            y="product_category",
            x="price",
            order=order,
            size=3,
            color="#E2E8F0",
            alpha=0.5,
            ax=ax,
        )

        outlier_frames: list[pd.DataFrame] = []
        # Identify high-price outliers independently within each category.
        for category, group in df.groupby("product_category"):
            q1 = group["price"].quantile(0.25)
            q3 = group["price"].quantile(0.75)
            iqr = q3 - q1
            threshold = q3 + (iqr_multiplier * iqr)
            outliers = group.loc[group["price"] > threshold].copy()
            outliers["product_category"] = category
            outlier_frames.append(outliers)

        if outlier_frames:
            outliers = pd.concat(outlier_frames, ignore_index=True)
            sns.scatterplot(
                data=outliers,
                y="product_category",
                x="price",
                color=StyleConfig.DANGER,
                s=55,
                edgecolor=StyleConfig.DANGER,
                linewidth=0.2,
                ax=ax,
                legend=False,
            )

        engine.finalize_axes(
            ax,
            self.title,
            xlabel="Price (TRY)",
            ylabel="Category",
            subtitle="Red points indicate upper-tail outliers using a Tukey IQR rule.",
            top_margin=0.82,
        )
        return fig
