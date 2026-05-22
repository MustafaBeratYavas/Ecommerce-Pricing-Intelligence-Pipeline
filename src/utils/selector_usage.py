"""Track runtime usage of configured selector contracts.

SelectorUsageTracker records which configured selectors are looked up, matched,
missed, or left unused during a scraping run. The report supports selector
maintenance without influencing scraping decisions.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime
from typing import Any

from src.definitions import ROOT_DIR


class SelectorUsageTracker:
    def __init__(self) -> None:
        self.enabled = False
        self.output_path = os.path.join(ROOT_DIR, "logs", "selector_usage_latest.json")
        self._records: dict[str, dict[str, Any]] = {}

    def configure(self, settings: dict[str, Any] | None = None) -> None:
        # Resolve reporting settings before any selector lookup is recorded.
        settings = settings if isinstance(settings, dict) else {}
        self.enabled = bool(settings.get("enabled", True))
        configured_path = settings.get("output_path")
        if configured_path:
            self.output_path = (
                configured_path
                if os.path.isabs(configured_path)
                else os.path.join(ROOT_DIR, configured_path)
            )

    def register_config(self, selectors: dict[str, Any] | None) -> None:
        # Register the configured selector tree so unused entries can be reported.
        if not self.enabled or not selectors:
            return
        self._register_node(("selectors",), selectors)

    def record_lookup(self, keys: tuple[object, ...], value: Any) -> None:
        # Separate config reads from DOM matches to expose unmeasured selectors.
        if not self.enabled:
            return
        path = self._path(keys)
        record = self._record(path)
        record["lookup_count"] += 1
        self._record_selector_values(record, value)

    def record_match(
        self,
        path: str | tuple[object, ...],
        selector: str | None,
        match_count: int,
        context: str,
    ) -> None:
        # Attach selector outcomes to callers so stale contracts are traceable.
        if not self.enabled or not selector:
            return
        normalized_path = self._path(path)
        record = self._record(normalized_path)
        record["selector_values"].add(selector)
        record["match_attempts"] += 1
        record["matched_elements"] += max(int(match_count), 0)
        if match_count > 0:
            record["successful_attempts"] += 1
        else:
            record["missed_attempts"] += 1
        record["contexts"][context] += 1

    def write_report(self) -> str | None:
        # Persist a compact JSON report for post-scrape selector maintenance.
        if not self.enabled:
            return None

        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        records = []
        for path, record in sorted(self._records.items()):
            selector_values = sorted(record["selector_values"])
            records.append(
                {
                    "path": path,
                    "selector_values": selector_values,
                    "configured": record["configured"],
                    "lookup_count": record["lookup_count"],
                    "match_attempts": record["match_attempts"],
                    "successful_attempts": record["successful_attempts"],
                    "missed_attempts": record["missed_attempts"],
                    "matched_elements": record["matched_elements"],
                    "contexts": dict(sorted(record["contexts"].items())),
                    "status": self._status(record),
                }
            )

        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "output_path": self._portable_output_path(),
            "summary": {
                "configured_entries": sum(
                    1 for record in records if record["configured"]
                ),
                "looked_up_entries": sum(
                    1 for record in records if record["lookup_count"] > 0
                ),
                "matched_entries": sum(
                    1 for record in records if record["successful_attempts"] > 0
                ),
                "unused_configured_entries": sum(
                    1 for record in records if record["status"] == "configured_unused"
                ),
                "looked_up_never_matched_entries": sum(
                    1
                    for record in records
                    if record["status"] == "looked_up_never_matched"
                ),
            },
            "records": records,
        }
        with open(self.output_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        return self.output_path

    def reset(self) -> None:
        self._records.clear()

    def _portable_output_path(self) -> str:
        # Prefer project-relative paths, but support temp paths on another drive.
        try:
            path = os.path.relpath(self.output_path, ROOT_DIR)
        except ValueError:
            path = os.path.abspath(self.output_path)
        return path.replace(os.sep, "/")

    def _register_node(self, path: tuple[object, ...], node: Any) -> None:
        # Flatten nested selector config into stable dotted paths.
        if isinstance(node, dict):
            for key, value in node.items():
                self._register_node((*path, key), value)
            return

        record = self._record(self._path(path))
        record["configured"] = True
        self._record_selector_values(record, node)

    def _record(self, path: str) -> dict[str, Any]:
        if path not in self._records:
            self._records[path] = {
                "configured": False,
                "selector_values": set(),
                "lookup_count": 0,
                "match_attempts": 0,
                "successful_attempts": 0,
                "missed_attempts": 0,
                "matched_elements": 0,
                "contexts": Counter(),
            }
        return self._records[path]

    @staticmethod
    def _record_selector_values(record: dict[str, Any], value: Any) -> None:
        if isinstance(value, str):
            record["selector_values"].add(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    record["selector_values"].add(item)

    @staticmethod
    def _status(record: dict[str, Any]) -> str:
        # Keep status labels mutually exclusive so reports are easy to triage.
        if record["successful_attempts"] > 0:
            return "matched"
        if record["match_attempts"] > 0:
            return "looked_up_never_matched"
        if record["lookup_count"] > 0:
            return "looked_up_not_measured"
        if record["configured"]:
            return "configured_unused"
        return "runtime_only"

    @staticmethod
    def _path(path: str | tuple[object, ...]) -> str:
        if isinstance(path, str):
            return path
        return ".".join(str(part) for part in path if part is not None)


selector_usage = SelectorUsageTracker()
