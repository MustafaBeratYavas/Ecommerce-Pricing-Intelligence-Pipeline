"""Unit tests for normalization alias telemetry reports."""

import json
import shutil
from pathlib import Path

from src.definitions import ROOT_DIR
from src.utils.normalization_usage import NormalizationUsageTracker


class FakeNormalizationConfig:
    def get(self, *keys, default=None):
        maps = {
            ("scraping", "marketplace_id_map"): {"10939": "Koctas"},
            ("scraping", "marketplace_name_aliases"): {"Koctas": "Koctas"},
            ("analysis", "marketplace_display_aliases"): {"Koctas": "Koctas"},
            ("analysis", "category_aliases"): {"Mouse": "Mouse"},
        }
        return maps.get(tuple(keys), default)


def test_normalization_usage_report_marks_used_and_unused_aliases():
    output_dir = Path(ROOT_DIR) / "_test_output" / "normalization_usage"
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "normalization_usage.json"
    tracker = NormalizationUsageTracker()

    try:
        tracker.configure({"enabled": True, "output_path": str(output_path)})
        tracker.register_alias_map(
            "analysis.category_aliases",
            {
                "Kulaklık": "Headset",
                "Mouse": "Mouse",
            },
        )
        tracker.record_hit(
            "analysis.category_aliases",
            "Kulaklık",
            "Kulaklık",
            "Headset",
            "test",
        )

        report_path = tracker.write_report()
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        statuses = {record["alias"]: record["status"] for record in payload["records"]}

        assert report_path == str(output_path)
        assert statuses["Kulaklık"] == "used"
        assert statuses["Mouse"] == "configured_unused"
        assert payload["summary"]["used_entries"] == 1
    finally:
        shutil.rmtree(output_dir.parent, ignore_errors=True)


def test_normalization_usage_can_be_disabled(tmp_path):
    output_path = tmp_path / "normalization_usage.json"
    tracker = NormalizationUsageTracker()

    tracker.configure({"enabled": False, "output_path": str(output_path)})
    tracker.register_config(FakeNormalizationConfig())
    tracker.record_hit("analysis.category_aliases", "Mouse", "Mouse", "Mouse", "test")

    assert tracker.write_report() is None
    assert not output_path.exists()


def test_normalization_usage_registers_configured_maps(tmp_path):
    output_path = tmp_path / "normalization_usage.json"
    tracker = NormalizationUsageTracker()

    tracker.configure({"enabled": True, "output_path": str(output_path)})
    tracker.register_config(FakeNormalizationConfig())

    tracker.write_report()
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["summary"]["configured_entries"] == 4
    assert payload["summary"]["unused_configured_entries"] == 4
