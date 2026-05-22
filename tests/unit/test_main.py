"""Unit tests for scraping pipeline bootstrap and fatal-error handling."""

import tomllib
import unittest
from importlib import metadata
from unittest.mock import MagicMock, patch

from src.main import PYPROJECT_PATH, _project_metadata, main


class TestMain(unittest.TestCase):
    @patch("src.main.BatchProcessor")
    @patch("src.main.ScraperService")
    @patch("src.main.SellerExtractor")
    @patch("src.main.DetailScraper")
    @patch("src.main.SearchService")
    @patch("src.main.WebDriverWait")
    @patch("src.main.BrowserEngine")
    @patch("src.main.DatabaseService")
    @patch("src.main.Config")
    @patch("src.main.Logger")
    @patch("src.main.normalization_usage")
    @patch("src.main.selector_usage")
    def test_main_normal_flow(
        self,
        mock_selector_usage,
        mock_normalization_usage,
        mock_logger_cls,
        mock_config,
        mock_db_cls,
        mock_browser_cls,
        mock_wait_cls,
        mock_search_cls,
        mock_detail_cls,
        mock_seller_cls,
        mock_scraper_cls,
        mock_batch_cls,
    ):

        mock_logger = MagicMock()
        mock_logger_cls.get_logger.return_value = mock_logger

        mock_config_inst = MagicMock()
        mock_config.return_value = mock_config_inst
        mock_config_inst.get.side_effect = lambda *a, **kw: {
            ("scraping", "retries"): 3,
            ("browser", "implicit_wait"): 5,
        }.get(a, kw.get("default"))

        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)

        mock_browser = MagicMock()
        mock_browser_cls.return_value = mock_browser
        mock_browser.start.return_value = MagicMock()

        mock_processor = MagicMock()
        mock_batch_cls.return_value = mock_processor

        main()

        # Normal startup should wire collaborators and hand control to the processor.
        mock_batch_cls.assert_called_once()
        mock_processor.run.assert_called_once_with(max_retries=3)

    @patch("src.main.Config")
    @patch("src.main.Logger")
    @patch("src.main.normalization_usage")
    @patch("src.main.selector_usage")
    def test_main_fatal_error(
        self,
        mock_selector_usage,
        mock_normalization_usage,
        mock_logger_cls,
        mock_config,
    ):

        mock_logger = MagicMock()
        mock_logger_cls.get_logger.return_value = mock_logger

        mock_config_inst = MagicMock()
        mock_config.return_value = mock_config_inst
        mock_config_inst.get.return_value = "2.0.0"

        # Fatal startup errors should exit cleanly instead of hanging.
        with patch("src.main.DatabaseService", side_effect=Exception("Database crash")):
            with self.assertRaises(SystemExit) as cm:
                main()

        self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()


def test_project_metadata_falls_back_to_pyproject_when_package_is_not_installed(
    monkeypatch,
):
    def raise_package_not_found(_package_name):
        raise metadata.PackageNotFoundError

    monkeypatch.setattr("src.main.metadata.metadata", raise_package_not_found)
    monkeypatch.setattr("src.main.metadata.version", raise_package_not_found)

    project = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))["project"]
    assert _project_metadata() == (project["name"], project["version"])
