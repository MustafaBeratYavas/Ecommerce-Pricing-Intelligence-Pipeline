"""Generate the strategic analytics chart portfolio and report."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

if __name__ == "__main__":
    sys.path.insert(
        0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )

from src.analysis.core import DataProcessor, DBHandler, PlotEngine, ReportGenerator
from src.analysis.plotters import (
    AssortmentVulnerabilityPlotter,
    GhostListingPlotter,
    MarketplaceAggressivenessPlotter,
    PortfolioSegmentationPlotter,
    PriceDispersionPlotter,
)
from src.analysis.style_config import StyleConfig
from src.core.config import Config
from src.utils.normalization_usage import normalization_usage


class StrategicAnalysisApp:
    def __init__(
        self,
        chart_output_dir: str | None = None,
        report_dir: str | None = None,
        report_path: str | None = None,
    ) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config = Config()
        # Register normalization telemetry for aliases applied during analysis.
        normalization_usage.configure(
            self.config.get("observability", "normalization_usage", default={})
        )
        normalization_usage.register_config(self.config)
        self.db_handler = DBHandler()
        self.data_processor = DataProcessor()
        self.plot_engine = PlotEngine(output_dir=chart_output_dir)
        self.report_generator = ReportGenerator(
            report_dir=report_dir,
            report_path=report_path,
        )
        self.plotters = self._build_plotter_registry()

    def _build_plotter_registry(self):
        # Keep chart ordering stable so generated filenames remain predictable.
        return [
            MarketplaceAggressivenessPlotter(),
            PriceDispersionPlotter(),
            GhostListingPlotter(),
            AssortmentVulnerabilityPlotter(),
            PortfolioSegmentationPlotter(),
        ]

    def run(self) -> None:
        start_time = time.time()
        raw_products = self.db_handler.fetch_products()
        dataset = self.data_processor.prepare_dataset(raw_products)
        self.plot_engine.clear_output()

        # Render every registered plotter into a common artifact contract.
        artifacts = []
        for index, plotter in enumerate(self.plotters, start=1):
            self.logger.info(
                "[%s/%s] Rendering %s", index, len(self.plotters), plotter.title
            )
            artifact = plotter.render(dataset, self.plot_engine)
            artifacts.append(
                {
                    "plotter": artifact.plotter,
                    "title": artifact.title,
                    "filename": artifact.filename,
                    "path": artifact.path,
                    "summary": artifact.summary,
                }
            )

        report_path = self.report_generator.generate(
            dataset.latest_date,
            artifacts,
            rejected_latest_rows=dataset.rejected_latest_rows,
            dataset_metrics={
                "raw_rows": len(dataset.raw),
                "latest_rows": len(dataset.latest_snapshot),
                "active_verified_offers": len(dataset.latest_active_offers),
                "product_metrics": len(dataset.product_metrics),
            },
        )
        elapsed = time.time() - start_time
        self.logger.info("Strategic analysis completed in %.1fs", elapsed)
        self.logger.info("Markdown report written to %s", report_path)
        normalization_report_path = normalization_usage.write_report()
        if normalization_report_path:
            self.logger.info(
                "Normalization usage report written to %s", normalization_report_path
            )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate strategic analytics charts and markdown report."
    )
    parser.add_argument(
        "--charts-dir",
        default=None,
        help="Optional chart output directory. Defaults to reports/charts.",
    )
    parser.add_argument(
        "--report-dir",
        default=None,
        help="Optional report directory. Defaults to reports.",
    )
    parser.add_argument(
        "--report-path",
        default=None,
        help="Optional complete markdown report path. Overrides --report-dir.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    StyleConfig.apply_theme()
    StrategicAnalysisApp(
        chart_output_dir=args.charts_dir,
        report_dir=args.report_dir,
        report_path=args.report_path,
    ).run()


if __name__ == "__main__":
    main()
