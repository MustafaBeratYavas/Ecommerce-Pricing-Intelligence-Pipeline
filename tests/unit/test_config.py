"""Unit tests for configuration singleton behavior."""

from src.core.config import Config


def test_config_get_preserves_falsy_values():
    Config.reset_instance()
    try:
        config = Config()
        assert config.get("browser", "headless", default=True) is False
    finally:
        Config.reset_instance()


def test_config_loads_split_yaml_files():
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


def test_reset_instance_discards_existing_instance_settings():
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
