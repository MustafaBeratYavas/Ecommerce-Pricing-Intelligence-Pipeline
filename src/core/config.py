"""Load configuration-backed behavior from the project YAML files.

Config merges the base settings with optional environment overlays and nested
environment-variable overrides, then exposes read-only lookup helpers for
callers. It deliberately avoids owning validation rules for individual
features; those remain at the service boundary that consumes each setting.
"""

import os
from typing import Any

import yaml  # type: ignore

from src.definitions import ROOT_DIR


class Config:
    _instance = None
    _ENV_PREFIX = "PRICING_PIPELINE__"
    _CONFIG_DIR_ENV = "PRICING_PIPELINE_CONFIG_DIR"
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
        config_dir = self._resolve_config_dir()
        settings: dict[str, Any] = {}
        loaded_files = 0
        try:
            for filename in self._config_files_for_environment():
                path = os.path.join(config_dir, filename)
                if not os.path.exists(path):
                    continue
                with open(path, encoding="utf-8") as f:
                    loaded = yaml.safe_load(f) or {}
                if not isinstance(loaded, dict):
                    raise RuntimeError(f"{path} must contain a YAML mapping")
                settings = self._deep_merge(settings, loaded)
                loaded_files += 1
            if loaded_files == 0:
                raise RuntimeError(f"No configuration files found in {config_dir}")
            self._apply_env_overrides(settings)
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
    def _resolve_config_dir(cls) -> str:
        configured_dir = os.environ.get(cls._CONFIG_DIR_ENV, "").strip()
        if configured_dir:
            config_dir = os.path.abspath(configured_dir)
            if not os.path.isdir(config_dir):
                raise RuntimeError(
                    f"{cls._CONFIG_DIR_ENV} does not point to a directory: {config_dir}"
                )
            return config_dir

        candidates = (
            os.path.join(os.getcwd(), "config"),
            os.path.join(ROOT_DIR, "config"),
        )
        for candidate in candidates:
            if os.path.isdir(candidate):
                return candidate

        raise RuntimeError(
            "Could not find a config directory. Run from the repository root or "
            f"set {cls._CONFIG_DIR_ENV}."
        )

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

    @classmethod
    def _config_files_for_environment(cls) -> tuple[str, ...]:
        app_env = os.environ.get("APP_ENV", "").strip()
        if not app_env:
            return cls._CONFIG_FILES

        if not app_env.replace("-", "").replace("_", "").isalnum():
            raise RuntimeError("APP_ENV may only contain letters, numbers, '-' or '_'")

        return (*cls._CONFIG_FILES, f"{app_env}.yaml")

    @classmethod
    def _apply_env_overrides(cls, settings: dict[str, Any]) -> None:
        for name, value in os.environ.items():
            if not name.startswith(cls._ENV_PREFIX):
                continue

            key_path = [
                segment.strip().lower()
                for segment in name.removeprefix(cls._ENV_PREFIX).split("__")
                if segment.strip()
            ]
            if not key_path:
                continue

            cls._set_nested(settings, key_path, cls._parse_env_value(value))

    @classmethod
    def _set_nested(
        cls,
        settings: dict[str, Any],
        key_path: list[str],
        value: Any,
    ) -> None:
        current = settings
        for key in key_path[:-1]:
            child = current.get(key)
            if not isinstance(child, dict):
                child = {}
                current[key] = child
            current = child
        current[key_path[-1]] = value

    @staticmethod
    def _parse_env_value(value: str) -> Any:
        normalized = value.strip()
        lowered = normalized.lower()

        if lowered in {"true", "yes", "on"}:
            return True
        if lowered in {"false", "no", "off"}:
            return False
        if lowered in {"none", "null"}:
            return None

        try:
            return int(normalized)
        except ValueError:
            pass

        try:
            return float(normalized)
        except ValueError:
            return value
