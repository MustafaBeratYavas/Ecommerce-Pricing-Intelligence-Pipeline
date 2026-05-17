"""Application entry point for the scraping pipeline."""

import os
import sys
import tomllib
from importlib import metadata
from pathlib import Path

# Allow direct execution from the repository root without installation.
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from selenium.webdriver.support.ui import WebDriverWait

from src.core.config import Config
from src.core.logger import Logger
from src.engine.batch_processor import BatchProcessor
from src.engine.browser import BrowserEngine
from src.services.database import DatabaseService
from src.services.detail_scraper import DetailScraper
from src.services.scraper_service import ScraperService
from src.services.search_service import SearchService
from src.services.seller_extractor import SellerExtractor
from src.utils.normalization_usage import normalization_usage
from src.utils.selector_usage import selector_usage

PACKAGE_NAME = "ecommerce-pricing-intelligence-pipeline"
PYPROJECT_PATH = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _project_metadata() -> tuple[str, str]:
    # Read package metadata from pyproject.toml after installation.
    try:
        app_name = metadata.metadata(PACKAGE_NAME)["Name"]
        version = metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return _project_metadata_from_pyproject()
    return app_name, version


def _project_metadata_from_pyproject() -> tuple[str, str]:
    # Keep source-tree execution aligned with the package manifest.
    try:
        project = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8")).get(
            "project", {}
        )
    except (OSError, tomllib.TOMLDecodeError):
        return PACKAGE_NAME, "0.0.0"

    if not isinstance(project, dict):
        return PACKAGE_NAME, "0.0.0"

    name = project.get("name")
    version = project.get("version")
    return (
        name if isinstance(name, str) and name else PACKAGE_NAME,
        version if isinstance(version, str) and version else "0.0.0",
    )


def main():
    # Initialize shared infrastructure before creating runtime services.
    Logger.setup()
    logger = Logger.get_logger("Main")
    config = Config()
    selector_usage.configure(config.get("observability", "selector_usage", default={}))
    selector_usage.register_config(config.get("selectors", default={}))
    normalization_usage.configure(
        config.get("observability", "normalization_usage", default={})
    )
    normalization_usage.register_config(config)

    app_name, version = _project_metadata()
    logger.info(f"Starting {app_name} v{version}...")

    try:
        # Keep database and browser lifecycles scoped to a single run.
        with DatabaseService() as db:
            with BrowserEngine() as driver:
                wait = WebDriverWait(
                    driver,
                    config.get("browser", "implicit_wait", default=5),
                )

                # Compose services explicitly so dependencies remain visible.
                search_service = SearchService(driver, wait)
                detail_scraper = DetailScraper(driver)
                seller_extractor = SellerExtractor(driver)

                # Let the batch processor own queue progression and retries.
                scraper = ScraperService(
                    driver,
                    search_service,
                    detail_scraper,
                    seller_extractor,
                    db,
                )

                # Use the configured retry budget for each queued product.
                processor = BatchProcessor(db, scraper)
                max_retries = config.get("scraping", "retries", default=3)
                processor.run(max_retries=max_retries)

    except KeyboardInterrupt:
        logger.warning("Process interrupted by user.")
        sys.exit(130)
    except Exception as e:
        logger.critical(f"Global fatal error: {e}")
        sys.exit(1)
    finally:
        report_path = selector_usage.write_report()
        if report_path:
            logger.info(f"Selector usage report written to {report_path}")
        normalization_report_path = normalization_usage.write_report()
        if normalization_report_path:
            logger.info(
                f"Normalization usage report written to {normalization_report_path}"
            )


if __name__ == "__main__":
    main()
