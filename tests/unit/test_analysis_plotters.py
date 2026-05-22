"""Unit tests for strategic plotter artifact and layout contracts."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest
from matplotlib import pyplot as plt

from src.analysis.core.data_processor import AnalyticsDataset
from src.analysis.core.plot_engine import PlotEngine
from src.analysis.main import StrategicAnalysisApp
from src.analysis.plotters import (
    AssortmentVulnerabilityPlotter,
    GhostListingPlotter,
    MarketplaceAggressivenessPlotter,
    PortfolioSegmentationPlotter,
    PriceDispersionPlotter,
)
from src.analysis.plotters.base_plotter import PlotArtifact
from src.analysis.style_config import StyleConfig
from src.definitions import ROOT_DIR

PLOTTER_CLASSES = [
    MarketplaceAggressivenessPlotter,
    PriceDispersionPlotter,
    GhostListingPlotter,
    AssortmentVulnerabilityPlotter,
    PortfolioSegmentationPlotter,
]


def _build_dataset(empty: bool = False) -> AnalyticsDataset:
    if empty:
        latest_active_offers = pd.DataFrame(
            columns=["product_code", "product_category", "marketplace", "price"]
        )
        product_metrics = pd.DataFrame(
            columns=[
                "product_code",
                "product_category",
                "offer_count",
                "seller_count",
                "avg_price",
                "price_spread_pct",
                "price_tier",
            ]
        )
        category_offer_totals = pd.DataFrame(
            columns=["product_category", "category_product_count"]
        )
    else:
        latest_active_offers = pd.DataFrame(
            [
                {
                    "product_code": "SKU-001",
                    "product_category": "Mouse",
                    "marketplace": "Amazon",
                    "price": 100.0,
                },
                {
                    "product_code": "SKU-001",
                    "product_category": "Mouse",
                    "marketplace": "Trendyol",
                    "price": 115.0,
                },
                {
                    "product_code": "SKU-002",
                    "product_category": "Headset",
                    "marketplace": "Amazon",
                    "price": 250.0,
                },
                {
                    "product_code": "SKU-002",
                    "product_category": "Headset",
                    "marketplace": "Hepsiburada",
                    "price": 275.0,
                },
                {
                    "product_code": "SKU-003",
                    "product_category": "Headset",
                    "marketplace": "Trendyol",
                    "price": 900.0,
                },
                {
                    "product_code": "SKU-003",
                    "product_category": "Headset",
                    "marketplace": "Amazon",
                    "price": 1600.0,
                },
            ]
        )
        product_metrics = pd.DataFrame(
            [
                {
                    "product_code": "SKU-001",
                    "product_category": "Mouse",
                    "offer_count": 2,
                    "seller_count": 2,
                    "avg_price": 107.5,
                    "price_spread_pct": 15.0,
                    "price_tier": "Entry-Level",
                },
                {
                    "product_code": "SKU-002",
                    "product_category": "Headset",
                    "offer_count": 2,
                    "seller_count": 7,
                    "avg_price": 262.5,
                    "price_spread_pct": 10.0,
                    "price_tier": "Mid-Range",
                },
                {
                    "product_code": "SKU-003",
                    "product_category": "Headset",
                    "offer_count": 2,
                    "seller_count": 19,
                    "avg_price": 1250.0,
                    "price_spread_pct": 77.8,
                    "price_tier": "Premium",
                },
            ]
        )
        category_offer_totals = pd.DataFrame(
            [
                {"product_category": "Mouse", "category_product_count": 1},
                {"product_category": "Headset", "category_product_count": 2},
            ]
        )

    latest_snapshot = latest_active_offers.copy()
    return AnalyticsDataset(
        raw=latest_snapshot.copy(),
        latest_snapshot=latest_snapshot,
        latest_active_offers=latest_active_offers,
        product_metrics=product_metrics,
        category_offer_totals=category_offer_totals,
        latest_date="2026-04-28",
    )


def _prepare_output_dir(name: str) -> Path:
    output_dir = Path(ROOT_DIR) / "_test_output" / "analysis_plotters" / name
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


@pytest.mark.parametrize("plotter_cls", PLOTTER_CLASSES)
def test_plotters_render_non_empty_dataset(plotter_cls):
    output_dir = _prepare_output_dir(f"non_empty_{plotter_cls.__name__}")
    engine = PlotEngine(output_dir=str(output_dir))
    plotter = plotter_cls()

    try:
        artifact = plotter.render(_build_dataset(), engine)

        assert isinstance(artifact, PlotArtifact)
        assert artifact.plotter == plotter_cls.__name__
        assert artifact.title == plotter.title
        assert artifact.summary == plotter.summary
        assert Path(artifact.path).is_file()
        assert Path(artifact.path).name == plotter.filename
        assert plt.imread(artifact.path).shape[:2] == (1080, 1920)
    finally:
        shutil.rmtree(output_dir.parent, ignore_errors=True)


@pytest.mark.parametrize("plotter_cls", PLOTTER_CLASSES)
def test_plotters_render_empty_dataset(plotter_cls):
    output_dir = _prepare_output_dir(f"empty_{plotter_cls.__name__}")
    engine = PlotEngine(output_dir=str(output_dir))
    plotter = plotter_cls()

    try:
        artifact = plotter.render(_build_dataset(empty=True), engine)

        assert Path(artifact.path).is_file()
        assert artifact.filename == plotter.filename
    finally:
        shutil.rmtree(output_dir.parent, ignore_errors=True)


def test_plot_engine_clear_output_removes_only_png_files():
    output_dir = _prepare_output_dir("clear_output")
    png_path = output_dir / "stale.png"
    keep_path = output_dir / "notes.txt"
    png_path.write_bytes(b"old chart")
    keep_path.write_text("keep me", encoding="utf-8")

    try:
        PlotEngine(output_dir=str(output_dir)).clear_output()

        assert not png_path.exists()
        assert keep_path.exists()
    finally:
        shutil.rmtree(output_dir.parent, ignore_errors=True)


def test_price_dispersion_legend_only_shows_active_categories():
    output_dir = _prepare_output_dir("price_dispersion_legend")
    engine = PlotEngine(output_dir=str(output_dir))
    fig = PriceDispersionPlotter().create_plot(_build_dataset(), engine)

    try:
        legend = fig.axes[0].get_legend()

        assert legend is not None
        assert [text.get_text() for text in legend.get_texts()] == ["Mouse", "Headset"]
    finally:
        plt.close(fig)
        shutil.rmtree(output_dir.parent, ignore_errors=True)


@pytest.mark.parametrize("plotter_cls", PLOTTER_CLASSES)
def test_plotters_use_shared_16_9_plot_area(plotter_cls):
    output_dir = _prepare_output_dir(f"plot_area_{plotter_cls.__name__}")
    engine = PlotEngine(output_dir=str(output_dir))
    fig = plotter_cls().create_plot(_build_dataset(), engine)

    try:
        main_axes = fig.axes[0]
        bounds = main_axes.get_position()

        assert bounds.x0 == pytest.approx(StyleConfig.PLOT_RECT[0])
        assert bounds.y0 == pytest.approx(StyleConfig.PLOT_RECT[1])
        assert bounds.width == pytest.approx(StyleConfig.PLOT_RECT[2])
        assert bounds.height == pytest.approx(StyleConfig.PLOT_RECT[3])
        assert bounds.width == pytest.approx(bounds.height)
        assert bounds.x0 + (bounds.width / 2) == pytest.approx(0.5)
    finally:
        plt.close(fig)
        shutil.rmtree(output_dir.parent, ignore_errors=True)


def test_portfolio_segmentation_legend_sits_below_plot_area():
    output_dir = _prepare_output_dir("portfolio_segmentation_legend")
    engine = PlotEngine(output_dir=str(output_dir))
    fig = PortfolioSegmentationPlotter().create_plot(_build_dataset(), engine)

    try:
        legend = fig.axes[0].get_legend()

        assert legend is not None
        fig.canvas.draw()
        legend_bounds = legend.get_window_extent()
        axes_bounds = fig.axes[0].get_window_extent()
        assert legend_bounds.y1 < axes_bounds.y0
    finally:
        plt.close(fig)
        shutil.rmtree(output_dir.parent, ignore_errors=True)


def test_assortment_vulnerability_bar_labels_stay_inside_plot_area():
    output_dir = _prepare_output_dir("assortment_vulnerability_labels")
    engine = PlotEngine(output_dir=str(output_dir))
    fig = AssortmentVulnerabilityPlotter().create_plot(_build_dataset(), engine)

    try:
        ax = fig.axes[0]
        fig.canvas.draw()
        axes_bounds = ax.get_window_extent()

        for label in ax.texts:
            assert label.get_window_extent().y1 <= axes_bounds.y1
    finally:
        plt.close(fig)
        shutil.rmtree(output_dir.parent, ignore_errors=True)


def test_strategic_analysis_app_writes_to_temp_outputs(monkeypatch):
    output_root = Path(ROOT_DIR) / "_test_output" / "strategic_analysis_app"
    chart_dir = output_root / "charts"
    report_path = output_root / "report.md"
    shutil.rmtree(output_root, ignore_errors=True)

    class StubDBHandler:
        def fetch_products(self):
            return pd.DataFrame(
                [
                    {
                        "id": 1,
                        "brand": "Razer",
                        "product_code": "SKU-001",
                        "product_category": "Mouse",
                        "product_name": "Razer Mouse SKU-001",
                        "marketplace": "Amazon",
                        "price": 100.0,
                        "product_url": "https://www.akakce.com/sku-001.html",
                        "scraped_at": "2026-04-28",
                        "source": "fixture",
                        "match_verified": 1,
                    },
                    {
                        "id": 2,
                        "brand": "Razer",
                        "product_code": "SKU-002",
                        "product_category": "Headset",
                        "product_name": "Razer Headset SKU-002",
                        "marketplace": "Trendyol",
                        "price": 250.0,
                        "product_url": "https://www.akakce.com/sku-002.html",
                        "scraped_at": "2026-04-28",
                        "source": "fixture",
                        "match_verified": 1,
                    },
                ]
            )

    monkeypatch.setattr("src.analysis.main.DBHandler", StubDBHandler)
    monkeypatch.setattr("src.analysis.main.normalization_usage", MagicMock())

    try:
        StrategicAnalysisApp(
            chart_output_dir=str(chart_dir),
            report_path=str(report_path),
        ).run()

        assert report_path.is_file()
        assert len(list(chart_dir.glob("*.png"))) == len(PLOTTER_CLASSES)
    finally:
        shutil.rmtree(output_root, ignore_errors=True)
