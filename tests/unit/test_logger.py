"""Unit tests for idempotent shared logging configuration."""

import logging

from src.core.logger import Logger


def test_logger_setup_creates_file_and_console_handlers(tmp_path, monkeypatch):
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    noisy_loggers = [
        logging.getLogger("selenium"),
        logging.getLogger("urllib3"),
        logging.getLogger("urllib3.connectionpool"),
        logging.getLogger("seleniumbase"),
    ]
    original_noisy_levels = {logger.name: logger.level for logger in noisy_loggers}
    Logger._configured = False

    class FakeConfig:
        def get(self, *keys, default=None):
            return "runtime-logs"

    monkeypatch.setattr("src.core.logger.Config", FakeConfig)
    monkeypatch.setattr("src.core.logger.ROOT_DIR", str(tmp_path))

    try:
        Logger.setup()
        first_handlers = [
            handler
            for handler in root_logger.handlers
            if handler not in original_handlers
        ]

        Logger.setup()
        second_handlers = [
            handler
            for handler in root_logger.handlers
            if handler not in original_handlers
        ]

        assert Logger._configured is True
        assert len(first_handlers) == 2
        assert second_handlers == first_handlers
        assert (tmp_path / "runtime-logs").is_dir()
        assert list((tmp_path / "runtime-logs").glob("scraper_*.log"))
        assert Logger.get_logger("pricing-test").name == "pricing-test"
        assert logging.getLogger("urllib3.connectionpool").level == logging.ERROR
    finally:
        for handler in list(root_logger.handlers):
            if handler not in original_handlers:
                root_logger.removeHandler(handler)
                handler.close()
        root_logger.setLevel(original_level)
        for logger in noisy_loggers:
            logger.setLevel(original_noisy_levels[logger.name])
        Logger._configured = False
