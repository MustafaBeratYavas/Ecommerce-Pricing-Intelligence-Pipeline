"""Write a markdown inventory of generated strategic charts."""

from __future__ import annotations

import os
from pathlib import Path

from src.core.config import Config
from src.definitions import ROOT_DIR


class ReportGenerator:
    def __init__(
        self,
        report_dir: str | None = None,
        report_path: str | None = None,
        config: Config | None = None,
    ) -> None:
        self.config = config or Config()
        # Resolve report destinations from config unless callers override them.
        default_dir = self.config.get("paths", "reports_dir", default="reports")
        self.report_filename = self.config.get(
            "paths",
            "strategic_report_filename",
            default="strategic_analysis_report.md",
        )
        self.report_dir = report_dir or os.path.join(ROOT_DIR, default_dir)
        self.report_path = report_path
        output_dir = (
            os.path.dirname(report_path) if report_path else self.report_dir
        ) or "."
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        latest_date: str,
        artifacts: list[dict[str, str]],
        rejected_latest_rows: int = 0,
        dataset_metrics: dict[str, int] | None = None,
    ) -> str:
        # Assemble a deterministic markdown report for charts generated this run.
        report_path = self.report_path or os.path.join(
            self.report_dir, self.report_filename
        )
        lines = [
            "# Strategic E-Commerce Analytics Report",
            "",
            f"- Snapshot Date: `{latest_date}`",
            f"- Charts Generated: `{len(artifacts)}`",
            f"- Rejected Unverified Rows: `{rejected_latest_rows}`",
        ]
        if dataset_metrics:
            lines.extend(
                [
                    f"- Raw Rows: `{dataset_metrics.get('raw_rows', 0)}`",
                    f"- Latest Snapshot Rows: `{dataset_metrics.get('latest_rows', 0)}`",
                    (
                        "- Active Verified Offers: "
                        f"`{dataset_metrics.get('active_verified_offers', 0)}`"
                    ),
                    f"- Product Metrics: `{dataset_metrics.get('product_metrics', 0)}`",
                ]
            )
        lines.extend(
            [
                "",
                "## Output Inventory",
                "",
            ]
        )

        for artifact in artifacts:
            # Store portable relative paths when artifacts live inside the project.
            raw_path = artifact["path"]
            artifact_path = (
                os.path.relpath(raw_path, ROOT_DIR)
                if os.path.isabs(raw_path)
                else raw_path
            ).replace(os.sep, "/")
            lines.extend(
                [
                    f"### {artifact['title']}",
                    "",
                    f"- Plotter: `{artifact['plotter']}`",
                    f"- File: `{artifact['filename']}`",
                    f"- Path: `{artifact_path}`",
                    f"- Summary: {artifact['summary']}",
                    "",
                ]
            )

        with open(report_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))

        return report_path
