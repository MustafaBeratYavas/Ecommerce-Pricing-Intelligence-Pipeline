"""Runtime telemetry for category and marketplace normalization rules."""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime
from typing import Any

from src.definitions import ROOT_DIR
from src.utils import string_utils


class NormalizationUsageTracker:
    TRACKED_MAPS = (
        ("scraping", "marketplace_id_map"),
        ("scraping", "marketplace_name_aliases"),
        ("analysis", "marketplace_display_aliases"),
        ("analysis", "category_aliases"),
    )

    def __init__(self) -> None:
        self.enabled = False
        self.output_path = os.path.join(
            ROOT_DIR, "logs", "normalization_usage_latest.json"
        )
        self._records: dict[tuple[str, str], dict[str, Any]] = {}

    def configure(self, settings: dict[str, Any] | None = None) -> None:
        # Resolve telemetry settings before alias maps are registered.
        settings = settings if isinstance(settings, dict) else {}
        self.enabled = bool(settings.get("enabled", True))
        configured_path = settings.get("output_path")
        if configured_path:
            self.output_path = (
                configured_path
                if os.path.isabs(configured_path)
                else os.path.join(ROOT_DIR, configured_path)
            )

    def register_config(self, config: Any) -> None:
        # Snapshot configured alias maps so unused rules are visible after a run.
        if not self.enabled:
            return
        for path in self.TRACKED_MAPS:
            aliases = config.get(*path, default={}) or {}
            self.register_alias_map(self._path(path), aliases)

    def register_alias_map(self, path: str, aliases: dict[str, Any] | None) -> None:
        # Normalize configured aliases once while preserving their original spelling.
        if not self.enabled or not isinstance(aliases, dict) or not aliases:
            return
        for alias, canonical in aliases.items():
            if alias is None or canonical is None:
                continue
            record = self._record(path, str(alias))
            record["configured"] = True
            record["canonical"] = str(canonical)
            record["normalized_key"] = self._normalize_key(str(alias))

    def record_hit(
        self,
        path: str | tuple[object, ...],
        alias: str,
        raw_value: str | None,
        normalized_value: str | None,
        context: str,
    ) -> None:
        # Attach every runtime normalization hit to the alias rule that handled it.
        if not self.enabled or not alias:
            return
        record = self._record(self._path(path), alias)
        record["hit_count"] += 1
        record["configured"] = record["configured"] or False
        record["canonical"] = normalized_value or record["canonical"]
        if raw_value:
            record["raw_values"][str(raw_value)] += 1
        record["contexts"][context] += 1

    def write_report(self) -> str | None:
        # Write a deterministic report that separates used rules from dead config.
        if not self.enabled:
            return None

        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        records = []
        for (path, alias), record in sorted(self._records.items()):
            records.append(
                {
                    "path": path,
                    "alias": alias,
                    "normalized_key": record["normalized_key"],
                    "canonical": record["canonical"],
                    "configured": record["configured"],
                    "hit_count": record["hit_count"],
                    "raw_values": dict(sorted(record["raw_values"].items())),
                    "contexts": dict(sorted(record["contexts"].items())),
                    "status": "used"
                    if record["hit_count"] > 0
                    else "configured_unused",
                }
            )

        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "output_path": self._portable_output_path(),
            "summary": {
                "configured_entries": sum(
                    1 for record in records if record["configured"]
                ),
                "used_entries": sum(1 for record in records if record["hit_count"] > 0),
                "unused_configured_entries": sum(
                    1 for record in records if record["status"] == "configured_unused"
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

    def _record(self, path: str, alias: str) -> dict[str, Any]:
        key = (path, alias)
        if key not in self._records:
            self._records[key] = {
                "configured": False,
                "canonical": None,
                "normalized_key": self._normalize_key(alias),
                "hit_count": 0,
                "raw_values": Counter(),
                "contexts": Counter(),
            }
        return self._records[key]

    @staticmethod
    def _normalize_key(value: str) -> str:
        return " ".join(string_utils.to_ascii(value).lower().split())

    @staticmethod
    def _path(path: str | tuple[object, ...]) -> str:
        if isinstance(path, str):
            return path
        return ".".join(str(part) for part in path if part is not None)


normalization_usage = NormalizationUsageTracker()
