"""Configure process-wide file and console logging.

Logger creates one run-scoped log file plus a concise console stream, then
returns named loggers for pipeline components. It centralizes handler setup so
service modules do not compete over logging configuration.
"""

import logging
import os
import sys
from datetime import datetime

from src.core.config import Config
from src.definitions import ROOT_DIR


class Logger:
    _configured = False

    @staticmethod
    def setup() -> None:
        # Configure logging once so repeated service construction stays idempotent.
        if Logger._configured:
            return

        config = Config()
        log_dir = config.get("paths", "logs_dir", default="logs")

        # Create the log directory before handlers attempt to open files.
        full_log_path = os.path.join(ROOT_DIR, log_dir)
        os.makedirs(full_log_path, exist_ok=True)

        # Use a unique file per run to preserve execution history.
        filename = f"scraper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        filepath = os.path.join(full_log_path, filename)

        # Keep log files plain while preserving readable color in the console.
        file_handler = logging.FileHandler(filepath, encoding="utf-8")
        file_fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)15s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_fmt)

        console_handler = logging.StreamHandler(sys.stdout)

        class ColoredFormatter(logging.Formatter):
            COLORS = {
                logging.DEBUG: "\033[94m",
                logging.INFO: "\033[92m",
                logging.WARNING: "\033[93m",
                logging.ERROR: "\033[91m",
                logging.CRITICAL: "\033[1;91m",
            }
            RESET = "\033[0m"

            def format(self, record):
                record_copy = logging.makeLogRecord(record.__dict__)
                color = self.COLORS.get(record_copy.levelno, self.RESET)
                record_copy.levelname = f"{color}{record_copy.levelname:8}{self.RESET}"
                return super().format(record_copy)

        console_fmt = ColoredFormatter(
            "%(asctime)s | %(levelname)s | %(name)15s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_fmt)

        # Attach handlers explicitly; basicConfig is a no-op if another
        # dependency configured logging before the application starts.
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

        # Reduce noise from verbose third-party libraries.
        logging.getLogger("selenium").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
        logging.getLogger("seleniumbase").setLevel(logging.WARNING)

        Logger._configured = True

    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        # Keep callers on named loggers while sharing the process-wide handlers.
        return logging.getLogger(name)
