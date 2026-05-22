"""Unit tests for selector contract telemetry reporting."""

import json
import shutil
from pathlib import Path

from src.definitions import ROOT_DIR
from src.utils.selector_usage import SelectorUsageTracker


def test_selector_usage_can_be_disabled(tmp_path):
    output_path = tmp_path / "selector_usage.json"
    tracker = SelectorUsageTracker()

    tracker.configure({"enabled": False, "output_path": str(output_path)})
    tracker.register_config({"product": {"title": "h1"}})
    tracker.record_lookup(("selectors", "product", "title"), "h1")
    tracker.record_match("selectors.product.title", "h1", 1, "test")

    assert tracker.write_report() is None
    assert not output_path.exists()


def test_selector_usage_report_marks_unused_and_matched_entries():
    output_dir = Path(ROOT_DIR) / "_test_output" / "selector_usage"
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "selector_usage.json"
    tracker = SelectorUsageTracker()
    try:
        tracker.configure({"enabled": True, "output_path": str(output_path)})
        tracker.register_config(
            {
                "search_input": "input[name='q']",
                "product": {
                    "title": "h1",
                    "unused": "div.never-used",
                },
            }
        )

        tracker.record_lookup(("selectors", "search_input"), "input[name='q']")
        tracker.record_match(
            "selectors.search_input",
            "input[name='q']",
            1,
            "test",
        )
        tracker.record_match(
            "selectors.product.title",
            "h1",
            0,
            "test",
        )

        report_path = tracker.write_report()
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        statuses = {record["path"]: record["status"] for record in payload["records"]}

        assert report_path == str(output_path)
        assert statuses["selectors.search_input"] == "matched"
        assert statuses["selectors.product.title"] == "looked_up_never_matched"
        assert statuses["selectors.product.unused"] == "configured_unused"
    finally:
        shutil.rmtree(output_dir.parent, ignore_errors=True)


def test_selector_usage_reports_looked_up_not_measured(tmp_path):
    output_path = tmp_path / "selector_usage.json"
    tracker = SelectorUsageTracker()

    tracker.configure({"enabled": True, "output_path": str(output_path)})
    tracker.record_lookup(("selectors", "search_input"), ["input[name='q']", 123])

    tracker.write_report()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    [record] = payload["records"]

    assert record["path"] == "selectors.search_input"
    assert record["selector_values"] == ["input[name='q']"]
    assert record["status"] == "looked_up_not_measured"
