"""Load project YAML configuration once and expose nested values."""

import os
from typing import Any

import yaml  # type: ignore

from src.definitions import ROOT_DIR


class Config:
    _instance = None
    _CONFIG_FILES = (
        "settings.yaml",
        "browser.yaml",
        "scraping.yaml",
        "selectors.yaml",
        "marketplaces.yaml",
        "analysis.yaml",
    )

    def __new__(cls):
        # Keep one parsed configuration per process to avoid repeated disk reads.
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._settings = {}
            cls._instance._load_config()
        return cls._instance

    def _load_config(self) -> None:
        config_dir = os.path.join(ROOT_DIR, "config")
        settings: dict[str, Any] = {}
        try:
            for filename in self._CONFIG_FILES:
                path = os.path.join(config_dir, filename)
                if not os.path.exists(path):
                    continue
                with open(path, encoding="utf-8") as f:
                    loaded = yaml.safe_load(f) or {}
                if not isinstance(loaded, dict):
                    raise RuntimeError(f"{path} must contain a YAML mapping")
                settings = self._deep_merge(settings, loaded)
            self._settings = settings
        except Exception as e:
            raise RuntimeError(f"Failed to load project configuration: {e}")

    def get(self, *keys, default=None) -> Any:
        # Walk the requested keys through the nested settings dictionary.
        data = self._settings
        for key in keys:
            if isinstance(data, dict):
                data = data.get(key)
            else:
                return default
        value = data if data is not None else default
        if keys and keys[0] == "selectors":
            try:
                from src.utils.selector_usage import selector_usage

                selector_usage.record_lookup(tuple(keys), value)
            except Exception:
                pass
        return value

    def as_dict(self) -> dict[str, Any]:
        return dict(self._settings)

    @classmethod
    def reset_instance(cls) -> None:
        # Reset singleton state for isolated tests.
        cls._instance = None

    @classmethod
    def _deep_merge(
        cls,
        base: dict[str, Any],
        override: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = cls._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged
