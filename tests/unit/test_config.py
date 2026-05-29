"""Unit tests for configuration loading, overlays, and singleton reset behavior."""

import os

from src.core.config import Config


def _clear_config_environment(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("PRICING_PIPELINE_CONFIG_DIR", raising=False)
    for name in list(os.environ):
        if name.startswith("PRICING_PIPELINE__"):
            monkeypatch.delenv(name, raising=False)


def test_config_get_preserves_falsy_values(monkeypatch):
    _clear_config_environment(monkeypatch)
    Config.reset_instance()
    try:
        config = Config()
        assert config.get("browser", "headless", default=True) is False
    finally:
        Config.reset_instance()


def test_config_loads_split_yaml_files(monkeypatch):
    _clear_config_environment(monkeypatch)
    Config.reset_instance()
    try:
        config = Config()

        assert config.get("browser", "profile_name") == "Profile 1"
        assert config.get("selectors", "product", "title") == "h1"
        assert config.get("scraping", "marketplace_id_map", "10939") == "Koçtaş"
        assert config.get("analysis", "price_tiers", "labels", "entry")
        assert config.get("charts", "style", "plot_rect") == [0.14, 0.17, 0.72, 0.72]
    finally:
        Config.reset_instance()


def test_reset_instance_discards_existing_instance_settings(monkeypatch):
    _clear_config_environment(monkeypatch)
    Config.reset_instance()
    try:
        first = Config()
        first._settings = {"temporary": {"value": "stale"}}

        Config.reset_instance()
        second = Config()

        assert second is not first
        assert second.get("temporary", "value") is None
    finally:
        Config.reset_instance()


def test_config_applies_environment_overrides(monkeypatch):
    _clear_config_environment(monkeypatch)
    monkeypatch.setenv("PRICING_PIPELINE__browser__headless", "true")
    monkeypatch.setenv("PRICING_PIPELINE__database__busy_timeout_ms", "12000")
    monkeypatch.setenv("PRICING_PIPELINE__scraping__retries", "1")
    monkeypatch.setenv("PRICING_PIPELINE__paths__logs_dir", "container-logs")

    Config.reset_instance()
    try:
        config = Config()

        assert config.get("browser", "headless") is True
        assert config.get("database", "busy_timeout_ms") == 12000
        assert config.get("scraping", "retries") == 1
        assert config.get("paths", "logs_dir") == "container-logs"
    finally:
        Config.reset_instance()


def test_config_loads_app_env_overlay(monkeypatch):
    _clear_config_environment(monkeypatch)
    monkeypatch.setenv("APP_ENV", "docker")

    Config.reset_instance()
    try:
        config = Config()

        assert config.get("browser", "headless") is True
        assert config.get("browser", "profile_name") == "Default"
    finally:
        Config.reset_instance()


def test_config_can_load_from_explicit_config_directory(tmp_path, monkeypatch):
    _clear_config_environment(monkeypatch)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.yaml").write_text(
        "browser:\n  headless: true\n", encoding="utf-8"
    )
    monkeypatch.setenv("PRICING_PIPELINE_CONFIG_DIR", str(config_dir))

    Config.reset_instance()
    try:
        config = Config()

        assert config.get("browser", "headless") is True
    finally:
        Config.reset_instance()
