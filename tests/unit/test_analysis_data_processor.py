"""Unit tests for analytics data-quality filtering and report output."""

import os
import shutil
from pathlib import Path

import pandas as pd

from src.analysis.core.data_processor import DataProcessor
from src.analysis.core.report_generator import ReportGenerator
from src.definitions import ROOT_DIR


def test_prepare_dataset_filters_unverified_latest_rows():
    df = pd.DataFrame(
        [
            {
                "id": 1,
                "brand": "Razer",
                "product_code": "SKU-001",
                "product_category": "Mouse",
                "product_name": "Razer Mouse SKU-001",
                "marketplace": "Amazon",
                "price": 100.0,
                "product_url": "https://www.akakce.com/mouse/sku-001.html",
                "scraped_at": "2026-04-27",
                "match_verified": 1,
            },
            {
                "id": 2,
                "brand": "Razer",
                "product_code": "SKU-002",
                "product_category": "Mouse",
                "product_name": "Different Razer Mouse",
                "marketplace": "Amazon",
                "price": 200.0,
                "product_url": "https://www.akakce.com/mouse/different.html",
                "scraped_at": "2026-04-27",
                "match_verified": 1,
            },
            {
                "id": 3,
                "brand": "Razer",
                "product_code": "SKU-003",
                "product_category": "Mouse",
                "product_name": "Razer Mouse SKU-003",
                "marketplace": "Trendyol",
                "price": 300.0,
                "product_url": "https://www.akakce.com/mouse/sku-003.html",
                "scraped_at": "2026-04-27",
                "match_verified": 0,
            },
        ]
    )

    dataset = DataProcessor().prepare_dataset(df)

    assert dataset.rejected_latest_rows == 2
    assert dataset.latest_active_offers["product_code"].tolist() == ["SKU-001"]
    assert dataset.product_metrics["product_code"].tolist() == ["SKU-001"]


def test_prepare_dataset_rejects_close_sku_variant_rows():
    df = pd.DataFrame(
        [
            {
                "id": 1,
                "brand": "Razer",
                "product_code": "RZ04-05220300-R3M1",
                "product_category": "Headset",
                "product_name": "Razer Barracuda X RZ04-05220300-R3U1",
                "marketplace": "Amazon",
                "price": 100.0,
                "product_url": "https://www.akakce.com/rz04-05220300-r3u1.html",
                "scraped_at": "2026-04-27",
                "match_verified": 1,
            }
        ]
    )

    dataset = DataProcessor().prepare_dataset(df)

    assert dataset.rejected_latest_rows == 1
    assert dataset.latest_active_offers.empty
    assert dataset.product_metrics.empty


def test_report_generator_writes_relative_artifact_paths():
    artifact_path = os.path.join(ROOT_DIR, "reports", "charts", "chart.png")
    report_dir = Path(ROOT_DIR) / "_test_output" / "report_generator"
    shutil.rmtree(report_dir, ignore_errors=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    generator = ReportGenerator(report_dir=str(report_dir))

    try:
        report_path = generator.generate(
            "2026-04-27",
            [
                {
                    "plotter": "ExamplePlotter",
                    "title": "Example",
                    "filename": "chart.png",
                    "path": artifact_path,
                    "summary": "Example summary.",
                }
            ],
            rejected_latest_rows=3,
            dataset_metrics={
                "raw_rows": 10,
                "latest_rows": 8,
                "active_verified_offers": 7,
                "product_metrics": 4,
            },
        )

        report = open(report_path, encoding="utf-8").read()

        assert "reports/charts/chart.png" in report
        assert ROOT_DIR not in report
        assert "Rejected Unverified Rows: `3`" in report
        assert "Raw Rows: `10`" in report
        assert "Active Verified Offers: `7`" in report
    finally:
        shutil.rmtree(report_dir.parent, ignore_errors=True)


def test_report_generator_accepts_explicit_report_path():
    report_path = Path(ROOT_DIR) / "_test_output" / "explicit_report" / "audit.md"
    shutil.rmtree(report_path.parent, ignore_errors=True)
    generator = ReportGenerator(report_path=str(report_path))

    try:
        result = generator.generate("2026-04-27", [], rejected_latest_rows=0)

        assert result == str(report_path)
        assert report_path.is_file()
    finally:
        shutil.rmtree(report_path.parent.parent, ignore_errors=True)


def test_marketplace_display_aliases_are_loaded_from_settings():
    class StubConfig:
        def get(self, *keys, default=None):
            mapping = {
                ("scraping", "marketplace_name_aliases"): {
                    "Hepsiburada Premium": "Hepsiburada",
                },
                ("analysis", "marketplace_display_aliases"): {
                    "PttAVM": "PTTAVM",
                    "Amazon Turkiye": "Amazon Turkey",
                    "Bilinmeyen Satici (Akakce ID:10939)": "Koçtaş",
                },
            }
            return mapping.get(keys, default)

    processor = DataProcessor(config=StubConfig())

    assert processor.normalize_marketplace_name("Hepsiburada Premium") == "Hepsiburada"
    assert processor.normalize_marketplace_name("PttAVM") == "PTTAVM"
    assert processor.normalize_marketplace_name("Amazon Turkiye") == "Amazon Turkey"
    assert (
        processor.normalize_marketplace_name("Bilinmeyen Satici (Akakce ID:10939)")
        == "Koçtaş"
    )


def test_price_tiers_are_loaded_from_settings():
    class StubConfig:
        def get(self, *keys, default=None):
            mapping = {
                ("analysis", "price_tiers"): {
                    "entry_upper": 1000,
                    "mid_upper": 5000,
                },
            }
            return mapping.get(keys, default)

    processor = DataProcessor(config=StubConfig())

    assert processor.assign_price_tier(999) == "Entry-Level"
    assert processor.assign_price_tier(1000) == "Mid-Range"
    assert processor.assign_price_tier(5001) == "Premium"
